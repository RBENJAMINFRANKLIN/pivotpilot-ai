import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.ai.llm import AIUnavailable
from app.api.v1 import router as v1_router
from app.config import get_settings
from app.db import SessionLocal
from app.security.ratelimit import enforce

log = logging.getLogger("pivotpilot")
CSRF_HEADER = "x-pivotpilot-client"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> FastAPI:
    s = get_settings()
    logging.basicConfig(level=s.log_level)
    for problem in s.validate_for_production():
        log.error("configuration problem: %s", problem)

    app = FastAPI(
        title="PivotPilot AI API",
        version="1.0.0",
        description="Career-transition platform API. All endpoints are versioned under /api/v1.",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-PivotPilot-Client"],
    )

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and request.method in UNSAFE:
            # CSRF: browsers cannot attach a custom header cross-site without a CORS
            # preflight, which our allow-list rejects. Bearer-token clients are exempt.
            if not request.headers.get("authorization") and request.headers.get(CSRF_HEADER) != "web":
                return JSONResponse({"detail": {"code": "CSRF_HEADER_MISSING", "message": "Missing client header."}}, status_code=403)
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > s.max_upload_bytes + 64 * 1024:
                return JSONResponse({"detail": {"code": "PAYLOAD_TOO_LARGE", "message": "Request is too large."}}, status_code=413)
        if path.startswith("/api/v1/"):
            try:
                enforce(request, "default", s.rate_limit_default_per_minute)
            except Exception as e:  # HTTPException from enforce
                return JSONResponse({"detail": e.detail}, status_code=429, headers=e.headers)  # type: ignore[attr-defined]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        return response

    @app.exception_handler(AIUnavailable)
    async def ai_unavailable(_: Request, exc: AIUnavailable):
        return JSONResponse({"detail": {"code": exc.code, "message": exc.message}}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def validation(_: Request, exc: RequestValidationError):
        errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse({"detail": {"code": "VALIDATION_ERROR", "message": "Some fields are invalid.", "errors": errors}}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse({"detail": {"code": "INTERNAL_ERROR", "message": "Something went wrong. Please try again."}}, status_code=500)

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready():
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
            return {"status": "ready", "database": "ok"}
        except Exception:
            return JSONResponse({"status": "unavailable", "database": "error"}, status_code=503)

    app.include_router(v1_router, prefix="/api/v1")
    _serve_frontend(app)
    return app


def _serve_frontend(app: FastAPI) -> None:
    """Single-server mode: when the React app has been built (frontend/dist), serve it from
    this process so one URL hosts everything and the session cookie stays first-party."""
    dist = Path(get_settings().frontend_dist or Path(__file__).resolve().parents[2] / "frontend" / "dist")
    index = dist / "index.html"
    if not index.is_file():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": {"code": "NOT_FOUND", "message": "Not found."}}, status_code=404)
        f = (dist / path).resolve()
        if path and dist in f.parents and f.is_file():
            return FileResponse(f)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
