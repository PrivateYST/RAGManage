from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.core.health import check_dependencies


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    app = FastAPI(title="RAGManage", version="0.1.0")

    @app.get("/api/v1/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health/ready")
    async def ready() -> JSONResponse:
        checks = await check_dependencies(config)
        healthy = all(value == "ok" for value in checks.values())
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={"status": "ready" if healthy else "not_ready", "checks": checks},
        )

    return app


app = create_app()
