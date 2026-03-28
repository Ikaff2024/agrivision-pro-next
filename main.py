import os
import time
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.auth.auth_routes import router as auth_router
from app.db.database import engine, Base
from app.db import models  # noqa: F401

load_dotenv()

# ── Logging structuré ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agrivision")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AgriVision Pro - CacaoEngine API",
    description="API exposant le moteur agronomique déterministe CacaoEngine",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")
allowed_origins = [o.strip() for o in _raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Middleware : logging des requêtes + timing ─────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)

    level = logging.WARNING if response.status_code >= 400 else logging.INFO
    logger.log(
        level,
        "%s %s → %d  [%s ms]",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    response.headers["X-Process-Time"] = str(duration_ms)
    return response


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne du serveur. L'équipe a été notifiée."},
    )


# ── Startup / Shutdown ────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    logger.info("AgriVision Pro API démarrée — CacaoEngine v1.0.0")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("AgriVision Pro API arrêtée.")


# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(api_router)
