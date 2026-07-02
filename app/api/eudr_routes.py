"""
Routes EUDR (EU Deforestation Regulation) — Sprint EUDR-01a.

Endpoints :
- GET /plantations/{id}/eudr-score    : breakdown des 5 regles + statut
- GET /plantations/{id}/eudr-status   : version condensee (badge + score)
- GET /eudr/cooperative-summary       : agrege par cooperative
- GET /eudr/plantations               : liste plantations triee par risque

Tous les endpoints sont en lecture seule (le polygone se sauve via
POST /plantations/{id}/boundary qui existe deja dans routes.py).

Permissions :
- admin/agronomist : voient toutes les plantations de leur coop
- technician : voient les plantations qui leur sont assignees
- viewer : interdit
"""
import datetime
import json
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import DeforestationCheck, Plantation, User
from app.eudr.scoring import EUDR_CUTOFF_YEAR, compute_eudr_score
from app.eudr.score_cache import ensure_scores, refresh_plantation_eudr, refresh_all_eudr
from app.services.eudr_reports import build_dds_context, dds_filename, generate_dds_pdf

router = APIRouter(prefix="", tags=["EUDR - conformite parcellaire"])

# Verdicts acceptes pour un controle de deforestation (cadre EUDR-01b).
_DEFORESTATION_VERDICTS = {"clear", "deforestation_detected", "inconclusive"}


class DeforestationCheckCreate(BaseModel):
    verdict: str = Field(description="clear | deforestation_detected | inconclusive")
    source: Optional[str] = Field(
        default="manual",
        description="hansen_gfc | gfw | field_visit | manual",
    )
    forest_loss_year: Optional[int] = Field(default=None, ge=2000, le=2100)
    notes: Optional[str] = None


