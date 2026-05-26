# CacaoGuard - Module de Lutte contre le Travail des Enfants
## Architecture Complète

### Nom du Module
**CacaoGuard Child Protection Module (CG-CPM)**
*Module de Protection de l'Enfant pour la Filière Cacao*

### Version
v1.0.0 - Conçu pour le contexte ivoirien

---

## 1. VUE D'ENSEMBLE DE L'ARCHITECTURE

### Stack Technique Recommandée
```
Backend:           Laravel 11 (PHP 8.2+) ou Node.js/NestJS
Frontend Web:      React.js 18+ avec Tailwind CSS
Mobile:            Flutter 3+ (offline-first avec SQLite)
Base de données:   PostgreSQL 15+
Cache:             Redis 7+
Stockage fichiers: MinIO (S3-compatible) ou AWS S3
Search:            Elasticsearch (optionnel pour rapports avancés)
Queue:             Redis Queue ou RabbitMQ
```

### Principes d'Architecture
- **Offline-first**: Synchronisation bidirectionnelle avec résolution de conflits
- **RGPD-like**: Chiffrement des données sensibles, anonymisation possible
- **Multi-niveaux**: Données agrégées pour coopérative, détaillées pour producteurs
- **Audit trail**: Journalisation complète de toutes les actions
- **Géolocalisation**: GPS avec précision et historique des mouvements

---

## 2. SCHÉMA DE BASE DE DONNÉES COMPLET

### 2.1 Tables Principales

#### `producers` (Producteurs)
```sql
CREATE TABLE producers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cooperative_id UUID NOT NULL REFERENCES cooperatives(id),
    producer_code VARCHAR(20) UNIQUE NOT NULL, -- Code producteur (ex: CI-COOP-001)
    
    -- Informations personnelles
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    date_of_birth DATE,
    gender ENUM('M', 'F') NOT NULL,
    phone VARCHAR(20),
    id_card_number VARCHAR(50), -- CNI ou pièce d'identité
    id_card_expiry DATE,
    
    -- Informations ferme
    farm_name VARCHAR(200),
    farm_size_hectares DECIMAL(8,2) NOT NULL DEFAULT 0,
    farm_location GEOGRAPHY(Point, 4326), -- GPS coordinates
    farm_address TEXT,
    village_id UUID REFERENCES villages(id),
    section_id UUID REFERENCES sections(id),
    
    -- Statut
    status ENUM('active', 'inactive', 'suspended', 'blacklisted') DEFAULT 'active',
    certification_status ENUM('none', 'rainforest', 'fairtrade', 'cocoa_horizons', 'organic') DEFAULT 'none',
    risk_level ENUM('low', 'medium', 'high', 'critical') DEFAULT 'low',
    
    -- Métadonnées
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    last_sync_at TIMESTAMP WITH TIME ZONE,
    
    -- Index
    INDEX idx_producers_cooperative (cooperative_id),
    INDEX idx_producers_village (village_id),
    INDEX idx_producers_risk (risk_level),
    INDEX idx_producers_location (farm_location)
);
```

#### `children` (Enfants des producteurs)
```sql
CREATE TABLE children (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    producer_id UUID NOT NULL REFERENCES producers(id) ON DELETE CASCADE,
    
    -- Informations enfant
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    date_of_birth DATE NOT NULL, -- Critique pour calcul âge
    gender ENUM('M', 'F') NOT NULL,
    birth_certificate_number VARCHAR(50), -- Numéro acte de naissance
    
    -- Statut scolaire
    school_status ENUM('not_school_age', 'enrolled', 'dropped_out', 'never_enrolled', 'completed') DEFAULT 'not_school_age',
    school_name VARCHAR(200),
    school_grade VARCHAR(20), -- Classe (CI, CP1, CP2, CE1, etc.)
    school_distance_km DECIMAL(5,2), -- Distance école en km
    school_attendance_rate DECIMAL(5,2), -- Taux de fréquentation %
    
    -- Évaluation risque
    risk_score DECIMAL(5,2) DEFAULT 0, -- Score calculé 0-100
    risk_level ENUM('none', 'low', 'medium', 'high', 'critical') DEFAULT 'none',
    risk_factors JSONB, -- Facteurs de risque détaillés
    
    -- Statut protection
    is_working_on_farm BOOLEAN DEFAULT FALSE,
    work_frequency ENUM('never', 'occasional', 'regular', 'daily') DEFAULT 'never',
    dangerous_tasks_performed JSONB, -- Liste des tâches dangereuses
    
    -- Suivi
    last_assessment_date DATE,
    next_assessment_date DATE,
    
    -- Métadonnées
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    
    -- Index
    INDEX idx_children_producer (producer_id),
    INDEX idx_children_risk (risk_level),
    INDEX idx_children_age (date_of_birth),
    INDEX idx_children_school (school_status)
);
```

