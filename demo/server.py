"""ZecPy Live: `uvicorn demo.server:app --port 8077`, then open http://127.0.0.1:8077.

Needs the regtest chain from the SDK repo (`devnet/up.sh`) and `zecpy` installed.
"""

from __future__ import annotations

import os
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .hub import Hub
from .scenes import SCENES
from .stage import Stage

STATIC = Path(__file__).parent / "static"
RUNS = Path(os.environ.get("ZECPY_DEMO_RUNS", Path(__file__).resolve().parents[1] / "runs"))

hub = Hub()
stage = Stage(hub, RUNS / time.strftime("%Y%m%d-%H%M%S"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await stage.start()
    hub.publish("chain", height=stage.devnet.height())
    yield
    await stage.stop()


app = FastAPI(title="ZecPy Live", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/events")
async def events() -> StreamingResponse:
    async def sse():
        async for line in hub.stream():
            yield f"data: {line}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream", headers={"cache-control": "no-cache"})


@app.post("/scenes/{name}")
async def run(name: str) -> dict[str, str]:
    scene = SCENES.get(name)
    if scene is None:
        raise HTTPException(404, f"no scene {name!r}")
    if stage.lock.locked():
        raise HTTPException(409, "a scene is already running")
    async with stage.lock:
        try:
            await scene(stage)
        except Exception as exc:
            traceback.print_exc()
            hub.publish("scene", scene=name, state="failed", error=str(exc)[:300])
            raise HTTPException(500, str(exc)[:300]) from exc
    return {"scene": name, "state": "done"}


@app.post("/reset")
async def reset() -> dict[str, str]:
    """Clears the screen between takes. Wallets made so far stay on disk."""
    hub.clear()
    hub.publish("chain", height=stage.devnet.height())
    return {"state": "reset"}
