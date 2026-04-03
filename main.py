import os
import time
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.auth.auth_routes import router as auth_router
from app.db.database import engine, Base
from app.db import models  # noqa: F401

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agrivision")


# ── Lifespan (remplace les @app.on_event dépréciés) ──────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Tables DB vérifiées/créées avec succès.")
    except Exception as e:
        logger.error("Erreur création tables : %s", e)
    logger.info("AgriVision Pro API démarrée — CacaoEngine v1.0.0")

    yield  # l'application tourne ici

    # Shutdown
    logger.info("AgriVision Pro API arrêtée.")


app = FastAPI(
    title="AgriVision Pro - CacaoEngine API",
    description="API exposant le moteur agronomique déterministe CacaoEngine",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Fallback explicite : Netlify prod + localhost dev
# En production Railway, surcharger via la variable ALLOWED_ORIGINS
_DEFAULT_ORIGINS = ",".join([
    "https://genuine-halva-d492f4.netlify.app",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:3000",
])
_raw = os.getenv("ALLOWED_ORIGINS", _DEFAULT_ORIGINS)
allowed_origins = [o.strip() for o in _raw.split(",") if o.strip()]

# Sécurité : refuser le wildcard en production
if "*" in allowed_origins:
    logger.warning("CORS: wildcard '*' détecté — à éviter en production !")

logger.info("CORS origines autorisées : %s", allowed_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Middleware timing ─────────────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    level = logging.WARNING if response.status_code >= 400 else logging.INFO
    logger.log(level, "%s %s → %d  [%s ms]",
                request.method, request.url.path, response.status_code, duration_ms)
    response.headers["X-Process-Time"] = str(duration_ms)
    return response

# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Erreur interne du serveur."})

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(api_router)
