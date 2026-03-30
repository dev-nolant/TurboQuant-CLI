from __future__ import annotations

import argparse
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn


def create_app(static_dir: Path, api_base: str) -> FastAPI:
    app = FastAPI()

    @app.api_route("/proxy/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def proxy(path: str, request: Request) -> Response:
        url = f"{api_base.rstrip('/')}/{path}"
        body = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.request(request.method, url, headers=headers, content=body, params=request.query_params)
        return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> Response:
        candidate = static_dir / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        index = static_dir / "index.html"
        if index.exists():
            html = index.read_text()
            html = html.replace("http://localhost:8080", "/proxy")
            html = html.replace("http://127.0.0.1:8080", "/proxy")
            return HTMLResponse(html)
        return PlainTextResponse("web ui not built", status_code=404)

    return app



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--static-dir", required=True)
    parser.add_argument("--api-base", required=True)
    args = parser.parse_args()
    app = create_app(Path(args.static_dir), args.api_base)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