#### `risk_assessments` (Évaluations des risques)
```sql
CREATE TABLE risk_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    producer_id UUID NOT NULL REFERENCES producers(id) ON DELETE CASCADE,
    child_id UUID REFERENCES children(id) ON DELETE CASCADE, -- Null si évaluation globale
    
    -- Type d'évaluation
    assessment_type ENUM('initial', 'annual', 'follow_up', 'complaint', 'emergency') NOT NULL,
    assessment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    
    -- Score et niveau
    overall_risk_score DECIMAL(5,2) NOT NULL, -- 0-100
    overall_risk_level ENUM('low', 'medium', 'high', 'critical') NOT NULL,
    
    -- Détails scoring (JSON pour flexibilité)
    risk_factors JSONB NOT NULL, -- {age_risk, education_risk, work_risk, economic_risk, etc.}
    
    -- Évaluateur
    assessor_id UUID NOT NULL REFERENCES users(id),
    assessment_location GEOGRAPHY(Point, 4326),
    
    -- Méthodologie
    methodology_version VARCHAR(20) DEFAULT '1.0', -- Version algorithme scoring
    
    -- Statut
    status ENUM('draft', 'completed', 'validated', 'escalated') DEFAULT 'completed',
    validated_by UUID REFERENCES users(id),
    validated_at TIMESTAMP WITH TIME ZONE,
    
    -- Métadonnées
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Index
    INDEX idx_assessments_producer (producer_id),
    INDEX idx_assessments_child (child_id),
    INDEX idx_assessments_date (assessment_date),
    INDEX idx_assessments_risk (overall_risk_level)
);
```

#### `monitoring_visits` (Visites de monitoring terrain)
```sql
CREATE TABLE monitoring_visits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    producer_id UUID NOT NULL REFERENCES producers(id) ON DELETE CASCADE,
    
    -- Planification
    scheduled_date DATE NOT NULL,
    actual_date DATE,
    visit_type ENUM('routine', 'follow_up', 'complaint', 'emergency') DEFAULT 'routine',
    priority ENUM('low', 'medium', 'high', 'urgent') DEFAULT 'medium',
    
    -- Équipe
    lead_assessor_id UUID NOT NULL REFERENCES users(id),
    team_members UUID[] REFERENCES users(id), -- Array d'IDs
    
    -- Localisation
    visit_location GEOGRAPHY(Point, 4326),
    gps_accuracy DECIMAL(5,2), -- Précision GPS en mètres
    
    -- Checklist standardisée
    checklist_data JSONB, -- Données checklist structurées
    checklist_score DECIMAL(5,2), -- Score checklist 0-100
    
    -- Observations
    observations TEXT,
    children_interviewed JSONB, -- Liste enfants interviewés avec consentement
    photos JSONB, -- Array de références photos {url, timestamp, gps, consent}
    
    -- Résultats
    findings JSONB, -- Constatations détaillées
    dangerous_tasks_observed JSONB, -- Tâches dangereuses observées
    immediate_actions_taken TEXT, -- Actions immédiates
    
    -- Statut
    status ENUM('scheduled', 'in_progress', 'completed', 'cancelled') DEFAULT 'scheduled',
    completion_date TIMESTAMP WITH TIME ZONE,
    
    -- Signature électronique
    producer_signature_data JSONB, -- {signature_image, timestamp, ip, device_id}
    assessor_signature_data JSONB,
    
    -- Métadonnées
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    synced_at TIMESTAMP WITH TIME ZONE,
    
    -- Index
    INDEX idx_visits_producer (producer_id),
    INDEX idx_visits_date (scheduled_date),
    INDEX idx_visits_status (status),
    INDEX idx_visits_priority (priority)
);
```

#### `remediation_plans` (Plans de remédiation individuels)
```sql
CREATE TABLE remediation_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    producer_id UUID NOT NULL REFERENCES producers(id) ON DELETE CASCADE,
    child_id UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    
    -- Identification
    plan_reference VARCHAR(50) UNIQUE NOT NULL, -- Ex: REM-2024-001
    triggered_by UUID REFERENCES risk_assessments(id), -- Évaluation déclencheuse
    
    -- Statut workflow
    status ENUM('draft', 'pending_approval', 'approved', 'in_progress', 'completed', 'closed', 'escalated') DEFAULT 'draft',
    priority ENUM('low', 'medium', 'high', 'urgent') NOT NULL,
    
    -- Objectifs
    main_objective TEXT NOT NULL, -- Objectif principal
    success_criteria JSONB, -- Critères de succès mesurables
    
    -- Actions planifiées
    planned_actions JSONB NOT NULL, -- Array d'actions {type, description, responsible, deadline}
    
    -- Suivi
    start_date DATE,
    expected_completion_date DATE,
    actual_completion_date DATE,
    
    -- Responsables
    case_worker_id UUID NOT NULL REFERENCES users(id), -- Travailleur social assigné
    supervisor_id UUID REFERENCES users(id),
    
    -- Approbations
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMP WITH TIME ZONE,
    approval_comments TEXT,
    
    -- Ressources allouées
    budget_allocated DECIMAL(10,2) DEFAULT 0,
    resources_provided JSONB, -- {school_kits, financial_aid, training, etc.}
    
    -- Suivi mensuel
    monthly_progress JSONB, -- Array de rapports mensuels
    
    -- Résultat final
    outcome ENUM('successful', 'partial_success', 'failed', 'ongoing') DEFAULT 'ongoing',
    outcome_description TEXT,
    
    -- Métadonnées
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    
    -- Index
    INDEX idx_remediation_producer (producer_id),
    INDEX idx_remediation_child (child_id),
    INDEX idx_remediation_status (status),
    INDEX idx_remediation_priority (priority)
);
```

