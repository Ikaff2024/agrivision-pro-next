"""
CacaoPilot OS - Module Social (CacaoGuard)
Modèles de données pour la protection de l'enfant et le monitoring social.
Version: v1.0.0
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Date, Time, Enum as SQLEnum, JSON, Numeric, UniqueConstraint
from sqlalchemy.orm import relationship, deferred
from sqlalchemy.sql import func
from app.db.database import Base
import enum


# ==================== ENUMS ====================

class RiskLevel(str, enum.Enum):
    """Niveaux de risque pour les évaluations sociales."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AssessmentType(str, enum.Enum):
    """Types d'évaluation des risques."""
    INITIAL = "initial"
    ANNUAL = "annual"
    FOLLOW_UP = "follow_up"
    COMPLAINT = "complaint"
    EMERGENCY = "emergency"


class AssessmentStatus(str, enum.Enum):
    """Statuts d'une évaluation."""
    DRAFT = "draft"
    COMPLETED = "completed"
    VALIDATED = "validated"
    ESCALATED = "escalated"


class VisitType(str, enum.Enum):
    """Types de visites de monitoring."""
    ROUTINE = "routine"
    FOLLOW_UP = "follow_up"
    COMPLAINT = "complaint"
    EMERGENCY = "emergency"


class VisitStatus(str, enum.Enum):
    """Statuts d'une visite."""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Priority(str, enum.Enum):
    """Niveaux de priorité."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class RemediationStatus(str, enum.Enum):
    """Statuts d'un plan de remédiation."""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED = "closed"
    ESCALATED = "escalated"


class ActionType(str, enum.Enum):
    """Types d'actions de remédiation."""
    EDUCATION = "education"
    ECONOMIC_SUPPORT = "economic_support"
    AWARENESS = "awareness"
    LEGAL = "legal"
    HEALTH = "health"
    OTHER = "other"


class ActionStatus(str, enum.Enum):
    """Statuts d'une action."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class TrainingType(str, enum.Enum):
    """Types de formations."""
    CHILD_PROTECTION = "child_protection"
    PARENTING = "parenting"
    LEGAL_RIGHTS = "legal_rights"
    ECONOMIC_EMPOWERMENT = "economic_empowerment"
    OTHER = "other"


class TrainingStatus(str, enum.Enum):
    """Statuts d'une session de formation."""
    PLANNED = "planned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"


class BlockReason(str, enum.Enum):
    """Motifs de blocage de traçabilité."""
    CHILD_LABOR_CASE = "child_labor_case"
    PENDING_INVESTIGATION = "pending_investigation"
    NON_COMPLIANCE = "non_compliance"
    AUDIT_FAILURE = "audit_failure"
    OTHER = "other"


class BlockStatus(str, enum.Enum):
    """Statuts d'un blocage."""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    EXPIRED = "expired"


class AlertType(str, enum.Enum):
    """Types d'alertes."""
    HIGH_RISK_CHILD = "high_risk_child"
    MISSED_VISIT = "missed_visit"
    OVERDUE_ACTION = "overdue_action"
    COMPLAINT = "complaint"
    AUDIT_FAILURE = "audit_failure"
    TRACEABILITY_BLOCK = "traceability_block"


class AlertStatus(str, enum.Enum):
    """Statuts d'une alerte."""
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    FALSE_POSITIVE = "false_positive"


class ComplaintType(str, enum.Enum):
    """Types de plaintes."""
    CHILD_LABOR = "child_labor"
    ABUSE = "abuse"
    EXPLOITATION = "exploitation"
    TRAFFICKING = "trafficking"
    OTHER = "other"


class ComplaintSeverity(str, enum.Enum):
    """Sévérité d'une plainte."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplaintStatus(str, enum.Enum):
    """Statuts d'une plainte."""
    RECEIVED = "received"
    UNDER_REVIEW = "under_review"
    INVESTIGATING = "investigating"
    SUBSTANTIATED = "substantiated"
    UNSUBSTANTIATED = "unsubstantiated"
    CLOSED = "closed"
    ESCALATED = "escalated"


