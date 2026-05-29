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
    return {"status": "ok"}


# ─── Plantations ─────────────────────────────────────────────────────────────

@router.post("/plantations")
def create_plantation(
    plantation: PlantationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    if not current_user.cooperative_id:
        raise HTTPException(
            status_code=400,
            detail="Votre compte n'est associé à aucune coopérative.",
        )

    # ── Trouver-ou-créer le Producteur lié au propriétaire ──────────────────
    # Sans ce rattachement, le producteur n'existe que comme texte (owner_name)
    # et n'apparaît pas dans les listes Producteurs (Protection enfant, EUDR,
    # CacaoGuard). On reproduit ici la migration de démarrage, mais au moment
    # de la création pour que toute nouvelle plantation génère son producteur.
    producer = None
    owner = (plantation.owner_name or "").strip()
    if owner:
        producer = (
            db.query(Producer)
            .filter(
                Producer.nom_complet == owner,
                Producer.cooperative_id == current_user.cooperative_id,
                Producer.is_active == True,
            )
            .first()
        )
        if not producer:
            producer = Producer(
                nom_complet=owner,
                cooperative_id=current_user.cooperative_id,
                is_active=True,
            )
            db.add(producer)
            db.flush()  # obtenir producer.id avant de lier la plantation

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
        total_pages = (total + page_size - 1) // page_size if page_size else 1
        return {
            "items": items,
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
    from app.db.models import Producer

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

    return {
        "sections": sections,
        "technicians": technicians,
        "certifications": ["FT", "RA", "BIO"],
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

VALID_ROLES = {"admin", "agronomist", "technician"}


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
        age = 5  # défaut fixe (avg_age_years non en base)
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
    count_per_hectare: float
    avg_age_years: Optional[float] = None
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

        coop_stats.append({
            "id": c.id,
            "name": c.name,
            "country": c.country,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "users_count": n_users,
            "plantations_count": n_plantations,
            "diagnostics_total": n_diags,
            "diagnostics_last_30d": n_diags_30d,
            "last_activity": last_diag.created_at.isoformat() if last_diag and last_diag.created_at else None,
            "status": "active" if n_diags_30d > 0 else ("new" if c.created_at and c.created_at >= thirty_days_ago else "inactive"),
        })

    # Distribution des risques globale
    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    latest_diags = db.query(Diagnostic).order_by(Diagnostic.created_at.desc()).limit(500).all()
    seen_plantations = set()
    for d in latest_diags:
        if d.plantation_id not in seen_plantations:
            seen_plantations.add(d.plantation_id)
            risk_counts[d.global_risk_level] = risk_counts.get(d.global_risk_level, 0) + 1

    return {
        "generated_at": now.isoformat(),
        "summary": {
            "total_cooperatives": total_coops,
            "active_cooperatives": active_coops,
            "suspended_cooperatives": total_coops - active_coops,
            "inactive_cooperatives_30d": inactive_coop_count,
            "total_users": total_users,
            "total_plantations": total_plantations,
            "total_diagnostics": total_diagnostics,
            "diagnostics_last_30d": diags_last_30d,
            "diagnostics_last_7d": diags_last_7d,
        },
        "risk_distribution": risk_counts,
        "cooperatives": coop_stats,
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
    if role not in ("admin", "agronomist", "technician"):
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

    result = await get_ai_advice(plantation_dict, diag_dict, agro_list, boundary_dict)
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

    return {
        "id": boundary.id,
        "plantation_id": plantation_id,
        "area_hectares": area,
        "points_count": points_count,
        "method": data.method,
        "message": f"Délimitation sauvegardée — {area} ha calculés automatiquement."
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
    """Cree une nouvelle recolte. Reserve aux roles admin et agronomist."""
    if current_user.role not in ("admin", "agronomist"):
        raise HTTPException(status_code=403, detail="Role agronome ou admin requis.")

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