#### `remediation_actions` (Actions individuelles de remédiation)
```sql
CREATE TABLE remediation_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    remediation_plan_id UUID NOT NULL REFERENCES remediation_plans(id) ON DELETE CASCADE,
    
    -- Détails action
    action_type ENUM('education', 'economic_support', 'awareness', 'legal', 'health', 'other') NOT NULL,
    description TEXT NOT NULL,
    
    -- Planification
    planned_date DATE NOT NULL,
    completed_date DATE,
    
    -- Responsabilité
    responsible_id UUID REFERENCES users(id), -- Personne responsable
    responsible_organization VARCHAR(200), -- ONG, école, etc.
    
    -- Statut
    status ENUM('pending', 'in_progress', 'completed', 'cancelled', 'overdue') DEFAULT 'pending',
    
    -- Preuves
    evidence JSONB, -- {documents, photos, signatures}
    notes TEXT,
    
    -- Impact
    impact_assessment TEXT, -- Évaluation impact
    
    -- Métadonnées
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Index
    INDEX idx_actions_plan (remediation_plan_id),
    INDEX idx_actions_status (status),
    INDEX idx_actions_type (action_type)
);
```

#### `training_sessions` (Sessions de formation)
```sql
CREATE TABLE training_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Informations session
    title VARCHAR(200) NOT NULL,
    description TEXT,
    training_type ENUM('child_protection', 'parenting', 'legal_rights', 'economic_empowerment', 'other') NOT NULL,
    
    -- Planification
    scheduled_date DATE NOT NULL,
    start_time TIME,
    end_time TIME,
    duration_hours DECIMAL(4,2),
    
    -- Lieu
    location VARCHAR(200) NOT NULL,
    location_gps GEOGRAPHY(Point, 4326),
    village_id UUID REFERENCES villages(id),
    
    -- Formateur
    trainer_id UUID NOT NULL REFERENCES users(id),
    trainer_organization VARCHAR(200), -- Ministère, ONG, etc.
    
    -- Participants
    expected_participants INTEGER DEFAULT 0,
    actual_participants INTEGER DEFAULT 0,
    participants JSONB, -- Array de {producer_id, signature, evaluation_score}
    
    -- Contenu
    materials_used JSONB, -- {presentations, handouts, videos}
    topics_covered JSONB, -- Liste des sujets abordés
    
    -- Évaluation
    pre_test_scores JSONB, -- Scores avant formation
    post_test_scores JSONB, -- Scores après formation
    effectiveness_rating DECIMAL(3,2), -- Note efficacité 0-5
    
    -- Statut
    status ENUM('planned', 'completed', 'cancelled', 'postponed') DEFAULT 'planned',
    
    -- Métadonnées
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    
    -- Index
    INDEX idx_training_date (scheduled_date),
    INDEX idx_training_type (training_type),
    INDEX idx_training_village (village_id)
);
```

#### `traceability_blocks` (Blocs de traçabilité)
```sql
CREATE TABLE traceability_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    producer_id UUID NOT NULL REFERENCES producers(id) ON DELETE CASCADE,
    
    -- Motif du blocage
    block_reason ENUM('child_labor_case', 'pending_investigation', 'non_compliance', 'audit_failure', 'other') NOT NULL,
    block_description TEXT NOT NULL,
    
    -- Référence cas
    related_case_id UUID, -- ID du cas de travail d'enfant
    related_assessment_id UUID REFERENCES risk_assessments(id),
    
    -- Impact traçabilité
    affects_all_production BOOLEAN DEFAULT TRUE,
    affected_batches JSONB, -- Lots spécifiques affectés
    
    -- Dates
    block_start_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expected_resolution_date DATE,
    actual_resolution_date DATE,
    
    -- Statut
    status ENUM('active', 'resolved', 'escalated', 'expired') DEFAULT 'active',
    
    -- Décision
    blocked_by UUID NOT NULL REFERENCES users(id),
    approved_by UUID REFERENCES users(id),
    resolution_notes TEXT,
    
    -- Métadonnées
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Index
    INDEX idx_blocks_producer (producer_id),
    INDEX idx_blocks_status (status),
    INDEX idx_blocks_date (block_start_date)
);
```

#### `alerts` (Système d'alertes)
```sql
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Type et priorité
    alert_type ENUM('high_risk_child', 'missed_visit', 'overdue_action', 'complaint', 'audit_failure', 'traceability_block') NOT NULL,
    priority ENUM('low', 'medium', 'high', 'critical') NOT NULL,
    
    -- Source
    source_entity VARCHAR(50) NOT NULL, -- producers, children, visits, etc.
    source_id UUID NOT NULL, -- ID de l'entité source
    
    -- Contenu
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB, -- Données contextuelles
    
    -- Gestion
    status ENUM('new', 'acknowledged', 'in_progress', 'resolved', 'escalated', 'false_positive') DEFAULT 'new',
    assigned_to UUID REFERENCES users(id), -- Personne assignée
    
    -- Escalade
    escalation_level INTEGER DEFAULT 0, -- Niveau d'escalade (0=non escaladé)
    escalated_to UUID REFERENCES users(id),
    escalated_at TIMESTAMP WITH TIME ZONE,
    
    -- Résolution
    resolved_by UUID REFERENCES users(id),
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT,
    
    -- Notifications
    notifications_sent JSONB, -- {email: [], push: [], sms: []}
    
    -- Métadonnées
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Index
    INDEX idx_alerts_type (alert_type),
    INDEX idx_alerts_priority (priority),
    INDEX idx_alerts_status (status),
    INDEX idx_alerts_assigned (assigned_to)
);
```

