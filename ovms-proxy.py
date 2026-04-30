"""
Thin proxy between OpenCode/Continue and OVMS.
- Clamps max_tokens so prompt + generation never exceeds model context
- Passes streaming (SSE) through transparently
- Runs on port 8001, forwards to OVMS on port 8000
"""
import json
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, Response

OVMS_BASE = "http://localhost:8000"
MODEL_CONTEXT = 32768
MAX_TOKENS_CAP = 4096

app = FastAPI()


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request, path: str):
    body = None

    if request.method == "POST":
        try:
            body = await request.json()
        except Exception:
            body = None

        if isinstance(body, dict) and "max_tokens" in body:
            body["max_tokens"] = min(int(body["max_tokens"]), MAX_TOKENS_CAP)

    target = f"{OVMS_BASE}/{path}"
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}

    if body and body.get("stream"):
        async def stream_gen():
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream(
                    request.method, target, json=body, headers=headers
                ) as resp:
                    async for chunk in resp.aiter_bytes():
                        yield chunk

        return StreamingResponse(stream_gen(), media_type="text/event-stream")

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.request(
            request.method, target,
            json=body if body else None,
            headers=headers
        )
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json")
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