class SchoolStatus(str, enum.Enum):
    """Statut scolaire d'un enfant."""
    NOT_SCHOOL_AGE = "not_school_age"
    ENROLLED = "enrolled"
    DROPPED_OUT = "dropped_out"
    NEVER_ENROLLED = "never_enrolled"
    COMPLETED = "completed"


class WorkFrequency(str, enum.Enum):
    """Fréquence de travail d'un enfant."""
    NEVER = "never"
    OCCASIONAL = "occasional"
    REGULAR = "regular"
    DAILY = "daily"


# ==================== MODÈLES ====================

class Child(Base):
    """
    Enfant d'un producteur.
    Modèle central pour le suivi de la protection de l'enfant.
    """
    __tablename__ = "children"

    id = Column(Integer, primary_key=True, index=True)
    producer_id = Column(Integer, ForeignKey("producers.id", ondelete="CASCADE"), nullable=False, index=True)

    # Informations enfant
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    date_of_birth = Column(Date, nullable=False)  # Critique pour calcul âge
    gender = Column(String(1), nullable=False)  # 'M' | 'F'
    birth_certificate_number = Column(String(50), nullable=True)  # Numéro acte de naissance

    # Statut scolaire
    school_status = Column(SQLEnum(SchoolStatus), default=SchoolStatus.NOT_SCHOOL_AGE)
    school_name = Column(String(200), nullable=True)
    school_grade = Column(String(20), nullable=True)  # Classe (CI, CP1, CP2, CE1, etc.)
    school_distance_km = Column(Numeric(5, 2), nullable=True)  # Distance école en km
    school_attendance_rate = Column(Numeric(5, 2), nullable=True)  # Taux de fréquentation %

    # Évaluation risque
    risk_score = Column(Numeric(5, 2), default=0)  # Score calculé 0-100
    risk_level = Column(SQLEnum(RiskLevel), default=RiskLevel.NONE, index=True)
    risk_factors = Column(JSON, nullable=True)  # Facteurs de risque détaillés

    # Statut protection
    is_working_on_farm = Column(Boolean, default=False)
    work_frequency = Column(SQLEnum(WorkFrequency), default=WorkFrequency.NEVER)
    dangerous_tasks_performed = Column(JSON, nullable=True)  # Liste des tâches dangereuses

    # Suivi
    last_assessment_date = Column(Date, nullable=True)
    next_assessment_date = Column(Date, nullable=True)

    # Métadonnées
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relations
    # Using lazy='joined' for producer to avoid N+1 queries when listing children
    producer = relationship("Producer", back_populates="children", lazy="joined")
    risk_assessments = relationship("RiskAssessment", back_populates="child", cascade="all, delete-orphan", lazy="select")
    remediation_plans = relationship("RemediationPlan", back_populates="child", cascade="all, delete-orphan", lazy="select")
    complaints = relationship("Complaint", back_populates="child", lazy="select")

    def __repr__(self):
        return f"<Child(id={self.id}, name='{self.first_name} {self.last_name}', risk={self.risk_level.value})>"