#### `complaints` (Plaintes et signalements)
```sql
CREATE TABLE complaints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identification
    complaint_reference VARCHAR(50) UNIQUE NOT NULL, -- Ex: CMP-2024-001
    source ENUM('hotline', 'field_agent', 'community', 'anonymous', 'audit', 'other') NOT NULL,
    
    -- Détails
    complaint_type ENUM('child_labor', 'abuse', 'exploitation', 'trafficking', 'other') NOT NULL,
    description TEXT NOT NULL,
    severity ENUM('low', 'medium', 'high', 'critical') NOT NULL,
    
    -- Parties impliquées
    reporter_name VARCHAR(200), -- Peut être anonyme
    reporter_contact VARCHAR(100),
    reporter_relationship ENUM('family', 'neighbor', 'teacher', 'agent', 'anonymous') DEFAULT 'anonymous',
    
    -- Entités concernées
    producer_id UUID REFERENCES producers(id),
    child_id UUID REFERENCES children(id),
    location_description TEXT,
    location_gps GEOGRAPHY(Point, 4326),
    
    -- Investigation
    status ENUM('received', 'under_review', 'investigating', 'substantiated', 'unsubstantiated', 'closed', 'escalated') DEFAULT 'received',
    assigned_investigator UUID REFERENCES users(id),
    
    -- Dates
    received_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    investigation_start_date DATE,
    investigation_end_date DATE,
    
    -- Résultats
    findings TEXT,
    actions_taken JSONB, -- Actions entreprises
    referral_made BOOLEAN DEFAULT FALSE,
    referred_to VARCHAR(200), -- Autorités, ONG, etc.
    
    -- Confidentialité
    is_confidential BOOLEAN DEFAULT TRUE,
    confidentiality_level ENUM('public', 'internal', 'confidential', 'restricted') DEFAULT 'confidential',
    
    -- Métadonnées
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    
    -- Index
    INDEX idx_complaints_status (status),
    INDEX idx_complaints_type (complaint_type),
    INDEX idx_complaints_severity (severity),
    INDEX idx_complaints_date (received_date)
);
```

### 2.2 Tables de Référence

#### `villages` (Villages)
```sql
CREATE TABLE villages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cooperative_id UUID NOT NULL REFERENCES cooperatives(id),
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) UNIQUE NOT NULL,
    region VARCHAR(100), -- Région (ex: San-Pédro, Soubré)
    department VARCHAR(100), -- Département
    sub_prefecture VARCHAR(100), -- Sous-préfecture
    location GEOGRAPHY(Point, 4326),
    population INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### `sections` (Sections de village)
```sql
CREATE TABLE sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    village_id UUID NOT NULL REFERENCES villages(id),
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) UNIQUE NOT NULL,
    location GEOGRAPHY(Point, 4326),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### `users` (Utilisateurs du système)
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cooperative_id UUID NOT NULL REFERENCES cooperatives(id),
    
    -- Informations personnelles
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    
    -- Rôle et permissions
    role ENUM('super_admin', 'cooperative_admin', 'field_agent', 'case_worker', 'trainer', 'auditor', 'viewer') NOT NULL,
    permissions JSONB, -- Permissions spécifiques
    
    -- Profil professionnel
    employee_id VARCHAR(50),
    position VARCHAR(100),
    department VARCHAR(100),
    
    -- Zone de responsabilité
    assigned_villages UUID[] REFERENCES villages(id), -- Villages assignés
    assigned_sections UUID[] REFERENCES sections(id),
    
    -- Statut
    is_active BOOLEAN DEFAULT TRUE,
    last_login_at TIMESTAMP WITH TIME ZONE,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    
    -- Métadonnées
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Index
    INDEX idx_users_cooperative (cooperative_id),
    INDEX idx_users_role (role),
    INDEX idx_users_email (email)
);
```

#### `cooperatives` (Coopératives)
```sql
CREATE TABLE cooperatives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    code VARCHAR(20) UNIQUE NOT NULL,
    registration_number VARCHAR(50),
    
    -- Adresse
    address TEXT,
    city VARCHAR(100),
    region VARCHAR(100),
    country VARCHAR(2) DEFAULT 'CI',
    
    -- Contact
    phone VARCHAR(20),
    email VARCHAR(255),
    website VARCHAR(255),
    
    -- Certification
    certifications JSONB, -- {rainforest, fairtrade, organic, etc.}
    certification_expiry_dates JSONB,
    
    -- Statistiques
    total_producers INTEGER DEFAULT 0,
    total_area_hectares DECIMAL(10,2) DEFAULT 0,
    
    -- Paramètres
    settings JSONB, -- Paramètres spécifiques coopérative
    risk_thresholds JSONB, -- Seuils de risque personnalisés
    
    -- Métadonnées
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 2.3 Tables de Synchronisation (Mobile)

