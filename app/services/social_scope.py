"""Cloisonnement multi-tenant des entités sociales / CacaoGuard.

Les entités sociales (Child, Alert, RemediationPlan, MonitoringVisit…) ne portent
PAS de `cooperative_id` direct : elles sont rattachées à une coopérative
INDIRECTEMENT via le producteur (`producer_id` → `Producer.cooperative_id`).
Ce module centralise le filtrage par coopérative afin d'éviter toute fuite
inter-tenant (ex. une alerte/notification d'une coop visible par une autre).

Principe FAIL-CLOSED : si l'utilisateur n'a pas de coopérative, ou si une entité
ne peut pas être rattachée à un producteur de sa coop, elle est EXCLUE.
"""
from __future__ import annotations

from typing import Optional, Set

from sqlalchemy.orm import Session

from app.db.models import Producer, User
from app.db.models_social import (
    Alert,
    Child,
    Complaint,
    MonitoringVisit,
    RemediationAction,
    RemediationPlan,
    RiskAssessment,
    SsrtePlantationVisit,
    TraceabilityBlock,
)


def coop_producer_ids(db: Session, coop_id: Optional[int]) -> Set[int]:
    """IDs des producteurs de la coopérative (ensemble vide si pas de coop)."""
    if coop_id is None:
        return set()
    return {pid for (pid,) in db.query(Producer.id).filter(Producer.cooperative_id == coop_id).all()}


def coop_alert_ids(db: Session, coop_id: Optional[int]) -> Set[int]:
    """IDs des alertes appartenant à la coopérative.

    Résout chaque alerte via son entité source (`source_entity`/`source_id`)
    jusqu'au producteur, puis ne garde que celles d'un producteur de la coop.
    FAIL-CLOSED : toute alerte non rattachable est exclue.
    """
    pids = coop_producer_ids(db, coop_id)
    if not pids:
        return set()
    pid_list = list(pids)

    def ids_by_producer(model) -> Set[int]:
        col = getattr(model, "producer_id", None)
        if col is None:
            return set()
        return {i for (i,) in db.query(model.id).filter(col.in_(pid_list)).all()}

    # source_entity → ensemble des source_id valides pour cette coop
    valid: dict[str, Set[int]] = {
        "producers": set(pids),
        "children": ids_by_producer(Child),
        "risk_assessments": ids_by_producer(RiskAssessment),
        "monitoring_visits": ids_by_producer(MonitoringVisit),
        "remediation_plans": ids_by_producer(RemediationPlan),
        "traceability_blocks": ids_by_producer(TraceabilityBlock),
        "complaints": ids_by_producer(Complaint),
        "ssrte_plantation_visits": ids_by_producer(SsrtePlantationVisit),
    }
    # remediation_actions → via le plan → producteur
    plan_ids = valid["remediation_plans"]
    if plan_ids:
        valid["remediation_actions"] = {
            i for (i,) in db.query(RemediationAction.id).filter(
                RemediationAction.remediation_plan_id.in_(list(plan_ids))
            ).all()
        }

    result: Set[int] = set()
    for entity, source_ids in valid.items():
        if not source_ids:
            continue
        rows = db.query(Alert.id).filter(
            Alert.source_entity == entity,
            Alert.source_id.in_(list(source_ids)),
        ).all()
        result.update(i for (i,) in rows)
    return result


def coop_complaint_ids(db: Session, coop_id: Optional[int]) -> Set[int]:
    """IDs des signalements (Complaint) appartenant à la coopérative.

    Un signalement est rattaché à une coop s'il vise un producteur/enfant de
    la coop, OU s'il a été créé par un utilisateur de la coop. Les signalements
    anonymes non rattachés (aucun producteur/enfant, aucun auteur) ne sont
    visibles d'aucune coopérative (fail-closed).
    """
    if coop_id is None:
        return set()
    pids = coop_producer_ids(db, coop_id)
    pid_list = list(pids)
    result: Set[int] = set()

    if pid_list:
        result |= {i for (i,) in db.query(Complaint.id).filter(Complaint.producer_id.in_(pid_list)).all()}
        child_ids = [i for (i,) in db.query(Child.id).filter(Child.producer_id.in_(pid_list)).all()]
        if child_ids:
            result |= {i for (i,) in db.query(Complaint.id).filter(Complaint.child_id.in_(child_ids)).all()}

    user_ids = [i for (i,) in db.query(User.id).filter(User.cooperative_id == coop_id).all()]
    if user_ids:
        result |= {i for (i,) in db.query(Complaint.id).filter(Complaint.created_by.in_(user_ids)).all()}
    return result
