"""
MQTT Handler
Robust async MQTT communication with Home Assistant integration.
"""

import asyncio
import json
import time
from typing import Dict, Set, Optional, Any, Callable
from dataclasses import dataclass
import paho.mqtt.client as mqtt
from tenacity import retry, stop_after_attempt, wait_exponential

from src.logger import get_logger
from src.config import MQTTConfig, HomeAssistantConfig
from src.persistence import StatePersistence

logger = get_logger(__name__)


@dataclass
class MQTTMessage:
    """Represents an MQTT message."""
    topic: str
    payload: str
    qos: int = 1
    retain: bool = False


class MQTTHandler:
    """
    Async MQTT handler with Home Assistant discovery support.
    Includes offline queueing and automatic reconnection.
    """
    
    def __init__(
        self,
        mqtt_config: MQTTConfig,
        ha_config: HomeAssistantConfig,
        persistence: StatePersistence
    ):
        """
        Initialize MQTT handler.
        
        Args:
            mqtt_config: MQTT configuration
            ha_config: Home Assistant configuration
            persistence: State persistence layer
        """
        self.mqtt_config = mqtt_config
        self.ha_config = ha_config
        self.persistence = persistence
        
        # MQTT Client
        client_id = mqtt_config.client_id or f"mbus_gateway_{int(time.time())}"
        self.client = mqtt.Client(client_id=client_id)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        # State
        self.connected = False
        self.ha_online = False
        self.discovery_sent: Set[str] = set()
        
        # Callbacks
        self.on_state_change: Optional[Callable] = None
        
        # Background tasks
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._queue_processor_task: Optional[asyncio.Task] = None
        
        logger.info(
            "mqtt_handler_init",
            broker=mqtt_config.broker,
            port=mqtt_config.port,
            client_id=client_id
        )
    
    async def start(self) -> None:
        """Start MQTT handler and connect."""
        self._running = True
        
        # Setup client
        if self.mqtt_config.username and self.mqtt_config.password:
            self.client.username_pw_set(
                self.mqtt_config.username,
                self.mqtt_config.password
            )
        
        # Last Will Testament
        self.client.will_set(
            self.ha_config.bridge_state_topic,
            "offline",
            qos=self.mqtt_config.qos,
            retain=True
        )
        
        # Connect
        await self._connect_with_retry()
        
        # Start background tasks
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._queue_processor_task = asyncio.create_task(self._process_queue_loop())
        
        logger.info("mqtt_handler_started")
    
    async def stop(self) -> None:
        """Stop MQTT handler."""
        self._running = False
        
        # Cancel tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self._queue_processor_task:
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect
        if self.connected:
            await self.publish(
                self.ha_config.bridge_state_topic,
                "offline",
                retain=True
            )
        
        self.client.loop_stop()
        self.client.disconnect()
        
        logger.info("mqtt_handler_stopped")
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=60)
    )
    async def _connect_with_retry(self) -> None:
        """Connect to MQTT broker with exponential backoff."""
        try:
            logger.info("mqtt_connecting", broker=self.mqtt_config.broker)
            
            self.client.connect(
                self.mqtt_config.broker,
                self.mqtt_config.port,
                self.mqtt_config.keepalive
            )
            
            # Start network loop in background
            self.client.loop_start()
            
            # Wait for connection
            for _ in range(50):
                if self.connected:
                    logger.info("mqtt_connected")
                    return
                await asyncio.sleep(0.1)
            
            raise ConnectionError("MQTT connection timeout")
        
        except Exception as e:
            logger.error("mqtt_connection_failed", error=str(e))
            raise
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker."""
        if rc == 0:
            self.connected = True
            logger.info("mqtt_broker_connected")
            
            # Publish bridge online status
            self.client.publish(
                self.ha_config.bridge_state_topic,
                "online",
                qos=self.mqtt_config.qos,
                retain=True
            )
            
            # Subscribe to Home Assistant status
            self.client.subscribe("homeassistant/status")
            
            # Reset discovery (will be resent)
            self.discovery_sent.clear()
        
        else:
            self.connected = False
            logger.error("mqtt_connection_failed", return_code=rc)
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from MQTT broker."""
        self.connected = False
        self.ha_online = False
        
        if rc == 0:
            logger.info("mqtt_disconnected_clean")
        else:
            logger.warning("mqtt_disconnected_unexpected", return_code=rc)
        
        # Clear discovery state
        self.discovery_sent.clear()
    
    def _on_message(self, client, userdata, msg):
        """Callback for received MQTT messages."""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            # Handle Home Assistant status
            if topic == "homeassistant/status":
                self.ha_online = (payload == "online")
                logger.info("ha_status_changed", online=self.ha_online)
                
                if self.ha_online:
                    # Trigger rediscovery
                    asyncio.create_task(self._send_all_discovery())
        
        except Exception as e:
            logger.error("message_callback_error", error=str(e))
    
    async def publish(
        self,
        topic: str,
        payload: str,
        qos: Optional[int] = None,
        retain: bool = False
    ) -> bool:
        """
        Publish MQTT message.
        
        Args:
            topic: MQTT topic
            payload: Message payload
            qos: Quality of Service (default from config)
            retain: Retain flag
            
        Returns:
            True if published, False if queued
        """
        if qos is None:
            qos = self.mqtt_config.qos
        
        if not self.connected:
            # Queue message for later delivery
            await self.persistence.queue_mqtt_message(topic, payload, qos, retain)
            logger.debug("message_queued", topic=topic)
            return False
        
        try:
            result = self.client.publish(topic, payload, qos=qos, retain=retain)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug("message_published", topic=topic)
                return True
            else:
                # Queue on failure
                await self.persistence.queue_mqtt_message(topic, payload, qos, retain)
                logger.warning("publish_failed_queued", topic=topic, rc=result.rc)
                return False
        
        except Exception as e:
            # Queue on exception
            await self.persistence.queue_mqtt_message(topic, payload, qos, retain)
            logger.error("publish_error_queued", topic=topic, error=str(e))
            return False
    
    async def publish_discovery(
        self,
        device_id: str,
        device_type: str,
        device_name: str,
        manufacturer: str,
        model: str,
        sw_version: str,
        attributes: Dict[str, Dict[str, Any]]
    ) -> None:
        """
        Publish Home Assistant discovery configuration for a device.
        
        Args:
            device_id: Unique device identifier
            device_type: Device type (e.g., "mbus_meter")
            device_name: Human-readable device name
            manufacturer: Manufacturer name
            model: Model name
            sw_version: Software version
            attributes: Dictionary of attributes (name -> {value, unit, type})
        """
        discovery_key = f"discovery_{device_id}"
        
        # Skip if already sent
        if discovery_key in self.discovery_sent:
            return
        
        logger.info("publishing_discovery", device_id=device_id, attributes=len(attributes))
        
        # Device info (common for all entities)
        device_info = {
            "identifiers": [device_id],
            "name": device_name,
            "manufacturer": manufacturer,
            "model": model,
            "sw_version": sw_version
        }
        
        # Publish discovery for each attribute
        for attr_name, attr_info in attributes.items():
            await self._publish_attribute_discovery(
                device_id,
                attr_name,
                attr_info,
                device_info
            )
            await asyncio.sleep(0.05)  # Rate limiting
        
        # Mark as sent
        self.discovery_sent.add(discovery_key)
        
        logger.info("discovery_published", device_id=device_id)
    
    async def _publish_attribute_discovery(
        self,
        device_id: str,
        attr_name: str,
        attr_info: Dict[str, Any],
        device_info: Dict[str, str]
    ) -> None:
        """Publish discovery for a single attribute."""
        # Sanitize attribute name for MQTT
        safe_attr = attr_name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        object_id = f"{device_id}_{safe_attr}"
        
        # Determine component type
        component = attr_info.get('type', 'sensor')
        if component not in ['sensor', 'binary_sensor', 'switch']:
            component = 'sensor'
        
        # State topic
        state_topic = f"{self.mqtt_config.topic_prefix}/device/{device_id}/{safe_attr}"
        
        # Build config
        config = {
            "name": attr_name,
            "unique_id": object_id,
            "state_topic": state_topic,
            "device": device_info,
            "availability": [
                {
                    "topic": self.ha_config.bridge_state_topic,
                    "payload_available": "online",
                    "payload_not_available": "offline"
                }
            ],
            "expire_after": self.ha_config.availability.expire_after
        }
        
        # Add unit if present
        unit = attr_info.get('unit')
        if unit and unit.lower() != "none":
            config["unit_of_measurement"] = unit
        
        # Add device class and icon
        self._add_device_class(config, attr_name, unit)
        
        # Binary sensor specific
        if component == "binary_sensor":
            if "status" in attr_name.lower():
                config["payload_on"] = "online"
                config["payload_off"] = "offline"
        
        # Discovery topic
        discovery_topic = f"{self.ha_config.discovery_prefix}/{component}/{object_id}/config"
        
        # Publish
        await self.publish(discovery_topic, json.dumps(config), retain=True)
    
    def _add_device_class(self, config: Dict, attr_name: str, unit: Optional[str]) -> None:
        """Add device_class and icon based on attribute."""
        attr_lower = attr_name.lower()
        unit_lower = (unit or "").lower()
        
        if "energie" in attr_lower or unit_lower in ["kwh", "wh", "mwh"]:
            config["device_class"] = "energy"
            config["icon"] = "mdi:lightning-bolt"
        elif "leistung" in attr_lower or unit_lower in ["w", "kw", "mw"]:
            config["device_class"] = "power"
            config["icon"] = "mdi:flash"
        elif "temperatur" in attr_lower or unit_lower in ["°c", "c"]:
            config["device_class"] = "temperature"
            config["icon"] = "mdi:thermometer"
        elif "spannung" in attr_lower or unit_lower == "v":
            config["device_class"] = "voltage"
            config["icon"] = "mdi:lightning-bolt"
        elif "strom" in attr_lower or unit_lower == "a":
            config["device_class"] = "current"
            config["icon"] = "mdi:current-ac"
        elif "ip" in attr_lower:
            config["icon"] = "mdi:ip-network"
        elif "status" in attr_lower:
            config["icon"] = "mdi:check-circle"
        elif "uptime" in attr_lower:
            config["icon"] = "mdi:clock"
        else:
            config["icon"] = "mdi:gauge"
    
    async def publish_state(
        self,
        device_id: str,
        attribute: str,
        value: Any
    ) -> None:
        """
        Publish device state for a single attribute.
        
        Args:
            device_id: Device identifier
            attribute: Attribute name
            value: Attribute value
        """
        # Sanitize attribute name
        safe_attr = attribute.lower().replace(" ", "_").replace("(", "").replace(")", "")
        
        # State topic
        topic = f"{self.mqtt_config.topic_prefix}/device/{device_id}/{safe_attr}"
        
        # Convert value to string
        if isinstance(value, (int, float)):
            payload = str(round(value, 4))
        else:
            payload = str(value)
        
        # Publish with retain
        await self.publish(topic, payload, retain=True)
    
    async def publish_device_states(
        self,
        device_id: str,
        attributes: Dict[str, Any]
    ) -> None:
        """
        Publish all attributes of a device.
        
        Args:
            device_id: Device identifier
            attributes: Dictionary of attribute values
        """
        for attr_name, value in attributes.items():
            await self.publish_state(device_id, attr_name, value)
            await asyncio.sleep(0.01)  # Rate limiting
    
    async def _heartbeat_loop(self) -> None:
        """Background task for heartbeat."""
        while self._running:
            try:
                interval = self.ha_config.availability.heartbeat_interval
                await asyncio.sleep(interval)
                
                if self.connected:
                    # Refresh bridge state
                    await self.publish(
                        self.ha_config.bridge_state_topic,
                        "online",
                        retain=True
                    )
                    
                    logger.debug("heartbeat_sent")
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("heartbeat_error", error=str(e))
                await asyncio.sleep(10)
    
    async def _process_queue_loop(self) -> None:
        """Background task to process queued messages."""
        while self._running:
            try:
                await asyncio.sleep(10)
                
                if not self.connected:
                    continue
                
                # Get queued messages
                messages = await self.persistence.get_queued_messages(limit=100)
                
                if not messages:
                    continue
                
                logger.info("processing_queue", count=len(messages))
                
                for msg in messages:
                    try:
                        result = self.client.publish(
                            msg['topic'],
                            msg['payload'],
                            qos=msg['qos'],
                            retain=msg['retain']
                        )
                        
                        if result.rc == mqtt.MQTT_ERR_SUCCESS:
                            # Delete from queue
                            await self.persistence.delete_queued_message(msg['id'])
                            logger.debug("queued_message_sent", topic=msg['topic'])
                        else:
                            logger.warning("queued_message_failed", topic=msg['topic'], rc=result.rc)
                            break  # Stop processing on error
                    
                    except Exception as e:
                        logger.error("queue_process_error", error=str(e))
                        break
                    
                    await asyncio.sleep(0.05)  # Rate limiting
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("queue_loop_error", error=str(e))
                await asyncio.sleep(30)
    
    async def _send_all_discovery(self) -> None:
        """Resend discovery for all devices (e.g., after HA restart)."""
        logger.info("resending_all_discovery")
        
        # Load all device states from persistence
        all_states = await self.persistence.load_all_device_states()
        
        for device_id, device_data in all_states.items():
            try:
                state = device_data['state']
                
                # Build attributes dict
                attributes = {}
                for key, value in state.items():
                    if not key.startswith('_'):
                        attributes[key] = {
                            'value': value,
                            'unit': '',
                            'type': 'sensor'
                        }
                
                await self.publish_discovery(
                    device_id=device_id,
                    device_type=device_data['device_type'],
                    device_name=device_data['name'],
                    manufacturer=device_data['manufacturer'],
                    model=device_data['model'],
                    sw_version=device_data['sw_version'],
                    attributes=attributes
                )
                
                await asyncio.sleep(0.2)
            
            except Exception as e:
                logger.error("rediscovery_error", device_id=device_id, error=str(e))
        
        logger.info("rediscovery_completed")
