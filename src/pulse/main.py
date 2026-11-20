"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import uvicorn
from fastapi import FastAPI

from pulse import __version__
from pulse.api.health import router as health_router
from pulse.api.metrics import router as metrics_router
from pulse.api.v1 import api_router
from pulse.config import Settings, get_settings
from pulse.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    logger.info(
        "pulse_api_starting",
        extra={"env": settings.env, "version": __version__},
    )
    yield
    logger.info("pulse_api_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory."""
    cfg = settings or get_settings()
    configure_logging(cfg)

    app = FastAPI(
        title="Pulse Data Engine",
        description=(
            "Social listening data acquisition platform. "
            "Phases 1–7: connectors, workers, matching, ClickHouse, usage/cost, Prometheus."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.settings = cfg

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(api_router)

    return app


app = create_app()


def run() -> None:
    """CLI entrypoint: `pulse` / `python -m pulse.main`."""
    settings = get_settings()
    uvicorn.run(
        "pulse.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_config=None,
    )


if __name__ == "__main__":
    run()