class RiskAssessment(Base):
    """
    Évaluation des risques pour un enfant ou un producteur.
    """
    __tablename__ = "risk_assessments"

    id = Column(Integer, primary_key=True, index=True)
    producer_id = Column(Integer, ForeignKey("producers.id", ondelete="CASCADE"), nullable=False, index=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=True, index=True)  # Null si évaluation globale

    # Type d'évaluation
    assessment_type = Column(SQLEnum(AssessmentType), nullable=False)
    assessment_date = Column(Date, nullable=False, default=func.now(), index=True)

    # Score et niveau
    overall_risk_score = Column(Numeric(5, 2), nullable=False)  # 0-100
    overall_risk_level = Column(SQLEnum(RiskLevel), nullable=False, index=True)

    # Détails scoring (JSON pour flexibilité)
    risk_factors = Column(JSON, nullable=False)  # {age_risk, education_risk, work_risk, economic_risk, etc.}

    # Évaluateur
    assessor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assessment_location = Column(String(255), nullable=True)  # GPS ou description

    # Méthodologie
    methodology_version = Column(String(20), default="1.0")  # Version algorithme scoring

    # Statut
    status = Column(SQLEnum(AssessmentStatus), default=AssessmentStatus.COMPLETED, index=True)
    validated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)

    # Métadonnées
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relations
    producer = relationship("Producer", back_populates="risk_assessments")
    child = relationship("Child", back_populates="risk_assessments")
    assessor = relationship("User", foreign_keys=[assessor_id])
    validator = relationship("User", foreign_keys=[validated_by])
    triggered_remediation_plans = relationship("RemediationPlan", back_populates="triggered_by_assessment", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<RiskAssessment(id={self.id}, type={self.assessment_type.value}, risk={self.overall_risk_level.value})>"


class MonitoringVisit(Base):
    """
    Visite de monitoring terrain chez un producteur.
    """
    __tablename__ = "monitoring_visits"

    id = Column(Integer, primary_key=True, index=True)
    producer_id = Column(Integer, ForeignKey("producers.id", ondelete="CASCADE"), nullable=False, index=True)

    # Planification
    scheduled_date = Column(Date, nullable=False, index=True)
    actual_date = Column(Date, nullable=True)
    visit_type = Column(SQLEnum(VisitType), default=VisitType.ROUTINE, index=True)
    priority = Column(SQLEnum(Priority), default=Priority.MEDIUM, index=True)

    # Équipe
    lead_assessor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    team_members = Column(String(500), nullable=True)  # IDs séparés par virgules

    # Localisation
    visit_location = Column(String(255), nullable=True)  # GPS ou description
    gps_accuracy = Column(Float, nullable=True)  # Précision GPS en mètres

    # Checklist standardisée
    checklist_data = Column(JSON, nullable=True)  # Données checklist structurées
    checklist_score = Column(Numeric(5, 2), nullable=True)  # Score checklist 0-100

    # Observations
    observations = Column(Text, nullable=True)
    children_interviewed = Column(JSON, nullable=True)  # Liste enfants interviewés
    photos = Column(JSON, nullable=True)  # Array de références photos

    # Résultats
    findings = Column(JSON, nullable=True)  # Constatations détaillées
    dangerous_tasks_observed = Column(JSON, nullable=True)  # Tâches dangereuses observées
    immediate_actions_taken = Column(Text, nullable=True)  # Actions immédiates

    # Statut
    status = Column(SQLEnum(VisitStatus), default=VisitStatus.SCHEDULED, index=True)
    completion_date = Column(DateTime(timezone=True), nullable=True)

    # Signature électronique
    producer_signature_data = Column(JSON, nullable=True)  # {signature_image, timestamp, ip, device_id}
    assessor_signature_data = Column(JSON, nullable=True)

    # Métadonnées
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)

    # Relations
    producer = relationship("Producer", back_populates="monitoring_visits")
    lead_assessor = relationship("User", foreign_keys=[lead_assessor_id])
    created_by_user = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<MonitoringVisit(id={self.id}, date={self.scheduled_date}, status={self.status.value})>"


