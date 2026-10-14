from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from app.components.c3_robustness_recovery.router import router as c3_router
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
    app.include_router(c3_router)

    from app.components.c4_policy_aware_safety.api.routes import router as c4_router

    app.include_router(c4_router)

    @app.exception_handler(RequestValidationError)
    async def c3_request_validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        if request.url.path.startswith("/api/v1/c3"):
            sanitized_errors = []
            for err in exc.errors():
                if isinstance(err, dict):
                    loc = [str(x) for x in err.get("loc", ())]
                    sanitized_errors.append(
                        {
                            "loc": loc,
                            "msg": err.get("msg", "Validation error"),
                            "type": err.get("type", "validation_error"),
                        }
                    )
                else:
                    sanitized_errors.append(
                        {
                            "loc": ["body"],
                            "msg": "Invalid JSON format or body content.",
                            "type": "json_invalid",
                        }
                    )
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"detail": sanitized_errors},
            )
        return await request_validation_exception_handler(request, exc)

    return app


app = create_app()
