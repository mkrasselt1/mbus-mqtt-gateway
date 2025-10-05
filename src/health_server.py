"""
Health Check HTTP Server
Provides health status and metrics for monitoring.
"""

import asyncio
import time
import json
from typing import Dict, Any, Optional
from aiohttp import web

from src.logger import get_logger

logger = get_logger(__name__)


class HealthServer:
    """HTTP server for health checks and metrics."""
    
    def __init__(self, port: int = 8080, enable_metrics: bool = True):
        """
        Initialize health server.
        
        Args:
            port: HTTP port to listen on
            enable_metrics: Enable Prometheus metrics endpoint
        """
        self.port = port
        self.enable_metrics = enable_metrics
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.start_time = time.time()
        
        # Health status
        self.status = {
            "healthy": True,
            "components": {}
        }
        
        # Setup routes
        self.app.router.add_get('/health', self._health_handler)
        self.app.router.add_get('/status', self._status_handler)
        
        if enable_metrics:
            self.app.router.add_get('/metrics', self._metrics_handler)
        
        logger.info("health_server_init", port=port)
    
    async def start(self) -> None:
        """Start HTTP server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await site.start()
        
        logger.info("health_server_started", port=self.port)
    
    async def stop(self) -> None:
        """Stop HTTP server."""
        if self.runner:
            await self.runner.cleanup()
        
        logger.info("health_server_stopped")
    
    def update_component_status(self, component: str, healthy: bool, **kwargs) -> None:
        """
        Update health status of a component.
        
        Args:
            component: Component name (e.g., "mbus", "mqtt", "persistence")
            healthy: Whether component is healthy
            **kwargs: Additional status information
        """
        self.status["components"][component] = {
            "healthy": healthy,
            "last_check": time.time(),
            **kwargs
        }
        
        # Overall health is healthy if all components are healthy
        self.status["healthy"] = all(
            c.get("healthy", False) 
            for c in self.status["components"].values()
        )
    
    async def _health_handler(self, request: web.Request) -> web.Response:
        """Handle /health endpoint (simple liveness check)."""
        if self.status["healthy"]:
            return web.Response(text="OK", status=200)
        else:
            return web.Response(text="UNHEALTHY", status=503)
    
    async def _status_handler(self, request: web.Request) -> web.Response:
        """Handle /status endpoint (detailed status)."""
        uptime = int(time.time() - self.start_time)
        
        response = {
            "status": "healthy" if self.status["healthy"] else "unhealthy",
            "uptime_seconds": uptime,
            "timestamp": time.time(),
            "components": self.status["components"]
        }
        
        return web.json_response(response)
    
    async def _metrics_handler(self, request: web.Request) -> web.Response:
        """Handle /metrics endpoint (Prometheus format)."""
        uptime = int(time.time() - self.start_time)
        
        metrics = []
        
        # Gateway uptime
        metrics.append(f"# HELP mbus_gateway_uptime_seconds Gateway uptime in seconds")
        metrics.append(f"# TYPE mbus_gateway_uptime_seconds gauge")
        metrics.append(f"mbus_gateway_uptime_seconds {uptime}")
        
        # Component health (1 = healthy, 0 = unhealthy)
        metrics.append(f"# HELP mbus_component_healthy Component health status")
        metrics.append(f"# TYPE mbus_component_healthy gauge")
        
        for component, status in self.status["components"].items():
            healthy = 1 if status.get("healthy", False) else 0
            metrics.append(f'mbus_component_healthy{{component="{component}"}} {healthy}')
        
        # Overall health
        metrics.append(f"# HELP mbus_gateway_healthy Overall gateway health")
        metrics.append(f"# TYPE mbus_gateway_healthy gauge")
        metrics.append(f"mbus_gateway_healthy {1 if self.status['healthy'] else 0}")
        
        return web.Response(text="\n".join(metrics) + "\n", content_type="text/plain")
