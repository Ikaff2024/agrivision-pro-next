"""
Workflow CacaoGuard - cycle de vie complet d'un plan de remediation.

Complete les endpoints `/remediation/plans` existants (list/create/progress)
avec les transitions formelles attendues par la roadmap (section 5.1) :

Plans :
- POST /remediation/plans/{id}/approve   : DRAFT/PENDING_APPROVAL -> APPROVED -> IN_PROGRESS
- POST /remediation/plans/{id}/complete  : IN_PROGRESS/APPROVED   -> COMPLETED (puis CLOSED si close=True)
- POST /remediation/plans/{id}/escalate  : actif                  -> ESCALATED (priorite alerte URGENT)

Actions :
- GET    /remediation/plans/{id}/actions     : liste actions d'un plan
- POST   /remediation/plans/{id}/actions     : ajoute une action a un plan actif
- GET    /remediation/actions/{id}           : detail action
- PUT    /remediation/actions/{id}           : maj action (statut, notes, preuves)
- DELETE /remediation/actions/{id}           : suppression (PENDING uniquement)
- POST   /remediation/actions/{id}/complete  : marque COMPLETED avec preuves obligatoires
"""
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User
from app.db.models_social import (
    ActionStatus,
    ActionType,
    Alert,
    AlertStatus,
    AlertType,
    Priority,
    RemediationAction,
    RemediationPlan,
    RemediationStatus,
)
from app.api.cacaoguard_ops_routes import (
    get_optional_current_user,
    plan_to_dict,
    record_privacy_access,
    require_role,
)
from app.services.social_scope import coop_producer_ids

router = APIRouter(tags=["CacaoGuard - workflow remediation"])


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------

class PlanApproval(BaseModel):
    approval_comments: str = Field(..., min_length=4, max_length=2000)
    supervisor_id: Optional[int] = None
    expected_completion_date: Optional[date] = None


class PlanCompletion(BaseModel):
    outcome: str = Field(..., pattern="^(successful|partial_success|failed)$")
    outcome_description: str = Field(..., min_length=4, max_length=2000)
    close_after: bool = Field(
        default=False,
        description="Si vrai, passe directement a CLOSED apres COMPLETED.",
    )


class PlanEscalation(BaseModel):
    reason: str = Field(..., min_length=4, max_length=2000)
    escalated_to: Optional[int] = Field(
        None,
        description="User id du superviseur escalade. Defaut : premier admin actif.",
    )


class ActionCreate(BaseModel):
    action_type: ActionType
    description: str = Field(..., min_length=4, max_length=2000)
    planned_date: date
    responsible_id: Optional[int] = None
    responsible_organization: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=2000)


class ActionUpdate(BaseModel):
    action_type: Optional[ActionType] = None
    description: Optional[str] = Field(None, min_length=4, max_length=2000)
    planned_date: Optional[date] = None
    responsible_id: Optional[int] = None
    responsible_organization: Optional[str] = Field(None, max_length=200)
    status: Optional[ActionStatus] = None
    notes: Optional[str] = Field(None, max_length=2000)
    evidence: Optional[dict] = None
    impact_assessment: Optional[str] = Field(None, max_length=2000)


class ActionCompletion(BaseModel):
    completed_date: date = Field(default_factory=date.today)
    evidence: dict = Field(
        ...,
        description="Preuves obligatoires : {documents?, photos?, signatures?}. Au moins une cle non vide.",
    )
    impact_assessment: Optional[str] = Field(None, max_length=2000)
    notes: Optional[str] = Field(None, max_length=2000)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

_APPROVAL_FROM = {RemediationStatus.DRAFT, RemediationStatus.PENDING_APPROVAL}
_COMPLETION_FROM = {RemediationStatus.APPROVED, RemediationStatus.IN_PROGRESS}
_ESCALATION_FROM = {
    RemediationStatus.DRAFT,
    RemediationStatus.PENDING_APPROVAL,
    RemediationStatus.APPROVED,
    RemediationStatus.IN_PROGRESS,
}
_FINAL_PLAN_STATUSES = {RemediationStatus.COMPLETED, RemediationStatus.CLOSED}


