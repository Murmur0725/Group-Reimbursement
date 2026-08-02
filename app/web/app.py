import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import init_config
from app.db.database import init_db
from app.web import (
    routes_actions,
    routes_dashboard,
    routes_downloads,
    routes_records,
    routes_sync,
)

BASE_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    init_config()
    init_db()
    app = FastAPI(title="Notion 报销后台")
    app.mount(
        "/static",
        StaticFiles(directory=BASE_DIR / "static"),
        name="static",
    )

    app.include_router(routes_dashboard.router)
    app.include_router(routes_records.router)
    app.include_router(routes_sync.router)
    app.include_router(routes_actions.router)
    app.include_router(routes_downloads.router)

    if os.getenv("ENABLE_BACKEND_SCHEDULER", "0") == "1":
        from app.services.scheduler import start_scheduler, stop_scheduler

        start_scheduler()

        @app.on_event("shutdown")
        def _shutdown_scheduler():
            stop_scheduler()

    return app


app = create_app()