#### `sync_queue` (File de synchronisation)
```sql
CREATE TABLE sync_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id VARCHAR(100) NOT NULL, -- ID appareil mobile
    user_id UUID NOT NULL REFERENCES users(id),
    
    -- Données
    entity_type VARCHAR(50) NOT NULL, -- producers, children, visits, etc.
    entity_id UUID NOT NULL,
    operation ENUM('create', 'update', 'delete') NOT NULL,
    payload JSONB NOT NULL, -- Données complètes
    
    -- Statut
    status ENUM('pending', 'syncing', 'completed', 'failed', 'conflict') DEFAULT 'pending',
    
    -- Conflits
    conflict_resolution ENUM('server_wins', 'client_wins', 'merge', 'manual') DEFAULT 'server_wins',
    
    -- Métadonnées
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    synced_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    
    -- Index
    INDEX idx_sync_device (device_id),
    INDEX idx_sync_user (user_id),
    INDEX idx_sync_status (status)
);
```

#### `audit_logs` (Journal d'audit)
```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Action
    action VARCHAR(50) NOT NULL, -- create, update, delete, view, export
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    
    -- Utilisateur
    user_id UUID REFERENCES users(id),
    user_email VARCHAR(255),
    user_role VARCHAR(50),
    
    -- Détails
    ip_address INET,
    user_agent TEXT,
    device_id VARCHAR(100),
    
    -- Changements
    old_values JSONB,
    new_values JSONB,
    changes_summary JSONB, -- Diff résumé
    
    -- Contexte
    reason TEXT, -- Motif de l'action (requis pour actions sensibles)
    
    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Index
    INDEX idx_audit_entity (entity_type, entity_id),
    INDEX idx_audit_user (user_id),
    INDEX idx_audit_action (action),
    INDEX idx_audit_date (created_at)
);
```

---

## 3. RELATIONS ENTRE TABLES

```
cooperatives (1) ─── (n) producers
cooperatives (1) ─── (n) villages
cooperatives (1) ─── (n) users

villages (1) ─── (n) sections
villages (1) ─── (n) producers
villages (1) ─── (n) training_sessions

sections (1) ─── (n) producers

producers (1) ─── (n) children
producers (1) ─── (n) risk_assessments
producers (1) ─── (n) monitoring_visits
producers (1) ─── (n) remediation_plans
producers (1) ─── (n) traceability_blocks
producers (n) ─── (n) training_sessions (via participants JSONB)

children (1) ─── (n) risk_assessments
children (1) ─── (n) remediation_plans
children (1) ─── (n) complaints

risk_assessments (1) ─── (n) remediation_plans (triggered_by)

monitoring_visits (1) ─── (n) photos (stockées dans JSONB)

remediation_plans (1) ─── (n) remediation_actions

users (1) ─── (n) risk_assessments (as assessor)
users (1) ─── (n) monitoring_visits (as lead_assessor)
users (1) ─── (n) remediation_plans (as case_worker)
users (1) ─── (n) training_sessions (as trainer)
users (1) ─── (n) complaints (as investigator)
users (1) ─── (n) alerts (as assigned_to)
users (1) ─── (n) audit_logs

alerts (1) ─── (1) source_entity (polymorphic: producers, children, visits, etc.)

complaints (1) ─── (1) producers (optional)
complaints (1) ─── (1) child (optional)

traceability_blocks (1) ─── (1) producers
traceability_blocks (1) ─── (1) related_assessment (optional)
```

---

## 4. STRUCTURE DES DOSSIERS (Laravel 11 Example)

