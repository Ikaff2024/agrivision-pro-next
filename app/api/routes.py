import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from io import BytesIO
from urllib.parse import quote
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.cacao_engine.engine import run_engine
from app.cacao_engine.inputs import CacaoInputs
from app.cacao_engine.outputs import EngineReport
from app.db.database import get_db
from app.db.models import Diagnostic, Plantation, Producer, User, Harvest
from app.auth.auth_service import get_current_user
from app.ml.image_diagnosis import analyze_leaf_image
from app.satellite.ndvi_service import get_ndvi
from app.recommendations import build_recommendations
from app.services.reports import (
    build_plantation_context,
    generate_plantation_pdf,
    report_filename,
    coop_brand,
    generate_agroforestry_pdf,
    agroforestry_report_filename,
)

router = APIRouter()


class PlantationCreate(BaseModel):
    name: str
    owner_name: str
    country: str
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    hectares: Optional[float] = Field(
        None,
        gt=0.25,
        le=500,
        description="Superficie en hectares (entre 0.25 et 500). "
                    "Le seuil minimum exclut les zones non agricoles "
                    "(toits, cours, jardins) ; le maximum exclut les saisies absurdes.",
    )
    plant_count: Optional[int] = None


class PlantationUpdate(BaseModel):
    """Mise a jour partielle d'une plantation. Tous les champs sont optionnels :
    seuls les champs explicitement fournis sont modifies (model_dump(exclude_unset))."""
    name: Optional[str] = None
    owner_name: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    hectares: Optional[float] = Field(None, gt=0.25, le=500)
    plant_count: Optional[int] = None


# ─── Health ──────────────────────────────────────────────────────────────────


# ─── Helper NDVI : interprétation pour garde-fous Anti-Détracteur ────────────
def _interpret_ndvi(ndvi: float) -> dict:
    """
    Interprète un NDVI brut (0.0 - 1.0) en fournissant :
      - status : code interne ("CRITICAL_LOW" | "STRESSED" | "MODERATE" | "HEALTHY")
      - label : libelle utilisateur FR
      - confidence : "low" | "high" — si low, l'app doit afficher un avertissement
                     pédagogique et NE PAS donner de recommandation agricole.
      - message : message pedagogique pour l'utilisateur (None si confidence="high")

    Seuils calibrés pour la cacaoculture :
      - ≤ 0.35 : couvert végétal insignifiant ou très dégradé
                 → confidence LOW, message pédagogique obligatoire
      - 0.35-0.50 : végétation faible/clairsemée → confidence HIGH, statut "Stressee"
      - 0.50-0.70 : végétation moyenne à dense → "Moderee"
      - > 0.70 : couvert dense → "Saine"
    """
    if ndvi <= 0.35:
        return {
            "status": "CRITICAL_LOW",
            "label": "Indéterminée",
            "confidence": "low",
            "message": (
                "Le satellite Sentinel-2 mesure un indice de végétation très faible "
                f"(NDVI = {ndvi:.2f}), correspondant habituellement à un sol nu, "
                "une zone urbaine, ou un couvert végétal sévèrement dégradé. "
                "Vérifiez que les coordonnées GPS correspondent bien à votre plantation. "
                "Aucune recommandation agricole automatique n'est générée tant que "
                "la zone n'est pas confirmée végétalisée."
            ),
        }
    if ndvi <= 0.50:
        return {"status": "STRESSED", "label": "Stressée", "confidence": "high", "message": None}
    if ndvi <= 0.70:
        return {"status": "MODERATE", "label": "Modérée", "confidence": "high", "message": None}
    return {"status": "HEALTHY", "label": "Saine", "confidence": "high", "message": None}


@router.get("/health")
def health_check():
    """Sante de l'API + diagnostic de persistance de la base.

    `database` indique le moteur reel (postgresql = persistant, sqlite =
    ephemere sur Railway, efface a chaque redeploiement). `persistent` resume
    si la configuration garantit la conservation des donnees.
    """
    from app.db.database import engine
    dialect = engine.dialect.name
    return {
        "status": "ok",
        "database": dialect,
        "database_url_configured": bool(os.getenv("DATABASE_URL")),
        "persistent": dialect == "postgresql",
    }


# ─── Plantations ─────────────────────────────────────────────────────────────

def _find_or_create_producer(db: Session, owner_name: Optional[str], cooperative_id: int):
    """Trouve (ou crée) le Producteur correspondant au propriétaire d'une
    plantation dans la coopérative donnée. Retourne le Producer ou None si
    owner_name est vide.

    Sans ce rattachement, le producteur n'existe que comme texte (owner_name)
    et n'apparaît pas dans les listes Producteurs (Protection enfant, EUDR,
    CacaoGuard).
    """
    owner = (owner_name or "").strip()
    if not owner:
        return None
    producer = (
        db.query(Producer)
        .filter(
            Producer.nom_complet == owner,
            Producer.cooperative_id == cooperative_id,
            Producer.is_active == True,
        )
        .first()
    )
    if not producer:
        producer = Producer(
            nom_complet=owner,
            cooperative_id=cooperative_id,
            is_active=True,
        )
        db.add(producer)
        db.flush()  # obtenir producer.id avant de lier la plantation
    return producer


