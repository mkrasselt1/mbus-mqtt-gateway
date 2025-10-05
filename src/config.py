"""
Configuration Management
Handles loading and validation of configuration from YAML/JSON files.
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings


class MQTTReconnectConfig(BaseModel):
    """MQTT Reconnection settings"""
    min_delay: int = Field(5, ge=1)
    max_delay: int = Field(300, ge=1)
    exponential: bool = True


class MQTTConfig(BaseModel):
    """MQTT Broker Configuration"""
    broker: str
    port: int = Field(1883, ge=1, le=65535)
    username: str = ""
    password: str = ""
    client_id: str = ""
    topic_prefix: str = "homeassistant"
    qos: int = Field(1, ge=0, le=2)
    keepalive: int = Field(60, ge=10)
    reconnect: MQTTReconnectConfig = MQTTReconnectConfig()


class MBusConfig(BaseModel):
    """M-Bus Configuration"""
    port: str
    baudrate: int = Field(9600, ge=300)
    timeout: float = Field(5.0, ge=0.1)
    scan_interval: int = Field(3600, ge=60)
    read_interval: int = Field(15, ge=5)
    max_retries: int = Field(3, ge=1)
    retry_delay: float = Field(2.0, ge=0.1)


class AvailabilityConfig(BaseModel):
    """Home Assistant Availability Settings"""
    expire_after: int = Field(300, ge=60)
    heartbeat_interval: int = Field(60, ge=10)


class HomeAssistantConfig(BaseModel):
    """Home Assistant Integration"""
    discovery_prefix: str = "homeassistant"
    availability: AvailabilityConfig = AvailabilityConfig()
    bridge_state_topic: str = "mbus/bridge/state"


class PersistenceConfig(BaseModel):
    """State Persistence Settings"""
    database: str = "/var/lib/mbus-gateway/state.db"
    enable_recovery: bool = True
    history_days: int = Field(7, ge=0)
    max_queue_size: int = Field(10000, ge=100)
    cleanup_interval: int = Field(86400, ge=3600)


class CircuitBreakerConfig(BaseModel):
    """Circuit Breaker Settings"""
    enabled: bool = True
    failure_threshold: int = Field(5, ge=1)
    timeout: int = Field(300, ge=60)


class AdvancedConfig(BaseModel):
    """Advanced Settings"""
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()
    worker_threads: int = Field(4, ge=1, le=32)
    graceful_shutdown_timeout: int = Field(30, ge=5)
    memory_limit_mb: int = Field(256, ge=64)


class MonitoringConfig(BaseModel):
    """Monitoring & Health Check Settings"""
    enable_http: bool = True
    http_port: int = Field(8080, ge=1024, le=65535)
    enable_metrics: bool = True
    metrics_path: str = "/metrics"
    enable_watchdog: bool = True
    watchdog_interval: int = Field(30, ge=10)


class LoggingConfig(BaseModel):
    """Logging Configuration"""
    level: str = Field("INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    format: str = Field("text", pattern="^(text|json)$")
    file: str = ""
    max_size_mb: int = Field(50, ge=1)
    backup_count: int = Field(5, ge=0)
    error_file: str = ""


class GatewayConfig(BaseModel):
    """Gateway Metadata"""
    name: str = "M-Bus Gateway"
    manufacturer: str = "Custom"
    model: str = "M-Bus MQTT Gateway v2"
    version: str = "2.0.0"


class Config(BaseModel):
    """Main Configuration"""
    mqtt: MQTTConfig
    mbus: MBusConfig
    homeassistant: HomeAssistantConfig = HomeAssistantConfig()
    persistence: PersistenceConfig = PersistenceConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
    logging: LoggingConfig = LoggingConfig()
    gateway: GatewayConfig = GatewayConfig()
    advanced: AdvancedConfig = AdvancedConfig()

    @validator("persistence")
    def validate_persistence_paths(cls, v):
        """Ensure database directory exists"""
        db_path = Path(v.database)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return v

    @validator("logging")
    def validate_logging_paths(cls, v):
        """Ensure log directory exists"""
        if v.file:
            log_path = Path(v.file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
        if v.error_file:
            error_path = Path(v.error_file)
            error_path.parent.mkdir(parents=True, exist_ok=True)
        return v

    @classmethod
    def load_from_file(cls, config_path: str) -> "Config":
        """
        Load configuration from YAML or JSON file.
        
        Args:
            config_path: Path to config file (*.yaml, *.yml, or *.json)
            
        Returns:
            Config instance
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config is invalid
        """
        path = Path(config_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        # Read file
        with open(path, 'r', encoding='utf-8') as f:
            if path.suffix in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            elif path.suffix == '.json':
                data = json.load(f)
            else:
                raise ValueError(f"Unsupported config format: {path.suffix}")
        
        # Parse and validate
        return cls(**data)

    @classmethod
    def load_from_legacy_json(cls, json_path: str) -> "Config":
        """
        Load configuration from legacy config.json format.
        Provides backward compatibility.
        
        Args:
            json_path: Path to legacy config.json
            
        Returns:
            Config instance
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            legacy_data = json.load(f)
        
        # Map legacy format to new format
        config_data = {
            "mqtt": {
                "broker": legacy_data.get("mqtt_broker", "localhost"),
                "port": legacy_data.get("mqtt_port", 1883),
                "username": legacy_data.get("mqtt_username", ""),
                "password": legacy_data.get("mqtt_password", ""),
                "topic_prefix": legacy_data.get("mqtt_topic", "homeassistant"),
            },
            "mbus": {
                "port": legacy_data.get("mbus_port", "/dev/ttyUSB0"),
                "baudrate": legacy_data.get("mbus_baudrate", 9600),
                "scan_interval": legacy_data.get("mbus_scan_interval_minutes", 60) * 60,
            }
        }
        
        return cls(**config_data)

    def save_to_file(self, output_path: str) -> None:
        """
        Save configuration to file (YAML or JSON).
        
        Args:
            output_path: Output file path
        """
        path = Path(output_path)
        data = self.model_dump()
        
        with open(path, 'w', encoding='utf-8') as f:
            if path.suffix in ['.yaml', '.yml']:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
            elif path.suffix == '.json':
                json.dump(data, f, indent=2)
            else:
                raise ValueError(f"Unsupported output format: {path.suffix}")


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from file or use defaults.
    
    Search order:
    1. Provided config_path
    2. Environment variable MBUS_CONFIG
    3. config.yaml in current directory
    4. config.json (legacy) in current directory
    5. /etc/mbus-gateway/config.yaml
    
    Args:
        config_path: Optional explicit config path
        
    Returns:
        Config instance
        
    Raises:
        FileNotFoundError: If no config file found
    """
    # 1. Explicit path
    if config_path:
        return Config.load_from_file(config_path)
    
    # 2. Environment variable
    env_config = os.getenv("MBUS_CONFIG")
    if env_config and Path(env_config).exists():
        return Config.load_from_file(env_config)
    
    # 3. config.yaml in current directory
    if Path("config.yaml").exists():
        return Config.load_from_file("config.yaml")
    
    # 4. config.json (legacy) in current directory
    if Path("config.json").exists():
        return Config.load_from_legacy_json("config.json")
    
    # 5. System config
    if Path("/etc/mbus-gateway/config.yaml").exists():
        return Config.load_from_file("/etc/mbus-gateway/config.yaml")
    
    raise FileNotFoundError(
        "No configuration file found. "
        "Please provide config.yaml or set MBUS_CONFIG environment variable."
    )