```
cacaoguard/
├── app/
│   ├── Models/
│   │   ├── Cooperative.php
│   │   ├── Producer.php
│   │   ├── Child.php
│   │   ├── RiskAssessment.php
│   │   ├── MonitoringVisit.php
│   │   ├── RemediationPlan.php
│   │   ├── RemediationAction.php
│   │   ├── TrainingSession.php
│   │   ├── TraceabilityBlock.php
│   │   ├── Alert.php
│   │   ├── Complaint.php
│   │   ├── Village.php
│   │   ├── Section.php
│   │   ├── User.php
│   │   ├── AuditLog.php
│   │   └── SyncQueue.php
│   │
│   ├── Http/
│   │   ├── Controllers/
│   │   │   ├── Api/
│   │   │   │   ├── V1/
│   │   │   │   │   ├── DashboardController.php
│   │   │   │   │   ├── ProducerController.php
│   │   │   │   │   ├── ChildController.php
│   │   │   │   │   ├── RiskAssessmentController.php
│   │   │   │   │   ├── MonitoringVisitController.php
│   │   │   │   │   ├── RemediationPlanController.php
│   │   │   │   │   ├── TrainingController.php
│   │   │   │   │   ├── TraceabilityController.php
│   │   │   │   │   ├── AlertController.php
│   │   │   │   │   ├── ComplaintController.php
│   │   │   │   │   ├── SyncController.php
│   │   │   │   │   └── ReportController.php
│   │   │   │   │
│   │   │   │   └── Mobile/
│   │   │   │       └── OfflineSyncController.php
│   │   │   │
│   │   │   └── Web/
│   │   │       ├── DashboardController.php
│   │   │       ├── ProducerController.php
│   │   │       ├── ChildController.php
│   │   │       ├── RiskAssessmentController.php
│   │   │       ├── MonitoringVisitController.php
│   │   │       ├── RemediationPlanController.php
│   │   │       ├── TrainingController.php
│   │   │       ├── ReportController.php
│   │   │       └── SettingsController.php
│   │   │
│   │   ├── Requests/
│   │   │   ├── StoreProducerRequest.php
│   │   │   ├── UpdateProducerRequest.php
│   │   │   ├── StoreChildRequest.php
│   │   │   ├── StoreRiskAssessmentRequest.php
│   │   │   ├── StoreMonitoringVisitRequest.php
│   │   │   ├── StoreRemediationPlanRequest.php
│   │   │   └── ...
│   │   │
│   │   └── Resources/
│   │       ├── ProducerResource.php
│   │       ├── ChildResource.php
│   │       ├── RiskAssessmentResource.php
│   │       └── ...
│   │
│   ├── Services/
│   │   ├── RiskScoringService.php
│   │   ├── ChildProtectionService.php
│   │   ├── RemediationService.php
│   │   ├── TraceabilityService.php
│   │   ├── AlertService.php
│   │   ├── SyncService.php
│   │   ├── ReportGenerationService.php
│   │   └── NotificationService.php
│   │
│   ├── Rules/
│   │   ├── ValidChildAge.php
│   │   ├── ValidGpsCoordinates.php
│   │   └── ...
│   │
│   ├── Observers/
│   │   ├── ProducerObserver.php
│   │   ├── ChildObserver.php
│   │   ├── RiskAssessmentObserver.php
│   │   └── ...
│   │
│   ├── Jobs/
│   │   ├── ProcessRiskAssessment.php
│   │   ├── GenerateAlerts.php
│   │   ├── SendNotifications.php
│   │   ├── SyncData.php
│   │   └── ...
│   │
│   ├── Notifications/
│   │   ├── HighRiskAlertNotification.php
│   │   ├── OverdueActionNotification.php
│   │   ├── VisitReminderNotification.php
│   │   └── ...
│   │
│   └── Traits/
│       ├── HasUuid.php
│       ├── HasAuditTrail.php
│       ├── HasGeoLocation.php
│       └── Syncable.php
│
├── database/
│   ├── migrations/
│   │   ├── 2024_01_01_000001_create_cooperatives_table.php
│   │   ├── 2024_01_01_000002_create_villages_table.php
│   │   ├── 2024_01_01_000003_create_sections_table.php
│   │   ├── 2024_01_01_000004_create_users_table.php
│   │   ├── 2024_01_01_000005_create_producers_table.php
│   │   ├── 2024_01_01_000006_create_children_table.php
│   │   ├── 2024_01_01_000007_create_risk_assessments_table.php
│   │   ├── 2024_01_01_000008_create_monitoring_visits_table.php
│   │   ├── 2024_01_01_000009_create_remediation_plans_table.php
│   │   ├── 2024_01_01_000010_create_remediation_actions_table.php
│   │   ├── 2024_01_01_000011_create_training_sessions_table.php
│   │   ├── 2024_01_01_000012_create_traceability_blocks_table.php
│   │   ├── 2024_01_01_000013_create_alerts_table.php
│   │   ├── 2024_01_01_000014_create_complaints_table.php
│   │   ├── 2024_01_01_000015_create_audit_logs_table.php
│   │   └── 2024_01_01_000016_create_sync_queue_table.php
│   │
│   └── seeders/
│       ├── CooperativeSeeder.php
│       ├── UserSeeder.php
│       ├── VillageSeeder.php
│       └── ...
│
├── routes/
│   ├── api.php
│   ├── web.php
│   └── mobile.php
│
├── resources/
│   ├── views/
│   │   ├── dashboard/
│   │   ├── producers/
│   │   ├── children/
│   │   ├── risk-assessments/
│   │   ├── monitoring-visits/
│   │   ├── remediation/
│   │   ├── training/
│   │   ├── reports/
│   │   └── ...
│   │
│   └── js/
│       ├── components/
│       │   ├── Dashboard/
│       │   ├── Producers/
│       │   ├── Children/
│       │   ├── RiskAssessment/
│       │   ├── MonitoringVisits/
│       │   ├── Remediation/
│       │   ├── Training/
│       │   ├── Reports/
│       │   └── Shared/
│       │
│       └── app.js
│
├── storage/
│   ├── app/
│   │   ├── public/
│   │   │   ├── photos/
│   │   │   │   └── visits/
│   │   │   ├── documents/
│   │   │   │   └── reports/
│   │   │   └── signatures/
│   │   │
│   │   └── private/
│   │       └── encrypted/
│   │
│   └── ...
│
├── tests/
│   ├── Feature/
│   │   ├── RiskAssessmentTest.php
│   │   ├── RemediationPlanTest.php
│   │   ├── TraceabilityBlockTest.php
│   │   └── ...
│   │
│   └── Unit/
│       ├── RiskScoringServiceTest.php
│       └── ...
│
├── .env.example
├── composer.json
├── package.json
├── vite.config.js
└── README.md
```

---

## 5. API ENDPOINTS PRINCIPAUX

