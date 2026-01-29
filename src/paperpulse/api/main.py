"""FastAPI application for PaperPulse API."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from paperpulse.api.routes import auth_router, profiles_router, users_router
from paperpulse.core.config import get_settings
from paperpulse.db.session import close_db, init_db

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Initializes database on startup and closes connections on shutdown.
    """
    settings = get_settings()
    logger.info(
        "Starting PaperPulse API",
        environment=settings.environment,
        debug=settings.debug,
    )

    # Initialize database
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise

    yield

    # Cleanup on shutdown
    logger.info("Shutting down PaperPulse API")
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application
    """
    settings = get_settings()

    app = FastAPI(
        title="PaperPulse API",
        description="AI-powered academic paper recommendations and digest system",
        version="0.2.0",
        lifespan=lifespan,
        debug=settings.debug,
        docs_url="/api/docs" if settings.is_development else None,
        redoc_url="/api/redoc" if settings.is_development else None,
        openapi_url="/api/openapi.json" if settings.is_development else None,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle uncaught exceptions."""
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    # Include routers
    app.include_router(
        auth_router,
        prefix="/api/v1/auth",
    )
    app.include_router(
        users_router,
        prefix="/api/v1/users",
    )
    app.include_router(
        profiles_router,
        prefix="/api/v1/profiles",
    )

    # Health check endpoint
    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """Health check endpoint.

        Returns:
            Health status
        """
        return {
            "status": "healthy",
            "version": "0.2.0",
            "environment": settings.environment,
        }

    # API info endpoint
    @app.get("/api/v1", tags=["info"])
    async def api_info() -> dict:
        """API information endpoint.

        Returns:
            API version and available endpoints
        """
        return {
            "name": "PaperPulse API",
            "version": "0.2.0",
            "description": "AI-powered academic paper recommendations",
            "endpoints": {
                "auth": "/api/v1/auth",
                "users": "/api/v1/users",
                "profiles": "/api/v1/profiles",
            },
        }

    return app


# Create the application instance
app = create_app()


def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Run the API server using uvicorn.

    Args:
        host: Host to bind to
        port: Port to listen on
        reload: Enable auto-reload for development
    """
    import uvicorn

    uvicorn.run(
        "paperpulse.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    run_server(reload=True)