class RemediationPlan(Base):
    """
    Plan de remédiation individuel pour un enfant.
    """
    __tablename__ = "remediation_plans"

    id = Column(Integer, primary_key=True, index=True)
    producer_id = Column(Integer, ForeignKey("producers.id", ondelete="CASCADE"), nullable=False, index=True)
    child_id = Column(Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True)

    # Identification
    plan_reference = Column(String(50), unique=True, nullable=False)  # Ex: REM-2024-001
    triggered_by = Column(Integer, ForeignKey("risk_assessments.id"), nullable=True, index=True)

    # Statut workflow
    status = Column(SQLEnum(RemediationStatus), default=RemediationStatus.DRAFT, index=True)
    priority = Column(SQLEnum(Priority), nullable=False, index=True)

    # Objectifs
    main_objective = Column(Text, nullable=False)  # Objectif principal
    success_criteria = Column(JSON, nullable=True)  # Critères de succès mesurables

    # Actions planifiées
    planned_actions = Column(JSON, nullable=True)  # Array d'actions {type, description, responsible, deadline}

    # Suivi
    start_date = Column(Date, nullable=True)
    expected_completion_date = Column(Date, nullable=True)
    actual_completion_date = Column(Date, nullable=True)

    # Responsables
    case_worker_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Travailleur social assigné
    supervisor_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Approbations
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approval_comments = Column(Text, nullable=True)

    # Ressources allouées
    budget_allocated = Column(Numeric(10, 2), default=0)
    resources_provided = Column(JSON, nullable=True)  # {school_kits, financial_aid, training, etc.}

    # Suivi mensuel
    monthly_progress = Column(JSON, nullable=True)  # Array de rapports mensuels

    # Résultat final
    outcome = Column(String(50), default="ongoing")  # successful, partial_success, failed, ongoing
    outcome_description = Column(Text, nullable=True)

    # Métadonnées
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relations
    producer = relationship("Producer", back_populates="remediation_plans")
    child = relationship("Child", back_populates="remediation_plans")
    triggered_by_assessment = relationship("RiskAssessment", back_populates="triggered_remediation_plans")
    case_worker = relationship("User", foreign_keys=[case_worker_id])
    actions = relationship("RemediationAction", back_populates="remediation_plan", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<RemediationPlan(id={self.id}, ref={self.plan_reference}, status={self.status.value})>"


class RemediationAction(Base):
    """
    Action individuelle de remédiation dans un plan.
    """
    __tablename__ = "remediation_actions"

    id = Column(Integer, primary_key=True, index=True)
    remediation_plan_id = Column(Integer, ForeignKey("remediation_plans.id", ondelete="CASCADE"), nullable=False, index=True)

    # Détails action
    action_type = Column(SQLEnum(ActionType), nullable=False, index=True)
    description = Column(Text, nullable=False)

    # Planification
    planned_date = Column(Date, nullable=False)
    completed_date = Column(Date, nullable=True)

    # Responsabilité
    responsible_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    responsible_organization = Column(String(200), nullable=True)  # ONG, école, etc.

    # Statut
    status = Column(SQLEnum(ActionStatus), default=ActionStatus.PENDING, index=True)

    # Preuves
    evidence = Column(JSON, nullable=True)  # {documents, photos, signatures}
    notes = Column(Text, nullable=True)

    # Impact
    impact_assessment = Column(Text, nullable=True)  # Évaluation impact

    # Métadonnées
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relations
    remediation_plan = relationship("RemediationPlan", back_populates="actions")
    responsible = relationship("User")

    def __repr__(self):
        return f"<RemediationAction(id={self.id}, type={self.action_type.value}, status={self.status.value})>"


class TrainingSession(Base):
    """
    Session de formation / sensibilisation.
    """
    __tablename__ = "training_sessions"

    id = Column(Integer, primary_key=True, index=True)
    cooperative_id = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)

    # Informations session
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    training_type = Column(SQLEnum(TrainingType), nullable=False, index=True)

    # Planification
    scheduled_date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    duration_hours = Column(Float, nullable=True)

    # Lieu
    location = Column(String(200), nullable=False)
    location_gps = Column(String(100), nullable=True)  # Coordonnées GPS
    village = Column(String(100), nullable=True)

    # Formateur
    trainer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    trainer_organization = Column(String(200), nullable=True)  # Ministère, ONG, etc.

    # Participants
    expected_participants = Column(Integer, default=0)
    actual_participants = Column(Integer, default=0)
    participants = Column(JSON, nullable=True)  # Array de {producer_id, signature, evaluation_score}

    # Contenu
    materials_used = Column(JSON, nullable=True)  # {presentations, handouts, videos}
    topics_covered = Column(JSON, nullable=True)  # Liste des sujets abordés

    # Évaluation
    pre_test_scores = Column(JSON, nullable=True)  # Scores avant formation
    post_test_scores = Column(JSON, nullable=True)  # Scores après formation
    effectiveness_rating = Column(Float, nullable=True)  # Note efficacité 0-5 (jugement formateur)

    # Satisfaction ANONYME des participants (collecte sans compte via QR/URL).
    # Jeton public non devinable + liste [{rating:0-5, comment, at}] — chaque
    # participant note SANS voir les autres (pas d'influence entre pairs).
    feedback_token = Column(String, nullable=True, unique=True, index=True)
    participant_feedback = Column(JSON, nullable=True)

    # Statut
    status = Column(SQLEnum(TrainingStatus), default=TrainingStatus.PLANNED, index=True)

    # Métadonnées
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relations
    cooperative = relationship("Cooperative")
    trainer = relationship("User", foreign_keys=[trainer_id])

    def __repr__(self):
        return f"<TrainingSession(id={self.id}, title='{self.title}', date={self.scheduled_date})>"