### 5.1 Authentication & Users
```
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
POST   /api/v1/auth/refresh
GET    /api/v1/users/profile
PUT    /api/v1/users/profile
```

### 5.2 Dashboard
```
GET    /api/v1/dashboard/summary
GET    /api/v1/dashboard/kpis
GET    /api/v1/dashboard/map-data
GET    /api/v1/dashboard/alerts
GET    /api/v1/dashboard/statistics
```

### 5.3 Producers
```
GET    /api/v1/producers              # List with filters
POST   /api/v1/producers              # Create
GET    /api/v1/producers/{id}         # Get details
PUT    /api/v1/producers/{id}         # Update
DELETE /api/v1/producers/{id}         # Delete (soft)
GET    /api/v1/producers/{id}/children
GET    /api/v1/producers/{id}/assessments
GET    /api/v1/producers/{id}/visits
GET    /api/v1/producers/{id}/remediation-plans
GET    /api/v1/producers/{id}/traceability-status
```

### 5.4 Children
```
GET    /api/v1/children               # List with filters
POST   /api/v1/children               # Create
GET    /api/v1/children/{id}          # Get details
PUT    /api/v1/children/{id}          # Update
DELETE /api/v1/children/{id}          # Delete (soft)
GET    /api/v1/children/{id}/risk-history
GET    /api/v1/children/{id}/remediation-plans
```

### 5.5 Risk Assessments
```
GET    /api/v1/risk-assessments       # List
POST   /api/v1/risk-assessments       # Create & calculate score
GET    /api/v1/risk-assessments/{id}  # Get details
PUT    /api/v1/risk-assessments/{id}  # Update
POST   /api/v1/risk-assessments/{id}/validate
GET    /api/v1/risk-assessments/statistics
```

### 5.6 Monitoring Visits
```
GET    /api/v1/monitoring-visits      # List with filters
POST   /api/v1/monitoring-visits      # Create
GET    /api/v1/monitoring-visits/{id} # Get details
PUT    /api/v1/monitoring-visits/{id} # Update
POST   /api/v1/monitoring-visits/{id}/complete
GET    /api/v1/monitoring-visits/schedule
POST   /api/v1/monitoring-visits/bulk-sync # Mobile sync
```

### 5.7 Remediation Plans
```
GET    /api/v1/remediation-plans              # List
POST   /api/v1/remediation-plans              # Create
GET    /api/v1/remediation-plans/{id}         # Get details
PUT    /api/v1/remediation-plans/{id}         # Update
POST   /api/v1/remediation-plans/{id}/approve
POST   /api/v1/remediation-plans/{id}/complete
GET    /api/v1/remediation-plans/{id}/actions
POST   /api/v1/remediation-plans/{id}/actions # Add action
PUT    /api/v1/remediation-plans/{id}/actions/{actionId}
```

### 5.8 Training Sessions
```
GET    /api/v1/training-sessions      # List
POST   /api/v1/training-sessions      # Create
GET    /api/v1/training-sessions/{id} # Get details
PUT    /api/v1/training-sessions/{id} # Update
POST   /api/v1/training-sessions/{id}/complete
POST   /api/v1/training-sessions/{id}/register
GET    /api/v1/training-sessions/statistics
```

### 5.9 Traceability
```
GET    /api/v1/traceability/blocks    # List active blocks
POST   /api/v1/traceability/blocks    # Create block
PUT    /api/v1/traceability/blocks/{id}/resolve
GET    /api/v1/traceability/producer/{id}/status
GET    /api/v1/traceability/batch/{batchId}/status
```

### 5.10 Alerts
```
GET    /api/v1/alerts                 # List with filters
GET    /api/v1/alerts/{id}            # Get details
PUT    /api/v1/alerts/{id}/acknowledge
PUT    /api/v1/alerts/{id}/resolve
PUT    /api/v1/alerts/{id}/escalate
GET    /api/v1/alerts/unread-count
```

### 5.11 Complaints
```
GET    /api/v1/complaints             # List (restricted access)
POST   /api/v1/complaints             # Create (anonymous possible)
GET    /api/v1/complaints/{id}        # Get details (restricted)
PUT    /api/v1/complaints/{id}        # Update investigation
POST   /api/v1/complaints/{id}/escalate
```

### 5.12 Reports
```
GET    /api/v1/reports/child-labor-summary
GET    /api/v1/reports/remediation-progress
GET    /api/v1/reports/training-effectiveness
GET    /api/v1/reports/audit-trail
GET    /api/v1/reports/due-diligence
POST   /api/v1/reports/export-pdf
POST   /api/v1/reports/export-excel
```

### 5.13 Sync (Mobile)
```
POST   /api/v1/sync/pull              # Get changes from server
POST   /api/v1/sync/push              # Send local changes
POST   /api/v1/sync/conflict/resolve  # Resolve conflicts
GET    /api/v1/sync/status            # Check sync status
```

---

## 6. MODÈLES DE DONNÉES CLÉS (Extraits)

