"""
Certification (module #3) : audits, non-conformites, actions correctives et echeances.

S'appuie sur le referentiel `Certification` deja seede (FT, RA, EUDR, ARS_1000).
Tout est cloisonne par cooperative ; ecriture reservee admin/agronomist.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import (
    Certification, CertificationAudit, NonConformity, Plantation, PlantationCertification, User,
)

router = APIRouter(tags=["Certification"])

_WRITE = {"admin", "agronomist", "gestionnaire"}
_AUDIT_STATUS = {"planned", "in_progress", "completed"}
_AUDIT_RESULT = {"pass", "conditional", "fail"}
_SEVERITY = {"minor", "major", "critical"}
_NC_STATUS = {"open", "in_progress", "resolved", "closed"}


# ── Payloads ─────────────────────────────────────────────────────────────────

class AuditCreate(BaseModel):
    certification_id: Optional[int] = None
    audit_date: Optional[datetime] = None
    audit_type: str = Field("internal", max_length=30)
    auditor_name: Optional[str] = Field(None, max_length=200)
    auditor_body: Optional[str] = Field(None, max_length=200)
    scope: Optional[str] = None
    notes: Optional[str] = None


class AuditComplete(BaseModel):
    result: str
    score_pct: Optional[float] = Field(None, ge=0, le=100)
    notes: Optional[str] = None


class NonConformityCreate(BaseModel):
    audit_id: Optional[int] = None
    certification_id: Optional[int] = None
    reference: Optional[str] = Field(None, max_length=120)
    severity: str = Field("minor")
    description: str = Field(..., min_length=3)
    corrective_action: Optional[str] = None
    responsible: Optional[str] = Field(None, max_length=200)
    due_date: Optional[date] = None


class NonConformityUpdate(BaseModel):
    status: Optional[str] = None
    corrective_action: Optional[str] = None
    responsible: Optional[str] = Field(None, max_length=200)
    due_date: Optional[date] = None
    resolution_notes: Optional[str] = None


def _coop_id(user: User):
    return user.cooperative_id


def _require_write(user: User) -> None:
    if user.role not in _WRITE:
        raise HTTPException(status_code=403, detail="Action reservee a l'administrateur / agronome.")


def _is_overdue(nc: NonConformity) -> bool:
    return bool(nc.due_date and nc.status not in {"resolved", "closed"} and nc.due_date < date.today())


# ── Serializers ──────────────────────────────────────────────────────────────

def audit_to_dict(a: CertificationAudit, cert_code: Optional[str] = None, nc_count: int = 0) -> dict:
    return {
        "id": a.id, "certification_id": a.certification_id, "certification_code": cert_code,
        "audit_date": a.audit_date, "audit_type": a.audit_type,
        "auditor_name": a.auditor_name, "auditor_body": a.auditor_body,
        "scope": a.scope, "status": a.status, "result": a.result,
        "score_pct": a.score_pct, "notes": a.notes,
        "non_conformity_count": nc_count, "created_at": a.created_at,
    }


def nc_to_dict(nc: NonConformity, cert_code: Optional[str] = None) -> dict:
    return {
        "id": nc.id, "audit_id": nc.audit_id, "certification_id": nc.certification_id,
        "certification_code": cert_code, "reference": nc.reference, "severity": nc.severity,
        "description": nc.description, "corrective_action": nc.corrective_action,
        "responsible": nc.responsible, "due_date": nc.due_date, "status": nc.status,
        "resolved_date": nc.resolved_date, "resolution_notes": nc.resolution_notes,
        "overdue": _is_overdue(nc), "created_at": nc.created_at,
    }


def _cert_codes(db: Session, ids: set) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {c.id: c.code for c in db.query(Certification).filter(Certification.id.in_(ids)).all()}


def _scoped_plantation(db: Session, plantation_id: int, user: User) -> Plantation:
    """Charge une plantation en respectant le cloisonnement par cooperative."""
    plantation = db.query(Plantation).filter(Plantation.id == plantation_id).first()
    if not plantation or (_coop_id(user) is not None and plantation.cooperative_id != _coop_id(user)):
        raise HTTPException(status_code=404, detail="Plantation introuvable.")
    return plantation


class PlantationCertAssign(BaseModel):
    """Affecte une certification a une parcelle (par id OU par code, ex. 'FT')."""
    certification_id: Optional[int] = None
    code: Optional[str] = Field(None, max_length=40)
    date_obtention: Optional[date] = None
    date_expiration: Optional[date] = None


def _resolve_cert(db: Session, data: PlantationCertAssign) -> Optional[Certification]:
    if data.certification_id:
        return db.query(Certification).filter(Certification.id == data.certification_id).first()
    if data.code:
        return db.query(Certification).filter(Certification.code == data.code.strip().upper()).first()
    return None


# ── Certifications d'une parcelle (affectation hors import de registre) ────────

@router.get("/plantations/{plantation_id:int}/certifications")
def list_plantation_certifications(
    plantation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste les certifications portees par une parcelle."""
    _scoped_plantation(db, plantation_id, current_user)
    links = db.query(PlantationCertification).filter(
        PlantationCertification.plantation_id == plantation_id
    ).all()
    codes = _cert_codes(db, {l.certification_id for l in links})
    return [{
        "id": l.id,
        "certification_id": l.certification_id,
        "code": codes.get(l.certification_id),
        "date_obtention": l.date_obtention,
        "date_expiration": l.date_expiration,
    } for l in links]


