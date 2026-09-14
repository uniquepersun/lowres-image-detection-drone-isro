"""
reference_routes.py

Shared FastAPI routes for uploading the 3 target/reference images and
streaming match results. Used by both app.py (real backend) and
mock_server.py (hardware-free dev backend), so the matching feature works
identically whether you're testing on the Mac or running on the Jetson.

Adds:
  POST   /reference-images/{slot}   - upload a target image (slot 1-3)
  DELETE /reference-images/{slot}   - clear a target image
  WS     /matches                   - match results, pushed at 5 Hz
"""

import asyncio

from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from object_matcher import reference_store, match_store, start_matching_thread, SLOTS

MATCHES_PUSH_HZ = 5


def register_reference_routes(app: FastAPI, frame_getter):
    """
    Attach reference-image + matches endpoints to `app`, and start the
    background matching loop reading frames via `frame_getter()` (a
    zero-arg callable returning the latest JPEG bytes or None).
    """

    start_matching_thread(frame_getter)

    @app.post("/reference-images/{slot}")
    async def upload_reference_image(slot: int, file: UploadFile = File(...)):
        if slot not in SLOTS:
            return JSONResponse({"error": "slot must be 1, 2, or 3"}, status_code=400)
        data = await file.read()
        ok = reference_store.set(slot, data)
        if not ok:
            return JSONResponse(
                {"error": "Couldn't find enough distinguishable features in that image. "
                          "Try a more detailed or higher-contrast image."},
                status_code=400,
            )
        return JSONResponse({"slot": slot, "loaded": True})

    @app.delete("/reference-images/{slot}")
    def clear_reference_image(slot: int):
        reference_store.clear(slot)
        match_store.update(slot, loaded=False, found=False, confidence=0.0, quad=None)
        return JSONResponse({"slot": slot, "loaded": False})

    @app.websocket("/matches")
    async def matches_ws(websocket: WebSocket):
        await websocket.accept()
        period = 1.0 / MATCHES_PUSH_HZ
        try:
            while True:
                await websocket.send_json(match_store.snapshot())
                await asyncio.sleep(period)
        except WebSocketDisconnect:
            pass