class TraceabilityBlock(Base):
    """
    Blocage de traçabilité pour un producteur (cas de travail d'enfant, non-conformité, etc.).
    """
    __tablename__ = "traceability_blocks"

    id = Column(Integer, primary_key=True, index=True)
    producer_id = Column(Integer, ForeignKey("producers.id", ondelete="CASCADE"), nullable=False, index=True)

    # Motif du blocage
    block_reason = Column(SQLEnum(BlockReason), nullable=False, index=True)
    block_description = Column(Text, nullable=False)

    # Référence cas
    related_case_id = Column(Integer, nullable=True)  # ID du cas de travail d'enfant
    related_assessment_id = Column(Integer, ForeignKey("risk_assessments.id"), nullable=True)

    # Impact traçabilité
    affects_all_production = Column(Boolean, default=True)
    affected_batches = Column(JSON, nullable=True)  # Lots spécifiques affectés

    # Dates
    block_start_date = Column(DateTime(timezone=True), nullable=False, default=func.now(), index=True)
    expected_resolution_date = Column(Date, nullable=True)
    actual_resolution_date = Column(Date, nullable=True)

    # Statut
    status = Column(SQLEnum(BlockStatus), default=BlockStatus.ACTIVE, index=True)

    # Décision
    blocked_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Métadonnées
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relations
    producer = relationship("Producer", back_populates="traceability_blocks")
    blocked_by_user = relationship("User", foreign_keys=[blocked_by])
    approver = relationship("User", foreign_keys=[approved_by])

    def __repr__(self):
        return f"<TraceabilityBlock(id={self.id}, producer_id={self.producer_id}, status={self.status.value})>"


class Alert(Base):
    """
    Système d'alertes (risque élevé, visite manquée, action en retard, etc.).
    """
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)

    # Type et priorité
    alert_type = Column(SQLEnum(AlertType), nullable=False, index=True)
    priority = Column(SQLEnum(Priority), nullable=False, index=True)

    # Source
    source_entity = Column(String(50), nullable=False, index=True)  # producers, children, visits, etc.
    source_id = Column(Integer, nullable=False, index=True)  # ID de l'entité source

    # Contenu
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    alert_metadata = Column("metadata", JSON, nullable=True)  # Données contextuelles

    # Gestion
    status = Column(SQLEnum(AlertStatus), default=AlertStatus.NEW, index=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Escalade
    escalation_level = Column(Integer, default=0)  # Niveau d'escalade (0=non escaladé)
    escalated_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True)

    # Résolution
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Notifications
    notifications_sent = Column(JSON, nullable=True)  # {email: [], push: [], sms: []}

    # Métadonnées
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relations
    assigned_user = relationship("User", foreign_keys=[assigned_to])
    resolver = relationship("User", foreign_keys=[resolved_by])
    escalated_user = relationship("User", foreign_keys=[escalated_to])

    def __repr__(self):
        return f"<Alert(id={self.id}, type={self.alert_type.value}, priority={self.priority.value})>"


class PrivacyAccessLog(Base):
    """
    Journal d'audit des acces aux donnees sensibles enfants.
    """
    __tablename__ = "privacy_access_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    user_role = Column(String(50), nullable=True, index=True)
    action = Column(String(80), nullable=False, index=True)
    source_entity = Column(String(80), nullable=False, index=True)
    source_id = Column(Integer, nullable=True, index=True)
    redacted = Column(Boolean, default=False, nullable=False)
    access_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User")

    def __repr__(self):
        return f"<PrivacyAccessLog(id={self.id}, action={self.action}, entity={self.source_entity})>"