def _action_to_dict(action: RemediationAction) -> dict:
    return {
        "id": action.id,
        "remediation_plan_id": action.remediation_plan_id,
        "action_type": action.action_type.value,
        "description": action.description,
        "planned_date": action.planned_date,
        "completed_date": action.completed_date,
        "responsible_id": action.responsible_id,
        "responsible_organization": action.responsible_organization,
        "status": action.status.value,
        "notes": action.notes,
        "evidence": action.evidence or {},
        "impact_assessment": action.impact_assessment,
        "created_at": action.created_at,
        "updated_at": action.updated_at,
    }


def _get_plan_or_404(db: Session, plan_id: int, current_user: User | None) -> RemediationPlan:
    # Cloisonnement : le plan doit appartenir à un producteur de la coopérative.
    pids = coop_producer_ids(db, current_user.cooperative_id if current_user else None)
    plan = db.query(RemediationPlan).filter(RemediationPlan.id == plan_id).first()
    if not plan or plan.producer_id not in pids:
        raise HTTPException(status_code=404, detail="Plan de remediation non trouve.")
    return plan


def _get_action_or_404(db: Session, action_id: int, current_user: User | None) -> RemediationAction:
    # Cloisonnement : l'action passe par son plan → producteur → coopérative.
    pids = coop_producer_ids(db, current_user.cooperative_id if current_user else None)
    action = db.query(RemediationAction).filter(RemediationAction.id == action_id).first()
    if action is not None:
        plan = db.query(RemediationPlan).filter(RemediationPlan.id == action.remediation_plan_id).first()
        if not plan or plan.producer_id not in pids:
            action = None
    if not action:
        raise HTTPException(status_code=404, detail="Action de remediation non trouvee.")
    return action


def _validate_user_id(db: Session, user_id: Optional[int], field: str) -> None:
    if user_id is None:
        return
    if not db.query(User).filter(User.id == user_id).first():
        raise HTTPException(status_code=404, detail=f"Utilisateur introuvable ({field}).")


def _first_admin_id(db: Session) -> Optional[int]:
    user = (
        db.query(User)
        .filter(User.role.in_(["admin", "agronomist"]), User.is_active == True)
        .order_by(User.id.asc())
        .first()
    )
    return user.id if user else None


def _evidence_has_content(evidence: Optional[dict]) -> bool:
    if not evidence:
        return False
    return any(bool(v) for v in evidence.values())


# ----------------------------------------------------------------------------
# Plan transitions
# ----------------------------------------------------------------------------

@router.post("/remediation/plans/{plan_id:int}/approve")
def approve_plan(
    plan_id: int,
    payload: PlanApproval,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Approbation formelle : DRAFT/PENDING_APPROVAL -> APPROVED puis IN_PROGRESS.

    Une approbation reglementaire impose un commentaire trace, l'identite
    de l'approbateur, et un superviseur designe.
    """
    require_role(current_user, {"admin", "agronomist"})
    plan = _get_plan_or_404(db, plan_id, current_user)

    if plan.status not in _APPROVAL_FROM:
        raise HTTPException(
            status_code=409,
            detail=f"Approbation refusee : plan en statut {plan.status.value}.",
        )

    _validate_user_id(db, payload.supervisor_id, "supervisor_id")

    approver_id = current_user.id if current_user else _first_admin_id(db)
    if approver_id is None:
        raise HTTPException(status_code=400, detail="Aucun approbateur disponible.")

    plan.status = RemediationStatus.APPROVED
    plan.approved_by = approver_id
    plan.approved_at = datetime.utcnow()
    plan.approval_comments = payload.approval_comments
    if payload.supervisor_id:
        plan.supervisor_id = payload.supervisor_id
    if payload.expected_completion_date:
        plan.expected_completion_date = payload.expected_completion_date
    if plan.start_date is None:
        plan.start_date = date.today()

    # Transition immediate APPROVED -> IN_PROGRESS pour debloquer l'execution
    plan.status = RemediationStatus.IN_PROGRESS

    db.commit()
    db.refresh(plan)
    record_privacy_access(
        db,
        current_user,
        action="approve_remediation_plan",
        source_entity="remediation_plans",
        source_id=plan.id,
        metadata={"reference": plan.plan_reference, "approver_id": approver_id},
    )
    db.commit()
    return plan_to_dict(plan)


@router.post("/remediation/plans/{plan_id:int}/complete")
def complete_plan(
    plan_id: int,
    payload: PlanCompletion,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Cloture COMPLETED (avec outcome obligatoire) ou CLOSED si close_after=True.

    Refuse si des actions sont encore PENDING / IN_PROGRESS / OVERDUE :
    forcer l'execution avant de declarer le plan complete.
    """
    require_role(current_user, {"admin", "agronomist"})
    plan = _get_plan_or_404(db, plan_id, current_user)

    if plan.status not in _COMPLETION_FROM:
        raise HTTPException(
            status_code=409,
            detail=f"Cloture refusee : plan en statut {plan.status.value}.",
        )

    pending = [
        a for a in plan.actions
        if a.status in {ActionStatus.PENDING, ActionStatus.IN_PROGRESS, ActionStatus.OVERDUE}
    ]
    if pending:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{len(pending)} action(s) non terminee(s) bloquent la cloture. "
                "Completer ou annuler les actions d'abord."
            ),
        )

    plan.status = RemediationStatus.CLOSED if payload.close_after else RemediationStatus.COMPLETED
    plan.outcome = payload.outcome
    plan.outcome_description = payload.outcome_description
    plan.actual_completion_date = date.today()

    # Resolution de l'alerte associee au plan
    alert = (
        db.query(Alert)
        .filter(
            Alert.source_entity == "remediation_plans",
            Alert.source_id == plan.id,
            Alert.status != AlertStatus.RESOLVED,
        )
        .first()
    )
    if alert:
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.utcnow()

    db.commit()
    db.refresh(plan)
    record_privacy_access(
        db,
        current_user,
        action="complete_remediation_plan",
        source_entity="remediation_plans",
        source_id=plan.id,
        metadata={
            "reference": plan.plan_reference,
            "outcome": payload.outcome,
            "closed": payload.close_after,
        },
    )
    db.commit()
    return plan_to_dict(plan)


