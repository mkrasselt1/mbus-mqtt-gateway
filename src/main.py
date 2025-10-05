"""
M-Bus MQTT Gateway - Main Application
Production-ready gateway with complete error handling.
"""

import asyncio
import signal
import sys
import time
import socket
import uuid
from pathlib import Path
from typing import Optional

from src.config import load_config, Config
from src.logger import setup_logging, get_logger
from src.persistence import StatePersistence
from src.mbus_handler import MBusHandler
from src.mqtt_handler import MQTTHandler

# Will be set after config load
logger = None


class Gateway:
    """Main gateway application orchestrator."""
    
    def __init__(self, config: Config):
        """
        Initialize gateway.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.running = False
        self.start_time = time.time()
        
        # Components
        self.persistence: Optional[StatePersistence] = None
        self.mbus: Optional[MBusHandler] = None
        self.mqtt: Optional[MQTTHandler] = None
        
        # Gateway info
        self.gateway_id = self._get_gateway_id()
        self.gateway_ip = self._get_local_ip()
        
        logger.info(
            "gateway_initialized",
            gateway_id=self.gateway_id,
            ip=self.gateway_ip,
            version=config.gateway.version
        )
    
    def _get_gateway_id(self) -> str:
        """Generate unique gateway ID from MAC address."""
        mac = uuid.getnode()
        mac_str = ':'.join(f'{(mac >> i) & 0xff:02x}' for i in range(40, -1, -8))
        return f"gateway_{mac_str.replace(':', '')}"
    
    def _get_local_ip(self) -> str:
        """Get local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    async def start(self) -> None:
        """Start all gateway components."""
        try:
            logger.info("gateway_starting")
            
            # 1. Initialize persistence
            logger.info("initializing_persistence")
            self.persistence = StatePersistence(self.config.persistence.database)
            await self.persistence.initialize()
            
            # 2. Initialize MQTT
            logger.info("initializing_mqtt")
            self.mqtt = MQTTHandler(
                self.config.mqtt,
                self.config.homeassistant,
                self.persistence
            )
            await self.mqtt.start()
            
            # 3. Publish gateway discovery
            await self._publish_gateway_discovery()
            
            # 4. Initialize M-Bus
            logger.info("initializing_mbus")
            self.mbus = MBusHandler(self.config.mbus)
            await self.mbus.start()
            
            # 5. Restore previous state
            await self._restore_state()
            
            # 6. Start monitoring loop
            self.running = True
            await self._monitoring_loop()
            
        except Exception as e:
            logger.error("gateway_start_failed", error=str(e), exc_info=True)
            raise
    
    async def stop(self) -> None:
        """Stop all gateway components."""
        logger.info("gateway_stopping")
        self.running = False
        
        # Stop components in reverse order
        if self.mbus:
            await self.mbus.stop()
        
        if self.mqtt:
            await self.mqtt.stop()
        
        if self.persistence:
            await self.persistence.close()
        
        logger.info("gateway_stopped")
    
    async def _publish_gateway_discovery(self) -> None:
        """Publish gateway as a device in Home Assistant."""
        gateway_attrs = {
            "IP-Adresse": {
                "value": self.gateway_ip,
                "unit": "",
                "type": "sensor"
            },
            "Status": {
                "value": "online",
                "unit": "",
                "type": "binary_sensor"
            },
            "Laufzeit": {
                "value": 0,
                "unit": "s",
                "type": "sensor"
            }
        }
        
        await self.mqtt.publish_discovery(
            device_id=self.gateway_id,
            device_type="gateway",
            device_name=self.config.gateway.name,
            manufacturer=self.config.gateway.manufacturer,
            model=self.config.gateway.model,
            sw_version=self.config.gateway.version,
            attributes=gateway_attrs
        )
        
        logger.info("gateway_discovery_published")
    
    async def _restore_state(self) -> None:
        """Restore previous device states from persistence."""
        logger.info("restoring_previous_state")
        
        states = await self.persistence.load_all_device_states()
        
        for device_id, device_data in states.items():
            # Skip gateway itself
            if device_id == self.gateway_id:
                continue
            
            # Publish discovery for restored devices
            state = device_data['state']
            attributes = {}
            
            for key, value in state.items():
                if not key.startswith('_'):
                    attributes[key] = {
                        "value": value,
                        "unit": "",
                        "type": "sensor"
                    }
            
            if attributes:
                await self.mqtt.publish_discovery(
                    device_id=device_id,
                    device_type=device_data['device_type'],
                    device_name=device_data['name'],
                    manufacturer=device_data.get('manufacturer', 'Unknown'),
                    model=device_data.get('model', 'Unknown'),
                    sw_version=device_data.get('sw_version', ''),
                    attributes=attributes
                )
                
                # Publish state as "stale" until fresh data arrives
                for attr_name in attributes.keys():
                    await self.mqtt.publish_state(device_id, attr_name, attributes[attr_name]['value'])
        
        logger.info("state_restored", devices=len(states))
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring and coordination loop."""
        logger.info("monitoring_loop_started")
        
        last_gateway_update = 0
        last_cleanup = 0
        
        while self.running:
            try:
                # Update gateway metrics every 30 seconds
                if time.time() - last_gateway_update >= 30:
                    await self._update_gateway_metrics()
                    last_gateway_update = time.time()
                
                # Process M-Bus data
                await self._process_mbus_data()
                
                # Cleanup old history daily
                if time.time() - last_cleanup >= self.config.persistence.cleanup_interval:
                    await self._cleanup_old_data()
                    last_cleanup = time.time()
                
                # Small delay
                await asyncio.sleep(1)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("monitoring_loop_error", error=str(e), exc_info=True)
                await asyncio.sleep(10)
        
        logger.info("monitoring_loop_stopped")
    
    async def _update_gateway_metrics(self) -> None:
        """Update gateway metrics (uptime, IP, etc.)."""
        uptime = int(time.time() - self.start_time)
        current_ip = self._get_local_ip()
        
        # Publish gateway state
        gateway_state = {
            "IP-Adresse": current_ip,
            "Status": "online",
            "Laufzeit": uptime
        }
        
        await self.mqtt.publish_device_states(self.gateway_id, gateway_state)
        
        # Save to persistence
        await self.persistence.save_device_state(
            device_id=self.gateway_id,
            device_type="gateway",
            name=self.config.gateway.name,
            state=gateway_state,
            manufacturer=self.config.gateway.manufacturer,
            model=self.config.gateway.model,
            sw_version=self.config.gateway.version,
            online=True
        )
        
        logger.debug("gateway_metrics_updated", uptime=uptime)
    
    async def _process_mbus_data(self) -> None:
        """Process M-Bus device data and publish to MQTT."""
        devices = self.mbus.get_all_devices()
        
        for address, device in devices.items():
            device_id = f"mbus_meter_{address}"
            
            # Handle offline devices
            if not device.online:
                logger.debug("device_offline", address=address)
                continue
            
            # Skip if no records
            if not device.records:
                continue
            
            # Build attributes dict
            attributes = {}
            state = {}
            
            for record in device.records:
                name = record['name']
                value = record['value']
                unit = record['unit']
                
                attributes[name] = {
                    "value": value,
                    "unit": unit,
                    "type": "sensor"
                }
                state[name] = value
            
            # Add status
            attributes["Status"] = {
                "value": "online",
                "unit": "",
                "type": "binary_sensor"
            }
            state["Status"] = "online"
            
            # Publish discovery (if new attributes)
            await self.mqtt.publish_discovery(
                device_id=device_id,
                device_type="mbus_meter",
                device_name=device.name,
                manufacturer=device.manufacturer,
                model=device.medium,
                sw_version=device.identification,
                attributes=attributes
            )
            
            # Publish state
            await self.mqtt.publish_device_states(device_id, state)
            
            # Save to persistence
            await self.persistence.save_device_state(
                device_id=device_id,
                device_type="mbus_meter",
                name=device.name,
                state=state,
                manufacturer=device.manufacturer,
                model=device.medium,
                sw_version=device.identification,
                online=True
            )
    
    async def _cleanup_old_data(self) -> None:
        """Cleanup old historical data."""
        if self.config.persistence.history_days > 0:
            deleted = await self.persistence.cleanup_old_history(
                self.config.persistence.history_days
            )
            if deleted > 0:
                logger.info("old_data_cleaned", rows=deleted)


async def main():
    """Main entry point."""
    global logger
    
    # Parse arguments
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    
    try:
        # Load configuration
        print("[INFO] Loading configuration...")
        config = load_config(config_path)
        
        # Setup logging
        logger = setup_logging(config.logging)
        logger.info("configuration_loaded", config_file=config_path or "default")
        
        # Create gateway
        gateway = Gateway(config)
        
        # Setup signal handlers
        loop = asyncio.get_event_loop()
        
        def signal_handler(sig):
            logger.info("signal_received", signal=sig.name)
            asyncio.create_task(gateway.stop())
        
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        
        # Start gateway
        await gateway.start()
    
    except KeyboardInterrupt:
        logger.info("interrupted_by_user")
    except Exception as e:
        if logger:
            logger.error("fatal_error", error=str(e), exc_info=True)
        else:
            print(f"[FATAL] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    # Run on Windows without signal handlers (not supported)
    if sys.platform == "win32":
        asyncio.run(main())
    else:
        asyncio.run(main())
