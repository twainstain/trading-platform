"""Base FastAPI application factory for trading systems.

Provides common endpoints that every product needs:
  - /health — system health check
  - /metrics — metrics snapshot
  - /pause + /resume — soft pause control
  - /config — current config inspection

Products extend the returned app with their own endpoints.

Usage:
    from api.base_app import create_base_app

    app = create_base_app(metrics=my_metrics)
    # Add product-specific endpoints:
    app.get("/opportunities")(get_opportunities)
"""

from __future__ import annotations

import os
import secrets
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_security = HTTPBasic()

# Module-level state shared across the app.
_metrics: Any = None
_paused = False
_start_time = time.time()


def _get_credentials() -> tuple[str, str]:
    """Read auth credentials from environment."""
    return (
        os.environ.get("DASHBOARD_USER", "admin"),
        os.environ.get("DASHBOARD_PASS", "admin"),
    )


def verify_credentials(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    """Verify HTTP Basic credentials. Returns username."""
    expected_user, expected_pass = _get_credentials()
    correct_user = secrets.compare_digest(credentials.username, expected_user)
    correct_pass = secrets.compare_digest(credentials.password, expected_pass)
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def create_base_app(
    metrics: Any = None,
    require_auth: bool = True,
    title: str = "Trading Platform",
    version: str = "0.1.0",
) -> FastAPI:
    """Create a FastAPI app with shared trading infrastructure endpoints.

    Args:
        metrics: A MetricsCollector instance (or None).
        require_auth: If True, all endpoints require HTTP Basic auth.
        title: App title for OpenAPI docs.
        version: App version.

    Returns:
        A FastAPI app that products extend with their own endpoints.
    """
    global _metrics, _start_time
    _metrics = metrics
    _start_time = time.time()

    app = FastAPI(title=title, version=version)

    auth_dep = [Depends(verify_credentials)] if require_auth else []

    @app.get("/health", dependencies=auth_dep)
    def health():
        return {
            "status": "paused" if _paused else "healthy",
            "uptime_seconds": round(time.time() - _start_time, 1),
        }

    @app.get("/metrics", dependencies=auth_dep)
    def get_metrics():
        if _metrics is None:
            return {"error": "metrics not configured"}
        return _metrics.snapshot()

    @app.get("/pause", dependencies=auth_dep)
    def pause_status():
        return {"paused": _paused}

    @app.post("/pause", dependencies=auth_dep)
    def pause():
        global _paused
        _paused = True
        return {"paused": True}

    @app.post("/resume", dependencies=auth_dep)
    def resume():
        global _paused
        _paused = False
        return {"paused": False}

    return app


def is_paused() -> bool:
    """Check if the system is in soft-pause state."""
    return _paused
