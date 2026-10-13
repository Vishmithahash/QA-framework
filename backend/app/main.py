from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.components.c2_state_aware_workflow.router import router as c2_router
from app.config import get_settings
from app.database import engine
from app.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(
        c2_router,
        prefix="/api/v1/c2",
        tags=["c2-state-aware-workflow"],
    )
    return app


app = create_app()
