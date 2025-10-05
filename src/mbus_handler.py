"""
M-Bus Handler
Async M-Bus device communication with robust error handling.
"""

import asyncio
import time
import meterbus
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from serial import Serial, SerialException, serial_for_url
from concurrent.futures import ThreadPoolExecutor

from src.logger import get_logger
from src.config import MBusConfig

logger = get_logger(__name__)


@dataclass
class MBusDevice:
    """Represents an M-Bus device."""
    address: str
    name: str
    manufacturer: str = "Unknown"
    medium: str = "Unknown"
    identification: str = ""
    last_seen: float = field(default_factory=time.time)
    online: bool = True
    consecutive_failures: int = 0
    records: List[Dict[str, Any]] = field(default_factory=list)
    
    def mark_online(self) -> None:
        """Mark device as online and reset failure counter."""
        self.online = True
        self.consecutive_failures = 0
        self.last_seen = time.time()
    
    def mark_failure(self) -> None:
        """Increment failure counter."""
        self.consecutive_failures += 1
        self.last_seen = time.time()
    
    def mark_offline(self) -> None:
        """Mark device as offline."""
        self.online = False
        self.last_seen = time.time()


class CircuitBreaker:
    """Circuit breaker to prevent repeated failures."""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 300):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before trying again
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open
    
    def record_success(self) -> None:
        """Record successful operation."""
        self.failures = 0
        self.state = "closed"
    
    def record_failure(self) -> None:
        """Record failed operation."""
        self.failures += 1
        self.last_failure_time = time.time()
        
        if self.failures >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                "circuit_breaker_opened",
                failures=self.failures,
                timeout=self.timeout
            )
    
    def can_attempt(self) -> bool:
        """Check if operation can be attempted."""
        if self.state == "closed":
            return True
        
        if self.state == "open":
            # Check if timeout has passed
            if time.time() - self.last_failure_time >= self.timeout:
                self.state = "half-open"
                self.failures = 0
                logger.info("circuit_breaker_half_open")
                return True
            return False
        
        # half-open state
        return True