@router.post("/plantations/{plantation_id:int}/certifications")
def assign_plantation_certification(
    plantation_id: int,
    data: PlantationCertAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Affecte une certification a une parcelle (idempotent). Admin / agronome / gestionnaire."""
    _require_write(current_user)
    _scoped_plantation(db, plantation_id, current_user)
    cert = _resolve_cert(db, data)
    if not cert:
        raise HTTPException(status_code=404, detail="Certification introuvable (id ou code).")
    link = db.query(PlantationCertification).filter(
        PlantationCertification.plantation_id == plantation_id,
        PlantationCertification.certification_id == cert.id,
    ).first()
    if not link:
        link = PlantationCertification(
            plantation_id=plantation_id,
            certification_id=cert.id,
            date_obtention=data.date_obtention,
            date_expiration=data.date_expiration,
        )
        db.add(link)
        db.commit()
        db.refresh(link)
    return {"id": link.id, "plantation_id": plantation_id, "certification_id": cert.id, "code": cert.code}


@router.delete("/plantations/{plantation_id:int}/certifications/{certification_id:int}")
def remove_plantation_certification(
    plantation_id: int,
    certification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retire une certification d'une parcelle. Admin / agronome / gestionnaire."""
    _require_write(current_user)
    _scoped_plantation(db, plantation_id, current_user)
    deleted = db.query(PlantationCertification).filter(
        PlantationCertification.plantation_id == plantation_id,
        PlantationCertification.certification_id == certification_id,
    ).delete()
    db.commit()
    return {"deleted": bool(deleted), "plantation_id": plantation_id, "certification_id": certification_id}


# ── Referentiel ──────────────────────────────────────────────────────────────

@router.get("/certifications")
def list_certifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Liste les standards de certification disponibles (referentiel)."""
    rows = db.query(Certification).filter(Certification.actif == True).order_by(Certification.code).all()
    return [{"id": c.id, "code": c.code, "nom_complet": c.nom_complet, "organisme": c.organisme} for c in rows]


# ── Audits ───────────────────────────────────────────────────────────────────

@router.get("/certification-audits")
def list_audits(
    status: Optional[str] = None,
    certification_id: Optional[int] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(CertificationAudit)
    if _coop_id(current_user) is not None:
        q = q.filter(CertificationAudit.cooperative_id == _coop_id(current_user))
    if status:
        q = q.filter(CertificationAudit.status == status)
    if certification_id:
        q = q.filter(CertificationAudit.certification_id == certification_id)
    audits = q.order_by(CertificationAudit.audit_date.desc()).limit(limit).all()
    codes = _cert_codes(db, {a.certification_id for a in audits})
    return [audit_to_dict(a, codes.get(a.certification_id), len(a.non_conformities)) for a in audits]


@router.post("/certification-audits", status_code=201)
def create_audit(data: AuditCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_write(current_user)
    if data.audit_type not in {"internal", "external", "surveillance"}:
        raise HTTPException(status_code=400, detail="Type d'audit invalide.")
    a = CertificationAudit(
        cooperative_id=_coop_id(current_user),
        certification_id=data.certification_id,
        audit_date=data.audit_date or datetime.utcnow(),
        audit_type=data.audit_type, auditor_name=data.auditor_name,
        auditor_body=data.auditor_body, scope=data.scope, notes=data.notes,
        status="planned", created_by_id=current_user.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    codes = _cert_codes(db, {a.certification_id})
    return audit_to_dict(a, codes.get(a.certification_id), 0)


@router.get("/certification-audits/{audit_id:int}")
def get_audit(audit_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    a = db.query(CertificationAudit).filter(CertificationAudit.id == audit_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Audit introuvable.")
    if _coop_id(current_user) is not None and a.cooperative_id != _coop_id(current_user):
        raise HTTPException(status_code=403, detail="Audit d'une autre cooperative.")
    codes = _cert_codes(db, {a.certification_id})
    data = audit_to_dict(a, codes.get(a.certification_id), len(a.non_conformities))
    data["non_conformities"] = [nc_to_dict(nc, codes.get(nc.certification_id)) for nc in a.non_conformities]
    return data


@router.post("/certification-audits/{audit_id:int}/complete")
def complete_audit(audit_id: int, data: AuditComplete, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_write(current_user)
    a = db.query(CertificationAudit).filter(CertificationAudit.id == audit_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Audit introuvable.")
    if _coop_id(current_user) is not None and a.cooperative_id != _coop_id(current_user):
        raise HTTPException(status_code=403, detail="Audit d'une autre cooperative.")
    if data.result not in _AUDIT_RESULT:
        raise HTTPException(status_code=400, detail=f"Resultat invalide : {sorted(_AUDIT_RESULT)}.")
    a.status = "completed"
    a.result = data.result
    a.score_pct = data.score_pct
    if data.notes:
        a.notes = data.notes
    db.commit()
    db.refresh(a)
    codes = _cert_codes(db, {a.certification_id})
    return audit_to_dict(a, codes.get(a.certification_id), len(a.non_conformities))


# ── Non-conformites ──────────────────────────────────────────────────────────

@router.get("/non-conformities")
def list_non_conformities(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    overdue: Optional[bool] = None,
    limit: int = Query(300, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(NonConformity)
    if _coop_id(current_user) is not None:
        q = q.filter(NonConformity.cooperative_id == _coop_id(current_user))
    if status:
        q = q.filter(NonConformity.status == status)
    if severity:
        q = q.filter(NonConformity.severity == severity)
    rows = q.order_by(NonConformity.created_at.desc()).limit(limit).all()
    codes = _cert_codes(db, {nc.certification_id for nc in rows})
    out = [nc_to_dict(nc, codes.get(nc.certification_id)) for nc in rows]
    if overdue is not None:
        out = [d for d in out if d["overdue"] == overdue]
    return out


@router.post("/non-conformities", status_code=201)
def create_non_conformity(data: NonConformityCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_write(current_user)
    if data.severity not in _SEVERITY:
        raise HTTPException(status_code=400, detail=f"Severite invalide : {sorted(_SEVERITY)}.")
    cert_id = data.certification_id
    if data.audit_id is not None:
        audit = db.query(CertificationAudit).filter(CertificationAudit.id == data.audit_id).first()
        if not audit:
            raise HTTPException(status_code=404, detail="Audit introuvable.")
        if _coop_id(current_user) is not None and audit.cooperative_id != _coop_id(current_user):
            raise HTTPException(status_code=403, detail="Audit d'une autre cooperative.")
        cert_id = cert_id or audit.certification_id
    nc = NonConformity(
        cooperative_id=_coop_id(current_user),
        audit_id=data.audit_id, certification_id=cert_id,
        reference=data.reference, severity=data.severity, description=data.description,
        corrective_action=data.corrective_action, responsible=data.responsible,
        due_date=data.due_date, status="open", created_by_id=current_user.id,
    )
    db.add(nc)
    db.commit()
    db.refresh(nc)
    codes = _cert_codes(db, {nc.certification_id})
    return nc_to_dict(nc, codes.get(nc.certification_id))


@router.patch("/non-conformities/{nc_id:int}")
def update_non_conformity(nc_id: int, data: NonConformityUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_write(current_user)
    nc = db.query(NonConformity).filter(NonConformity.id == nc_id).first()
    if not nc:
        raise HTTPException(status_code=404, detail="Non-conformite introuvable.")
    if _coop_id(current_user) is not None and nc.cooperative_id != _coop_id(current_user):
        raise HTTPException(status_code=403, detail="Non-conformite d'une autre cooperative.")
    if data.status is not None:
        if data.status not in _NC_STATUS:
            raise HTTPException(status_code=400, detail=f"Statut invalide : {sorted(_NC_STATUS)}.")
        nc.status = data.status
        if data.status in {"resolved", "closed"} and not nc.resolved_date:
            nc.resolved_date = date.today()
    if data.corrective_action is not None:
        nc.corrective_action = data.corrective_action
    if data.responsible is not None:
        nc.responsible = data.responsible
    if data.due_date is not None:
        nc.due_date = data.due_date
    if data.resolution_notes is not None:
        nc.resolution_notes = data.resolution_notes
    db.commit()
    db.refresh(nc)
    codes = _cert_codes(db, {nc.certification_id})
    return nc_to_dict(nc, codes.get(nc.certification_id))


# ── Synthese ─────────────────────────────────────────────────────────────────

# ── Cockpit certification : couverture, échéances, registre, affectation en masse ─

def _exp_date(link: PlantationCertification):
    """Date d'expiration en `date` (le champ est un DateTime) — None si absente."""
    d = link.date_expiration
    if d is None:
        return None
    return d.date() if hasattr(d, "date") else d


def _link_status(link: PlantationCertification, today: date) -> str:
    d = _exp_date(link)
    if d is None:
        return "valid"            # pas d'échéance connue
    if d < today:
        return "expired"
    if d <= today + timedelta(days=90):
        return "expiring"
    return "valid"


@router.get("/certification/coverage")
def certification_coverage(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Couverture par standard : parcelles/producteurs/surface certifiés + échéances.

    Cloisonné par coopérative. Sert le cockpit (KPI par certification + alertes)."""
    coop = _coop_id(current_user)
    pq = db.query(Plantation)
    if coop is not None:
        pq = pq.filter(Plantation.cooperative_id == coop)
    plantations = pq.all()
    ha_by_pid = {p.id: float(p.hectares or 0) for p in plantations}
    prod_by_pid = {p.id: p.producer_id for p in plantations}
    pid_set = set(ha_by_pid.keys())

    links = (
        db.query(PlantationCertification)
        .filter(PlantationCertification.plantation_id.in_(pid_set)).all()
        if pid_set else []
    )
    certs = db.query(Certification).filter(Certification.actif == True).order_by(Certification.code).all()
    today = date.today()

    total_hectares = round(sum(ha_by_pid.values()), 2)
    coverage = []
    for c in certs:
        clinks = [l for l in links if l.certification_id == c.id]
        cert_pids = {l.plantation_id for l in clinks}
        producers = {prod_by_pid.get(pid) for pid in cert_pids if prod_by_pid.get(pid)}
        hectares = round(sum(ha_by_pid.get(pid, 0) for pid in cert_pids), 2)
        statuses = [_link_status(l, today) for l in clinks]
        coverage.append({
            "certification_id": c.id, "code": c.code, "nom_complet": c.nom_complet,
            "plantations_certified": len(cert_pids),
            "producers_certified": len(producers),
            "hectares_certified": hectares,
            "pct_plantations": round(len(cert_pids) / len(pid_set) * 100, 1) if pid_set else 0.0,
            "pct_hectares": round(hectares / total_hectares * 100, 1) if total_hectares else 0.0,
            "expired": statuses.count("expired"),
            "expiring_soon": statuses.count("expiring"),   # ≤ 90 jours
        })
    return {
        "total_plantations": len(pid_set),
        "total_hectares": total_hectares,
        "certifications": coverage,
    }


@router.get("/certification/register")
def certification_register(
    code: Optional[str] = Query(None, description="Filtre par code certification (FT, RA…)"),
    status: Optional[str] = Query(None, description="valid | expiring | expired"),
    limit: int = Query(2000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registre certifié : une ligne par parcelle × certification (exportable CSV)."""
    coop = _coop_id(current_user)
    pq = db.query(Plantation)
    if coop is not None:
        pq = pq.filter(Plantation.cooperative_id == coop)
    plantations = {p.id: p for p in pq.all()}
    if not plantations:
        return {"count": 0, "rows": []}

    lq = db.query(PlantationCertification).filter(
        PlantationCertification.plantation_id.in_(plantations.keys())
    )
    if code:
        cert = db.query(Certification).filter(Certification.code == code.strip().upper()).first()
        if not cert:
            return {"count": 0, "rows": []}
        lq = lq.filter(PlantationCertification.certification_id == cert.id)
    links = lq.limit(limit).all()
    codes = _cert_codes(db, {l.certification_id for l in links})
    # Producteurs (pour le nom) — chargés en une passe.
    from app.db.models import Producer
    prod_ids = {plantations[l.plantation_id].producer_id for l in links if l.plantation_id in plantations}
    prod_ids = {pid for pid in prod_ids if pid}
    producers = {
        p.id: p.nom_complet
        for p in (db.query(Producer).filter(Producer.id.in_(prod_ids)).all() if prod_ids else [])
    }
    today = date.today()
    rows = []
    for l in links:
        p = plantations.get(l.plantation_id)
        if not p:
            continue
        st = _link_status(l, today)
        if status and st != status:
            continue
        exp = _exp_date(l)
        obt = l.date_obtention.date() if (l.date_obtention and hasattr(l.date_obtention, "date")) else l.date_obtention
        rows.append({
            "plantation_id": p.id, "plantation_name": p.name,
            "producer_name": producers.get(p.producer_id) or "",
            "certification_id": l.certification_id, "code": codes.get(l.certification_id),
            "hectares": float(p.hectares or 0),
            "date_obtention": obt.isoformat() if obt else None,
            "date_expiration": exp.isoformat() if exp else None,
            "status": st,
        })
    return {"count": len(rows), "rows": rows}


class BulkCertAssign(BaseModel):
    certification_id: Optional[int] = None
    code: Optional[str] = Field(None, max_length=40)
    plantation_ids: list[int] = Field(default_factory=list)
    date_obtention: Optional[date] = None
    date_expiration: Optional[date] = None


@router.post("/certification/bulk-assign")
def bulk_assign_certification(
    data: BulkCertAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Affecte une certification à plusieurs parcelles d'un coup (idempotent).

    Met à jour les dates si le lien existe déjà. Admin / agronome / gestionnaire."""
    _require_write(current_user)
    cert = _resolve_cert(db, PlantationCertAssign(certification_id=data.certification_id, code=data.code))
    if not cert:
        raise HTTPException(status_code=404, detail="Certification introuvable (id ou code).")
    coop = _coop_id(current_user)
    valid_ids = {
        p.id for p in db.query(Plantation.id, Plantation.cooperative_id)
        .filter(Plantation.id.in_(data.plantation_ids)).all()
        if coop is None or p.cooperative_id == coop
    } if data.plantation_ids else set()
    created, updated = 0, 0
    obt = datetime(data.date_obtention.year, data.date_obtention.month, data.date_obtention.day) if data.date_obtention else None
    exp = datetime(data.date_expiration.year, data.date_expiration.month, data.date_expiration.day) if data.date_expiration else None
    for pid in valid_ids:
        link = db.query(PlantationCertification).filter(
            PlantationCertification.plantation_id == pid,
            PlantationCertification.certification_id == cert.id,
        ).first()
        if link:
            if obt is not None:
                link.date_obtention = obt
            if exp is not None:
                link.date_expiration = exp
            updated += 1
        else:
            db.add(PlantationCertification(
                plantation_id=pid, certification_id=cert.id,
                date_obtention=obt, date_expiration=exp,
            ))
            created += 1
    db.commit()
    return {"certification": cert.code, "created": created, "updated": updated,
            "requested": len(data.plantation_ids), "applied": len(valid_ids)}


class BulkCertRemove(BaseModel):
    certification_id: int
    plantation_ids: list[int] = Field(default_factory=list)


@router.post("/certification/bulk-remove")
def bulk_remove_certification(
    data: BulkCertRemove,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retire une certification de plusieurs parcelles d'un coup. Admin/agronome/gestionnaire."""
    _require_write(current_user)
    coop = _coop_id(current_user)
    valid_ids = {
        p.id for p in db.query(Plantation.id, Plantation.cooperative_id)
        .filter(Plantation.id.in_(data.plantation_ids)).all()
        if coop is None or p.cooperative_id == coop
    } if data.plantation_ids else set()
    deleted = 0
    if valid_ids:
        deleted = db.query(PlantationCertification).filter(
            PlantationCertification.plantation_id.in_(valid_ids),
            PlantationCertification.certification_id == data.certification_id,
        ).delete(synchronize_session=False)
        db.commit()
    return {"deleted": deleted, "certification_id": data.certification_id}


@router.get("/certification/summary")
def certification_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    aq = db.query(CertificationAudit)
    nq = db.query(NonConformity)
    if _coop_id(current_user) is not None:
        aq = aq.filter(CertificationAudit.cooperative_id == _coop_id(current_user))
        nq = nq.filter(NonConformity.cooperative_id == _coop_id(current_user))
    audits = aq.all()
    ncs = nq.all()
    open_ncs = [nc for nc in ncs if nc.status not in {"resolved", "closed"}]
    return {
        "audits_total": len(audits),
        "audits_planned": len([a for a in audits if a.status == "planned"]),
        "audits_completed": len([a for a in audits if a.status == "completed"]),
        "non_conformities_total": len(ncs),
        "non_conformities_open": len(open_ncs),
        "non_conformities_overdue": len([nc for nc in open_ncs if _is_overdue(nc)]),
        "by_severity": {
            s: len([nc for nc in open_ncs if nc.severity == s]) for s in sorted(_SEVERITY)
        },
    }
