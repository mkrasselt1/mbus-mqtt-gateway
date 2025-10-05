"""
State Persistence Layer
SQLite-based state management with async support.
"""

import aiosqlite
import json
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime, timedelta

from src.logger import get_logger

logger = get_logger(__name__)


class StatePersistence:
    """
    Handles state persistence to SQLite database.
    Provides crash recovery and offline queueing.
    """
    
    def __init__(self, db_path: str):
        """
        Initialize state persistence.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None
        
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        logger.info("state_persistence_init", db_path=db_path)
    
    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        self.db = await aiosqlite.connect(self.db_path)
        
        # Enable WAL mode for better concurrency
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA synchronous=NORMAL")
        
        # Create tables
        await self._create_tables()
        
        logger.info("state_persistence_initialized", db_path=self.db_path)
    
    async def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        
        # Device states table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS device_states (
                device_id TEXT PRIMARY KEY,
                device_type TEXT NOT NULL,
                name TEXT NOT NULL,
                manufacturer TEXT,
                model TEXT,
                sw_version TEXT,
                state_json TEXT NOT NULL,
                last_update REAL NOT NULL,
                online INTEGER DEFAULT 1
            )
        """)
        
        # MQTT message queue (for offline buffering)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS mqtt_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                payload TEXT NOT NULL,
                qos INTEGER DEFAULT 1,
                retain INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            )
        """)
        
        # State change history (optional)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS state_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                attribute TEXT NOT NULL,
                value TEXT NOT NULL,
                timestamp REAL NOT NULL,
                FOREIGN KEY (device_id) REFERENCES device_states(device_id)
            )
        """)
        
        # Create indices for performance
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_device_time 
            ON state_history(device_id, timestamp DESC)
        """)
        
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_queue_created 
            ON mqtt_queue(created_at ASC)
        """)
        
        await self.db.commit()
        
        logger.debug("database_tables_created")
    
    async def save_device_state(
        self, 
        device_id: str,
        device_type: str,
        name: str,
        state: Dict[str, Any],
        manufacturer: str = "Unknown",
        model: str = "Unknown",
        sw_version: str = "",
        online: bool = True
    ) -> None:
        """
        Save or update device state.
        
        Args:
            device_id: Unique device identifier
            device_type: Type of device (e.g., "mbus_meter", "gateway")
            name: Human-readable device name
            state: Device state as dictionary
            manufacturer: Device manufacturer
            model: Device model
            sw_version: Software version
            online: Whether device is online
        """
        state_json = json.dumps(state)
        timestamp = time.time()
        
        await self.db.execute("""
            INSERT INTO device_states 
            (device_id, device_type, name, manufacturer, model, sw_version, state_json, last_update, online)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                device_type = excluded.device_type,
                name = excluded.name,
                manufacturer = excluded.manufacturer,
                model = excluded.model,
                sw_version = excluded.sw_version,
                state_json = excluded.state_json,
                last_update = excluded.last_update,
                online = excluded.online
        """, (device_id, device_type, name, manufacturer, model, sw_version, 
              state_json, timestamp, int(online)))
        
        await self.db.commit()
        
        logger.debug("device_state_saved", device_id=device_id, online=online)
    
    async def load_device_state(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Load device state from database.
        
        Args:
            device_id: Device identifier
            
        Returns:
            Device state dictionary or None if not found
        """
        async with self.db.execute(
            "SELECT state_json, last_update, online FROM device_states WHERE device_id = ?",
            (device_id,)
        ) as cursor:
            row = await cursor.fetchone()
            
            if row:
                state_json, last_update, online = row
                state = json.loads(state_json)
                state['_last_update'] = last_update
                state['_online'] = bool(online)
                
                logger.debug("device_state_loaded", device_id=device_id)
                return state
            
            return None
    
    async def load_all_device_states(self) -> Dict[str, Dict[str, Any]]:
        """
        Load all device states from database.
        
        Returns:
            Dictionary mapping device_id to state
        """
        states = {}
        
        async with self.db.execute(
            "SELECT device_id, device_type, name, manufacturer, model, sw_version, state_json, last_update, online "
            "FROM device_states"
        ) as cursor:
            async for row in cursor:
                device_id, device_type, name, manufacturer, model, sw_version, state_json, last_update, online = row
                
                states[device_id] = {
                    'device_type': device_type,
                    'name': name,
                    'manufacturer': manufacturer,
                    'model': model,
                    'sw_version': sw_version,
                    'state': json.loads(state_json),
                    'last_update': last_update,
                    'online': bool(online)
                }
        
        logger.info("all_device_states_loaded", count=len(states))
        return states
    
    async def queue_mqtt_message(
        self,
        topic: str,
        payload: str,
        qos: int = 1,
        retain: bool = False
    ) -> None:
        """
        Queue MQTT message for later delivery (when offline).
        
        Args:
            topic: MQTT topic
            payload: Message payload
            qos: Quality of Service
            retain: Retain flag
        """
        timestamp = time.time()
        
        await self.db.execute("""
            INSERT INTO mqtt_queue (topic, payload, qos, retain, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (topic, payload, qos, int(retain), timestamp))
        
        await self.db.commit()
        
        logger.debug("mqtt_message_queued", topic=topic)
    
    async def get_queued_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get queued MQTT messages (oldest first).
        
        Args:
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of message dictionaries
        """
        messages = []
        
        async with self.db.execute("""
            SELECT id, topic, payload, qos, retain, created_at
            FROM mqtt_queue
            ORDER BY created_at ASC
            LIMIT ?
        """, (limit,)) as cursor:
            async for row in cursor:
                msg_id, topic, payload, qos, retain, created_at = row
                messages.append({
                    'id': msg_id,
                    'topic': topic,
                    'payload': payload,
                    'qos': qos,
                    'retain': bool(retain),
                    'created_at': created_at
                })
        
        if messages:
            logger.info("queued_messages_retrieved", count=len(messages))
        
        return messages
    
    async def delete_queued_message(self, message_id: int) -> None:
        """
        Delete a message from the queue after successful delivery.
        
        Args:
            message_id: Message ID to delete
        """
        await self.db.execute("DELETE FROM mqtt_queue WHERE id = ?", (message_id,))
        await self.db.commit()
    
    async def clear_queue(self) -> int:
        """
        Clear all queued messages.
        
        Returns:
            Number of messages deleted
        """
        cursor = await self.db.execute("DELETE FROM mqtt_queue")
        await self.db.commit()
        count = cursor.rowcount
        
        logger.info("mqtt_queue_cleared", count=count)
        return count
    
    async def get_queue_size(self) -> int:
        """
        Get current queue size.
        
        Returns:
            Number of queued messages
        """
        async with self.db.execute("SELECT COUNT(*) FROM mqtt_queue") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    
    async def cleanup_old_history(self, days: int = 7) -> int:
        """
        Delete history older than specified days.
        
        Args:
            days: Number of days to keep
            
        Returns:
            Number of rows deleted
        """
        cutoff = time.time() - (days * 86400)
        
        cursor = await self.db.execute(
            "DELETE FROM state_history WHERE timestamp < ?",
            (cutoff,)
        )
        await self.db.commit()
        
        count = cursor.rowcount
        if count > 0:
            logger.info("old_history_cleaned", count=count, days=days)
        
        return count
    
    async def close(self) -> None:
        """Close database connection."""
        if self.db:
            await self.db.close()
            logger.info("state_persistence_closed")
