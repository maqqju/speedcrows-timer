"""
Sprint Timer — FastAPI backend

Endpoints:
  POST /upload              — upload a video file, returns video_id + metadata
  POST /analyse/{video_id}  — start analysis with gate definitions
  WS   /ws/{video_id}       — stream frame previews + crossing events
  GET  /results/{video_id}  — fetch completed timing results
  DELETE /video/{video_id}  — clean up temp file
"""

import asyncio
import base64
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from pipeline import VideoPipeline
from tracker import TrackState, gates_from_payload, update_tracker

app = FastAPI(title="Sprint Timer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store: video_id → { path, meta, results, ws_queue }
sessions: dict[str, dict] = {}

UPLOAD_DIR = Path(tempfile.gettempdir()) / "sprint_timer_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    video_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / f"{video_id}{Path(file.filename).suffix}"

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Quick metadata read (non-blocking enough for FastAPI)
    pipeline = VideoPipeline(str(dest))
    meta = pipeline.info
    pipeline.release()

    sessions[video_id] = {
        "path": str(dest),
        "meta": meta,
        "results": None,
        "queue": asyncio.Queue(),
    }

    return {"video_id": video_id, "meta": meta}


# ---------------------------------------------------------------------------
# Analyse (kicks off processing in background)
# ---------------------------------------------------------------------------

@app.post("/analyse/{video_id}")
async def start_analysis(video_id: str, body: dict):
    session = sessions.get(video_id)
    if not session:
        return JSONResponse({"error": "Unknown video_id"}, status_code=404)

    gate_defs = body.get("gates", [])

    # Run processing in a thread so we don't block the event loop
    asyncio.get_event_loop().run_in_executor(
        None, _run_analysis, video_id, gate_defs
    )

    return {"status": "started"}


def _run_analysis(video_id: str, gate_defs: list):
    session = sessions[video_id]
    path = session["path"]
    queue: asyncio.Queue = session["queue"]
    loop = asyncio.new_event_loop()

    try:
        pipeline = VideoPipeline(path, learning_rate=0.003)
        meta = pipeline.info
        frame_w, frame_h = meta["width"], meta["height"]

        # Warmup background model
        pipeline.warmup(n_frames=90)

        gates = gates_from_payload(gate_defs, frame_w, frame_h)
        state = TrackState(gates=gates)

        for frame_data in pipeline.process_frames(gates=gates, thumb_width=640):
            centroid = frame_data["centroid"]
            timestamp = frame_data["timestamp"]

            new_crossings = update_tracker(state, centroid, timestamp)

            # Encode thumbnail as base64 for JSON transport
            thumb_b64 = base64.b64encode(frame_data["thumb_jpeg"]).decode()

            msg = {
                "type": "frame",
                "frame_index": frame_data["frame_index"],
                "timestamp": round(timestamp, 4),
                "progress": round(frame_data["progress"], 4),
                "centroid": centroid,
                "thumb": thumb_b64,
                "new_crossings": new_crossings,
            }

            loop.run_until_complete(queue.put(json.dumps(msg)))

        # Final results
        results = {
            "crossings": state.crossings,
            "splits": _compute_splits(state.crossings),
        }
        session["results"] = results

        done_msg = {"type": "done", "results": results}
        loop.run_until_complete(queue.put(json.dumps(done_msg)))

        pipeline.release()

    except Exception as e:
        err_msg = {"type": "error", "message": str(e)}
        loop.run_until_complete(queue.put(json.dumps(err_msg)))
    finally:
        loop.close()


def _compute_splits(crossings: list) -> list:
    """Compute inter-gate splits from ordered crossings."""
    if not crossings:
        return []

    splits = []
    for i, crossing in enumerate(crossings):
        entry = {
            "gate_id": crossing["gate_id"],
            "gate_label": crossing["gate_label"],
            "cumulative": round(crossing["split_time"], 4),
            "split": None,
        }
        if i > 0:
            entry["split"] = round(
                crossing["split_time"] - crossings[i - 1]["split_time"], 4
            )
        splits.append(entry)
    return splits


# ---------------------------------------------------------------------------
# WebSocket streaming
# ---------------------------------------------------------------------------

@app.websocket("/ws/{video_id}")
async def websocket_stream(websocket: WebSocket, video_id: str):
    session = sessions.get(video_id)
    if not session:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    queue: asyncio.Queue = session["queue"]

    try:
        while True:
            msg = await asyncio.wait_for(queue.get(), timeout=30.0)
            await websocket.send_text(msg)

            parsed = json.loads(msg)
            if parsed["type"] in ("done", "error"):
                break

    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        await websocket.close()


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@app.get("/results/{video_id}")
async def get_results(video_id: str):
    session = sessions.get(video_id)
    if not session:
        return JSONResponse({"error": "Unknown video_id"}, status_code=404)
    if session["results"] is None:
        return JSONResponse({"status": "processing"})
    return session["results"]


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

@app.delete("/video/{video_id}")
async def delete_video(video_id: str):
    session = sessions.pop(video_id, None)
    if session and os.path.exists(session["path"]):
        os.remove(session["path"])
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Serve frontend from /
# ---------------------------------------------------------------------------

frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
