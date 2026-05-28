import os
import time
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.api.assignment_routes import router as assignment_router, sub_router as substitution_router
from app.api.audit_trail_routes import router as audit_trail_router
from app.api.cacaoguard_routes import router as cacaoguard_router
from app.api.cacaoguard_ops_routes import router as cacaoguard_ops_router
from app.api.complaint_routes import router as complaint_router
from app.api.eudr_routes import router as eudr_router
from app.api.farmforce_routes import router as farmforce_router
from app.api.import_routes import router as import_router
from app.api.notification_routes import router as notification_router
from app.api.producer_routes import router as producer_router
from app.api.remediation_routes import router as remediation_router
from app.api.social_routes import router as social_router
from app.api.ssrte_routes import router as ssrte_router
from app.api.sync_routes import router as sync_router
from app.auth.auth_routes import router as auth_router
from app.db.database import engine, Base
from app.db import models  # noqa: F401
from app.db import models_social  # noqa: F401

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

    # ── Migrations idempotentes (colonnes ajoutées post-déploiement initial) ──
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            if engine.dialect.name == "postgresql":
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE NOT NULL"
                ))
                conn.execute(text(
                    "ALTER TABLE cooperatives ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE NOT NULL"
                ))
                conn.execute(text(
                    "ALTER TABLE plantations ADD COLUMN IF NOT EXISTS plant_count INTEGER"
                ))
                # Sprint #0 - Phase 0.1.a-1 : entite Producer
                conn.execute(text(
                    "ALTER TABLE plantations ADD COLUMN IF NOT EXISTS producer_id INTEGER REFERENCES producers(id)"
                ))
                conn.commit()
                logger.info("Migrations colonnes : OK (is_active, plant_count, producer_id)")

                # Sprint #0 - Phase 0.1.a-1 : migration de donnees owner_name -> Producer
                # Pour chaque plantation ayant un owner_name mais pas de producer_id,
                # creer un Producer et lier la plantation.
                migrated = conn.execute(text("""
                    WITH new_producers AS (
                        INSERT INTO producers (nom_complet, cooperative_id, is_active)
                        SELECT DISTINCT p.owner_name, p.cooperative_id, TRUE
                        FROM plantations p
                        WHERE p.owner_name IS NOT NULL
                          AND p.owner_name <> ''
                          AND p.producer_id IS NULL
                          AND NOT EXISTS (
                              SELECT 1 FROM producers pr
                              WHERE pr.nom_complet = p.owner_name
                                AND (pr.cooperative_id = p.cooperative_id
                                     OR (pr.cooperative_id IS NULL AND p.cooperative_id IS NULL))
                          )
                        RETURNING id, nom_complet, cooperative_id
                    )
                    SELECT COUNT(*) FROM new_producers
                """))
                n_created = migrated.scalar() or 0

                linked = conn.execute(text("""
                    UPDATE plantations p
                    SET producer_id = pr.id
                    FROM producers pr
                    WHERE p.producer_id IS NULL
                      AND p.owner_name IS NOT NULL
                      AND p.owner_name <> ''
                      AND pr.nom_complet = p.owner_name
                      AND (pr.cooperative_id = p.cooperative_id
                           OR (pr.cooperative_id IS NULL AND p.cooperative_id IS NULL))
                """))
                conn.commit()
                logger.info(
                    "Migration donnees Producer : %d producteurs crees, %d plantations liees",
                    n_created, linked.rowcount
                )

                # Sprint #0 - Phase 0.1.a-2 : seed des certifications de base
                # FT et RA sont seedees d'office (cooperative YEYASSO les utilise).
                conn.execute(text("""
                    INSERT INTO certifications (code, nom_complet, organisme, actif)
                    VALUES
                        ('FT', 'Fairtrade', 'FLOCERT', TRUE),
                        ('RA', 'Rainforest Alliance', 'Rainforest Alliance', TRUE),
                        ('EUDR', 'EU Deforestation Regulation', 'Union Europeenne', TRUE),
                        ('ARS_1000', 'ARS 1000 - Cacao durable', 'Conseil Cafe-Cacao', TRUE)
                    ON CONFLICT (code) DO NOTHING
                """))
                conn.commit()
                logger.info("Seed certifications : OK (FT, RA, EUDR, ARS_1000)")

                # Sprint #0 - Phase 0.1.a-4 : colonnes commerciales sur harvests
                for col_ddl in [
                    "ALTER TABLE harvests ADD COLUMN IF NOT EXISTS certification_id INTEGER REFERENCES certifications(id)",
                    "ALTER TABLE harvests ADD COLUMN IF NOT EXISTS campagne_id INTEGER REFERENCES campagnes(id)",
                    "ALTER TABLE harvests ADD COLUMN IF NOT EXISTS numero_recu_achat VARCHAR",
                    "ALTER TABLE harvests ADD COLUMN IF NOT EXISTS nbre_sacs INTEGER",
                    "ALTER TABLE harvests ADD COLUMN IF NOT EXISTS is_conventional BOOLEAN DEFAULT FALSE NOT NULL",
                ]:
                    conn.execute(text(col_ddl))
                conn.commit()
                logger.info("Migrations Harvest : OK (certification_id, campagne_id, recu, sacs, conventional)")
    except Exception as e:
        logger.warning("Migration colonnes (ignorée si déjà présente) : %s", e)
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
_raw = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5500,http://127.0.0.1:5500,"
    "http://localhost:5510,http://127.0.0.1:5510,"
    "http://localhost:5520,http://127.0.0.1:5520",
)
allowed_origins = [o.strip() for o in _raw.split(",") if o.strip()]
for local_origin in (
    "http://localhost:5510",
    "http://127.0.0.1:5510",
    "http://localhost:5520",
    "http://127.0.0.1:5520",
):
    if local_origin not in allowed_origins:
        allowed_origins.append(local_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    # Autorise tous les previews/deploiements Netlify (staging, deploy previews)
    # ainsi que le domaine prod agri-vision-pro.com et ses sous-domaines.
    allow_origin_regex=r"https://([a-z0-9-]+\.)*(netlify\.app|agri-vision-pro\.com)",
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
app.include_router(assignment_router)
app.include_router(substitution_router)
app.include_router(import_router)
app.include_router(producer_router)
app.include_router(farmforce_router)
app.include_router(social_router)
app.include_router(cacaoguard_router)
app.include_router(cacaoguard_ops_router)
app.include_router(complaint_router)
app.include_router(remediation_router)
app.include_router(audit_trail_router)
app.include_router(notification_router)
app.include_router(sync_router)
app.include_router(eudr_router)
app.include_router(ssrte_router)