@router.post("/plantations")
def create_plantation(
    plantation: PlantationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("admin", "gestionnaire"):
        raise HTTPException(status_code=403, detail="Droits administrateur ou gestionnaire requis.")

    if not current_user.cooperative_id:
        raise HTTPException(
            status_code=400,
            detail="Votre compte n'est associé à aucune coopérative.",
        )

    producer = _find_or_create_producer(db, plantation.owner_name, current_user.cooperative_id)

    new_plantation = Plantation(
        name=plantation.name,
        owner_name=plantation.owner_name,
        country=plantation.country,
        region=plantation.region,
        latitude=plantation.latitude,
        longitude=plantation.longitude,
        hectares=plantation.hectares,
        plant_count=plantation.plant_count,
        cooperative_id=current_user.cooperative_id,  # toujours rattachée
        producer_id=producer.id if producer else None,
    )
    db.add(new_plantation)
    db.commit()
    db.refresh(new_plantation)
    return new_plantation


@router.put("/plantations/{plantation_id}")
def update_plantation(
    plantation_id: int,
    data: PlantationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Met a jour les champs d'une plantation (admin, dans sa cooperative).

    Mise a jour partielle : seuls les champs fournis sont modifies. Si le
    proprietaire (owner_name) change, le rattachement Producteur est recalcule
    (trouver-ou-creer) pour rester coherent avec EUDR / Protection enfant.
    """
    if current_user.role not in ("admin", "gestionnaire"):
        raise HTTPException(status_code=403, detail="Droits administrateur ou gestionnaire requis.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    fields = data.model_dump(exclude_unset=True)

    # Re-lier le producteur si le proprietaire change.
    if "owner_name" in fields:
        plantation.owner_name = fields.pop("owner_name")
        producer = _find_or_create_producer(db, plantation.owner_name, current_user.cooperative_id)
        plantation.producer_id = producer.id if producer else None

    for key, value in fields.items():
        setattr(plantation, key, value)

    db.commit()
    db.refresh(plantation)
    return plantation


def visible_plantation_ids(user, db):
    """
    Calcule l'ensemble des ids de plantations visibles par un technicien :
    ses parcelles attribuees + les parcelles des techniciens qu'il remplace
    actuellement (remplacement actif et dans sa periode).

    Retourne une liste d'ids. Utilisee pour le cloisonnement par role.
    Pour un admin, cette fonction n'a pas a etre appelee (admin voit tout).
    """
    from datetime import datetime
    from app.db.models import PlantationAssignment, TechnicianSubstitution

    technician_ids = {user.id}

    # Techniciens que cet utilisateur remplace actuellement
    now = datetime.utcnow()
    subs = db.query(TechnicianSubstitution).filter(
        TechnicianSubstitution.substitute_technician_id == user.id,
        TechnicianSubstitution.is_active == True,
    ).all()
    for s in subs:
        if s.date_debut <= now <= s.date_fin:
            technician_ids.add(s.absent_technician_id)

    # Plantations attribuees a l'un de ces techniciens
    assignments = db.query(PlantationAssignment).filter(
        PlantationAssignment.technician_id.in_(list(technician_ids)),
        PlantationAssignment.is_active == True,
    ).all()
    return [a.plantation_id for a in assignments]

@router.get("/plantations")
def get_plantations(
    skip: int = 0,
    limit: int = Query(1000, ge=1, le=5000),
    search: Optional[str] = Query(None, description="Recherche nom producteur ou code plantation"),
    technician_id: Optional[int] = Query(None, description="Filtre par technicien assigne"),
    assigned_to_me: bool = Query(False, description="Technicien: filtre sur mes plantations attribuees"),
    producer_id: Optional[int] = Query(None, description="Filtre par producteur"),
    section: Optional[str] = Query(None, description="Filtre par section"),
    certification: Optional[str] = Query(None, description="Filtre par code certification"),
    diagnostic: Optional[str] = Query(None, description="diagnosed | not_diagnosed"),
    risk: Optional[str] = Query(None, description="Filtre par niveau de risque du dernier diagnostic : LOW|MEDIUM|HIGH"),
    page: Optional[int] = Query(None, ge=1, description="Numero de page (mode pagine)"),
    page_size: int = Query(100, ge=1, le=5000, description="Taille de page"),
    paginated: bool = Query(False, description="Si true, renvoie un objet pagine"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Liste des plantations de la cooperative, avec filtres et pagination.

    Retro-compatible : sans 'paginated', renvoie une liste brute comme avant.
    Avec 'paginated=true', renvoie {items, total, page, page_size, total_pages}.
    """
    from app.db.models import (
        Producer, PlantationCertification, Certification, Diagnostic,
    )

    q = db.query(Plantation).filter(
        Plantation.cooperative_id == current_user.cooperative_id
    )

    # --- Cloisonnement par role (Sprint #1 phase 1.4) ---
    # Un technicien ne voit que ses parcelles attribuees + remplacements.
    # admin et agronomist : comportement inchange (voient tout).
    if getattr(current_user, "role", None) == "technician":
        visible_ids = visible_plantation_ids(current_user, db)
        q = q.filter(Plantation.id.in_(visible_ids or [-1]))

    # Filtre explicite "mes plantations" pour les profils techniciens.
    # Pour admin/agronomist, le filtre est ignore afin de conserver leur vue cooperative.
    if assigned_to_me and getattr(current_user, "role", None) == "technician":
        assigned_ids = visible_plantation_ids(current_user, db)
        q = q.filter(Plantation.id.in_(assigned_ids or [-1]))

    if producer_id is not None:
        q = q.filter(Plantation.producer_id == producer_id)

    # --- Filtre recherche : code plantation (name) ou nom producteur ---
    if search and isinstance(search, str) and search.strip():
        like = f"%{search.strip()}%"
        q = q.outerjoin(Producer, Plantation.producer_id == Producer.id).filter(
            (Plantation.name.ilike(like)) |
            (Plantation.owner_name.ilike(like)) |
            (Producer.nom_complet.ilike(like)) |
            (Producer.code_yeyasso.ilike(like))
        )

    # --- Filtre par technicien assigne ---
    if technician_id is not None and isinstance(technician_id, int):
        from app.db.models import PlantationAssignment
        assigned_ids = [
            a.plantation_id for a in db.query(PlantationAssignment).filter(
                PlantationAssignment.technician_id == technician_id,
                PlantationAssignment.is_active == True,
            ).all()
        ]
        q = q.filter(Plantation.id.in_(assigned_ids or [-1]))

    # --- Filtre par section (via le producteur) ---
    if section and isinstance(section, str) and section.strip():
        prod_ids = [
            p.id for p in db.query(Producer).filter(
                Producer.cooperative_id == current_user.cooperative_id,
                Producer.section == section,
            ).all()
        ]
        q = q.filter(Plantation.producer_id.in_(prod_ids or [-1]))

    # --- Filtre par certification ---
    if certification and isinstance(certification, str) and certification.strip():
        cert = db.query(Certification).filter(
            Certification.code == certification.strip().upper()
        ).first()
        if cert:
            cert_plant_ids = [
                pc.plantation_id for pc in db.query(PlantationCertification).filter(
                    PlantationCertification.certification_id == cert.id
                ).all()
            ]
            q = q.filter(Plantation.id.in_(cert_plant_ids or [-1]))
        else:
            q = q.filter(Plantation.id.in_([-1]))

    # --- Filtre par etat de diagnostic ---
    if diagnostic in ("diagnosed", "not_diagnosed"):
        diagnosed_ids = [
            d.plantation_id for d in db.query(Diagnostic.plantation_id).distinct().all()
        ]
        if diagnostic == "diagnosed":
            q = q.filter(Plantation.id.in_(diagnosed_ids or [-1]))
        else:
            if diagnosed_ids:
                q = q.filter(~Plantation.id.in_(diagnosed_ids))

    # --- Filtre par niveau de risque (dernier diagnostic) — P2 scale ---
    if risk and isinstance(risk, str) and risk.strip():
        from sqlalchemy import func as _f
        latest_diag = (
            db.query(Diagnostic.plantation_id, _f.max(Diagnostic.created_at).label("mc"))
            .group_by(Diagnostic.plantation_id).subquery()
        )
        risk_ids = [
            row[0] for row in db.query(Diagnostic.plantation_id)
            .join(latest_diag, (Diagnostic.plantation_id == latest_diag.c.plantation_id)
                  & (Diagnostic.created_at == latest_diag.c.mc))
            .filter(_f.upper(Diagnostic.global_risk_level) == risk.strip().upper())
            .all()
        ]
        q = q.filter(Plantation.id.in_(risk_ids or [-1]))

    # --- Mode pagine ou liste brute ---
    if paginated or page is not None:
        current_page = page or 1
        total = q.count()
        items = (
            q.order_by(Plantation.id)
            .offset((current_page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        # Enrichissement de la page (P2 scale) : score EUDR (cache) + dernier diagnostic.
        # Fait UNIQUEMENT sur la page (≤ page_size lignes) → reste rapide à 7000 parcelles.
        from app.eudr.score_cache import ensure_scores
        ensure_scores(items, db)
        page_ids = [p.id for p in items]
        diag_map = {}
        if page_ids:
            for pid, gscore, grisk in (
                db.query(Diagnostic.plantation_id, Diagnostic.global_score, Diagnostic.global_risk_level)
                .filter(Diagnostic.plantation_id.in_(page_ids))
                .order_by(Diagnostic.plantation_id, Diagnostic.created_at.desc())
                .all()
            ):
                if pid not in diag_map:  # 1re occurrence = diagnostic le plus récent (tri desc)
                    diag_map[pid] = (gscore, grisk)
        enriched = []
        for p in items:
            gscore, grisk = diag_map.get(p.id, (None, None))
            enriched.append({
                "id": p.id, "name": p.name, "owner_name": p.owner_name,
                "region": p.region, "country": p.country, "hectares": p.hectares,
                "latitude": p.latitude, "longitude": p.longitude,
                "producer_id": p.producer_id,
                "score": float(gscore) if gscore is not None else None,
                "risk_level": grisk,
                "eudr_status": p.eudr_status,
                "eudr_score": p.eudr_score,
                "eudr_max": p.eudr_max_score,
                "export_waiver": p.export_waiver_at is not None,
            })
        total_pages = (total + page_size - 1) // page_size if page_size else 1
        return {
            "items": enriched,
            "total": total,
            "page": current_page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    # --- Mode liste brute (retro-compatible) ---
    return q.order_by(Plantation.id).offset(skip).limit(limit).all()


@router.get("/plantations/filters-options")
def get_plantations_filters_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Renvoie les valeurs disponibles pour alimenter les menus de filtres
    de la liste des plantations : sections et techniciens de la cooperative.
    """
    from app.db.models import Certification, Plantation, PlantationCertification, Producer

    coop_id = current_user.cooperative_id

    # Sections distinctes
    sections = sorted({
        p.section for p in db.query(Producer.section).filter(
            Producer.cooperative_id == coop_id,
            Producer.section.isnot(None),
        ).distinct().all()
        if p.section
    })

    # Techniciens de la cooperative
    technicians = [
        {"id": u.id, "email": u.email}
        for u in db.query(User).filter(
            User.cooperative_id == coop_id,
            User.role == "technician",
        ).all()
    ]

    # Certifications réellement présentes sur les plantations de la coopérative
    # (au lieu d'une liste figée) → le filtre ne propose que des choix utiles.
    cert_codes = sorted({
        row[0] for row in db.query(Certification.code)
        .join(PlantationCertification, PlantationCertification.certification_id == Certification.id)
        .join(Plantation, Plantation.id == PlantationCertification.plantation_id)
        .filter(Plantation.cooperative_id == coop_id)
        .distinct().all()
        if row[0]
    })

    return {
        "sections": sections,
        "technicians": technicians,
        "certifications": cert_codes,
    }


@router.get("/plantations/{plantation_id}")
def get_plantation(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    diagnostics = (
        db.query(Diagnostic)
        .filter(Diagnostic.plantation_id == plantation_id)
        .all()
    )
    return {"plantation": plantation, "diagnostics": diagnostics}



@router.delete("/plantations/{plantation_id}")
def delete_plantation(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprime une plantation et ses diagnostics associés. Admin uniquement."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    # Supprimer les diagnostics associés d'abord
    db.query(Diagnostic).filter(Diagnostic.plantation_id == plantation_id).delete()
    db.delete(plantation)
    db.commit()

    return {"message": f"Plantation '{plantation.name}' supprimée avec succès."}

# ─── Diagnostic agronomique ───────────────────────────────────────────────────

@router.post("/cacao/diagnostic", response_model=None)
def diagnostic_endpoint(
    plantation_id: int,
    inputs: CacaoInputs,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(status_code=403, detail="Rôle agronome requis.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    # ── Couche 2 Agroforesterie : substituer l'ombrage si inventaire disponible ──
    agro_records = db.query(AgroforestryRecord).filter(
        AgroforestryRecord.plantation_id == plantation_id
    ).all()
    if agro_records:
        SHADE_FACTORS = {
            "Gliricidia sepium": 0.8,  "Leucaena leucocephala": 0.7,
            "Erythrina spp.": 0.9,     "Albizzia adianthifolia": 1.0,
            "Musa spp.": 0.4,          "Persea americana": 0.8,
            "Mangifera indica": 1.0,   "Citrus sinensis": 0.6,
            "Dacryodes edulis": 0.75,  "Cola nitida": 0.7,
            "Carica papaya": 0.3,      "Milicia excelsa": 1.0,
            "Terminalia superba": 1.0, "Ceiba pentandra": 1.0,
            "Khaya senegalensis": 1.0, "Elaeis guineensis": 0.85,
            "Cocos nucifera": 0.8,     "Tectona grandis": 0.9,
        }
        shade_sum = sum(
            (r.count_per_hectare or 0) * SHADE_FACTORS.get(r.species_name, 0.6)
            for r in agro_records
        )
        computed_shade = min(100.0, round(shade_sum / 40 * 100, 1))
        inputs = CacaoInputs(
            country=inputs.country,
            region=inputs.region,
            humidity_pct=inputs.humidity_pct,
            rainfall_mm_month=inputs.rainfall_mm_month,
            avg_temp_c=inputs.avg_temp_c,
            plantation_age_years=inputs.plantation_age_years,
            shade_tree_density_pct=computed_shade,
        )

    report: EngineReport = run_engine(inputs)

    new_diagnostic = Diagnostic(
        plantation_id=plantation_id,
        country=inputs.country,
        region=inputs.region,
        humidity_pct=inputs.humidity_pct,
        rainfall_mm_month=inputs.rainfall_mm_month,
        avg_temp_c=inputs.avg_temp_c,
        plantation_age_years=inputs.plantation_age_years,
        shade_tree_density_pct=inputs.shade_tree_density_pct,
        global_score=report.global_score,
        global_risk_level=report.global_risk_level,
    )
    db.add(new_diagnostic)
    db.commit()
    db.refresh(new_diagnostic)
    # Générer les recommandations actionnables
    rec_list = build_recommendations(
        module_results=[
            {"module_name": m.module_name, "score": m.score, "reasons": m.reasons}
            for m in report.module_results
        ],
        inputs={
            "humidity_pct":           inputs.humidity_pct,
            "rainfall_mm_month":      inputs.rainfall_mm_month,
            "avg_temp_c":             inputs.avg_temp_c,
            "shade_tree_density_pct": inputs.shade_tree_density_pct,
            "plantation_age_years":   inputs.plantation_age_years,
        },
        global_score=report.global_score,
        global_risk=report.global_risk_level,
    )

    return {
        "global_score":      report.global_score,
        "global_risk_level": report.global_risk_level,
        "module_results":    [
            {"module_name": m.module_name, "score": m.score,
             "risk_level": m.risk_level, "reasons": m.reasons}
            for m in report.module_results
        ],
        "recommendations":   rec_list,
        "diagnostic_id":     new_diagnostic.id,
    }



@router.get("/diagnostics/{diagnostic_id}/recommendations")
def get_diagnostic_recommendations(
    diagnostic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retourne les recommandations actionnables pour un diagnostic existant."""
    diag = db.query(Diagnostic).filter(
        Diagnostic.id == diagnostic_id,
    ).first()
    if not diag:
        raise HTTPException(status_code=404, detail="Diagnostic introuvable.")

    # Recalculer les recs depuis les données stockées
    rec_list = build_recommendations(
        module_results=[],  # pas de module_results en DB, on utilise les inputs
        inputs={
            "humidity_pct":           diag.humidity_pct,
            "rainfall_mm_month":      diag.rainfall_mm_month,
            "avg_temp_c":             diag.avg_temp_c,
            "shade_tree_density_pct": None,
            "plantation_age_years":   None,
        },
        global_score=diag.global_score,
        global_risk=diag.global_risk_level,
    )
    return rec_list

# ─── Historique diagnostics ───────────────────────────────────────────────────

@router.get("/diagnostics")
def get_diagnostics(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Diagnostic)
        .join(Plantation)
        .filter(Plantation.cooperative_id == current_user.cooperative_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/diagnostics/{diagnostic_id}")
def get_diagnostic(
    diagnostic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    diag = (
        db.query(Diagnostic)
        .join(Plantation)
        .filter(
            Diagnostic.id == diagnostic_id,
            Plantation.cooperative_id == current_user.cooperative_id,
        )
        .first()
    )
    if not diag:
        raise HTTPException(status_code=404, detail="Diagnostic introuvable.")
    return diag


@router.get("/plantations/{plantation_id}/history")
def get_plantation_history(
    plantation_id: int,
    limit: Optional[int] = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    query = (
        db.query(Diagnostic)
        .filter(Diagnostic.plantation_id == plantation_id)
        .order_by(Diagnostic.created_at.desc())
    )
    if limit:
        query = query.limit(limit)

    return [
        {
            "date": d.created_at.strftime("%Y-%m-%d") if d.created_at else None,
            "score": d.global_score,
            "risk_level": d.global_risk_level,
        }
        for d in query.all()
    ]


# ─── Carte ────────────────────────────────────────────────────────────────────

def _latest_diag_by_plantation(plantation_ids: list, db: Session) -> dict:
    """
    Retourne le dernier diagnostic de chaque plantation en UNE SEULE requête.
    Évite le problème N+1 (1 requête par plantation en boucle).
    """
    if not plantation_ids:
        return {}
    # Sous-requête : date max du dernier diagnostic par plantation
    subq = (
        db.query(
            Diagnostic.plantation_id,
            func.max(Diagnostic.created_at).label("max_at"),
        )
        .filter(Diagnostic.plantation_id.in_(plantation_ids))
        .group_by(Diagnostic.plantation_id)
        .subquery()
    )
    # Jointure pour récupérer les lignes complètes
    latest_diags = (
        db.query(Diagnostic)
        .join(
            subq,
            (Diagnostic.plantation_id == subq.c.plantation_id)
            & (Diagnostic.created_at == subq.c.max_at),
        )
        .all()
    )
    return {d.plantation_id: d for d in latest_diags}


@router.get("/map/plantations")
def get_map_plantations(
    risk_level: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plantations = (
        db.query(Plantation)
        .filter(Plantation.cooperative_id == current_user.cooperative_id)
        .all()
    )
    latest_map = _latest_diag_by_plantation([p.id for p in plantations], db)
    results = []
    for p in plantations:
        latest = latest_map.get(p.id)
        if not latest:
            continue
        if risk_level and latest.global_risk_level != risk_level:
            continue
        results.append({
            "id": p.id,
            "name": p.name,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "risk_level": latest.global_risk_level,
            "score": latest.global_score,
        })
    return results


@router.get("/map/stats")
def get_map_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plantations = (
        db.query(Plantation)
        .filter(Plantation.cooperative_id == current_user.cooperative_id)
        .all()
    )
    latest_map = _latest_diag_by_plantation([p.id for p in plantations], db)
    high = medium = low = 0
    for p in plantations:
        latest = latest_map.get(p.id)
        if latest:
            if latest.global_risk_level == "HIGH":
                high += 1
            elif latest.global_risk_level == "MEDIUM":
                medium += 1
            elif latest.global_risk_level == "LOW":
                low += 1

    return {
        "total_plantations": len(plantations),
        "high_risk_plantations": high,
        "medium_risk_plantations": medium,
        "low_risk_plantations": low,
    }


# ─── Image / ML ──────────────────────────────────────────────────────────────

@router.post("/diagnostic/image")
async def diagnostic_image(
    file: UploadFile = File(...),
    plantation_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"admin", "technician"}:
        raise HTTPException(status_code=403, detail="Rôle technicien requis.")

    # Vérifier la plantation avant de traiter l'image
    if plantation_id is not None:
        plantation = db.query(Plantation).filter(
            Plantation.id == plantation_id,
            Plantation.cooperative_id == current_user.cooperative_id,
        ).first()
        if not plantation:
            raise HTTPException(status_code=404, detail="Plantation introuvable.")

    # Lecture en mémoire — pas d'écriture disque (filesystem éphémère sur Railway)
    contents = await file.read()

    # Exécution du module ML (stub pour l'instant)
    # NOTE : le stub ignore le contenu — on lui passe le nom de fichier pour
    # compatibilité avec la signature existante de analyze_leaf_image.
    import tempfile
    with tempfile.NamedTemporaryFile(delete=True, suffix=".jpg") as tmp:
        tmp.write(contents)
        tmp.flush()
        diagnosis_result = analyze_leaf_image(tmp.name)

    # On ne persiste PAS les diagnostics image en DB :
    # ils n'ont pas de données climatiques réelles (humidity, rainfall, temp)
    # et corrupraient les statistiques agronomiques du dashboard.
    # Quand le vrai modèle ML sera intégré, un type de diagnostic dédié sera créé.

    return diagnosis_result


# ─── Satellite NDVI ───────────────────────────────────────────────────────────

@router.get("/satellite/ndvi")
def get_ndvi_endpoint(
    latitude: float,
    longitude: float,
    current_user: User = Depends(get_current_user),
):
    ndvi_result = get_ndvi(latitude, longitude)
    interpretation = _interpret_ndvi(ndvi_result["ndvi"])
    return {
        "ndvi": ndvi_result["ndvi"],
        "vegetation_status": ndvi_result["vegetation_status"],
        # Garde-fou Anti-Détracteur (Sprint R1d)
        "ndvi_label": interpretation["label"],
        "confidence": interpretation["confidence"],
        "warning_message": interpretation["message"],
    }


@router.get("/plantations/{plantation_id}/satellite")
def get_plantation_satellite_analysis(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    if plantation.latitude is None or plantation.longitude is None:
        raise HTTPException(
            status_code=400,
            detail="Coordonnées GPS manquantes pour cette plantation.",
        )

    ndvi_result = get_ndvi(plantation.latitude, plantation.longitude)
    interpretation = _interpret_ndvi(ndvi_result["ndvi"])
    return {
        "plantation_id": plantation.id,
        "ndvi": ndvi_result["ndvi"],
        "vegetation_status": ndvi_result["vegetation_status"],
        # Garde-fou Anti-Détracteur (Sprint R1d)
        "ndvi_label": interpretation["label"],
        "confidence": interpretation["confidence"],
        "warning_message": interpretation["message"],
    }


# ─── Admin — Gestion des membres ─────────────────────────────────────────────

class UpdateRoleRequest(BaseModel):
    role: str  # "admin" | "agronomist" | "technician"

VALID_ROLES = {"admin", "agronomist", "technician", "gestionnaire"}


@router.get("/admin/members")
def get_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste tous les membres de la coopérative. Admin uniquement."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    members = (
        db.query(User)
        .filter(User.cooperative_id == current_user.cooperative_id)
        .order_by(User.created_at.asc())
        .all()
    )
    return [
        {
            "id": m.id,
            "email": m.email,
            "role": m.role,
            "is_active": m.is_active,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "is_current_user": m.id == current_user.id,
        }
        for m in members
    ]


@router.put("/admin/members/{user_id}/role")
def update_member_role(
    user_id: int,
    req: UpdateRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change le rôle d'un membre. Admin uniquement. Un admin ne peut pas dégrader son propre rôle."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Rôle invalide : {req.role}.")

    # Empêcher l'admin de se dégrader lui-même (évite de perdre le dernier admin)
    if user_id == current_user.id and req.role != "admin":
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez pas modifier votre propre rôle.",
        )

    member = db.query(User).filter(
        User.id == user_id,
        User.cooperative_id == current_user.cooperative_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable.")

    member.role = req.role
    db.commit()
    db.refresh(member)
    return {"id": member.id, "email": member.email, "role": member.role}


@router.delete("/admin/members/{user_id}")
def remove_member(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprime un membre de la coopérative. Admin uniquement. Ne peut pas se supprimer soi-même."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    if user_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez pas supprimer votre propre compte.",
        )

    member = db.query(User).filter(
        User.id == user_id,
        User.cooperative_id == current_user.cooperative_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable.")

    db.delete(member)
    db.commit()
    return {"message": f"Membre {member.email} supprimé avec succès."}


# ════════════════════════════════════════════════════════════════
# ─── Agroforesterie ──────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════

from app.db.models import AgroforestryRecord, Cooperative, PlantationBoundary
from app.ai_advisor import get_ai_advice

# ── Bibliothèque d'espèces — coefficients agronomiques & carbone ──────────────
# carbon_factor : tCO₂ stockée par arbre par an (allométrie simplifiée FAO/IPCC)
# shade_factor  : contribution à l'ombrage par arbre (arbres/ha → % ombrage)
SPECIES_LIBRARY = [
    # Légumineuses fixatrices d'azote (ombrage rapide)
    {"name":"Gliricidia sepium",    "local":"Gliricidi",    "layer":"intermediate", "carbon_factor":0.012, "shade_factor":0.8,  "category":"Légumineuse"},
    {"name":"Leucaena leucocephala","local":"Leucéna",      "layer":"intermediate", "carbon_factor":0.010, "shade_factor":0.7,  "category":"Légumineuse"},
    {"name":"Erythrina spp.",       "local":"Érythrine",    "layer":"superior",     "carbon_factor":0.018, "shade_factor":0.9,  "category":"Légumineuse"},
    {"name":"Albizzia adianthifolia","local":"Albizzia",    "layer":"superior",     "carbon_factor":0.025, "shade_factor":1.0,  "category":"Légumineuse"},
    # Fruitiers
    {"name":"Musa spp.",            "local":"Bananier",     "layer":"understory",   "carbon_factor":0.004, "shade_factor":0.4,  "category":"Fruitier"},
    {"name":"Persea americana",     "local":"Avocatier",    "layer":"intermediate", "carbon_factor":0.015, "shade_factor":0.8,  "category":"Fruitier"},
    {"name":"Mangifera indica",     "local":"Manguier",     "layer":"superior",     "carbon_factor":0.022, "shade_factor":1.0,  "category":"Fruitier"},
    {"name":"Citrus sinensis",      "local":"Oranger",      "layer":"intermediate", "carbon_factor":0.010, "shade_factor":0.6,  "category":"Fruitier"},
    {"name":"Dacryodes edulis",     "local":"Safoutier",    "layer":"intermediate", "carbon_factor":0.014, "shade_factor":0.75, "category":"Fruitier"},
    {"name":"Cola nitida",          "local":"Colatier",     "layer":"intermediate", "carbon_factor":0.012, "shade_factor":0.7,  "category":"Fruitier"},
    {"name":"Carica papaya",        "local":"Papayer",      "layer":"understory",   "carbon_factor":0.003, "shade_factor":0.3,  "category":"Fruitier"},
    # Timber / bois d'oeuvre
    {"name":"Milicia excelsa",      "local":"Iroko",        "layer":"superior",     "carbon_factor":0.045, "shade_factor":1.0,  "category":"Timber"},
    {"name":"Terminalia superba",   "local":"Fraké",        "layer":"superior",     "carbon_factor":0.038, "shade_factor":1.0,  "category":"Timber"},
    {"name":"Ceiba pentandra",      "local":"Fromager",     "layer":"superior",     "carbon_factor":0.042, "shade_factor":1.0,  "category":"Timber"},
    {"name":"Khaya senegalensis",   "local":"Khaya",        "layer":"superior",     "carbon_factor":0.040, "shade_factor":1.0,  "category":"Timber"},
    # Palmiers / divers
    {"name":"Elaeis guineensis",    "local":"Palmier à huile","layer":"superior",   "carbon_factor":0.020, "shade_factor":0.85, "category":"Divers"},
    {"name":"Cocos nucifera",       "local":"Cocotier",     "layer":"superior",     "carbon_factor":0.018, "shade_factor":0.8,  "category":"Divers"},
    {"name":"Tectona grandis",      "local":"Teck",         "layer":"superior",     "carbon_factor":0.035, "shade_factor":0.9,  "category":"Timber"},
]

def _compute_metrics(records) -> dict:
    """
    Calcule les métriques agroforestières à partir des enregistrements.
    - shade_score      : % d'ombrage estimé (0-100)
    - diversity_score  : score de diversité floristique (0-100)
    - carbon_stock_tco2_ha : stock carbone estimé (tCO₂/ha)
    - conformity_score : score global de conformité agroforestière (0-100)
    """
    if not records:
        return {
            "shade_score": 0, "diversity_score": 0,
            "carbon_stock_tco2_ha": 0.0, "conformity_score": 0,
            "total_trees_per_ha": 0, "species_count": 0
        }

    species_lib = {s["name"]: s for s in SPECIES_LIBRARY}

    total_trees = 0.0
    shade_sum = 0.0
    carbon_sum = 0.0
    species_seen = set()

    for r in records:
        density = r.count_per_hectare or 0
        # Age moyen reel si renseigne, sinon defaut prudent de 5 ans.
        age = r.avg_age_years if r.avg_age_years is not None else 5
        total_trees += density
        species_seen.add(r.species_name)

        lib = species_lib.get(r.species_name)
        cf = lib["carbon_factor"] if lib else 0.010   # défaut générique
        sf = lib["shade_factor"]  if lib else 0.6

        # Facteur âge : croît jusqu'à 2.0 à 30 ans (log)
        import math
        age_factor = min(2.0, 0.4 + (math.log1p(age) / math.log1p(30)) * 1.6)

        shade_sum  += density * sf
        carbon_sum += density * cf * age_factor

    # Ombrage : 40 arbres/ha de plein couvert = 100% ombrage (règle empirique cacao)
    shade_score = min(100, round(shade_sum / 40 * 100))

    # Diversité : 1 espèce = 10pts, chaque espèce suppl. +12pts, plafonné 100
    species_count = len(species_seen)
    diversity_score = min(100, 10 + (species_count - 1) * 12) if species_count else 0

    # Carbone : plafonné à 5 tCO₂/ha (valeur réaliste pour agroforesterie cacao)
    carbon_score = min(100, round(carbon_sum / 5 * 100))

    # Conformité globale : ombrage 40% + diversité 30% + carbone 30%
    conformity_score = round(shade_score * 0.4 + diversity_score * 0.3 + carbon_score * 0.3)

    return {
        "shade_score": shade_score,
        "diversity_score": diversity_score,
        "carbon_stock_tco2_ha": round(carbon_sum, 2),
        "carbon_score": carbon_score,
        "conformity_score": conformity_score,
        "total_trees_per_ha": round(total_trees, 1),
        "species_count": species_count,
    }



def _build_recommendations(metrics: dict, records: list) -> list:
    recos = []
    shade    = metrics["shade_score"]
    div      = metrics["diversity_score"]
    carbon   = metrics["carbon_score"]
    conf     = metrics["conformity_score"]
    trees    = metrics["total_trees_per_ha"]
    sp_count = metrics["species_count"]

    # Ombrage
    if shade == 0:
        recos.append({"priority":"high","icon":"🌳","title":"Aucun arbre d'ombrage enregistré",
            "action":"Planter en urgence des arbres d'ombrage a croissance rapide : Gliricidia sepium ou Musa spp. (Bananier) — objectif minimum 20 arbres/ha."})
    elif shade < 35:
        recos.append({"priority":"high","icon":"🌿","title":"Ombrage insuffisant — stress thermique possible",
            "action":f"Densite actuelle : {trees} arbres/ha. Planter 15 a 20 arbres/ha supplementaires de Gliricidia ou Erythrina pour atteindre l'optimal (20-50%)."})
    elif shade > 75:
        recos.append({"priority":"medium","icon":"✂️","title":"Ombrage excessif — risque fongique",
            "action":"Canopee trop dense (> 75%). Elaguer les arbres d'ombrage pour ameliorer la circulation d'air et reduire les risques de pourriture des cabosses."})
    else:
        recos.append({"priority":"low","icon":"✅","title":"Ombrage optimal",
            "action":"Densite d'ombrage dans la plage ideale (20-75%). Maintenir les pratiques actuelles."})

    # Diversite
    if sp_count == 1:
        recos.append({"priority":"medium","icon":"🌱","title":"Diversite floristique faible — 1 seule espece",
            "action":"Introduire 2 a 3 especes complementaires. Recommandations : Persea americana (Avocatier) pour les revenus + Gliricidia sepium pour la fixation d'azote."})
    elif sp_count == 2:
        recos.append({"priority":"low","icon":"🌿","title":"Diversite a ameliorer",
            "action":"Objectif : 3 especes minimum pour la conformite EUDR. Ajouter une espece de strate superieure (Iroko, Manguier) pour ameliorer le score carbone."})
    elif sp_count >= 3:
        recos.append({"priority":"low","icon":"✅","title":"Bonne diversite floristique",
            "action":f"{sp_count} especes enregistrees. Continuer a diversifier avec des essences a fort potentiel carbone pour renforcer la certification."})

    # Carbone
    if 0 < carbon < 20:
        recos.append({"priority":"medium","icon":"🌍","title":"Stock carbone tres faible",
            "action":"Planter des essences a fort potentiel carbone : Milicia excelsa (Iroko), Ceiba pentandra (Fromager), Khaya senegalensis. Objectif : 1 tCO2/ha minimum."})
    elif carbon < 50:
        recos.append({"priority":"low","icon":"📈","title":"Stock carbone en developpement",
            "action":"Augmenter la densite d'arbres a longue duree de vie (Iroko, Frake, Khaya) pour accelerer la sequestration carbone et acceder aux financements climatiques."})

    # Conformite globale
    if conf < 35:
        recos.append({"priority":"high","icon":"⚠️","title":"Non conforme aux standards EUDR",
            "action":"Score de conformite critique. Votre plantation ne repond pas encore aux exigences EUDR. Appliquer en priorite les recommandations ombrage et diversite."})
    elif conf < 65:
        recos.append({"priority":"medium","icon":"📋","title":"Conformite partielle — ameliorations necessaires",
            "action":"Des progres ont ete faits mais des ajustements sont requis. Concentrez-vous sur le point ayant le score le plus faible."})
    else:
        recos.append({"priority":"low","icon":"🏆","title":"Plantation conforme aux standards agroforestiers",
            "action":"Excellent niveau de conformite. Cette plantation peut etre presentee aux acheteurs et certifications EUDR/Rainforest Alliance."})

    priority_order = {"high": 0, "medium": 1, "low": 2}
    recos.sort(key=lambda x: priority_order.get(x["priority"], 3))
    return recos

class AgroforestryCreate(BaseModel):
    species_name: str
    local_name: Optional[str] = None
    layer: Optional[str] = None
    count_per_hectare: float = Field(
        gt=0,
        description="Densite d'arbres par hectare (strictement positive).",
    )
    avg_age_years: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None


@router.get("/species-library")
def get_species_library(current_user: User = Depends(get_current_user)):
    """Retourne la bibliothèque des espèces agroforestières."""
    return SPECIES_LIBRARY




@router.put("/plantations/{plantation_id}/plants")
def update_plant_count(
    plantation_id: int,
    plant_count: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Met a jour le nombre de plants d'une plantation."""
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(status_code=403, detail="Droits insuffisants.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    if plant_count < 0:
        raise HTTPException(status_code=400, detail="Nombre de plants invalide.")

    plantation.plant_count = plant_count
    db.commit()

    result = {"plant_count": plant_count, "plantation_id": plantation_id}
    if plantation.hectares and plantation.hectares > 0:
        density = round(plant_count / plantation.hectares)
        result["density_per_ha"] = density
        if density < 800:
            result["alert_level"] = "warning"
            result["alert"] = f"Densite insuffisante ({density} pieds/ha). Minimum CCC : 800 pieds/ha."
        elif density > 1200:
            result["alert_level"] = "info"
            result["alert"] = f"Densite elevee ({density} pieds/ha). Eclaircissage possible."
        else:
            result["alert_level"] = "success"
            result["alert"] = f"Densite optimale ({density} pieds/ha). Conforme CCC."
        result["production_min_kg"] = round(plant_count * 0.4)
        result["production_max_kg"] = round(plant_count * 0.6)
    return result


@router.get("/plantations/{plantation_id}/agroforestry")
def get_agroforestry(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retourne l'inventaire agroforestier d'une plantation + métriques calculées."""
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    records = db.query(AgroforestryRecord).filter(
        AgroforestryRecord.plantation_id == plantation_id
    ).all()

    metrics = _compute_metrics(records)
    recommendations = _build_recommendations(metrics, records) if records else []

    return {
        "plantation_id": plantation_id,
        "plantation_name": plantation.name,
        "hectares": plantation.hectares,
        "records": [
            {
                "id": r.id,
                "species_name": r.species_name,
                "count_per_hectare": r.count_per_hectare,
            }
            for r in records
        ],
        "metrics": metrics,
        "recommendations": recommendations,
    }


@router.post("/plantations/{plantation_id}/agroforestry", status_code=201)
def add_agroforestry_record(
    plantation_id: int,
    data: AgroforestryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ajoute une espèce à l'inventaire agroforestier d'une plantation."""
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(status_code=403, detail="Rôle agronome requis.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    record = AgroforestryRecord(
        plantation_id=plantation_id,
        species_name=data.species_name,
        count_per_hectare=data.count_per_hectare,
        avg_age_years=data.avg_age_years,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "message": "Espèce ajoutée avec succès."}


@router.delete("/agroforestry/{record_id}", status_code=200)
def delete_agroforestry_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprime un enregistrement agroforestier. Admin uniquement."""
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(status_code=403, detail="Rôle agronome requis.")

    record = db.query(AgroforestryRecord).join(Plantation).filter(
        AgroforestryRecord.id == record_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Enregistrement introuvable.")

    db.delete(record)
    db.commit()
    return {"message": "Enregistrement supprimé."}


@router.get("/agroforestry/summary")
def get_agroforestry_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bilan agroforestier global de la coopérative.
    Retourne le stock carbone agrégé et les scores moyens.
    """
    plantations = db.query(Plantation).filter(
        Plantation.cooperative_id == current_user.cooperative_id
    ).all()

    total_carbon = 0.0
    total_trees = 0.0
    conformity_scores = []
    species_all = set()

    for p in plantations:
        records = db.query(AgroforestryRecord).filter(
            AgroforestryRecord.plantation_id == p.id
        ).all()
        if not records:
            continue
        m = _compute_metrics(records)
        ha = p.hectares or 1.0
        total_carbon += m["carbon_stock_tco2_ha"] * ha
        total_trees += m["total_trees_per_ha"] * ha
        conformity_scores.append(m["conformity_score"])
        for r in records:
            species_all.add(r.species_name)

    avg_conformity = round(sum(conformity_scores) / len(conformity_scores)) if conformity_scores else 0

    coop = db.query(Cooperative).filter(
        Cooperative.id == current_user.cooperative_id
    ).first()
    cooperative_name = coop.name if coop else "Cooperative"

    return {
        "cooperative_name": cooperative_name,
        "total_carbon_tco2": round(total_carbon, 1),
        "total_trees_estimated": round(total_trees),
        "avg_conformity_score": avg_conformity,
        "plantations_with_inventory": len(conformity_scores),
        "total_plantations": len(plantations),
        "unique_species_count": len(species_all),
    }


@router.get("/agroforestry/report.pdf")
def get_agroforestry_report_pdf(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bilan agroforestier de la coopérative au format PDF brandé, cohérent avec
    les autres états (couverture, synthèse KPI, inventaire des espèces, détail
    par parcelle). Remplace l'impression navigateur côté frontend.
    """
    from datetime import datetime as _dt

    species_lib = {s["name"]: s for s in SPECIES_LIBRARY}

    plantations = db.query(Plantation).filter(
        Plantation.cooperative_id == current_user.cooperative_id
    ).all()

    total_carbon = 0.0
    total_trees = 0.0
    conformity_scores = []
    # Agrégation par espèce : arbres estimés cumulés (densité × ha)
    species_trees: dict[str, float] = {}
    plantation_rows = []

    for p in plantations:
        records = db.query(AgroforestryRecord).filter(
            AgroforestryRecord.plantation_id == p.id
        ).all()
        if not records:
            continue
        m = _compute_metrics(records)
        ha = p.hectares or 1.0
        carbon_p = m["carbon_stock_tco2_ha"] * ha
        trees_p = m["total_trees_per_ha"] * ha
        total_carbon += carbon_p
        total_trees += trees_p
        conformity_scores.append(m["conformity_score"])

        for r in records:
            species_trees[r.species_name] = (
                species_trees.get(r.species_name, 0.0) + (r.count_per_hectare or 0) * ha
            )

        plantation_rows.append({
            "name": p.name,
            "species_count": m["species_count"],
            "trees_est": round(trees_p),
            "carbon_tco2": round(carbon_p, 1),
            "conformity": m["conformity_score"],
        })

    avg_conformity = (
        round(sum(conformity_scores) / len(conformity_scores)) if conformity_scores else 0
    )

    species_list = []
    for name, trees in sorted(species_trees.items(), key=lambda kv: kv[1], reverse=True):
        lib = species_lib.get(name)
        species_list.append({
            "name": name,
            "local": lib["local"] if lib else None,
            "layer": ({
                "understory": "Sous-étage",
                "intermediate": "Intermédiaire",
                "superior": "Supérieure",
            }.get(lib["layer"], lib["layer"]) if lib else None),
            "trees": round(trees),
        })

    plantation_rows.sort(key=lambda r: r["carbon_tco2"], reverse=True)

    brand = coop_brand(db, current_user.cooperative_id)
    context = {
        **brand,
        "generated_at": _dt.now().strftime("%d/%m/%Y à %H:%M"),
        "s": {
            "total_carbon_tco2": round(total_carbon, 1),
            "total_trees_estimated": round(total_trees),
            "unique_species_count": len(species_trees),
            "plantations_with_inventory": len(conformity_scores),
            "total_plantations": len(plantations),
            "avg_conformity_score": avg_conformity,
        },
        "species": species_list,
        "plantations": plantation_rows,
    }

    try:
        pdf_bytes = generate_agroforestry_pdf(context)
    except Exception as e:
        import traceback, logging
        logging.getLogger("agrivision").error(
            "Echec generation bilan agroforestier PDF : %s\n%s",
            type(e).__name__, traceback.format_exc()
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la generation du bilan : {type(e).__name__} - {str(e)[:200]}"
        )

    filename = agroforestry_report_filename()
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"{filename}\"; "
            f"filename*=UTF-8''{quote(filename)}"
        )
    }
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=headers,
    )


# ════════════════════════════════════════════════════════════════════════════
# ─── Suspension — Niveau 1 (Admin coopérative) ──────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

@router.put("/admin/members/{user_id}/suspend")
def suspend_member(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Suspend un membre de la coopérative. Admin uniquement."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas suspendre votre propre compte.")

    member = db.query(User).filter(
        User.id == user_id,
        User.cooperative_id == current_user.cooperative_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable.")
    if not member.is_active:
        raise HTTPException(status_code=400, detail="Ce membre est déjà suspendu.")

    member.is_active = False
    db.commit()
    return {"message": f"Compte {member.email} suspendu.", "user_id": member.id, "is_active": False}


@router.put("/admin/members/{user_id}/activate")
def activate_member(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Réactive un membre suspendu. Admin uniquement."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    member = db.query(User).filter(
        User.id == user_id,
        User.cooperative_id == current_user.cooperative_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable.")
    if member.is_active:
        raise HTTPException(status_code=400, detail="Ce membre est déjà actif.")

    member.is_active = True
    db.commit()
    return {"message": f"Compte {member.email} réactivé.", "user_id": member.id, "is_active": True}


# ════════════════════════════════════════════════════════════════════════════
# ─── Suspension — Niveau 2 (IKAFFANAN LTD — propriétaire plateforme) ────────
# ════════════════════════════════════════════════════════════════════════════

from fastapi import Header

def _check_owner_key(x_owner_key: Optional[str] = Header(None)):
    """Vérifie la clé propriétaire IKAFFANAN LTD."""
    owner_key = os.getenv("OWNER_API_KEY")
    if not owner_key:
        raise HTTPException(status_code=503, detail="OWNER_API_KEY non configurée sur le serveur.")
    if x_owner_key != owner_key:
        raise HTTPException(status_code=401, detail="Clé propriétaire invalide.")


@router.get("/owner/cooperatives")
def list_cooperatives(
    db: Session = Depends(get_db),
    x_owner_key: Optional[str] = Header(None),
):
    """Liste toutes les coopératives. Réservé IKAFFANAN LTD."""
    _check_owner_key(x_owner_key)
    coops = db.query(Cooperative).order_by(Cooperative.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "country": c.country,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "members_count": len(c.users),
        }
        for c in coops
    ]


@router.put("/owner/cooperatives/{coop_id}/suspend")
def suspend_cooperative(
    coop_id: int,
    db: Session = Depends(get_db),
    x_owner_key: Optional[str] = Header(None),
):
    """Suspend une coopérative entière. Réservé IKAFFANAN LTD."""
    _check_owner_key(x_owner_key)
    coop = db.query(Cooperative).filter(Cooperative.id == coop_id).first()
    if not coop:
        raise HTTPException(status_code=404, detail="Coopérative introuvable.")
    if not coop.is_active:
        raise HTTPException(status_code=400, detail="Coopérative déjà suspendue.")
    coop.is_active = False
    db.commit()
    return {"message": f"Coopérative '{coop.name}' suspendue.", "coop_id": coop.id, "is_active": False}


@router.put("/owner/cooperatives/{coop_id}/activate")
def activate_cooperative(
    coop_id: int,
    db: Session = Depends(get_db),
    x_owner_key: Optional[str] = Header(None),
):
    """Réactive une coopérative suspendue. Réservé IKAFFANAN LTD."""
    _check_owner_key(x_owner_key)
    coop = db.query(Cooperative).filter(Cooperative.id == coop_id).first()
    if not coop:
        raise HTTPException(status_code=404, detail="Coopérative introuvable.")
    if coop.is_active:
        raise HTTPException(status_code=400, detail="Coopérative déjà active.")
    coop.is_active = True
    db.commit()
    return {"message": f"Coopérative '{coop.name}' réactivée.", "coop_id": coop.id, "is_active": True}


# ════════════════════════════════════════════════════════════════════════════
# ─── Dashboard Propriétaire — Statistiques globales IKAFFANAN LTD ───────────
# ════════════════════════════════════════════════════════════════════════════

@router.get("/owner/stats")
def owner_stats(
    db: Session = Depends(get_db),
    x_owner_key: Optional[str] = Header(None),
):
    """Statistiques globales de la plateforme. Reserve IKAFFANAN LTD."""
    _check_owner_key(x_owner_key)

    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func

    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    seven_days_ago  = now - timedelta(days=7)

    # Totaux globaux
    total_coops       = db.query(Cooperative).count()
    active_coops      = db.query(Cooperative).filter(Cooperative.is_active == True).count()
    total_users       = db.query(User).count()
    total_plantations = db.query(Plantation).count()
    total_diagnostics = db.query(Diagnostic).count()

    # Activite recente
    diags_last_30d = db.query(Diagnostic).filter(
        Diagnostic.created_at >= thirty_days_ago
    ).count()
    diags_last_7d = db.query(Diagnostic).filter(
        Diagnostic.created_at >= seven_days_ago
    ).count()

    # Coopératives sans activite depuis 30j
    active_coop_ids = db.query(Diagnostic.plantation_id).join(
        Plantation, Diagnostic.plantation_id == Plantation.id
    ).filter(
        Diagnostic.created_at >= thirty_days_ago
    ).subquery()

    all_coop_ids = db.query(Plantation.cooperative_id).distinct().all()
    all_coop_ids_set = {r[0] for r in all_coop_ids if r[0]}

    active_via_diag = db.query(Plantation.cooperative_id).join(
        Diagnostic, Diagnostic.plantation_id == Plantation.id
    ).filter(
        Diagnostic.created_at >= thirty_days_ago
    ).distinct().all()
    active_via_diag_set = {r[0] for r in active_via_diag if r[0]}
    inactive_coop_count = len(all_coop_ids_set - active_via_diag_set)

    # Stats par cooperative
    coops = db.query(Cooperative).order_by(Cooperative.created_at.desc()).all()
    coop_stats = []
    for c in coops:
        n_users = db.query(User).filter(User.cooperative_id == c.id).count()
        n_plantations = db.query(Plantation).filter(Plantation.cooperative_id == c.id).count()
        n_diags = db.query(Diagnostic).join(
            Plantation, Diagnostic.plantation_id == Plantation.id
        ).filter(Plantation.cooperative_id == c.id).count()
        n_diags_30d = db.query(Diagnostic).join(
            Plantation, Diagnostic.plantation_id == Plantation.id
        ).filter(
            Plantation.cooperative_id == c.id,
            Diagnostic.created_at >= thirty_days_ago
        ).count()
        last_diag = db.query(Diagnostic).join(
            Plantation, Diagnostic.plantation_id == Plantation.id
        ).filter(
            Plantation.cooperative_id == c.id
        ).order_by(Diagnostic.created_at.desc()).first()

        from app.services.plans import normalize_plan
        # Comparaison tz-safe : SQLite renvoie des datetimes naïfs, Postgres aware.
        created = c.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        is_new = bool(created and created >= thirty_days_ago)
        coop_stats.append({
            "id": c.id,
            "name": c.name,
            "country": c.country,
            "is_active": c.is_active,
            "plan": normalize_plan(getattr(c, "plan", None)),
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "users_count": n_users,
            "plantations_count": n_plantations,
            "diagnostics_total": n_diags,
            "diagnostics_last_30d": n_diags_30d,
            "last_activity": last_diag.created_at.isoformat() if last_diag and last_diag.created_at else None,
            "status": "active" if n_diags_30d > 0 else ("new" if is_new else "inactive"),
        })

    # Distribution des risques globale
    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    latest_diags = db.query(Diagnostic).order_by(Diagnostic.created_at.desc()).limit(500).all()
    seen_plantations = set()
    for d in latest_diags:
        if d.plantation_id not in seen_plantations:
            seen_plantations.add(d.plantation_id)
            risk_counts[d.global_risk_level] = risk_counts.get(d.global_risk_level, 0) + 1

    # KPIs plateforme issus des modules recents (protection enfant, tracabilite,
    # commercial). Agregats globaux peu couteux (count/sum), tous coops confondus.
    from app.db.models import Lot, Producer, PurchaseRecord  # noqa: E402
    from app.db.models_social import (  # noqa: E402
        BlockStatus, Child, RiskLevel, SsrtePlantationVisit, TraceabilityBlock,
    )
    from app.services.plans import PLAN_CATEGORIES, normalize_plan as _np  # noqa: E402

    total_producers = db.query(func.count(Producer.id)).filter(Producer.is_active == True).scalar() or 0
    total_children = db.query(func.count(Child.id)).filter(Child.is_active == True).scalar() or 0
    high_risk_children = db.query(func.count(Child.id)).filter(
        Child.is_active == True, Child.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]),
    ).scalar() or 0
    active_blocks = db.query(func.count(TraceabilityBlock.id)).filter(
        TraceabilityBlock.status == BlockStatus.ACTIVE,
    ).scalar() or 0
    suspected_visits = db.query(func.count(SsrtePlantationVisit.id)).filter(
        SsrtePlantationVisit.suspected_child_labor == True,
    ).scalar() or 0
    total_lots = db.query(func.count(Lot.id)).scalar() or 0
    purchase_volume_kg = db.query(func.coalesce(func.sum(PurchaseRecord.net_weight_kg), 0)).scalar() or 0
    purchase_amount = db.query(func.coalesce(func.sum(PurchaseRecord.total_amount_fcfa), 0)).scalar() or 0

    # Repartition par plan d'abonnement
    plan_distribution = {p: 0 for p in PLAN_CATEGORIES}
    for c in coops:
        plan_distribution[_np(getattr(c, "plan", None))] = plan_distribution.get(_np(getattr(c, "plan", None)), 0) + 1

    return {
        "generated_at": now.isoformat(),
        "summary": {
            "total_cooperatives": total_coops,
            "active_cooperatives": active_coops,
            "suspended_cooperatives": total_coops - active_coops,
            "inactive_cooperatives_30d": inactive_coop_count,
            "total_users": total_users,
            "total_plantations": total_plantations,
            "total_producers": total_producers,
            "total_diagnostics": total_diagnostics,
            "diagnostics_last_30d": diags_last_30d,
            "diagnostics_last_7d": diags_last_7d,
            # Protection de l'enfant / tracabilite
            "total_children": total_children,
            "high_risk_children": high_risk_children,
            "active_traceability_blocks": active_blocks,
            "suspected_child_labor_visits": suspected_visits,
            # Commercial & tracabilite
            "total_lots": total_lots,
            "total_purchase_volume_kg": round(float(purchase_volume_kg), 1),
            "total_purchase_amount_fcfa": round(float(purchase_amount), 0),
        },
        "risk_distribution": risk_counts,
        "plan_distribution": plan_distribution,
        "cooperatives": coop_stats,
    }


class OwnerPlanUpdate(BaseModel):
    plan: str


@router.put("/owner/cooperatives/{coop_id}/plan")
def owner_set_cooperative_plan(
    coop_id: int,
    data: OwnerPlanUpdate,
    db: Session = Depends(get_db),
    x_owner_key: Optional[str] = Header(None),
):
    """Change le plan d'abonnement d'une cooperative. Reserve IKAFFANAN LTD."""
    _check_owner_key(x_owner_key)
    from app.services.plans import PLAN_CATEGORIES
    if data.plan not in PLAN_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Plan invalide : {sorted(PLAN_CATEGORIES)}.")
    coop = db.query(Cooperative).filter(Cooperative.id == coop_id).first()
    if not coop:
        raise HTTPException(status_code=404, detail="Cooperative introuvable.")
    coop.plan = data.plan
    db.commit()
    return {"coop_id": coop.id, "name": coop.name, "plan": coop.plan}


# ════════════════════════════════════════════════════════════════════════════
# ─── Cout de revient IA (API Claude) par cooperative — IKAFFANAN LTD ────────
# ════════════════════════════════════════════════════════════════════════════

def _parse_ai_cost_period(from_: Optional[str], to: Optional[str]):
    """
    Parse une periode optionnelle (YYYY-MM-DD). Defaut : 30 derniers jours.
    Retourne (start_dt, end_dt) en UTC ; `end_dt` inclut toute la journee `to`.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)

    def _parse_day(s, default):
        if not s:
            return default
        try:
            d = datetime.strptime(s.strip()[:10], "%Y-%m-%d")
            return d.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            return default

    start = _parse_day(from_, now - timedelta(days=30))
    end_day = _parse_day(to, now)
    # Borne haute inclusive : fin de la journee demandee.
    end = end_day.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start, end


def _ai_cost_summary_query(db: Session, start, end, coop_id: Optional[int] = None):
    """Agrege l'usage IA (nb d'appels, tokens, cout USD) sur la periode."""
    from app.db.models import AiUsage
    q = db.query(
        func.count(AiUsage.id),
        func.coalesce(func.sum(AiUsage.input_tokens), 0),
        func.coalesce(func.sum(AiUsage.output_tokens), 0),
        func.coalesce(func.sum(AiUsage.cost_usd), 0.0),
    ).filter(AiUsage.created_at >= start, AiUsage.created_at <= end)
    if coop_id is not None:
        q = q.filter(AiUsage.cooperative_id == coop_id)
    calls, in_tok, out_tok, cost_usd = q.one()
    return {
        "calls": int(calls or 0),
        "input_tokens": int(in_tok or 0),
        "output_tokens": int(out_tok or 0),
        "cost_usd": round(float(cost_usd or 0.0), 4),
    }


@router.get("/owner/ai-cost")
def owner_ai_cost(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_owner_key: Optional[str] = Header(None),
):
    """
    Cout de revient des appels IA (API Claude) sur une periode, ventile par
    cooperative. Reserve IKAFFANAN LTD. Le cout USD est fige a l'enregistrement
    (vraie facturation Anthropic) ; la conversion FCFA est indicative au taux courant.
    """
    _check_owner_key(x_owner_key)
    from app.db.models import AiUsage
    from app.services.ai_cost import pricing_info, usd_to_fcfa

    start, end = _parse_ai_cost_period(from_, to)

    # Agregat par cooperative
    rows = (
        db.query(
            AiUsage.cooperative_id,
            func.count(AiUsage.id),
            func.coalesce(func.sum(AiUsage.input_tokens), 0),
            func.coalesce(func.sum(AiUsage.output_tokens), 0),
            func.coalesce(func.sum(AiUsage.cost_usd), 0.0),
        )
        .filter(AiUsage.created_at >= start, AiUsage.created_at <= end)
        .group_by(AiUsage.cooperative_id)
        .all()
    )

    # Noms des cooperatives concernees (une seule requete)
    coop_ids = [r[0] for r in rows if r[0] is not None]
    names = {}
    if coop_ids:
        for c in db.query(Cooperative).filter(Cooperative.id.in_(coop_ids)).all():
            names[c.id] = c.name

    by_coop = []
    for coop_id, calls, in_tok, out_tok, cost_usd in rows:
        cost_usd = round(float(cost_usd or 0.0), 4)
        by_coop.append({
            "cooperative_id": coop_id,
            "cooperative_name": names.get(coop_id, "—") if coop_id else "(sans coopérative)",
            "calls": int(calls or 0),
            "input_tokens": int(in_tok or 0),
            "output_tokens": int(out_tok or 0),
            "cost_usd": cost_usd,
            "cost_fcfa": usd_to_fcfa(cost_usd),
        })
    by_coop.sort(key=lambda x: x["cost_usd"], reverse=True)

    totals = _ai_cost_summary_query(db, start, end)
    totals["cost_fcfa"] = usd_to_fcfa(totals["cost_usd"])

    return {
        "period": {"from": start.date().isoformat(), "to": end.date().isoformat()},
        "pricing": pricing_info(),
        "totals": totals,
        "by_cooperative": by_coop,
    }


@router.get("/owner/cooperatives/{coop_id}/ai-cost")
def owner_cooperative_ai_cost(
    coop_id: int,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_owner_key: Optional[str] = Header(None),
):
    """Cout de revient IA d'une cooperative donnee sur une periode. Reserve IKAFFANAN LTD."""
    _check_owner_key(x_owner_key)
    from app.services.ai_cost import pricing_info, usd_to_fcfa

    coop = db.query(Cooperative).filter(Cooperative.id == coop_id).first()
    if not coop:
        raise HTTPException(status_code=404, detail="Coopérative introuvable.")

    start, end = _parse_ai_cost_period(from_, to)
    totals = _ai_cost_summary_query(db, start, end, coop_id=coop_id)
    totals["cost_fcfa"] = usd_to_fcfa(totals["cost_usd"])

    return {
        "cooperative_id": coop.id,
        "cooperative_name": coop.name,
        "period": {"from": start.date().isoformat(), "to": end.date().isoformat()},
        "pricing": pricing_info(),
        "totals": totals,
    }


@router.put("/admin/members/{user_id}/reset-password")
def reset_member_password(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reinitialise le mot de passe d'un membre.
    Retourne un mot de passe temporaire a communiquer au membre.
    Admin uniquement.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas reinitialiser votre propre mot de passe.")

    member = db.query(User).filter(
        User.id == user_id,
        User.cooperative_id == current_user.cooperative_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable.")

    # Generer un mot de passe temporaire lisible (format : Mot-XXXX)
    import random, string
    adjectives = ["Cacao", "Foret", "Soleil", "Pluie", "Terre", "Arbre", "Canne", "Feuil"]
    adj = random.choice(adjectives)
    digits = ''.join(random.choices(string.digits, k=4))
    temp_password = f"{adj}-{digits}"

    from app.auth.auth_service import get_password_hash
    member.password_hash = get_password_hash(temp_password)
    db.commit()

    return {
        "message": f"Mot de passe de {member.email} reinitialise.",
        "temp_password": temp_password,
        "user_id": member.id,
    }

class MemberCreate(BaseModel):
    email: str
    role: str = "technician"


@router.post("/admin/members")
def create_member(
    payload: MemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cree un nouveau membre de la cooperative (technicien, agronome, admin).
    Genere un mot de passe temporaire a communiquer au membre.
    Admin uniquement.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    email = (payload.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Adresse email invalide.")

    role = (payload.role or "technician").strip().lower()
    if role not in ("admin", "agronomist", "technician", "gestionnaire"):
        raise HTTPException(status_code=400, detail="Role invalide.")

    # Email deja utilise ?
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409,
                            detail="Un compte existe deja avec cette adresse email.")

    # Mot de passe temporaire (meme format que reset-password)
    import random, string
    adjectives = ["Cacao", "Foret", "Soleil", "Pluie", "Terre", "Arbre", "Canne", "Feuil"]
    adj = random.choice(adjectives)
    digits = ''.join(random.choices(string.digits, k=4))
    temp_password = f"{adj}-{digits}"

    from app.auth.auth_service import get_password_hash
    new_user = User(
        email=email,
        password_hash=get_password_hash(temp_password),
        role=role,
        cooperative_id=current_user.cooperative_id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": f"Compte {email} cree.",
        "temp_password": temp_password,
        "user_id": new_user.id,
        "role": new_user.role,
    }


# ════════════════════════════════════════════════════════════════════════════
# ─── Conseil IA Agronome ────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

@router.post("/plantations/{plantation_id}/ai-advice")
async def plantation_ai_advice(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Génère un conseil agronomique IA complet pour une plantation.
    Agrège : diagnostic, agroforesterie, boundary → appel Claude API.
    """
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    latest_diag = (
        db.query(Diagnostic)
        .filter(Diagnostic.plantation_id == plantation_id)
        .order_by(Diagnostic.created_at.desc())
        .first()
    )
    agro_records = (
        db.query(AgroforestryRecord)
        .filter(AgroforestryRecord.plantation_id == plantation_id)
        .all()
    )
    boundary = (
        db.query(PlantationBoundary)
        .filter(PlantationBoundary.plantation_id == plantation_id)
        .first()
    )

    plantation_dict = {
        "id": plantation.id, "name": plantation.name,
        "owner_name": plantation.owner_name, "country": plantation.country,
        "region": plantation.region, "hectares": plantation.hectares, "plant_count": plantation.plant_count,
    }
    diag_dict = {
        "global_score": latest_diag.global_score,
        "global_risk_level": latest_diag.global_risk_level,
        "humidity_pct": latest_diag.humidity_pct,
        "rainfall_mm_month": latest_diag.rainfall_mm_month,
        "avg_temp_c": latest_diag.avg_temp_c,
        "plantation_age_years": latest_diag.plantation_age_years,
        "shade_tree_density_pct": latest_diag.shade_tree_density_pct,
    } if latest_diag else None
    agro_list = [
        {"species_name": r.species_name, "count_per_hectare": r.count_per_hectare}
        for r in agro_records
    ]
    boundary_dict = (
        {"has_boundary": True, "area_hectares": boundary.area_hectares}
        if boundary else {"has_boundary": False}
    )

    result, usage = await get_ai_advice(plantation_dict, diag_dict, agro_list, boundary_dict)

    # Suivi du cout de revient : on enregistre les tokens reellement consommes.
    # Best-effort : un echec d'enregistrement ne doit jamais casser la reponse IA.
    if usage:
        try:
            from app.db.models import AiUsage
            from app.services.ai_cost import compute_cost_usd
            db.add(AiUsage(
                cooperative_id=current_user.cooperative_id,
                user_id=current_user.id,
                plantation_id=plantation_id,
                feature="ai_advice",
                model=usage.get("model", ""),
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cost_usd=compute_cost_usd(usage.get("input_tokens", 0), usage.get("output_tokens", 0), usage.get("model")),
            ))
            db.commit()
        except Exception as e:
            db.rollback()
            import logging
            logging.getLogger("agrivision").warning("Enregistrement AiUsage echoue (ignore) : %s", e)

    return result


# ════════════════════════════════════════════════════════════════════════════
# ─── Délimitation de parcelles ──────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

import json as json_module
import math as math_module

def _calculate_area_hectares(coordinates: list) -> float:
    """
    Calcule la superficie d'un polygone en hectares via la formule de Shoelace
    adaptée aux coordonnées géographiques (approximation sphérique).
    Précision suffisante pour des parcelles < 100 ha.
    """
    if not coordinates or len(coordinates) < 3:
        return 0.0
    
    # Facteur de conversion : 1 degré ≈ 111 320 mètres à l'équateur
    R = 6371000  # rayon de la Terre en mètres
    
    def to_rad(deg):
        return deg * math_module.pi / 180
    
    n = len(coordinates)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        lat1 = to_rad(coordinates[i][1])
        lat2 = to_rad(coordinates[j][1])
        lng1 = to_rad(coordinates[i][0])
        lng2 = to_rad(coordinates[j][0])
        area += (lng2 - lng1) * (2 + math_module.sin(lat1) + math_module.sin(lat2))
    
    area = abs(area) * R * R / 2
    return round(area / 10000, 4)  # m² → hectares


class BoundaryCreate(BaseModel):
    geojson: str          # GeoJSON string du polygone
    method: str = "manual"  # "manual" | "gps_track"


@router.post("/plantations/{plantation_id}/boundary", status_code=201)
def save_boundary(
    plantation_id: int,
    data: BoundaryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sauvegarde ou met à jour les limites d'une plantation."""
    if current_user.role not in ("admin", "agronomist"):
        raise HTTPException(status_code=403, detail="Droits insuffisants.")

    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    # Valider et parser le GeoJSON
    try:
        geo = json_module.loads(data.geojson)
        coords = geo.get("coordinates", [[]])[0]  # premier anneau du polygone
        if len(coords) < 3:
            raise ValueError("Polygone invalide")
    except Exception:
        raise HTTPException(status_code=400, detail="GeoJSON invalide.")

    # Calculer la superficie
    area = _calculate_area_hectares(coords)
    points_count = len(coords)

    # Mettre à jour ou créer
    boundary = db.query(PlantationBoundary).filter(
        PlantationBoundary.plantation_id == plantation_id
    ).first()

    if boundary:
        boundary.geojson = data.geojson
        boundary.area_hectares = area
        boundary.method = data.method
        boundary.points_count = points_count
    else:
        boundary = PlantationBoundary(
            plantation_id=plantation_id,
            geojson=data.geojson,
            area_hectares=area,
            method=data.method,
            points_count=points_count,
        )
        db.add(boundary)

    # Mettre à jour les hectares de la plantation si pas encore renseignés
    if not plantation.hectares:
        plantation.hectares = area

    db.commit()
    db.refresh(boundary)
    # Délimitation modifiée → le score EUDR change (polygone / aire / GPS) : rafraîchir le cache.
    from app.eudr.score_cache import refresh_plantation_eudr
    refresh_plantation_eudr(plantation, db)
    db.commit()

    return {
        "id": boundary.id,
        "plantation_id": plantation_id,
        "area_hectares": area,
        "points_count": points_count,
        "method": data.method,
        "message": f"Délimitation sauvegardée — {area} ha calculés automatiquement."
    }


def _square_geojson(lat: float, lng: float, hectares: float) -> str:
    """Construit un polygone carré GeoJSON centré sur (lat, lng), dimensionné à
    `hectares`. Réplique la logique de `quickSquare()` du frontend (carré
    « surface ») pour des délimitations cohérentes côté serveur."""
    side = math_module.sqrt(max(hectares, 0.0001) * 10000.0)   # côté en mètres
    half = side / 2.0
    d_lat = half / 111320.0
    cos_lat = math_module.cos(lat * math_module.pi / 180.0) or 1e-9
    d_lng = half / (111320.0 * cos_lat)
    ring = [
        [lng - d_lng, lat - d_lat],
        [lng + d_lng, lat - d_lat],
        [lng + d_lng, lat + d_lat],
        [lng - d_lng, lat + d_lat],
        [lng - d_lng, lat - d_lat],   # fermeture de l'anneau
    ]
    return json_module.dumps({"type": "Polygon", "coordinates": [ring]})


@router.post("/plantations/boundaries/generate-missing")
def generate_missing_boundaries(
    limit: int = 500,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Génère en masse des délimitations carrées (P3 — passage à l'échelle).

    Pour chaque parcelle de la coopérative **sans délimitation** mais disposant
    d'un GPS + d'une superficie déclarés, crée un polygone carré (méthode
    « generated ») centré sur le GPS, dimensionné à la superficie, puis
    rafraîchit le cache EUDR. Traité **par lots** (`limit`) pour ne jamais
    bloquer sur des milliers de parcelles : le frontend rappelle l'endpoint
    tant que `remaining > 0`. Ne touche jamais une parcelle déjà délimitée.
    """
    if current_user.role not in ("admin", "agronomist"):
        raise HTTPException(status_code=403, detail="Droits insuffisants.")

    limit = max(1, min(limit, 2000))   # garde-fou : lots bornés

    # Parcelles de la coop déjà délimitées (à exclure)
    delimited_subq = (
        db.query(PlantationBoundary.plantation_id)
        .join(Plantation, Plantation.id == PlantationBoundary.plantation_id)
        .filter(Plantation.cooperative_id == current_user.cooperative_id)
    )

    # Parcelles sans délimitation mais générables (GPS + superficie exploitables)
    generatable_q = db.query(Plantation).filter(
        Plantation.cooperative_id == current_user.cooperative_id,
        ~Plantation.id.in_(delimited_subq),
        Plantation.latitude.isnot(None),
        Plantation.longitude.isnot(None),
        Plantation.hectares.isnot(None),
        Plantation.hectares > 0,
    )
    total_generatable = generatable_q.count()
    batch = generatable_q.limit(limit).all()

    for p in batch:
        geojson_str = _square_geojson(p.latitude, p.longitude, p.hectares)
        ring = json_module.loads(geojson_str)["coordinates"][0]
        db.add(PlantationBoundary(
            plantation_id=p.id,
            geojson=geojson_str,
            area_hectares=_calculate_area_hectares(ring),
            points_count=len(ring),
            method="generated",
        ))
    db.commit()

    # Le polygone change le score EUDR (polygone valide / aire) → rafraîchir le cache.
    if batch:
        from app.eudr.score_cache import refresh_plantation_eudr
        for p in batch:
            refresh_plantation_eudr(p, db)
        db.commit()

    generated = len(batch)
    remaining = max(0, total_generatable - generated)   # générables encore en attente

    # Parcelles encore sans délimitation, toutes causes confondues, après ce lot…
    still_missing = db.query(Plantation).filter(
        Plantation.cooperative_id == current_user.cooperative_id,
        ~Plantation.id.in_(delimited_subq),
    ).count()
    # … dont celles qu'on ne peut PAS générer automatiquement (GPS/superficie manquants).
    without_gps = max(0, still_missing - remaining)

    if generated:
        msg = f"{generated} délimitation(s) générée(s) automatiquement."
    elif total_generatable == 0 and without_gps == 0:
        msg = "Toutes les parcelles sont déjà délimitées."
    else:
        msg = "Aucune parcelle à générer (GPS ou superficie manquants)."

    return {
        "generated": generated,
        "remaining": remaining,
        "without_gps": without_gps,
        "message": msg,
    }


@router.get("/plantations/{plantation_id}/boundary")
def get_boundary(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retourne les limites d'une plantation."""
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    boundary = db.query(PlantationBoundary).filter(
        PlantationBoundary.plantation_id == plantation_id
    ).first()

    if not boundary:
        return {"has_boundary": False}

    return {
        "has_boundary": True,
        "id": boundary.id,
        "geojson": boundary.geojson,
        "area_hectares": boundary.area_hectares,
        "points_count": boundary.points_count,
        "method": boundary.method,
        "created_at": boundary.created_at.isoformat() if boundary.created_at else None,
    }


@router.delete("/plantations/{plantation_id}/boundary")
def delete_boundary(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprime les limites d'une plantation."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    boundary = db.query(PlantationBoundary).filter(
        PlantationBoundary.plantation_id == plantation_id
    ).first()
    if not boundary:
        raise HTTPException(status_code=404, detail="Aucune délimitation trouvée.")

    db.delete(boundary)
    db.commit()
    return {"message": "Délimitation supprimée."}


# ════════════════════════════════════════════════════════════════════════════
# ─── Recoltes (Harvests) ────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

from datetime import datetime, date as date_type


VALID_QUALITIES = {"Bonne", "Moyenne", "Defauts"}


class HarvestCreate(BaseModel):
    harvest_date: datetime
    quantity_kg: float
    quality: str
    price_per_kg_fcfa: Optional[float] = None
    notes: Optional[str] = None
    is_historical: bool = False
    numero_recu_achat: Optional[str] = None
    nbre_sacs: Optional[int] = None


class HarvestUpdate(BaseModel):
    harvest_date: Optional[datetime] = None
    quantity_kg: Optional[float] = None
    quality: Optional[str] = None
    price_per_kg_fcfa: Optional[float] = None
    notes: Optional[str] = None


def compute_season(d) -> str:
    """
    Determine la saison cacao en Cote d'Ivoire :
    - "grande"      : octobre a janvier (mois 10, 11, 12, 1)
    - "petite"      : avril a juin (mois 4, 5, 6)
    - "intersaison" : autres mois (fevrier, mars, juillet, aout, septembre)
    """
    if d is None:
        return "intersaison"
    m = d.month if hasattr(d, "month") else d
    if m in (10, 11, 12, 1):
        return "grande"
    if m in (4, 5, 6):
        return "petite"
    return "intersaison"


def _check_plantation_access(plantation_id: int, db: Session, current_user: User) -> Plantation:
    """Verifie que la plantation existe et appartient a la cooperative de l'utilisateur."""
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    return plantation


@router.post("/plantations/{plantation_id}/harvests", status_code=201)
def create_harvest(
    plantation_id: int,
    harvest: HarvestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cree une nouvelle recolte. Reserve aux roles admin, agronomist et gestionnaire."""
    if current_user.role not in ("admin", "agronomist", "gestionnaire"):
        raise HTTPException(status_code=403, detail="Role agronome, gestionnaire ou admin requis.")

    _check_plantation_access(plantation_id, db, current_user)

    if harvest.quality not in VALID_QUALITIES:
        raise HTTPException(
            status_code=400,
            detail=f"Qualite invalide. Valeurs acceptees : {sorted(VALID_QUALITIES)}",
        )
    if harvest.quantity_kg <= 0:
        raise HTTPException(status_code=400, detail="La quantite doit etre superieure a 0.")
    if harvest.price_per_kg_fcfa is not None and harvest.price_per_kg_fcfa < 0:
        raise HTTPException(status_code=400, detail="Le prix ne peut pas etre negatif.")

    new_harvest = Harvest(
        plantation_id=plantation_id,
        harvest_date=harvest.harvest_date,
        quantity_kg=harvest.quantity_kg,
        quality=harvest.quality,
        price_per_kg_fcfa=harvest.price_per_kg_fcfa,
        season=compute_season(harvest.harvest_date),
        notes=harvest.notes,
        is_historical=harvest.is_historical,
        created_by_user_id=current_user.id,
        numero_recu_achat=harvest.numero_recu_achat,
        nbre_sacs=harvest.nbre_sacs,
    )
    db.add(new_harvest)
    db.commit()
    db.refresh(new_harvest)
    return new_harvest


@router.get("/plantations/{plantation_id}/harvests")
def list_harvests(
    plantation_id: int,
    year: Optional[int] = None,
    season: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste les recoltes d'une plantation, triees par date decroissante."""
    _check_plantation_access(plantation_id, db, current_user)

    query = db.query(Harvest).filter(Harvest.plantation_id == plantation_id)

    if year is not None:
        query = query.filter(func.extract("year", Harvest.harvest_date) == year)
    if season is not None:
        if season not in ("grande", "petite", "intersaison"):
            raise HTTPException(status_code=400, detail="Saison invalide.")
        query = query.filter(Harvest.season == season)

    return query.order_by(Harvest.harvest_date.desc()).all()


@router.get("/plantations/{plantation_id}/harvests/stats")
def harvest_stats(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Statistiques agregees des recoltes d'une plantation :
    - total_kg_all_time
    - total_kg_current_year
    - count_total
    - by_season : { "grande": kg, "petite": kg, "intersaison": kg } pour l'annee en cours
    - by_year   : [ { "year": 2025, "total_kg": ... }, ... ]
    """
    _check_plantation_access(plantation_id, db, current_user)

    harvests = db.query(Harvest).filter(Harvest.plantation_id == plantation_id).all()

    if not harvests:
        return {
            "total_kg_all_time": 0,
            "total_kg_current_year": 0,
            "count_total": 0,
            "by_season": {"grande": 0, "petite": 0, "intersaison": 0},
            "by_year": [],
        }

    current_year = datetime.now().year

    total_all = sum(h.quantity_kg for h in harvests)
    total_current_year = sum(
        h.quantity_kg for h in harvests if h.harvest_date.year == current_year
    )

    by_season = {"grande": 0.0, "petite": 0.0, "intersaison": 0.0}
    for h in harvests:
        if h.harvest_date.year == current_year and h.season in by_season:
            by_season[h.season] += h.quantity_kg

    years_dict = {}
    for h in harvests:
        y = h.harvest_date.year
        years_dict[y] = years_dict.get(y, 0) + h.quantity_kg
    by_year = [
        {"year": y, "total_kg": round(kg, 2)}
        for y, kg in sorted(years_dict.items(), reverse=True)
    ]

    return {
        "total_kg_all_time": round(total_all, 2),
        "total_kg_current_year": round(total_current_year, 2),
        "count_total": len(harvests),
        "by_season": {k: round(v, 2) for k, v in by_season.items()},
        "by_year": by_year,
    }


@router.put("/harvests/{harvest_id}")
def update_harvest(
    harvest_id: int,
    update: HarvestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Modifie une recolte existante. Reserve aux admin et agronomist."""
    if current_user.role not in ("admin", "agronomist"):
        raise HTTPException(status_code=403, detail="Role agronome ou admin requis.")

    harvest = db.query(Harvest).filter(Harvest.id == harvest_id).first()
    if not harvest:
        raise HTTPException(status_code=404, detail="Recolte introuvable.")

    _check_plantation_access(harvest.plantation_id, db, current_user)

    if update.quality is not None and update.quality not in VALID_QUALITIES:
        raise HTTPException(
            status_code=400,
            detail=f"Qualite invalide. Valeurs acceptees : {sorted(VALID_QUALITIES)}",
        )
    if update.quantity_kg is not None and update.quantity_kg <= 0:
        raise HTTPException(status_code=400, detail="La quantite doit etre superieure a 0.")
    if update.price_per_kg_fcfa is not None and update.price_per_kg_fcfa < 0:
        raise HTTPException(status_code=400, detail="Le prix ne peut pas etre negatif.")

    if update.harvest_date is not None:
        harvest.harvest_date = update.harvest_date
        harvest.season = compute_season(update.harvest_date)
    if update.quantity_kg is not None:
        harvest.quantity_kg = update.quantity_kg
    if update.quality is not None:
        harvest.quality = update.quality
    if update.price_per_kg_fcfa is not None:
        harvest.price_per_kg_fcfa = update.price_per_kg_fcfa
    if update.notes is not None:
        harvest.notes = update.notes

    db.commit()
    db.refresh(harvest)
    return harvest


@router.delete("/harvests/{harvest_id}")
def delete_harvest(
    harvest_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprime une recolte. Reserve aux admins."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    harvest = db.query(Harvest).filter(Harvest.id == harvest_id).first()
    if not harvest:
        raise HTTPException(status_code=404, detail="Recolte introuvable.")

    _check_plantation_access(harvest.plantation_id, db, current_user)

    db.delete(harvest)
    db.commit()
    return {"message": "Recolte supprimee avec succes."}

# ─── Reports PDF (Sprint R1a) ─────────────────────────────────────────────────

@router.get("/plantations/{plantation_id}/report.pdf")
def get_plantation_report_pdf(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Génère le rapport PDF complet d'une plantation.

    Permissions : admin et agronomist uniquement (pas de viewer ni technician).
    Multi-tenant : la plantation doit appartenir à la coopérative de l'utilisateur.
    Robuste : fonctionne aussi pour une plantation sans diagnostic ni récolte.
    """
    # 1. Vérification du rôle
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(
            status_code=403,
            detail="Génération de rapport réservée aux rôles admin et agronome."
        )

    # 2. Récupération multi-tenant de la plantation
    plantation = db.query(Plantation).filter(
        Plantation.id == plantation_id,
        Plantation.cooperative_id == current_user.cooperative_id,
    ).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")

    # 3. Construction du contexte + génération du PDF
    try:
        context = build_plantation_context(db, plantation)
        pdf_bytes = generate_plantation_pdf(context)
    except Exception as e:
        # Log explicite avec la stack trace dans les logs Railway
        import traceback, logging
        logger_pdf = logging.getLogger("agrivision")
        logger_pdf.error(
            "Echec generation PDF plantation %s : %s\n%s",
            plantation_id, type(e).__name__, traceback.format_exc()
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la generation du rapport : {type(e).__name__} - {str(e)[:200]}"
        )

    # 4. Réponse en streaming avec filename URL-encoded (gère les accents)
    filename = report_filename(plantation)
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"{filename}\"; "
            f"filename*=UTF-8''{quote(filename)}"
        )
    }
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=headers,
    )
