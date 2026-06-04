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
    }


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

    by_status = {"conforme": 0, "a_verifier": 0, "non_conforme": 0}
    with_poly = 0
    total_score = 0
    total_max = 0
    for p in plantations:
        s = compute_eudr_score(p, db)
        by_status[s.status] = by_status.get(s.status, 0) + 1
        if s.has_polygon:
            with_poly += 1
        total_score += s.score
        total_max += s.max_score

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

    enriched = []
    for p in plantations[:limit]:
        s = compute_eudr_score(p, db)
        enriched.append({
            "id": p.id,
            "name": p.name,
            "producer_id": p.producer_id,
            "owner_name": p.owner_name,
            "region": p.region,
            "hectares": p.hectares,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "eudr_score": s.score,
            "eudr_max": s.max_score,
            "eudr_status": s.status,
            "eudr_color": s.badge_color,
            "has_polygon": s.has_polygon,
            "rules_failed": [r.rule_id for r in s.rules if not r.passed],
        })

    if sort == "name":
        enriched.sort(key=lambda x: (x["name"] or "").lower())
    elif sort == "score":
        enriched.sort(key=lambda x: x["eudr_score"])
    else:  # risk
        status_order = {"non_conforme": 0, "a_verifier": 1, "conforme": 2}
        enriched.sort(key=lambda x: (status_order.get(x["eudr_status"], 9), x["eudr_score"]))

    return {"count": len(enriched), "plantations": enriched}


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
    # Renvoie aussi le score recalcule pour rafraichir l'UI immediatement.
    score = compute_eudr_score(plantation, db)
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

    score = compute_eudr_score(plantation, db)
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
    if current_user.role not in ("admin", "agronomist"):
        raise HTTPException(status_code=403, detail="Generation DDS reservee aux admin/agronome.")
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation:
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    _check_access(plantation, current_user)

    context = build_dds_context(plantation, db, operator_name=operator)
    pdf_bytes = generate_dds_pdf(context)
    filename = dds_filename(plantation)
    # En-tete RFC5987 pour les noms de fichiers avec accents
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )
