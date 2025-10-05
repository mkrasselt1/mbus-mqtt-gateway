"""
Structured Logging Setup
Provides consistent logging across the application.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
import structlog
from logging.handlers import RotatingFileHandler

from src.config import LoggingConfig


def setup_logging(config: LoggingConfig) -> structlog.BoundLogger:
    """
    Setup structured logging based on configuration.
    
    Args:
        config: Logging configuration
        
    Returns:
        Configured structlog logger
    """
    # Configure standard logging
    log_level = getattr(logging, config.level.upper())
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    if config.format == "json":
        # JSON format for production
        console_formatter = logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'
        )
    else:
        # Human-readable format for development
        console_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)8s] %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (if configured)
    if config.file:
        file_path = Path(config.file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            config.file,
            maxBytes=config.max_size_mb * 1024 * 1024,
            backupCount=config.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(console_formatter)
        root_logger.addHandler(file_handler)
    
    # Error file handler (if configured)
    if config.error_file:
        error_path = Path(config.error_file)
        error_path.parent.mkdir(parents=True, exist_ok=True)
        
        error_handler = RotatingFileHandler(
            config.error_file,
            maxBytes=config.max_size_mb * 1024 * 1024,
            backupCount=config.backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(console_formatter)
        root_logger.addHandler(error_handler)
    
    # Configure structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    
    if config.format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    logger = structlog.get_logger()
    logger.info("logging_initialized", level=config.level, format=config.format)
    
    return logger


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Configured logger
    """
    if name:
        return structlog.get_logger(name)
    return structlog.get_logger()