@router.post("/remediation/plans/{plan_id:int}/escalate")
def escalate_plan(
    plan_id: int,
    payload: PlanEscalation,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Escalade vers un superviseur. Aggrave l'alerte associee a URGENT/ESCALATED."""
    require_role(current_user, {"admin", "agronomist"})
    plan = _get_plan_or_404(db, plan_id, current_user)

    if plan.status not in _ESCALATION_FROM:
        raise HTTPException(
            status_code=409,
            detail=f"Escalade refusee : plan en statut {plan.status.value}.",
        )

    _validate_user_id(db, payload.escalated_to, "escalated_to")
    escalated_to = payload.escalated_to or _first_admin_id(db)
    if escalated_to is None:
        raise HTTPException(status_code=400, detail="Aucun destinataire d'escalade disponible.")

    plan.status = RemediationStatus.ESCALATED
    plan.priority = Priority.URGENT
    plan.supervisor_id = escalated_to

    alert = (
        db.query(Alert)
        .filter(
            Alert.source_entity == "remediation_plans",
            Alert.source_id == plan.id,
            Alert.status != AlertStatus.RESOLVED,
        )
        .first()
    )
    if alert:
        alert.priority = Priority.URGENT
        alert.status = AlertStatus.ESCALATED
        alert.escalated_to = escalated_to
        alert.escalated_at = datetime.utcnow()
        alert.escalation_level = (alert.escalation_level or 0) + 1
        alert.message = f"{alert.message} | Escalade : {payload.reason}"
    else:
        db.add(Alert(
            source_entity="remediation_plans",
            source_id=plan.id,
            alert_type=AlertType.OVERDUE_ACTION,
            priority=Priority.URGENT,
            status=AlertStatus.ESCALATED,
            title=f"Plan {plan.plan_reference} escalade",
            message=f"Escalade : {payload.reason}",
            escalated_to=escalated_to,
            escalated_at=datetime.utcnow(),
            escalation_level=1,
            alert_metadata={
                "plan_id": plan.id,
                "reference": plan.plan_reference,
                "reason": payload.reason,
            },
        ))

    db.commit()
    db.refresh(plan)
    record_privacy_access(
        db,
        current_user,
        action="escalate_remediation_plan",
        source_entity="remediation_plans",
        source_id=plan.id,
        metadata={
            "reference": plan.plan_reference,
            "reason": payload.reason,
            "escalated_to": escalated_to,
        },
    )
    db.commit()
    return plan_to_dict(plan)


# ----------------------------------------------------------------------------
# Actions CRUD
# ----------------------------------------------------------------------------

@router.get("/remediation/plans/{plan_id:int}/actions")
def list_plan_actions(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist", "technician"})
    plan = _get_plan_or_404(db, plan_id, current_user)
    return [_action_to_dict(a) for a in plan.actions]


@router.post("/remediation/plans/{plan_id:int}/actions", status_code=201)
def add_plan_action(
    plan_id: int,
    payload: ActionCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    plan = _get_plan_or_404(db, plan_id, current_user)

    if plan.status in _FINAL_PLAN_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Plan en statut final ({plan.status.value}) : ajout d'action interdit.",
        )

    _validate_user_id(db, payload.responsible_id, "responsible_id")

    action = RemediationAction(
        remediation_plan_id=plan.id,
        action_type=payload.action_type,
        description=payload.description,
        planned_date=payload.planned_date,
        responsible_id=payload.responsible_id,
        responsible_organization=payload.responsible_organization,
        notes=payload.notes,
        status=ActionStatus.PENDING,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return _action_to_dict(action)


_VALID_ACTION_TYPES = {t.value for t in ActionType}


@router.post("/remediation/plans/{plan_id:int}/suggest-actions")
def suggest_plan_actions(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Propose (IA) un BROUILLON d'actions de remédiation à partir du profil et des
    facteurs de risque de l'enfant. Ne crée RIEN : renvoie des suggestions que le
    travailleur social revoit puis ajoute. Réservé admin/agronome."""
    require_role(current_user, {"admin", "agronomist"})
    plan = _get_plan_or_404(db, plan_id, current_user)

    from app.db.models_social import Child
    child = db.query(Child).filter(Child.id == plan.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Enfant du plan introuvable.")

    def _age(dob):
        try:
            return int((date.today() - dob).days / 365.25)
        except Exception:  # noqa: BLE001
            return None

    facts = (
        f"- Âge : {_age(child.date_of_birth)} ans ; sexe : {child.gender}.\n"
        f"- Scolarité : {getattr(child.school_status, 'value', child.school_status)}"
        f"{' (école : ' + child.school_name + ')' if getattr(child, 'school_name', None) else ''}.\n"
        f"- Travaille à la ferme : {'oui' if child.is_working_on_farm else 'non'}"
        f"{' — fréquence ' + getattr(child.work_frequency, 'value', str(child.work_frequency)) if child.is_working_on_farm and child.work_frequency else ''}.\n"
        f"- Tâches dangereuses : {', '.join(child.dangerous_tasks_performed) if getattr(child, 'dangerous_tasks_performed', None) else 'aucune signalée'}.\n"
        f"- Niveau de risque : {getattr(child.risk_level, 'value', child.risk_level)} (score {child.risk_score}).\n"
        f"- Facteurs de risque : {child.risk_factors or {}}.\n"
        f"- Objectif du plan : {plan.main_objective}."
    )
    prompt = (
        "Tu es travailleur social spécialiste de la lutte contre le travail des enfants "
        "dans le cacao en Côte d'Ivoire. À partir UNIQUEMENT du profil ci-dessous, propose "
        "3 à 5 actions de remédiation CONCRÈTES et réalisables.\n"
        "EXIGENCES DE SPÉCIFICITÉ (importantes) :\n"
        "- Chaque action doit s'appuyer sur un ÉLÉMENT PRÉCIS du profil (cite l'âge, le statut "
        "scolaire, la fréquence de travail ou la tâche dangereuse concernée) — pas de conseil "
        "passe-partout applicable à n'importe quel enfant.\n"
        "- Si une tâche dangereuse est signalée, au moins une action doit la traiter directement.\n"
        "- Adapte le délai (timeframe_days) à l'urgence : risque critique/élevé = délais courts.\n"
        "- Varie les types d'action (n'empile pas 4 fois le même type) et évite les formulations "
        "génériques type « sensibiliser la famille » sans objet précis.\n"
        'Réponds STRICTEMENT en JSON : une liste d\'objets {"action_type","description",'
        '"timeframe_days"} où action_type ∈ {education, economic_support, awareness, legal, '
        "health, other} ; description = 1 phrase actionnable et SPÉCIFIQUE à cet enfant ; "
        "timeframe_days = entier. N'ajoute aucun texte hors du JSON.\n\n"
        f"PROFIL ENFANT :\n{facts}"
    )
    try:
        from app.services import llm_client
        # Température plus haute : évite des brouillons quasi identiques d'un enfant à l'autre.
        out = llm_client.chat(db, prompt, max_tokens=700, temperature=0.7)
    except llm_client.LLMNotConfigured as ex:
        raise HTTPException(status_code=502, detail=str(ex))
    except Exception as ex:  # noqa: BLE001
        import httpx as _httpx
        if isinstance(ex, _httpx.HTTPError):
            raise HTTPException(status_code=502, detail=f"Fournisseur IA injoignable : {type(ex).__name__}.")
        raise

    import json as _json
    import re as _re
    text = out.get("text") or ""
    m = _re.search(r"\[.*\]", text, _re.DOTALL)
    suggestions = []
    if m:
        try:
            for it in _json.loads(m.group(0)):
                if not isinstance(it, dict):
                    continue
                at = str(it.get("action_type", "other")).strip().lower()
                if at not in _VALID_ACTION_TYPES:
                    at = "other"
                desc = str(it.get("description", "")).strip()
                if not desc:
                    continue
                try:
                    days = int(it.get("timeframe_days") or 30)
                except (TypeError, ValueError):
                    days = 30
                suggestions.append({"action_type": at, "description": desc[:2000],
                                    "timeframe_days": max(1, min(days, 365))})
        except (ValueError, TypeError):
            suggestions = []

    # Suivi du coût (best-effort).
    try:
        from app.db.models import AiUsage
        from app.services.ai_cost import compute_cost_usd
        it_, ot_ = out.get("input_tokens", 0), out.get("output_tokens", 0)
        db.add(AiUsage(
            cooperative_id=current_user.cooperative_id if current_user else None,
            user_id=current_user.id if current_user else None,
            plantation_id=None, feature="remediation_suggest",
            model=out.get("model", ""), input_tokens=it_, output_tokens=ot_,
            cost_usd=compute_cost_usd(it_, ot_, out.get("model")),
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

    return {"plan_id": plan.id, "model": out.get("model"), "suggestions": suggestions}


@router.get("/remediation/actions/{action_id:int}")
def get_action(
    action_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist", "technician"})
    return _action_to_dict(_get_action_or_404(db, action_id, current_user))


@router.put("/remediation/actions/{action_id:int}")
def update_action(
    action_id: int,
    payload: ActionUpdate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    action = _get_action_or_404(db, action_id, current_user)

    if action.status == ActionStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Action deja COMPLETED : reouvrir via un nouvel enregistrement.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    if "responsible_id" in update_data:
        _validate_user_id(db, update_data["responsible_id"], "responsible_id")

    for field, value in update_data.items():
        setattr(action, field, value)

    db.commit()
    db.refresh(action)
    return _action_to_dict(action)


@router.delete("/remediation/actions/{action_id:int}", status_code=204)
def delete_action(
    action_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    require_role(current_user, {"admin", "agronomist"})
    action = _get_action_or_404(db, action_id, current_user)

    if action.status != ActionStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Action en statut {action.status.value} : suppression interdite.",
        )

    db.delete(action)
    db.commit()
    return None


@router.post("/remediation/actions/{action_id:int}/complete")
def complete_action(
    action_id: int,
    payload: ActionCompletion,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    """Cloture d'une action avec preuves obligatoires (audit EUDR)."""
    require_role(current_user, {"admin", "agronomist", "technician"})
    action = _get_action_or_404(db, action_id, current_user)

    if action.status == ActionStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Action deja completee.")
    if action.status == ActionStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Action annulee : impossible a completer.")

    if not _evidence_has_content(payload.evidence):
        raise HTTPException(
            status_code=400,
            detail="Preuves obligatoires : fournir au moins un document/photo/signature.",
        )

    action.status = ActionStatus.COMPLETED
    action.completed_date = payload.completed_date
    action.evidence = payload.evidence
    if payload.impact_assessment:
        action.impact_assessment = payload.impact_assessment
    if payload.notes:
        action.notes = payload.notes

    db.commit()
    db.refresh(action)
    return _action_to_dict(action)
