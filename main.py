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
from app.api.dashboard_routes import router as dashboard_router
from app.api.satellite_routes import router as satellite_router
from app.api.lot_routes import router as lot_router
from app.api.purchase_routes import router as purchase_router
from app.api.market_routes import router as market_router
from app.api.veille_routes import router as veille_router
from app.api.twin_routes import router as twin_router
from app.api.weather_routes import router as weather_router
from app.api.certification_routes import router as certification_router
from app.api.plan_routes import router as plan_router
from app.api.assistant_routes import router as assistant_router
from app.api.ai_insights_routes import router as ai_insights_router
from app.api.public_routes import router as public_router
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
                    "ALTER TABLE cooperatives ADD COLUMN IF NOT EXISTS logo_data TEXT"
                ))
                conn.execute(text(
                    "ALTER TABLE cooperatives ADD COLUMN IF NOT EXISTS logo_size VARCHAR DEFAULT 'md' NOT NULL"
                ))
                conn.execute(text(
                    "ALTER TABLE cooperatives ADD COLUMN IF NOT EXISTS logo_plaque BOOLEAN DEFAULT TRUE NOT NULL"
                ))
                conn.execute(text(
                    "ALTER TABLE cooperatives ADD COLUMN IF NOT EXISTS managers JSON"
                ))
                conn.execute(text(
                    "ALTER TABLE cooperatives ADD COLUMN IF NOT EXISTS enforce_social_export_block BOOLEAN DEFAULT FALSE NOT NULL"
                ))
                conn.execute(text(
                    "ALTER TABLE cooperatives ADD COLUMN IF NOT EXISTS living_income_benchmark_cfa DOUBLE PRECISION"
                ))
                conn.execute(text(
                    "ALTER TABLE cooperatives ADD COLUMN IF NOT EXISTS public_report_token VARCHAR"
                ))
                conn.execute(text(
                    "ALTER TABLE complaints ADD COLUMN IF NOT EXISTS cooperative_id INTEGER REFERENCES cooperatives(id)"
                ))
                conn.execute(text(
                    "ALTER TABLE training_sessions ADD COLUMN IF NOT EXISTS feedback_token VARCHAR"
                ))
                conn.execute(text(
                    "ALTER TABLE training_sessions ADD COLUMN IF NOT EXISTS participant_feedback JSON"
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

                # Agroforesterie : age moyen des arbres (utilise dans le calcul carbone)
                conn.execute(text(
                    "ALTER TABLE agroforestry_records ADD COLUMN IF NOT EXISTS avg_age_years DOUBLE PRECISION"
                ))
                conn.commit()
                logger.info("Migration Agroforestry : OK (avg_age_years)")

                # Export : derogation admin (plantations) + infos exportateur (lots)
                for col_ddl in [
                    "ALTER TABLE plantations ADD COLUMN IF NOT EXISTS export_waiver_reason TEXT",
                    "ALTER TABLE plantations ADD COLUMN IF NOT EXISTS export_waiver_by VARCHAR",
                    "ALTER TABLE plantations ADD COLUMN IF NOT EXISTS export_waiver_at TIMESTAMPTZ",
                    "ALTER TABLE lots ADD COLUMN IF NOT EXISTS exporter VARCHAR",
                    "ALTER TABLE lots ADD COLUMN IF NOT EXISTS external_ref VARCHAR",
                ]:
                    conn.execute(text(col_ddl))
                conn.commit()
                logger.info("Migrations export : OK (export_waiver_*, exporter, external_ref)")

                # SSRTE : cycle de vie brouillon -> definitif. DEFAULT 'final' =>
                # les fiches deja saisies (modele "create = fige") restent verrouillees ;
                # les nouvelles fiches partent en 'draft' (defaut applicatif du modele).
                for tbl in ("ssrte_community_profiles", "ssrte_household_profiles", "ssrte_plantation_visits"):
                    conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS status VARCHAR(10) DEFAULT 'final' NOT NULL"))
                    conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS finalized_at TIMESTAMPTZ"))
                    conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS finalized_by VARCHAR(200)"))
                conn.commit()
                logger.info("Migrations SSRTE : OK (status, finalized_at, finalized_by)")

                # Fiche B : situation économique du ménage (B.25, B.26, B.18e, B.29)
                for col_ddl in [
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS housing_type VARCHAR(40)",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS household_assets JSON",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS allow_worker_interview BOOLEAN",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS head_photo_ref VARCHAR(255)",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS head_photo_data TEXT",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS head_photo_consent BOOLEAN DEFAULT FALSE NOT NULL",
                ]:
                    conn.execute(text(col_ddl))
                conn.commit()
                logger.info("Migrations Fiche B eco : OK (housing_type, household_assets, allow_worker_interview, head_photo_ref/data/consent)")

                # Cache du score EUDR par parcelle (P1 — passage à l'échelle 7000+ parcelles)
                for col_ddl in [
                    "ALTER TABLE plantations ADD COLUMN IF NOT EXISTS eudr_score INTEGER",
                    "ALTER TABLE plantations ADD COLUMN IF NOT EXISTS eudr_max_score INTEGER",
                    "ALTER TABLE plantations ADD COLUMN IF NOT EXISTS eudr_status VARCHAR(20)",
                    "ALTER TABLE plantations ADD COLUMN IF NOT EXISTS eudr_color VARCHAR(10)",
                    "ALTER TABLE plantations ADD COLUMN IF NOT EXISTS eudr_has_polygon BOOLEAN",
                    "ALTER TABLE plantations ADD COLUMN IF NOT EXISTS eudr_rules_failed JSON",
                    "ALTER TABLE plantations ADD COLUMN IF NOT EXISTS eudr_computed_at TIMESTAMP",
                ]:
                    conn.execute(text(col_ddl))
                conn.commit()
                logger.info("Migrations EUDR cache : OK (eudr_score/max/status/color/has_polygon/rules_failed/computed_at)")

                # Dissociation social/EUDR (eudr-1.2) : le score passe de 6 à 5 règles.
                # On invalide le cache des parcelles encore évaluées avec 6 règles
                # (eudr_max_score = 6) pour qu'il soit recalculé en 5 règles à la
                # 1re lecture (ensure_scores). Auto-limité : après recalcul max=5,
                # la condition ne matche plus → no-op aux démarrages suivants.
                conn.execute(text(
                    "UPDATE plantations SET eudr_computed_at = NULL WHERE eudr_max_score = 6"
                ))
                conn.commit()
                logger.info("Migration EUDR 1.2 : cache 6-règles invalidé (recalcul lazy en 5 règles)")

                # FarmForce (Livret de suivi) : depenses menage + revenu net disponible
                for col_ddl in [
                    "ALTER TABLE farmforce_assessments ADD COLUMN IF NOT EXISTS household_expense_items JSON",
                    "ALTER TABLE farmforce_assessments ADD COLUMN IF NOT EXISTS total_household_expenses_cfa DOUBLE PRECISION DEFAULT 0 NOT NULL",
                    "ALTER TABLE farmforce_assessments ADD COLUMN IF NOT EXISTS net_income_cfa DOUBLE PRECISION DEFAULT 0 NOT NULL",
                ]:
                    conn.execute(text(col_ddl))
                conn.commit()
                logger.info("Migration FarmForce : OK (household_expense_items, net_income_cfa)")

                # Photo du producteur (identification / carte) — data-URI base64 en
                # TEXT (meme stockage que le logo cooperative) + consentement explicite.
                for col_ddl in [
                    "ALTER TABLE producers ADD COLUMN IF NOT EXISTS photo_data TEXT",
                    "ALTER TABLE producers ADD COLUMN IF NOT EXISTS photo_consent BOOLEAN DEFAULT FALSE NOT NULL",
                ]:
                    conn.execute(text(col_ddl))
                conn.commit()
                logger.info("Migration Producer photo : OK (photo_data, photo_consent)")

                # SSRTE P1 : blocs detailles des fiches A/B/C
                for col_ddl in [
                    "ALTER TABLE ssrte_community_profiles ADD COLUMN IF NOT EXISTS schools JSON",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS farm_info JSON",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS adults_observed JSON",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS workers_present JSON",
                ]:
                    conn.execute(text(col_ddl))
                conn.commit()
                logger.info("Migration SSRTE P1 : OK (schools, farm_info, adults_observed, workers_present)")

                # SSRTE - couverture complete Fiche A : admin, GPS/heures, remarques par section
                for col_ddl in [
                    "ALTER TABLE ssrte_community_profiles ADD COLUMN IF NOT EXISTS supplier VARCHAR(200)",
                    "ALTER TABLE ssrte_community_profiles ADD COLUMN IF NOT EXISTS sub_prefecture VARCHAR(200)",
                    "ALTER TABLE ssrte_community_profiles ADD COLUMN IF NOT EXISTS collection_agent_code VARCHAR(100)",
                    "ALTER TABLE ssrte_community_profiles ADD COLUMN IF NOT EXISTS collection_agent_name VARCHAR(200)",
                    "ALTER TABLE ssrte_community_profiles ADD COLUMN IF NOT EXISTS gps_start VARCHAR(120)",
                    "ALTER TABLE ssrte_community_profiles ADD COLUMN IF NOT EXISTS time_start VARCHAR(20)",
                    "ALTER TABLE ssrte_community_profiles ADD COLUMN IF NOT EXISTS gps_end VARCHAR(120)",
                    "ALTER TABLE ssrte_community_profiles ADD COLUMN IF NOT EXISTS time_end VARCHAR(20)",
                    "ALTER TABLE ssrte_community_profiles ADD COLUMN IF NOT EXISTS section_notes JSON",
                ]:
                    conn.execute(text(col_ddl))
                conn.commit()
                logger.info("Migration SSRTE Fiche A : OK (admin, gps/heures, section_notes)")

                # SSRTE - couverture complete Fiche B : admin, visite, travailleurs
                for col_ddl in [
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS supplier VARCHAR(200)",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS sub_prefecture VARCHAR(200)",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS locality VARCHAR(200)",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS collection_agent_code VARCHAR(100)",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS producer_ssrte_code VARCHAR(100)",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS gps_start VARCHAR(120)",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS time_start VARCHAR(20)",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS time_end VARCHAR(20)",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS survey_type VARCHAR(40)",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS producer_available BOOLEAN",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS unavailable_reason VARCHAR(60)",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS visited_person_status VARCHAR(60)",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS external_workers_count INTEGER",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS daily_workers_count INTEGER",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS non_daily_workers JSON",
                    "ALTER TABLE ssrte_household_profiles ADD COLUMN IF NOT EXISTS section_notes JSON",
                ]:
                    conn.execute(text(col_ddl))
                conn.commit()
                logger.info("Migration SSRTE Fiche B : OK (admin, visite, travailleurs, section_notes)")

                # SSRTE - couverture complete Fiche C : admin, comptages, enfants hors menage
                for col_ddl in [
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS section VARCHAR(100)",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS supplier VARCHAR(200)",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS sub_prefecture VARCHAR(200)",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS locality VARCHAR(200)",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS collection_agent_code VARCHAR(100)",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS producer_ssrte_code VARCHAR(100)",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS time_start VARCHAR(20)",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS time_end VARCHAR(20)",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS adults_count INTEGER",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS daily_workers_count INTEGER",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS allow_worker_interview BOOLEAN",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS children_present_count INTEGER",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS non_household_children_count INTEGER",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS non_household_children JSON",
                    "ALTER TABLE ssrte_plantation_visits ADD COLUMN IF NOT EXISTS section_notes JSON",
                ]:
                    conn.execute(text(col_ddl))
                conn.commit()
                logger.info("Migration SSRTE Fiche C : OK (admin, comptages, enfants hors menage, section_notes)")

                # Tracabilite des lots (#1) : lien recolte -> lot
                # (les tables warehouses/lots/lot_movements sont creees par create_all)
                conn.execute(text(
                    "ALTER TABLE harvests ADD COLUMN IF NOT EXISTS lot_id INTEGER REFERENCES lots(id)"
                ))
                conn.commit()
                logger.info("Migration Tracabilite lots : OK (harvests.lot_id)")

                # Plans d'abonnement (feature-gating) : defaut 'enterprise' = tout active
                conn.execute(text(
                    "ALTER TABLE cooperatives ADD COLUMN IF NOT EXISTS plan VARCHAR DEFAULT 'enterprise' NOT NULL"
                ))
                conn.commit()
                logger.info("Migration Plans : OK (cooperatives.plan)")

                # Lot d'import (annulation d'un import errone) : tag sur producteurs/plantations
                # (la table import_batches est creee par create_all)
                for col_ddl in [
                    "ALTER TABLE producers ADD COLUMN IF NOT EXISTS import_batch_id VARCHAR",
                    "ALTER TABLE plantations ADD COLUMN IF NOT EXISTS import_batch_id VARCHAR",
                ]:
                    conn.execute(text(col_ddl))
                conn.commit()
                logger.info("Migration Import batch : OK (producers/plantations.import_batch_id)")

                # Classification producteur : membre (recolte) vs non-membre (achat)
                conn.execute(text(
                    "ALTER TABLE producers ADD COLUMN IF NOT EXISTS "
                    "type_producteur VARCHAR DEFAULT 'membre' NOT NULL"
                ))
                conn.commit()
                logger.info("Migration Producer : OK (type_producteur)")

            elif engine.dialect.name == "sqlite":
                # SQLite ne supporte pas ADD COLUMN IF NOT EXISTS : on verifie
                # la presence de la colonne via PRAGMA avant de l'ajouter.
                existing = {row[1] for row in conn.execute(text("PRAGMA table_info(producers)"))}
                if "type_producteur" not in existing:
                    conn.execute(text(
                        "ALTER TABLE producers ADD COLUMN "
                        "type_producteur VARCHAR NOT NULL DEFAULT 'membre'"
                    ))
                    conn.commit()
                    logger.info("Migration Producer (sqlite) : OK (type_producteur)")
                coop_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(cooperatives)"))}
                if "living_income_benchmark_cfa" not in coop_cols:
                    conn.execute(text(
                        "ALTER TABLE cooperatives ADD COLUMN living_income_benchmark_cfa FLOAT"
                    ))
                    conn.commit()
                    logger.info("Migration Cooperative (sqlite) : OK (living_income_benchmark_cfa)")
                if "public_report_token" not in coop_cols:
                    conn.execute(text("ALTER TABLE cooperatives ADD COLUMN public_report_token VARCHAR"))
                    conn.commit()
                    logger.info("Migration Cooperative (sqlite) : OK (public_report_token)")
                comp_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(complaints)"))}
                if "cooperative_id" not in comp_cols:
                    conn.execute(text("ALTER TABLE complaints ADD COLUMN cooperative_id INTEGER"))
                    conn.commit()
                    logger.info("Migration Complaint (sqlite) : OK (cooperative_id)")
                ts_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(training_sessions)"))}
                if "feedback_token" not in ts_cols:
                    conn.execute(text("ALTER TABLE training_sessions ADD COLUMN feedback_token VARCHAR"))
                    conn.commit()
                    logger.info("Migration TrainingSession (sqlite) : OK (feedback_token)")
                if "participant_feedback" not in ts_cols:
                    conn.execute(text("ALTER TABLE training_sessions ADD COLUMN participant_feedback JSON"))
                    conn.commit()
                    logger.info("Migration TrainingSession (sqlite) : OK (participant_feedback)")
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
    # ainsi que les domaines prod et leurs sous-domaines (www, etc.) :
    #   - app-agrivision-pro.com  (domaine prod actuel)
    #   - agri-vision-pro.com     (variante historique conservée)
    allow_origin_regex=r"https://([a-z0-9-]+\.)*(netlify\.app|agri-vision-pro\.com|app-agrivision-pro\.com)",
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
app.include_router(dashboard_router)
app.include_router(satellite_router)
app.include_router(lot_router)
app.include_router(purchase_router)
app.include_router(market_router)
app.include_router(veille_router)
app.include_router(twin_router)
app.include_router(weather_router)
app.include_router(certification_router)
app.include_router(plan_router)
app.include_router(assistant_router)
app.include_router(ai_insights_router)
app.include_router(public_router)
