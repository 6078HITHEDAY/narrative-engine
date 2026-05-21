"""FastAPI 应用工厂。"""

from __future__ import annotations

from fastapi import FastAPI

from narrative_engine.core.engine import NarrativeEngine


def create_app(engine: NarrativeEngine | None = None) -> FastAPI:
    if engine is None:
        engine = NarrativeEngine()

    app = FastAPI(title="narrative-engine", version="0.1.0")

    app.state.engine = engine

    from narrative_engine.api.routes import router
    app.include_router(router)

    return app