def _deforestation_check_to_dict(c: DeforestationCheck) -> dict:
    return {
        "id": c.id,
        "plantation_id": c.plantation_id,
        "verdict": c.verdict,
        "source": c.source,
        "forest_loss_year": c.forest_loss_year,
        "notes": c.notes,
        "check_date": c.check_date.isoformat() if c.check_date else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _accessible_plantations(db: Session, user: User) -> list[Plantation]:
    """Liste des plantations visibles pour `user` (scoping cooperative)."""
    query = db.query(Plantation)
    if user.cooperative_id is not None:
        query = query.filter(Plantation.cooperative_id == user.cooperative_id)
    if user.role == "technician":
        # Reuse de PlantationAssignment si disponible
        try:
            from app.db.models import PlantationAssignment
            assigned_ids = [
                a.plantation_id for a in db.query(PlantationAssignment).filter(
                    PlantationAssignment.technician_id == user.id,
                    PlantationAssignment.is_active == True,
                ).all()
            ]
            if assigned_ids:
                query = query.filter(Plantation.id.in_(assigned_ids))
            else:
                return []
        except ImportError:
            pass
    return query.all()


def _check_access(plantation: Plantation, user: User) -> None:
    if user.role == "viewer":
        raise HTTPException(status_code=403, detail="EUDR : role viewer non autorise.")
    if user.cooperative_id is not None and plantation.cooperative_id != user.cooperative_id:
        raise HTTPException(status_code=403, detail="Plantation d'une autre cooperative.")


@router.get("/plantations/{plantation_id}/eudr-score")
def get_eudr_score(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retourne le breakdown complet des 5 regles EUDR + statut."""
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    _check_access(plantation, current_user)
    score = compute_eudr_score(plantation, db)
    return score.to_dict()


@router.get("/plantations/{plantation_id}/eudr-status")
def get_eudr_status(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Version condensee pour les badges (status + score sans le detail)."""
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    _check_access(plantation, current_user)
    s = compute_eudr_score(plantation, db)
    return {
        "plantation_id": s.plantation_id,
        "score": s.score,
        "max_score": s.max_score,
        "status": s.status,
        "badge_color": s.badge_color,
        "has_polygon": s.has_polygon,
        "methodology_version": s.methodology_version,
        "export_waiver": plantation.export_waiver_at is not None,
        "export_waiver_reason": plantation.export_waiver_reason,
    }


class ExportWaiverRequest(BaseModel):
    reason: str = Field(..., min_length=8, max_length=500)


@router.post("/plantations/{plantation_id}/export-waiver")
def grant_export_waiver(
    plantation_id: int,
    data: ExportWaiverRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Derogation export (ADMIN uniquement) : autorise l'expedition de la production
    de cette parcelle malgre une non-conformite EUDR. Tracee (motif, auteur, date)
    et journalisee dans les mouvements du lot au moment de l'expedition."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Derogation export : reservee a l'administrateur.")
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    _check_access(plantation, current_user)
    plantation.export_waiver_reason = data.reason.strip()
    plantation.export_waiver_by = current_user.email
    plantation.export_waiver_at = datetime.datetime.utcnow()
    db.commit()
    return {
        "plantation_id": plantation.id,
        "export_waiver": True,
        "reason": plantation.export_waiver_reason,
        "granted_by": plantation.export_waiver_by,
        "granted_at": plantation.export_waiver_at.isoformat(),
    }


@router.delete("/plantations/{plantation_id}/export-waiver")
def revoke_export_waiver(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retire la derogation export d'une plantation. ADMIN uniquement."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Derogation export : reservee a l'administrateur.")
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    _check_access(plantation, current_user)
    plantation.export_waiver_reason = None
    plantation.export_waiver_by = None
    plantation.export_waiver_at = None
    db.commit()
    return {"plantation_id": plantation.id, "export_waiver": False}


@router.get("/eudr/cooperative-summary")
def get_cooperative_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """KPIs cooperative : % conformes, % a verifier, % non conformes."""
    if current_user.role == "viewer":
        raise HTTPException(status_code=403, detail="EUDR : role viewer non autorise.")
    plantations = _accessible_plantations(db, current_user)
    if not plantations:
        return {
            "total": 0,
            "conforme": 0,
            "a_verifier": 0,
            "non_conforme": 0,
            "with_polygon": 0,
            "without_polygon": 0,
            "average_score": 0.0,
            "compliance_rate_pct": 0.0,
        }

    ensure_scores(plantations, db)  # lit le cache ; calcule les manquants en 1 passe
    by_status = {"conforme": 0, "a_verifier": 0, "non_conforme": 0}
    with_poly = 0
    total_score = 0
    total_max = 0
    for p in plantations:
        by_status[p.eudr_status] = by_status.get(p.eudr_status, 0) + 1
        if p.eudr_has_polygon:
            with_poly += 1
        total_score += p.eudr_score or 0
        total_max += p.eudr_max_score or 0

    total = len(plantations)
    avg = (total_score / total_max * 100) if total_max else 0
    return {
        "total": total,
        "conforme": by_status["conforme"],
        "a_verifier": by_status["a_verifier"],
        "non_conforme": by_status["non_conforme"],
        "with_polygon": with_poly,
        "without_polygon": total - with_poly,
        "average_score_pct": round(avg, 1),
        "compliance_rate_pct": round(by_status["conforme"] / total * 100, 1) if total else 0,
    }


# Ordre d'affichage + libellés/actions des blocages de conformité (les plus
# actionnables d'abord). Les rule_id correspondent à app/eudr/scoring.py.
# EUDR = environnement/géoloc uniquement (le social est dissocié : plus de
# "no_active_block" ici).
_GAP_DEFS = [
    ("polygon_valid", "Parcelles à délimiter", "Tracer le polygone sur la carte"),
    ("no_deforestation", "Contrôle déforestation à faire", "Lancer le contrôle satellite (GFW)"),
    ("recent_inspection", "Inspection de plus de 12 mois", "Planifier une visite terrain"),
    ("area_matches", "Superficie incohérente", "Vérifier la superficie déclarée vs tracé"),
    ("gps_in_cocoa_zone", "Localisation hors zone cacao", "Corriger les coordonnées GPS"),
]


@router.get("/eudr/readiness")
def eudr_readiness(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tableau « Prêt pour l'EUDR » : parcelles regroupées par blocage de conformité.

    Pour chaque règle échouée : le nombre de parcelles concernées + un échantillon
    (jusqu'à 100) avec l'action recommandée, afin de piloter la mise en conformité.
    Lecture seule, réservé aux rôles non-viewer (scope coopérative).
    """
    if current_user.role == "viewer":
        raise HTTPException(status_code=403, detail="EUDR : role viewer non autorise.")

    plantations = _accessible_plantations(db, current_user)
    gaps = {
        rid: {"rule_id": rid, "label": label, "action": action, "count": 0, "plantations": []}
        for rid, label, action in _GAP_DEFS
    }
    ensure_scores(plantations, db)
    total = 0
    ready = 0
    for p in plantations:
        total += 1
        if p.eudr_status == "conforme":
            ready += 1
        for rid in (p.eudr_rules_failed or []):
            if rid in gaps:
                g = gaps[rid]
                g["count"] += 1
                if len(g["plantations"]) < 100:
                    g["plantations"].append({
                        "id": p.id, "name": p.name, "owner_name": p.owner_name,
                    })

    return {
        "total": total,
        "ready": ready,
        "ready_pct": round(ready / total * 100, 1) if total else 0.0,
        "gaps": [gaps[rid] for rid, _, _ in _GAP_DEFS],
    }


@router.get("/eudr/plantations")
def list_plantations_with_eudr(
    sort: str = Query("risk", pattern="^(risk|score|name)$"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste les plantations accessibles avec leur score EUDR.

    `sort=risk` : non_conforme d'abord puis a_verifier puis conforme.
    `sort=score` : score ascendant (faibles d'abord).
    `sort=name` : ordre alphabetique.
    """
    if current_user.role == "viewer":
        raise HTTPException(status_code=403, detail="EUDR : role viewer non autorise.")
    plantations = _accessible_plantations(db, current_user)

    subset = plantations[:limit]
    ensure_scores(subset, db)
    enriched = []
    for p in subset:
        enriched.append({
            "id": p.id,
            "name": p.name,
            "producer_id": p.producer_id,
            "owner_name": p.owner_name,
            "region": p.region,
            "hectares": p.hectares,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "eudr_score": p.eudr_score or 0,
            "eudr_max": p.eudr_max_score or 0,
            "eudr_status": p.eudr_status or "a_verifier",
            "eudr_color": p.eudr_color or "orange",
            "has_polygon": bool(p.eudr_has_polygon),
            "export_waiver": p.export_waiver_at is not None,
            "rules_failed": p.eudr_rules_failed or [],
        })

    if sort == "name":
        enriched.sort(key=lambda x: (x["name"] or "").lower())
    elif sort == "score":
        enriched.sort(key=lambda x: x["eudr_score"])
    else:  # risk
        status_order = {"non_conforme": 0, "a_verifier": 1, "conforme": 2}
        enriched.sort(key=lambda x: (status_order.get(x["eudr_status"], 9), x["eudr_score"]))

    return {"count": len(enriched), "plantations": enriched}


@router.post("/eudr/recompute")
def recompute_eudr_scores(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recalcule et met en cache le score EUDR de toutes les parcelles de la coopérative.

    À lancer après un gros import (ou périodiquement) pour que les agrégats restent
    instantanés. Réservé à la direction (admin / agronome), scope coopérative.
    """
    if current_user.role not in {"admin", "agronomist"}:
        raise HTTPException(status_code=403, detail="Recompute EUDR réservé à la direction.")
    n = refresh_all_eudr(db, coop_id=current_user.cooperative_id)
    return {"recomputed": n}


# ----------------------------------------------------------------------------
# Sprint EUDR-01b : controle de deforestation (cadre extensible Hansen/GFW)
# ----------------------------------------------------------------------------

@router.post("/plantations/{plantation_id}/deforestation-check", status_code=201)
def record_deforestation_check(
    plantation_id: int,
    data: DeforestationCheckCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enregistre un controle de deforestation (regle EUDR R6).

    Cadre extensible : aujourd'hui saisie manuelle / constat terrain ; demain
    rempli automatiquement par l'integration Hansen GFC / Global Forest Watch.
    Reserve admin/agronomist.
    """
    if current_user.role not in ("admin", "agronomist"):
        raise HTTPException(status_code=403, detail="Controle deforestation reserve aux admin/agronome.")
    verdict = (data.verdict or "").lower()
    if verdict not in _DEFORESTATION_VERDICTS:
        raise HTTPException(
            status_code=422,
            detail=f"Verdict invalide. Attendu : {', '.join(sorted(_DEFORESTATION_VERDICTS))}.",
        )
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    _check_access(plantation, current_user)

    check = DeforestationCheck(
        plantation_id=plantation_id,
        verdict=verdict,
        source=data.source or "manual",
        forest_loss_year=data.forest_loss_year,
        notes=data.notes,
        check_date=datetime.datetime.utcnow(),
    )
    db.add(check)
    db.commit()
    db.refresh(check)
    # La déforestation change le score → met à jour le cache + renvoie le score frais.
    score = refresh_plantation_eudr(plantation, db)
    db.commit()
    return {"check": _deforestation_check_to_dict(check), "eudr_score": score.to_dict()}


@router.get("/plantations/{plantation_id}/deforestation-checks")
def list_deforestation_checks(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Historique des controles de deforestation d'une plantation (recent d'abord)."""
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    _check_access(plantation, current_user)
    checks = (
        db.query(DeforestationCheck)
        .filter(DeforestationCheck.plantation_id == plantation_id)
        .order_by(DeforestationCheck.check_date.desc().nullslast(), DeforestationCheck.id.desc())
        .all()
    )
    return {
        "plantation_id": plantation_id,
        "cutoff_year": EUDR_CUTOFF_YEAR,
        "count": len(checks),
        "checks": [_deforestation_check_to_dict(c) for c in checks],
    }


def _verdict_from_deforestation_signal(signal: dict) -> tuple[str, str]:
    """Traduit un signal satellite (Global Forest Watch) en verdict EUDR R6.

    Choix RESPONSABLE : sans donnees reelles (cle GFW absente => 'simulation'),
    on ne declare JAMAIS 'clear' (pas de fausse attestation), on renvoie
    'inconclusive' pour signaler qu'un controle reel reste a faire.
    Retourne (verdict, source).
    """
    if (signal.get("source") or "").lower() == "simulation":
        return "inconclusive", "gfw_simulation"
    if signal.get("loss_detected"):
        return "deforestation_detected", "gfw"
    return "clear", "gfw"


@router.post("/plantations/{plantation_id}/deforestation-check/auto", status_code=201)
def auto_deforestation_check(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Controle de deforestation AUTOMATIQUE via Global Forest Watch (regle R6).

    Interroge GFW sur le POLYGONE de la parcelle et enregistre le verdict, ce qui
    met a jour le score EUDR sans saisie manuelle. Requiert une delimitation.
    Reserve admin/agronomist.

    Mapping (cf. _verdict_from_deforestation_signal) :
      - donnees reelles, 0 alerte post-2020 -> clear (R6 passe)
      - donnees reelles, >=1 alerte          -> deforestation_detected (R6 echoue)
      - simulation (GFW_API_KEY absente)      -> inconclusive (controle reel a faire)
    """
    if current_user.role not in ("admin", "agronomist"):
        raise HTTPException(status_code=403, detail="Controle deforestation reserve aux admin/agronome.")
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    _check_access(plantation, current_user)

    boundary = plantation.boundary
    if boundary is None or not boundary.geojson:
        raise HTTPException(
            status_code=400,
            detail="Delimitez d'abord la parcelle : un polygone est requis pour l'analyse satellite.",
        )
    try:
        geometry = json.loads(boundary.geojson)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="Polygone de la parcelle illisible (GeoJSON invalide).")
    if isinstance(geometry, dict) and geometry.get("type") == "Feature":
        geometry = geometry.get("geometry") or {}

    # Import local : isole la dependance satellite (reseau) du chargement du module.
    from app.satellite.provider import get_deforestation_for_geometry

    signal = get_deforestation_for_geometry(geometry)
    verdict, source = _verdict_from_deforestation_signal(signal)

    check = DeforestationCheck(
        plantation_id=plantation_id,
        verdict=verdict,
        source=source,
        forest_loss_year=None,
        notes=signal.get("note"),
        check_date=datetime.datetime.utcnow(),
    )
    db.add(check)
    db.commit()
    db.refresh(check)

    # Le contrôle déforestation change le score → on MET À JOUR LE CACHE (colonnes
    # eudr_*), sinon la liste/résumé EUDR (qui lisent le cache) restent figés après
    # une vérification satellite / NDVI. (Même correctif que le contrôle manuel.)
    score = refresh_plantation_eudr(plantation, db)
    db.commit()
    return {
        "check": _deforestation_check_to_dict(check),
        "deforestation": signal,
        "eudr_score": score.to_dict(),
        "auto": True,
    }


# ----------------------------------------------------------------------------
# Sprint EUDR-01c : export DDS (Due Diligence Statement) PDF
# ----------------------------------------------------------------------------

@router.get("/plantations/{plantation_id}/eudr-dds.pdf")
def download_eudr_dds(
    plantation_id: int,
    operator: Optional[str] = Query(None, description="Nom de l'operateur a afficher dans la DDS"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Telecharge le Due Diligence Statement (DDS) EUDR de la parcelle au format PDF.

    Reserve aux roles admin/agronomist (document officiel a remettre a un
    auditeur externe). Le PDF inclut : identification parcelle, verdict
    conformite, detail des 5 regles, polygone, liens cooperative, attestation.
    """
    if current_user.role not in ("admin", "agronomist", "gestionnaire"):
        raise HTTPException(status_code=403, detail="Generation DDS reservee aux admin/agronome/gestionnaire.")
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    _check_access(plantation, current_user)

    context = build_dds_context(plantation, db, operator_name=operator)
    # Garde-fou EUDR : ne jamais emettre un DDS base sur des donnees satellite
    # SIMULEES (cle Global Forest Watch absente). Sinon on attesterait une
    # conformite sur une preuve de deforestation fictive.
    if context.get("data_simulation"):
        raise HTTPException(
            status_code=409,
            detail=(
                "DDS bloqué : le contrôle de déforestation repose sur des données "
                "SIMULÉES (Global Forest Watch non configuré). Configurez GFW_API_KEY "
                "puis relancez le contrôle satellite, ou enregistrez un contrôle "
                "terrain, avant d'émettre le Due Diligence Statement."
            ),
        )
    pdf_bytes = generate_dds_pdf(context)
    filename = dds_filename(plantation)
    # En-tete RFC5987 pour les noms de fichiers avec accents
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )
