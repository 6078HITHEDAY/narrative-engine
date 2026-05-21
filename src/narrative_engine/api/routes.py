"""API 路由。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from narrative_engine.api.schemas import (
    ChapterSwitchRequest,
    HealthResponse,
    StoryInfo,
    StoryLoadRequest,
    TellRequest,
)
from narrative_engine.models.narrative import NarrativeOutput

router = APIRouter()


async def _get_engine(request: Request):
    return request.app.state.engine


# ---- 叙事生成 ----

@router.post("/tell")
async def tell(req: TellRequest, request: Request):
    engine = await _get_engine(request)

    if req.stream:
        async def sse_stream():
            for partial in engine.tell_stream(req.state, req.kind, req.context, req.npc_id):
                if isinstance(partial, NarrativeOutput):
                    yield f"data: {partial.model_dump_json(ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                yield f"data: {json.dumps({'partial': partial.model_dump()}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse_stream(), media_type="text/event-stream")

    result = engine.tell(req.state, req.kind, req.context, req.npc_id)
    return result.model_dump()


# ---- 故事管理 ----

@router.get("/story", response_model=StoryInfo)
async def story_info(request: Request):
    engine = await _get_engine(request)
    return StoryInfo(
        title=engine.story_title,
        chapter=engine.current_chapter,
        chapters=engine.list_chapters(),
        npcs=list(engine.npcs.keys()),
    )


@router.post("/story/load")
async def story_load(req: StoryLoadRequest, request: Request):
    engine = await _get_engine(request)
    engine.load_story(req.story_dir, chapter=req.chapter)
    return {"status": "ok", "chapter": engine.current_chapter}


@router.get("/story/chapters")
async def story_chapters(request: Request):
    engine = await _get_engine(request)
    return {"chapters": engine.list_chapters()}


@router.post("/story/chapter/switch")
async def chapter_switch(req: ChapterSwitchRequest, request: Request):
    engine = await _get_engine(request)
    engine.switch_chapter(req.chapter)
    return {"status": "ok", "chapter": engine.current_chapter}


@router.post("/story/npcs/reload")
async def npcs_reload(request: Request):
    engine = await _get_engine(request)
    engine.reload_npcs()
    return {"status": "ok", "npcs": list(engine.npcs.keys())}


# ---- 健康检查 ----

@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()