class Complaint(Base):
    """
    Plaintes et signalements.
    """
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True)

    # Rattachement direct à la coopérative (indispensable pour les signalements
    # PUBLICS anonymes sans producteur lié : sans ceci ils seraient orphelins).
    cooperative_id = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)

    # Identification
    complaint_reference = Column(String(50), unique=True, nullable=False)  # Ex: CMP-2024-001
    source = Column(String(50), nullable=False, index=True)  # hotline, field_agent, community, anonymous, audit

    # Détails
    complaint_type = Column(SQLEnum(ComplaintType), nullable=False, index=True)
    severity = Column(SQLEnum(ComplaintSeverity), nullable=False, index=True)
    description = Column(Text, nullable=False)

    # Parties impliquées
    reporter_name = Column(String(200), nullable=True)  # Peut être anonyme
    reporter_contact = Column(String(100), nullable=True)
    reporter_relationship = Column(String(50), nullable=True)  # family, neighbor, teacher, agent, anonymous

    # Entités concernées
    producer_id = Column(Integer, ForeignKey("producers.id"), nullable=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=True, index=True)
    location_description = Column(Text, nullable=True)
    location_gps = Column(String(100), nullable=True)

    # Investigation
    status = Column(SQLEnum(ComplaintStatus), default=ComplaintStatus.RECEIVED, index=True)
    assigned_investigator = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Dates
    received_date = Column(DateTime(timezone=True), nullable=False, default=func.now(), index=True)
    investigation_start_date = Column(Date, nullable=True)
    investigation_end_date = Column(Date, nullable=True)

    # Résultats
    findings = Column(Text, nullable=True)
    actions_taken = Column(JSON, nullable=True)  # Actions entreprises
    referral_made = Column(Boolean, default=False)
    referred_to = Column(String(200), nullable=True)  # Autorités, ONG, etc.

    # Confidentialité
    is_confidential = Column(Boolean, default=True)
    confidentiality_level = Column(String(50), default="confidential")  # public, internal, confidential, restricted

    # Métadonnées
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relations
    producer = relationship("Producer", back_populates="complaints")
    child = relationship("Child", back_populates="complaints")
    investigator = relationship("User", foreign_keys=[assigned_investigator])

    def __repr__(self):
        return f"<Complaint(id={self.id}, ref={self.complaint_reference}, type={self.complaint_type.value})>"