### Producer Model (Laravel)
```php
class Producer extends Model
{
    use HasUuid, HasAuditTrail, HasGeoLocation, Syncable;
    
    protected $fillable = [
        'cooperative_id', 'producer_code', 'first_name', 'last_name',
        'date_of_birth', 'gender', 'phone', 'farm_name', 'farm_size_hectares',
        'farm_location', 'village_id', 'section_id', 'status', 'risk_level'
    ];
    
    protected $casts = [
        'farm_location' => 'geography',
        'date_of_birth' => 'date',
        'farm_size_hectares' => 'decimal:2'
    ];
    
    // Relations
    public function children() { return $this->hasMany(Child::class); }
    public function riskAssessments() { return $this->hasMany(RiskAssessment::class); }
    public function monitoringVisits() { return $this->hasMany(MonitoringVisit::class); }
    public function remediationPlans() { return $this->hasMany(RemediationPlan::class); }
    public function traceabilityBlocks() { return $this->hasMany(TraceabilityBlock::class); }
    public function village() { return $this->belongsTo(Village::class); }
    public function section() { return $this->belongsTo(Section::class); }
    
    // Scopes
    public function scopeActive($query) { return $query->where('status', 'active'); }
    public function scopeHighRisk($query) { return $query->where('risk_level', 'high'); }
    public function scopeInVillage($query, $villageId) { return $query->where('village_id', $villageId); }
    
    // Methods
    public function calculateRiskLevel(): string { /* ... */ }
    public function hasActiveChildLaborCase(): bool { /* ... */ }
    public function isTraceabilityBlocked(): bool { /* ... */ }
}
```

### Child Model (Laravel)
```php
class Child extends Model
{
    use HasUuid, HasAuditTrail, Syncable;
    
    protected $fillable = [
        'producer_id', 'first_name', 'last_name', 'date_of_birth', 'gender',
        'school_status', 'school_name', 'school_grade', 'school_distance_km',
        'risk_score', 'risk_level', 'risk_factors', 'is_working_on_farm',
        'work_frequency', 'dangerous_tasks_performed', 'last_assessment_date'
    ];
    
    protected $casts = [
        'date_of_birth' => 'date',
        'risk_factors' => 'array',
        'dangerous_tasks_performed' => 'array',
        'school_distance_km' => 'decimal:2',
        'risk_score' => 'decimal:2'
    ];
    
    // Relations
    public function producer() { return $this->belongsTo(Producer::class); }
    public function riskAssessments() { return $this->hasMany(RiskAssessment::class); }
    public function remediationPlans() { return $this->hasMany(RemediationPlan::class); }
    
    // Scopes
    public function scopeOfAge($query, $minAge, $maxAge) { /* ... */ }
    public function scopeOutOfSchool($query) { return $query->where('school_status', '!=', 'enrolled'); }
    public function scopeHighRisk($query) { return $query->where('risk_level', 'high'); }
    
    // Methods
    public function getAgeAttribute(): int { /* Calculate from DOB */ }
    public function isOfWorkingAge(): bool { return $this->age >= 15; }
    public function isAtRisk(): bool { return in_array($this->risk_level, ['medium', 'high', 'critical']); }
    public function requiresRemediation(): bool { /* ... */ }
}
```

### RiskAssessment Model (Laravel)
```php
class RiskAssessment extends Model
{
    use HasUuid, HasAuditTrail, Syncable;
    
    protected $fillable = [
        'producer_id', 'child_id', 'assessment_type', 'assessment_date',
        'overall_risk_score', 'overall_risk_level', 'risk_factors',
        'assessor_id', 'assessment_location', 'methodology_version', 'status'
    ];
    
    protected $casts = [
        'assessment_date' => 'date',
        'risk_factors' => 'array',
        'assessment_location' => 'geography',
        'overall_risk_score' => 'decimal:2',
        'validated_at' => 'datetime'
    ];
    
    // Relations
    public function producer() { return $this->belongsTo(Producer::class); }
    public function child() { return $this->belongsTo(Child::class); }
    public function assessor() { return $this->belongsTo(User::class, 'assessor_id'); }
    public function validator() { return $this->belongsTo(User::class, 'validated_by'); }
    public function remediationPlans() { return $this->hasMany(RemediationPlan::class, 'triggered_by'); }
    
    // Methods
    public function calculateScore(array $data): float {
        return app(RiskScoringService::class)->calculate($data);
    }
    
    public function determineRiskLevel(float $score): string {
        if ($score >= 80) return 'critical';
        if ($score >= 60) return 'high';
        if ($score >= 40) return 'medium';
        return 'low';
    }
    
    public function shouldTriggerRemediation(): bool {
        return in_array($this->overall_risk_level, ['high', 'critical']);
    }
}
```

---

## 7. PROCHAINES ÉTAPES

Après validation de cette architecture, nous procéderons à :

1. **Création des migrations** - Toutes les tables avec contraintes
2. **Implémentation des modèles** - Avec relations et méthodes métier
3. **Développement des API** - Endpoints RESTful complets
4. **Logique de scoring** - Algorithme de calcul de risque détaillé
5. **Système de remédiation** - Workflow complet avec approvals
6. **Interface dashboard** - Visualisation des KPI et cartes
7. **Application mobile** - Synchronisation offline-first
8. **Rapports et exports** - PDF, Excel, conformité EUDR

Cette architecture est conçue pour être **évolutive**, **sécurisée** et **adaptée au contexte ivoirien** avec ses défis de connectivité et de littératie numérique.