class MBusHandler:
    """
    Async M-Bus communication handler.
    Uses thread pool for blocking serial I/O.
    """
    
    def __init__(self, config: MBusConfig):
        """
        Initialize M-Bus handler.
        
        Args:
            config: M-Bus configuration
        """
        self.config = config
        self.devices: Dict[str, MBusDevice] = {}
        self.circuit_breaker = CircuitBreaker()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._running = False
        self._scan_task: Optional[asyncio.Task] = None
        self._read_task: Optional[asyncio.Task] = None
        
        logger.info(
            "mbus_handler_init",
            port=config.port,
            baudrate=config.baudrate,
            timeout=config.timeout
        )
    
    async def start(self) -> None:
        """Start M-Bus handler."""
        self._running = True
        
        # Initial scan
        await self.scan_devices()
        
        # Start background tasks
        self._scan_task = asyncio.create_task(self._scan_loop())
        self._read_task = asyncio.create_task(self._read_loop())
        
        logger.info("mbus_handler_started", devices=len(self.devices))
    
    async def stop(self) -> None:
        """Stop M-Bus handler."""
        self._running = False
        
        # Cancel tasks
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        
        logger.info("mbus_handler_stopped")
    
    async def _scan_loop(self) -> None:
        """Background task for periodic device scanning."""
        while self._running:
            try:
                await asyncio.sleep(self.config.scan_interval)
                await self.scan_devices()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scan_loop_error", error=str(e))
                await asyncio.sleep(60)
    
    async def _read_loop(self) -> None:
        """Background task for periodic device reading."""
        while self._running:
            try:
                await asyncio.sleep(self.config.read_interval)
                await self.read_all_devices()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("read_loop_error", error=str(e))
                await asyncio.sleep(10)
    
    async def scan_devices(self) -> List[str]:
        """
        Scan for M-Bus devices on the network.
        
        Returns:
            List of discovered device addresses
        """
        if not self.circuit_breaker.can_attempt():
            logger.warning("scan_skipped_circuit_breaker_open")
            return []
        
        logger.info("mbus_scan_started")
        
        try:
            # Run blocking scan in thread pool
            loop = asyncio.get_event_loop()
            addresses = await loop.run_in_executor(
                self.executor,
                self._scan_devices_sync
            )
            
            # Update device registry
            for address in addresses:
                if address not in self.devices:
                    self.devices[address] = MBusDevice(
                        address=address,
                        name=f"M-Bus Meter {address}"
                    )
                    logger.info("new_device_discovered", address=address)
            
            self.circuit_breaker.record_success()
            logger.info("mbus_scan_completed", devices=len(addresses))
            
            return addresses
            
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error("mbus_scan_failed", error=str(e))
            return []
    
    def _scan_devices_sync(self) -> List[str]:
        """Synchronous device scan (runs in thread pool)."""
        discovered = []
        
        try:
            with serial_for_url(
                self.config.port,
                self.config.baudrate,
                8, 'E', 1,
                timeout=self.config.timeout
            ) as ser:
                # Initialize slaves
                self._init_slaves(ser)
                
                # Scan secondary addresses
                self._scan_secondary_range(ser, 0, "FFFFFFFFFFFFFFFF", discovered)
        
        except SerialException as e:
            logger.error("serial_error_scan", error=str(e))
            raise
        
        return discovered
    
    def _init_slaves(self, ser: Serial) -> bool:
        """Initialize M-Bus slaves."""
        if not self._ping_address(ser, meterbus.ADDRESS_NETWORK_LAYER):
            return self._ping_address(ser, meterbus.ADDRESS_BROADCAST_NOREPLY)
        return True
    
    def _ping_address(self, ser: Serial, address: int, retries: int = 2) -> bool:
        """Ping M-Bus address."""
        for _ in range(retries + 1):
            meterbus.send_ping_frame(ser, address, False)
            try:
                frame = meterbus.load(meterbus.recv_frame(ser, 1))
                if isinstance(frame, meterbus.TelegramACK):
                    return True
            except meterbus.MBusFrameDecodeError:
                pass
            time.sleep(0.5)
        return False
    
    def _scan_secondary_range(
        self,
        ser: Serial,
        pos: int,
        mask: str,
        discovered: List[str]
    ) -> None:
        """Recursively scan secondary address range."""
        if mask[pos].upper() == 'F':
            l_start, l_end = 0, 9
        else:
            if pos < 15:
                self._scan_secondary_range(ser, pos + 1, mask, discovered)
            else:
                l_start = l_end = ord(mask[pos]) - ord('0')
        
        if mask[pos].upper() == 'F' or pos == 15:
            for i in range(l_start, l_end + 1):
                new_mask = (mask[:pos] + f"{i:1X}" + mask[pos + 1:]).upper()
                result = self._probe_secondary_address(ser, new_mask)
                
                if result == "match":
                    if new_mask not in discovered:
                        discovered.append(new_mask)
                        logger.debug("device_found", address=new_mask)
                elif result == "collision":
                    self._scan_secondary_range(ser, pos + 1, new_mask, discovered)
    
    def _probe_secondary_address(self, ser: Serial, mask: str) -> str:
        """
        Probe secondary address.
        
        Returns:
            "match", "collision", or "no_reply"
        """
        meterbus.send_select_frame(ser, mask, False)
        
        try:
            frame = meterbus.load(meterbus.recv_frame(ser, 1))
        except meterbus.MBusFrameDecodeError as e:
            frame = e.value
        
        if isinstance(frame, meterbus.TelegramACK):
            meterbus.send_request_frame(ser, meterbus.ADDRESS_NETWORK_LAYER, False)
            time.sleep(0.5)
            
            try:
                frame = meterbus.load(meterbus.recv_frame(ser))
                if isinstance(frame, meterbus.TelegramLong):
                    return "match"
            except meterbus.MBusFrameDecodeError:
                pass
            
            return "no_reply"
        
        if frame:  # Collision
            return "collision"
        
        return "no_reply"
    
    async def read_all_devices(self) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Read data from all known devices.
        
        Returns:
            Dictionary mapping device address to data (or None if failed)
        """
        results = {}
        
        for address, device in self.devices.items():
            # Skip offline devices
            if not device.online and device.consecutive_failures >= self.config.max_retries:
                continue
            
            data = await self.read_device(address)
            results[address] = data
            
            # Small delay between devices
            await asyncio.sleep(0.1)
        
        return results
    
    async def read_device(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Read data from a specific device.
        
        Args:
            address: Device address
            
        Returns:
            Device data or None if failed
        """
        device = self.devices.get(address)
        if not device:
            logger.warning("device_not_found", address=address)
            return None
        
        if not self.circuit_breaker.can_attempt():
            logger.debug("read_skipped_circuit_breaker", address=address)
            return None
        
        try:
            # Run blocking read in thread pool
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                self.executor,
                self._read_device_sync,
                address
            )
            
            if data:
                device.mark_online()
                device.records = data.get('records', [])
                device.manufacturer = data.get('manufacturer', 'Unknown')
                device.medium = data.get('medium', 'Unknown')
                device.identification = data.get('identification', '')
                
                self.circuit_breaker.record_success()
                
                logger.debug(
                    "device_read_success",
                    address=address,
                    records=len(device.records)
                )
                
                return data
            else:
                device.mark_failure()
                
                if device.consecutive_failures >= self.config.max_retries:
                    device.mark_offline()
                    logger.warning(
                        "device_marked_offline",
                        address=address,
                        failures=device.consecutive_failures
                    )
                
                return None
        
        except Exception as e:
            device.mark_failure()
            self.circuit_breaker.record_failure()
            logger.error("device_read_error", address=address, error=str(e))
            return None
    
    def _read_device_sync(self, address: str) -> Optional[Dict[str, Any]]:
        """Synchronous device read (runs in thread pool)."""
        try:
            ibt = meterbus.inter_byte_timeout(self.config.baudrate)
            
            with serial_for_url(
                self.config.port,
                self.config.baudrate,
                8, 'E', 1,
                inter_byte_timeout=ibt,
                timeout=self.config.timeout
            ) as ser:
                frame = self._read_standard_data(ser, address)
                
                if not frame:
                    return None
                
                # Parse frame
                if not hasattr(frame, 'body') or not hasattr(frame.body, 'bodyPayload'):
                    return None
                
                # Extract records
                records = []
                for idx, rec in enumerate(frame.records):
                    name = self._get_sensor_name(rec.unit, idx)
                    value = rec.value
                    
                    # Convert to serializable type
                    if isinstance(value, (float, int)):
                        value = round(float(value), 4)
                    
                    records.append({
                        'name': name,
                        'value': value,
                        'unit': rec.unit,
                        'function': getattr(rec, 'function_field', {}).get('parts', [None])[0]
                    })
                
                return {
                    'manufacturer': frame.body.bodyHeader.manufacturer_field.decodeManufacturer,
                    'identification': ''.join(f'{b:02x}' for b in frame.body.bodyHeader.id_nr),
                    'medium': frame.body.bodyHeader.measure_medium_field.parts[0],
                    'access_no': frame.body.bodyHeader.acc_nr_field.parts[0],
                    'records': records
                }
        
        except Exception as e:
            logger.debug("sync_read_error", address=address, error=str(e))
            return None
    
    def _read_standard_data(self, ser: Serial, address: str):
        """Read standard data frame from device."""
        try:
            if meterbus.is_primary_address(address):
                if not self._ping_address(ser, address):
                    return None
                
                meterbus.send_request_frame(ser, address, False)
                frame_data = meterbus.recv_frame(ser, meterbus.FRAME_DATA_LENGTH)
                
                if frame_data:
                    return meterbus.load(frame_data)
            
            elif meterbus.is_secondary_address(address):
                meterbus.send_select_frame(ser, address, False)
                
                try:
                    frame_data = meterbus.recv_frame(ser, 1)
                    if frame_data:
                        frame = meterbus.load(frame_data)
                    else:
                        return None
                except meterbus.MBusFrameDecodeError as e:
                    frame = e.value
                
                if not isinstance(frame, meterbus.TelegramACK):
                    return None
                
                meterbus.send_request_frame(ser, meterbus.ADDRESS_NETWORK_LAYER, False)
                time.sleep(0.3)
                
                frame_data = meterbus.recv_frame(ser, meterbus.FRAME_DATA_LENGTH)
                if frame_data:
                    return meterbus.load(frame_data)
        
        except Exception as e:
            logger.debug("read_standard_data_error", error=str(e))
        
        return None
    
    def _get_sensor_name(self, unit: str, index: int) -> str:
        """Generate friendly sensor name from unit."""
        if not unit or unit.lower() == "none":
            return f"Zählerstand {index}"
        
        unit_lower = unit.lower()
        
        # Energy units
        if unit_lower in ["kwh", "wh", "mwh"]:
            return f"Energie ({unit})"
        elif unit_lower in ["w", "kw", "mw"]:
            return f"Leistung ({unit})"
        elif unit_lower in ["v", "kv"]:
            return f"Spannung ({unit})"
        elif unit_lower in ["a", "ma"]:
            return f"Strom ({unit})"
        elif unit_lower in ["°c", "c"]:
            return f"Temperatur ({unit})"
        elif unit_lower in ["m³", "m3", "l"]:
            return f"Volumen ({unit})"
        else:
            return f"Messwert {index} ({unit})"
    
    def get_device(self, address: str) -> Optional[MBusDevice]:
        """Get device by address."""
        return self.devices.get(address)
    
    def get_all_devices(self) -> Dict[str, MBusDevice]:
        """Get all devices."""
        return self.devices.copy()