class SsrteCommunityProfile(Base):
    """
    Fiche SSRTE A - FO: profil communaute/localite.
    """
    __tablename__ = "ssrte_community_profiles"

    id = Column(Integer, primary_key=True, index=True)
    locality = Column(String(200), nullable=False, index=True)
    section = Column(String(100), nullable=True, index=True)
    cooperative_id = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)
    interview_date = Column(Date, nullable=False, index=True)
    respondent_name = Column(String(200), nullable=True)
    respondent_role = Column(String(100), nullable=True)
    # Bloc identification administrative (A.02-A.06)
    supplier = Column(String(200), nullable=True)            # A.02 Fournisseur
    sub_prefecture = Column(String(200), nullable=True)      # A.03 Sous-prefecture
    collection_agent_code = Column(String(100), nullable=True)   # A.05 Code agent de collecte
    collection_agent_name = Column(String(200), nullable=True)   # A.06 Nom de l'agent de collecte
    # GPS + heures de visite (A.07a/A.07b/A.07c)
    gps_start = Column(String(120), nullable=True)
    time_start = Column(String(20), nullable=True)
    gps_end = Column(String(120), nullable=True)
    time_end = Column(String(20), nullable=True)
    # Remarques + actions proposees, une entree par section (cle = section)
    section_notes = Column(JSON, nullable=True)
    school_available = Column(Boolean, default=False, nullable=False)
    nearest_school_distance_km = Column(Numeric(6, 2), nullable=True)
    has_child_protection_committee = Column(Boolean, default=False, nullable=False)
    committee_members = Column(JSON, nullable=True)
    risks_identified = Column(JSON, nullable=True)
    services_available = Column(JSON, nullable=True)
    # Tableau detaille des ecoles (A.22-A.29) : liste de dicts par ecole
    # (nom, gps, type, construite_par, salles, enseignants, eleves, cantine, latrines).
    schools = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    # Cycle de vie : brouillon modifiable -> definitif (verrouille pour l'audit).
    # Les fiches anterieures sont retro-classees "final" via le DEFAULT SQL de migration.
    status = Column(String(10), default="draft", nullable=False, index=True)
    finalized_at = Column(DateTime(timezone=True), nullable=True)
    finalized_by = Column(String(200), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class SsrteHouseholdProfile(Base):
    """
    Fiche SSRTE B / F1: profilage de menage producteur.
    """
    __tablename__ = "ssrte_household_profiles"

    id = Column(Integer, primary_key=True, index=True)
    producer_id = Column(Integer, ForeignKey("producers.id", ondelete="CASCADE"), nullable=False, index=True)
    interview_date = Column(Date, nullable=False, index=True)
    interviewer_name = Column(String(200), nullable=True)
    # Identification administrative (B.02-B.07)
    supplier = Column(String(200), nullable=True)              # B.02
    sub_prefecture = Column(String(200), nullable=True)        # B.03
    locality = Column(String(200), nullable=True)              # B.04
    collection_agent_code = Column(String(100), nullable=True) # B.05
    producer_ssrte_code = Column(String(100), nullable=True)   # B.07
    # GPS + heures (B.09a/b/c)
    gps_start = Column(String(120), nullable=True)
    time_start = Column(String(20), nullable=True)
    time_end = Column(String(20), nullable=True)
    # Type d'enquete + statut de la visite (B.10a/b, B.15)
    survey_type = Column(String(40), nullable=True)            # SSRTE / Visite communautaire
    producer_available = Column(Boolean, nullable=True)        # B.10a
    unavailable_reason = Column(String(60), nullable=True)     # B.10b
    visited_person_status = Column(String(60), nullable=True)  # B.15
    # Travailleurs (B.18b/c/d)
    external_workers_count = Column(Integer, nullable=True)    # B.18b
    daily_workers_count = Column(Integer, nullable=True)       # B.18c
    non_daily_workers = Column(JSON, nullable=True)            # B.18d (nom/statut/telephone)
    # Remarques + actions proposees, une entree par section
    section_notes = Column(JSON, nullable=True)
    household_size = Column(Integer, nullable=True)
    children_count = Column(Integer, nullable=True)
    school_age_children_count = Column(Integer, nullable=True)
    enrolled_children_count = Column(Integer, nullable=True)
    household_members = Column(JSON, nullable=True)
    vulnerabilities = Column(JSON, nullable=True)
    child_work_declarations = Column(JSON, nullable=True)
    school_constraints = Column(JSON, nullable=True)
    # Informations exploitation (B.16-B.23) : parcelles, superficie et
    # production cacao & cafe. Dict de cles scalaires.
    farm_info = Column(JSON, nullable=True)
    # Situation économique du ménage (Fiche B section 7)
    housing_type = Column(String(40), nullable=True)            # B.25 : moderne | traditionnel
    household_assets = Column(JSON, nullable=True)              # B.26 : possessions du ménage
    allow_worker_interview = Column(Boolean, nullable=True)     # B.18e : autorise l'entretien des travailleurs
    head_photo_ref = Column(String(255), nullable=True)        # B.29 : référence photo (texte, historique)
    # B.29 : photo RÉELLE du chef de ménage — data-URI base64 en TEXT (même mécanisme
    # que le logo coop / la photo producteur). `deferred` : blob jamais chargé en liste.
    head_photo_data = deferred(Column(Text, nullable=True))
    head_photo_consent = Column(Boolean, default=False, nullable=False)  # consentement (donnée personnelle)
    risk_score = Column(Numeric(5, 2), default=0, nullable=False)
    risk_level = Column(SQLEnum(RiskLevel), default=RiskLevel.NONE, nullable=False, index=True)
    consent_given = Column(Boolean, default=False, nullable=False)
    signature_data = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(10), default="draft", nullable=False, index=True)
    finalized_at = Column(DateTime(timezone=True), nullable=True)
    finalized_by = Column(String(200), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    producer = relationship("Producer", back_populates="ssrte_household_profiles")


class SsrtePlantationVisit(Base):
    """
    Fiche SSRTE C: visite de plantation.
    """
    __tablename__ = "ssrte_plantation_visits"

    id = Column(Integer, primary_key=True, index=True)
    plantation_id = Column(Integer, ForeignKey("plantations.id", ondelete="CASCADE"), nullable=False, index=True)
    producer_id = Column(Integer, ForeignKey("producers.id", ondelete="CASCADE"), nullable=True, index=True)
    visit_date = Column(Date, nullable=False, index=True)
    interviewer_name = Column(String(200), nullable=True)
    gps_location = Column(String(255), nullable=True)
    gps_accuracy = Column(Float, nullable=True)
    # Identification administrative (C.01-C.07)
    section = Column(String(100), nullable=True)               # C.01
    supplier = Column(String(200), nullable=True)              # C.02
    sub_prefecture = Column(String(200), nullable=True)        # C.03
    locality = Column(String(200), nullable=True)              # C.04
    collection_agent_code = Column(String(100), nullable=True) # C.05
    producer_ssrte_code = Column(String(100), nullable=True)   # C.07
    # Heures de visite (C.09b/c)
    time_start = Column(String(20), nullable=True)
    time_end = Column(String(20), nullable=True)
    # Comptages adultes / travailleurs / enfants (C.10a/b/d, C.11, C.12)
    adults_count = Column(Integer, nullable=True)              # C.10a
    daily_workers_count = Column(Integer, nullable=True)       # C.10b
    allow_worker_interview = Column(Boolean, nullable=True)    # C.10d
    children_present_count = Column(Integer, nullable=True)    # C.11
    non_household_children_count = Column(Integer, nullable=True)  # C.12
    # Enfants non-membres du menage presents (V01-V10, C.14-C.18)
    non_household_children = Column(JSON, nullable=True)
    # Remarques + actions proposees, une entree par section
    section_notes = Column(JSON, nullable=True)
    checklist_data = Column(JSON, nullable=True)
    children_observed = Column(JSON, nullable=True)
    # Adultes presents (C.10a) et travailleurs non-journaliers (C.10c) :
    # listes de dicts (nom, statut, telephone...).
    adults_observed = Column(JSON, nullable=True)
    workers_present = Column(JSON, nullable=True)
    dangerous_tasks_observed = Column(JSON, nullable=True)
    suspected_child_labor = Column(Boolean, default=False, nullable=False, index=True)
    immediate_actions_taken = Column(Text, nullable=True)
    photos = Column(JSON, nullable=True)
    consent_given = Column(Boolean, default=False, nullable=False)
    producer_signature_data = Column(JSON, nullable=True)
    assessor_signature_data = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(10), default="draft", nullable=False, index=True)
    finalized_at = Column(DateTime(timezone=True), nullable=True)
    finalized_by = Column(String(200), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    producer = relationship("Producer", back_populates="ssrte_plantation_visits")
    plantation = relationship("Plantation", back_populates="ssrte_visits")


class NotificationItem(Base):
    """
    Notification in-app pour un utilisateur, derivee d'une Alert CacaoGuard.

    Un Alert peut donner naissance a plusieurs NotificationItem (fan-out
    par utilisateur). La contrainte d'unicite (user_id, alert_id) garantit
    l'idempotence du fan-out a chaque sync.
    """
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True)

    # Snapshot (decouple de l'Alert pour resister aux suppressions)
    notification_type = Column(SQLEnum(AlertType), nullable=False, index=True)
    priority = Column(SQLEnum(Priority), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)  # source_entity, source_id, metadata pour deep-link

    # Etat per-user
    read_at = Column(DateTime(timezone=True), nullable=True, index=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User")
    alert = relationship("Alert")

    __table_args__ = (
        UniqueConstraint("user_id", "alert_id", name="uq_notification_user_alert"),
    )

    def __repr__(self):
        return f"<NotificationItem(id={self.id}, user={self.user_id}, alert={self.alert_id}, read={self.read_at is not None})>"


class SyncOperationLog(Base):
    """
    Trace des operations synchronisees depuis un client offline.

    Chaque op_id (genere cote client) est unique : idempotence stricte.
    Permet de rejouer un /sync/push sans dupliquer un enregistrement
    cote serveur si le client perd la reponse reseau.
    """
    __tablename__ = "sync_operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    op_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    op_type = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False, index=True)
    payload = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, index=True)  # success | duplicate | conflict | error
    server_entity_id = Column(Integer, nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    client_timestamp = Column(DateTime(timezone=True), nullable=True)
    applied_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User")

    def __repr__(self):
        return f"<SyncOperationLog(op_id={self.op_id}, type={self.op_type}, status={self.status})>"
