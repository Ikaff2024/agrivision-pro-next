# CacaoGuard - Feuille de Route d'Implémentation
## Guide Complet de Déploiement

---

## 1. PHASE 1: CONFIGURATION INITIALE (Semaines 1-2)

### 1.1 Prérequis Système

```bash
# Système d'exploitation
- Ubuntu 20.04+ / Windows 11 / macOS 12+

# PHP (pour Laravel)
- PHP 8.2+ avec extensions: pgsql, redis, gd, mbstring, xml, bcmath

# Node.js (pour frontend)
- Node.js 18+ et npm 9+

# Base de données
- PostgreSQL 15+
- Redis 7+

# Outils de développement
- Git
- Docker et Docker Compose (optionnel mais recommandé)
- Composer (gestionnaire de paquets PHP)
```

### 1.2 Installation de l'Environnement de Développement

```bash
# 1. Créer le projet Laravel
composer create-project laravel/laravel:^11.0 cacaoguard
cd cacaoguard

# 2. Installer les dépendances frontend
npm install

# 3. Configurer l'environnement
cp .env.example .env
php artisan key:generate

# 4. Configurer la base de données dans .env
DB_CONNECTION=pgsql
DB_HOST=127.0.0.1
DB_PORT=5432
DB_DATABASE=cacaoguard
DB_USERNAME=cacaoguard_user
DB_PASSWORD=votre_mot_de_passe_secure

# 5. Installer les packages additionnels
composer require spatie/laravel-permission
composer require laravel/sanctum
composer require intervention/image
composer require maatwebsite/excel
composer require barryvdh/laravel-dompdf
composer require league/flysystem-aws-s3-v3

# 6. Lancer les migrations (après création)
php artisan migrate

# 7. Démarrer le serveur de développement
php artisan serve
npm run dev
```

### 1.3 Structure de Projet Finale

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
│   │   │   │   └── V1/
│   │   │   │       ├── AuthController.php
│   │   │   │       ├── DashboardController.php
│   │   │   │       ├── ProducerController.php
│   │   │   │       ├── ChildController.php
│   │   │   │       ├── RiskAssessmentController.php
│   │   │   │       ├── MonitoringVisitController.php
│   │   │   │       ├── RemediationPlanController.php
│   │   │   │       ├── TrainingController.php
│   │   │   │       ├── TraceabilityController.php
│   │   │   │       ├── AlertController.php
│   │   │   │       ├── ComplaintController.php
│   │   │   │       ├── SyncController.php
│   │   │   │       └── ReportController.php
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
│   │   │   ├── Auth/
│   │   │   │   ├── LoginRequest.php
│   │   │   │   └── RegisterRequest.php
│   │   │   │
│   │   │   ├── Producer/
│   │   │   │   ├── StoreProducerRequest.php
│   │   │   │   └── UpdateProducerRequest.php
│   │   │   │
│   │   │   ├── Child/
│   │   │   │   ├── StoreChildRequest.php
│   │   │   │   └── UpdateChildRequest.php
│   │   │   │
│   │   │   ├── RiskAssessment/
│   │   │   │   ├── StoreRiskAssessmentRequest.php
│   │   │   │   └── UpdateRiskAssessmentRequest.php
│   │   │   │
│   │   │   ├── MonitoringVisit/
│   │   │   │   ├── StoreMonitoringVisitRequest.php
│   │   │   │   └── UpdateMonitoringVisitRequest.php
│   │   │   │
│   │   │   └── RemediationPlan/
│   │   │       ├── StoreRemediationPlanRequest.php
│   │   │       └── UpdateRemediationPlanRequest.php
│   │   │
│   │   └── Resources/
│   │       ├── ProducerResource.php
│   │       ├── ChildResource.php
│   │       ├── RiskAssessmentResource.php
│   │       ├── MonitoringVisitResource.php
│   │       ├── RemediationPlanResource.php
│   │       └── UserResource.php
│   │
│   ├── Services/
│   │   ├── RiskScoringService.php
│   │   ├── ChildProtectionService.php
│   │   ├── RemediationService.php
│   │   ├── RemediationPlanGenerator.php
│   │   ├── RemediationApprovalWorkflow.php
│   │   ├── RemediationActionTracker.php
│   │   ├── RemediationEscalationHandler.php
│   │   ├── TraceabilityService.php
│   │   ├── AlertService.php
│   │   ├── SyncService.php
│   │   ├── ReportGenerationService.php
│   │   ├── NotificationService.php
│   │   └── GeoLocationService.php
│   │
│   ├── Observers/
│   │   ├── ProducerObserver.php
│   │   ├── ChildObserver.php
│   │   ├── RiskAssessmentObserver.php
│   │   ├── MonitoringVisitObserver.php
│   │   └── RemediationPlanObserver.php
│   │
│   ├── Jobs/
│   │   ├── ProcessRiskAssessment.php
│   │   ├── GenerateAlerts.php
│   │   ├── SendNotifications.php
│   │   ├── SyncData.php
│   │   ├── GenerateReport.php
│   │   └── ProcessPhotoUpload.php
│   │
│   ├── Notifications/
│   │   ├── HighRiskAlertNotification.php
│   │   ├── OverdueActionNotification.php
│   │   ├── VisitReminderNotification.php
│   │   ├── PlanApprovalNotification.php
│   │   ├── PlanApprovedNotification.php
│   │   ├── PlanRejectedNotification.php
│   │   ├── PlanCompletedNotification.php
│   │   └── PlanEscalatedNotification.php
│   │
│   ├── Rules/
│   │   ├── ValidChildAge.php
│   │   ├── ValidGpsCoordinates.php
│   │   ├── ValidPhoneNumber.php
│   │   └── UniqueProducerCode.php
│   │
│   └── Traits/
│       ├── HasUuid.php
│       ├── HasAuditTrail.php
│       ├── HasGeoLocation.php
│       ├── Syncable.php
│       └── HasSignature.php
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
│   │   ├── 2024_01_01_000016_create_sync_queue_table.php
│   │   └── 2024_01_01_000017_create_permission_tables.php
│   │
│   └── seeders/
│       ├── DatabaseSeeder.php
│       ├── CooperativeSeeder.php
│       ├── UserSeeder.php
│       ├── VillageSeeder.php
│       ├── ProducerSeeder.php
│       └── RiskThresholdSeeder.php
│
├── routes/
│   ├── api.php
│   ├── web.php
│   └── mobile.php
│
├── resources/
│   ├── views/
│   │   ├── layouts/
│   │   │   ├── app.blade.php
│   │   │   └── guest.blade.php
│   │   │
│   │   ├── auth/
│   │   │   ├── login.blade.php
│   │   │   └── register.blade.php
│   │   │
│   │   ├── dashboard/
│   │   │   └── index.blade.php
│   │   │
│   │   ├── producers/
│   │   │   ├── index.blade.php
│   │   │   ├── create.blade.php
│   │   │   ├── edit.blade.php
│   │   │   └── show.blade.php
│   │   │
│   │   ├── children/
│   │   │   ├── index.blade.php
│   │   │   └── show.blade.php
│   │   │
│   │   ├── risk-assessments/
│   │   │   ├── create.blade.php
│   │   │   └── show.blade.php
│   │   │
│   │   ├── monitoring-visits/
│   │   │   ├── schedule.blade.php
│   │   │   ├── execute.blade.php
│   │   │   └── report.blade.php
│   │   │
│   │   ├── remediation/
│   │   │   ├── plans/
│   │   │   │   ├── index.blade.php
│   │   │   │   ├── show.blade.php
│   │   │   │   └── approve.blade.php
│   │   │   │
│   │   │   └── actions/
│   │   │       └── track.blade.php
│   │   │
│   │   ├── training/
│   │   │   ├── index.blade.php
│   │   │   └── show.blade.php
│   │   │
│   │   ├── reports/
│   │   │   ├── index.blade.php
│   │   │   ├── child-labor-summary.blade.php
│   │   │   └── due-diligence.blade.php
│   │   │
│   │   └── settings/
│   │       └── index.blade.php
│   │
│   └── js/
│       ├── app.js
│       ├── bootstrap.js
│       │
│       └── components/
│           ├── Dashboard/
│           │   ├── KPI.vue
│           │   ├── RiskMap.vue
│           │   ├── AlertsPanel.vue
│           │   └── StatisticsChart.vue
│           │
│           ├── Producers/
│           │   ├── ProducerList.vue
│           │   ├── ProducerForm.vue
│           │   ├── ProducerCard.vue
│           │   └── FamilySection.vue
│           │
│           ├── Children/
│           │   ├── ChildList.vue
│           │   ├── ChildProfile.vue
│           │   └── RiskIndicator.vue
│           │
│           ├── RiskAssessment/
│           │   ├── AssessmentForm.vue
│           │   ├── Questionnaire.vue
│           │   ├── ScoreCalculator.vue
│           │   └── RiskFactors.vue
│           │
│           ├── MonitoringVisits/
│           │   ├── VisitScheduler.vue
│           │   ├── VisitChecklist.vue
│           │   ├── PhotoCapture.vue
│           │   └── SignaturePad.vue
│           │
│           ├── Remediation/
│           │   ├── PlanGenerator.vue
│           │   ├── PlanTimeline.vue
│           │   ├── ActionTracker.vue
│           │   └── ProgressChart.vue
│           │
│           ├── Training/
│           │   ├── SessionManager.vue
│           │   └── ParticipantTracker.vue
│           │
│           ├── Reports/
│           │   ├── ReportBuilder.vue
│           │   ├── PDFExport.vue
│           │   └── ExcelExport.vue
│           │
│           └── Shared/
│               ├── Header.vue
│               ├── Sidebar.vue
│               ├── Modal.vue
│               ├── DataTable.vue
│               ├── Pagination.vue
│               └── LoadingSpinner.vue
│
├── storage/
│   └── app/
│       ├── public/
│       │   ├── photos/
│       │   │   └── visits/
│       │   ├── documents/
│       │   │   └── reports/
│       │   └── signatures/
│       │
│       └── private/
│           └── encrypted/
│
├── tests/
│   ├── Feature/
│   │   ├── AuthTest.php
│   │   ├── ProducerManagementTest.php
│   │   ├── RiskAssessmentTest.php
│   │   ├── RemediationPlanTest.php
│   │   ├── TraceabilityBlockTest.php
│   │   └── SyncTest.php
│   │
│   └── Unit/
│       ├── RiskScoringServiceTest.php
│       ├── RemediationPlanGeneratorTest.php
│       └── AlertServiceTest.php
│
├── .env.example
├── .gitignore
├── composer.json
├── package.json
├── phpunit.xml
├── vite.config.js
├── tailwind.config.js
├── README.md
└── ARCHITECTURE.md
```

---

## 2. PHASE 2: MIGRATIONS DE BASE DE DONNÉES (Semaine 3)

### 2.1 Création des Migrations

```bash
# Créer toutes les migrations
php artisan make:migration create_cooperatives_table
php artisan make:migration create_villages_table
php artisan make:migration create_sections_table
php artisan make:migration create_users_table
php artisan make:migration create_producers_table
php artisan make:migration create_children_table
php artisan make:migration create_risk_assessments_table
php artisan make:migration create_monitoring_visits_table
php artisan make:migration create_remediation_plans_table
php artisan make:migration create_remediation_actions_table
php artisan make:migration create_training_sessions_table
php artisan make:migration create_traceability_blocks_table
php artisan make:migration create_alerts_table
php artisan make:migration create_complaints_table
php artisan make:migration create_audit_logs_table
php artisan make:migration create_sync_queue_table
```

### 2.2 Exemple de Migration Complète (Producer)

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * Table: producers (Producteurs de cacao)
     * Description: Informations sur les producteurs membres de la coopérative
     */
    public function up(): void
    {
        Schema::create('producers', function (Blueprint $table) {
            // Primary Key
            $table->uuid('id')->primary();
            
            // Foreign Keys
            $table->uuid('cooperative_id');
            $table->foreign('cooperative_id')
                ->references('id')
                ->on('cooperatives')
                ->onDelete('cascade');
            
            $table->uuid('village_id')->nullable();
            $table->foreign('village_id')
                ->references('id')
                ->on('villages')
                ->onDelete('set null');
            
            $table->uuid('section_id')->nullable();
            $table->foreign('section_id')
                ->references('id')
                ->on('sections')
                ->onDelete('set null');
            
            $table->uuid('created_by')->nullable();
            $table->foreign('created_by')
                ->references('id')
                ->on('users')
                ->onDelete('set null');
            
            // Code producteur unique (ex: CI-COOP-001)
            $table->string('producer_code', 20)->unique();
            
            // Informations personnelles
            $table->string('first_name', 100);
            $table->string('last_name', 100);
            $table->date('date_of_birth')->nullable();
            $table->enum('gender', ['M', 'F']);
            $table->string('phone', 20)->nullable();
            $table->string('id_card_number', 50)->nullable();
            $table->date('id_card_expiry')->nullable();
            
            // Informations ferme
            $table->string('farm_name', 200)->nullable();
            $table->decimal('farm_size_hectares', 8, 2)->default(0);
            $table->text('farm_address')->nullable();
            
            // Géolocalisation (PostGIS)
            // Note: Requires postgres-extender package or raw SQL
            $table->point('farm_location')->nullable();
            
            // Statut
            $table->enum('status', ['active', 'inactive', 'suspended', 'blacklisted'])
                ->default('active');
            
            $table->enum('certification_status', [
                'none', 'rainforest', 'fairtrade', 'cocoa_horizons', 'organic'
            ])->default('none');
            
            // Niveau de risque (calculé automatiquement)
            $table->enum('risk_level', ['low', 'medium', 'high', 'critical'])
                ->default('low');
            
            // Métadonnées
            $table->timestamp('last_sync_at')->nullable();
            $table->timestamps();
            
            // Index
            $table->index('cooperative_id');
            $table->index('village_id');
            $table->index('section_id');
            $table->index('status');
            $table->index('risk_level');
            $table->index('certification_status');
            
            // Index composite pour recherches courantes
            $table->index(['cooperative_id', 'status']);
            $table->index(['cooperative_id', 'risk_level']);
            $table->index(['village_id', 'status']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('producers');
    }
};
```

### 2.3 Migration pour Table avec JSONB (RiskAssessment)

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * Table: risk_assessments (Évaluations des risques)
     * Description: Évaluations périodiques du risque de travail des enfants
     */
    public function up(): void
    {
        Schema::create('risk_assessments', function (Blueprint $table) {
            $table->uuid('id')->primary();
            
            // Foreign Keys
            $table->uuid('producer_id');
            $table->foreign('producer_id')
                ->references('id')
                ->on('producers')
                ->onDelete('cascade');
            
            $table->uuid('child_id')->nullable();
            $table->foreign('child_id')
                ->references('id')
                ->on('children')
                ->onDelete('cascade');
            
            $table->uuid('assessor_id');
            $table->foreign('assessor_id')
                ->references('id')
                ->on('users')
                ->onDelete('restrict');
            
            $table->uuid('validated_by')->nullable();
            $table->foreign('validated_by')
                ->references('id')
                ->on('users')
                ->onDelete('set null');
            
            // Type d'évaluation
            $table->enum('assessment_type', [
                'initial',      // Première évaluation
                'annual',       // Évaluation annuelle
                'follow_up',    // Suivi post-remédiation
                'complaint',    // Suite à une plainte
                'emergency'     // Urgence
            ]);
            
            // Date d'évaluation
            $table->date('assessment_date')->default(DB::raw('CURRENT_DATE'));
            
            // Score et niveau de risque
            $table->decimal('overall_risk_score', 5, 2);
            $table->enum('overall_risk_level', ['low', 'medium', 'high', 'critical']);
            
            // Facteurs de risque détaillés (JSON)
            // Structure: {age_risk, education_risk, work_risk, economic_risk, geographic_risk, history_risk}
            $table->jsonb('risk_factors');
            
            // Localisation de l'évaluation
            $table->point('assessment_location')->nullable();
            
            // Version de la méthodologie de scoring
            $table->string('methodology_version', 20)->default('1.0');
            
            // Statut
            $table->enum('status', ['draft', 'completed', 'validated', 'escalated'])
                ->default('completed');
            
            // Timestamps
            $table->timestamp('validated_at')->nullable();
            $table->timestamps();
            
            // Index
            $table->index('producer_id');
            $table->index('child_id');
            $table->index('assessor_id');
            $table->index('assessment_date');
            $table->index('overall_risk_level');
            $table->index('status');
            
            // Index pour recherches par date et risque
            $table->index(['assessment_date', 'overall_risk_level']);
            $table->index(['producer_id', 'assessment_date']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('risk_assessments');
    }
};
```

---

## 3. PHASE 3: MODÈLES ET RELATIONS (Semaine 4)

### 3.1 Modèle Producer

```php
<?php

namespace App\Models;

use App\Traits\HasUuid;
use App\Traits\HasAuditTrail;
use App\Traits\HasGeoLocation;
use App\Traits\Syncable;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Producer extends Model
{
    use HasFactory, HasUuid, HasAuditTrail, HasGeoLocation, Syncable;

    /**
     * The attributes that are mass assignable.
     */
    protected $fillable = [
        'cooperative_id',
        'producer_code',
        'first_name',
        'last_name',
        'date_of_birth',
        'gender',
        'phone',
        'id_card_number',
        'id_card_expiry',
        'farm_name',
        'farm_size_hectares',
        'farm_location',
        'farm_address',
        'village_id',
        'section_id',
        'status',
        'certification_status',
        'risk_level',
        'created_by',
    ];

    /**
     * The attributes that should be cast.
     */
    protected $casts = [
        'date_of_birth' => 'date',
        'id_card_expiry' => 'date',
        'farm_size_hectares' => 'decimal:2',
        'farm_location' => 'geography',
    ];

    /**
     * Boot the model.
     */
    protected static function boot()
    {
        parent::boot();

        static::creating(function ($producer) {
            if (empty($producer->producer_code)) {
                $producer->producer_code = self::generateProducerCode($producer->cooperative_id);
            }
        });

        static::updated(function ($producer) {
            if ($producer->isDirty('risk_level')) {
                // Log risk level change for audit
                AuditLog::create([
                    'action' => 'risk_level_changed',
                    'entity_type' => 'producer',
                    'entity_id' => $producer->id,
                    'old_values' => ['risk_level' => $producer->getOriginal('risk_level')],
                    'new_values' => ['risk_level' => $producer->risk_level],
                ]);
            }
        });
    }

    /**
     * Generate unique producer code.
     */
    private static function generateProducerCode(string $cooperativeId): string
    {
        $cooperative = Cooperative::find($cooperativeId);
        $prefix = strtoupper(substr($cooperative->code, 0, 4));
        $lastProducer = self::where('cooperative_id', $cooperativeId)
            ->orderBy('id', 'desc')
            ->first();
        
        $nextNumber = $lastProducer 
            ? intval(substr($lastProducer->producer_code, -4)) + 1 
            : 1;
        
        return sprintf('%s-%04d', $prefix, $nextNumber);
    }

    // ==================== RELATIONS ====================

    public function cooperative(): BelongsTo
    {
        return $this->belongsTo(Cooperative::class);
    }

    public function village(): BelongsTo
    {
        return $this->belongsTo(Village::class);
    }

    public function section(): BelongsTo
    {
        return $this->belongsTo(Section::class);
    }

    public function children(): HasMany
    {
        return $this->hasMany(Child::class);
    }

    public function riskAssessments(): HasMany
    {
        return $this->hasMany(RiskAssessment::class);
    }

    public function monitoringVisits(): HasMany
    {
        return $this->hasMany(MonitoringVisit::class);
    }

    public function remediationPlans(): HasMany
    {
        return $this->hasMany(RemediationPlan::class);
    }

    public function traceabilityBlocks(): HasMany
    {
        return $this->hasMany(TraceabilityBlock::class);
    }

    public function createdBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }

    // ==================== SCOPES ====================

    public function scopeActive($query)
    {
        return $query->where('status', 'active');
    }

    public function scopeInactive($query)
    {
        return $query->where('status', 'inactive');
    }

    public function scopeSuspended($query)
    {
        return $query->where('status', 'suspended');
    }

    public function scopeBlacklisted($query)
    {
        return $query->where('status', 'blacklisted');
    }

    public function scopeHighRisk($query)
    {
        return $query->whereIn('risk_level', ['high', 'critical']);
    }

    public function scopeMediumRisk($query)
    {
        return $query->where('risk_level', 'medium');
    }

    public function scopeLowRisk($query)
    {
        return $query->where('risk_level', 'low');
    }

    public function scopeInVillage($query, string $villageId)
    {
        return $query->where('village_id', $villageId);
    }

    public function scopeInSection($query, string $sectionId)
    {
        return $query->where('section_id', $sectionId);
    }

    public function scopeWithCertification($query, string $certification)
    {
        return $query->where('certification_status', $certification);
    }

    public function scopeSearch($query, string $searchTerm)
    {
        return $query->where(function ($q) use ($searchTerm) {
            $q->where('first_name', 'like', "%{$searchTerm}%")
              ->orWhere('last_name', 'like', "%{$searchTerm}%")
              ->orWhere('producer_code', 'like', "%{$searchTerm}%")
              ->orWhere('phone', 'like', "%{$searchTerm}%");
        });
    }

    // ==================== METHODS ====================

    /**
     * Get producer's full name.
     */
    public function getFullNameAttribute(): string
    {
        return "{$this->first_name} {$this->last_name}";
    }

    /**
     * Check if producer has active children.
     */
    public function hasActiveChildren(): bool
    {
        return $this->children()->where('is_active', true)->exists();
    }

    /**
     * Get children at risk.
     */
    public function getChildrenAtRiskAttribute()
    {
        return $this->children()->whereIn('risk_level', ['medium', 'high', 'critical'])->get();
    }

    /**
     * Check if producer has active child labor case.
     */
    public function hasActiveChildLaborCase(): bool
    {
        return $this->remediationPlans()
            ->whereIn('status', ['in_progress', 'pending_approval', 'approved'])
            ->exists();
    }

    /**
     * Check if producer is traceability blocked.
     */
    public function isTraceabilityBlocked(): bool
    {
        return $this->traceabilityBlocks()
            ->where('status', 'active')
            ->exists();
    }

    /**
     * Get latest risk assessment.
     */
    public function getLatestRiskAssessmentAttribute()
    {
        return $this->riskAssessments()
            ->orderBy('assessment_date', 'desc')
            ->first();
    }

    /**
     * Calculate and update risk level based on children's risk.
     */
    public function calculateRiskLevel(): string
    {
        $children = $this->children()->where('is_active', true)->get();
        
        if ($children->isEmpty()) {
            $this->risk_level = 'low';
            $this->save();
            return 'low';
        }

        $highestRisk = $children->max('risk_level');
        
        // Map child risk level to producer risk level
        $riskMapping = [
            'critical' => 'critical',
            'high' => 'high',
            'medium' => 'medium',
            'low' => 'low',
            'none' => 'low',
        ];

        $this->risk_level = $riskMapping[$highestRisk] ?? 'low';
        $this->save();
        
        return $this->risk_level;
    }

    /**
     * Get producer's location coordinates.
     */
    public function getCoordinatesAttribute(): ?array
    {
        if (!$this->farm_location) {
            return null;
        }

        return [
            'latitude' => $this->farm_location->getLatitude(),
            'longitude' => $this->farm_location->getLongitude(),
        ];
    }

    /**
     * Check if producer requires immediate attention.
     */
    public function requiresImmediateAttention(): bool
    {
        return $this->risk_level === 'critical' 
            || $this->hasActiveChildLaborCase()
            || $this->isTraceabilityBlocked();
    }

    /**
     * Get statistics for this producer.
     */
    public function getStatisticsAttribute(): array
    {
        return [
            'total_children' => $this->children()->count(),
            'children_in_school' => $this->children()->where('school_status', 'enrolled')->count(),
            'children_at_risk' => $this->children_at_risk->count(),
            'total_assessments' => $this->riskAssessments()->count(),
            'total_visits' => $this->monitoringVisits()->count(),
            'active_remediation_plans' => $this->remediationPlans()
                ->whereIn('status', ['in_progress', 'approved'])
                ->count(),
            'last_assessment_date' => $this->latestRiskAssessment?->assessment_date,
            'last_visit_date' => $this->monitoringVisits()
                ->orderBy('scheduled_date', 'desc')
                ->value('scheduled_date'),
        ];
    }
}
```

### 3.2 Modèle Child

```php
<?php

namespace App\Models;

use App\Traits\HasUuid;
use App\Traits\HasAuditTrail;
use App\Traits\Syncable;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Carbon\Carbon;

class Child extends Model
{
    use HasFactory, HasUuid, HasAuditTrail, Syncable;

    /**
     * The attributes that are mass assignable.
     */
    protected $fillable = [
        'producer_id',
        'first_name',
        'last_name',
        'date_of_birth',
        'gender',
        'birth_certificate_number',
        'school_status',
        'school_name',
        'school_grade',
        'school_distance_km',
        'school_attendance_rate',
        'risk_score',
        'risk_level',
        'risk_factors',
        'is_working_on_farm',
        'work_frequency',
        'dangerous_tasks_performed',
        'last_assessment_date',
        'next_assessment_date',
        'is_active',
        'created_by',
    ];

    /**
     * The attributes that should be cast.
     */
    protected $casts = [
        'date_of_birth' => 'date',
        'risk_factors' => 'array',
        'dangerous_tasks_performed' => 'array',
        'school_distance_km' => 'decimal:5,2',
        'school_attendance_rate' => 'decimal:5,2',
        'risk_score' => 'decimal:5,2',
        'last_assessment_date' => 'date',
        'next_assessment_date' => 'date',
        'is_active' => 'boolean',
    ];

    /**
     * Boot the model.
     */
    protected static function boot()
    {
        parent::boot();

        static::creating(function ($child) {
            // Set next assessment date if not set
            if (!$child->next_assessment_date) {
                $child->next_assessment_date = Carbon::now()->addMonths(6);
            }
        });

        static::updated(function ($child) {
            // Log significant changes
            if ($child->isDirty('risk_level')) {
                AuditLog::create([
                    'action' => 'child_risk_level_changed',
                    'entity_type' => 'child',
                    'entity_id' => $child->id,
                    'old_values' => ['risk_level' => $child->getOriginal('risk_level')],
                    'new_values' => ['risk_level' => $child->risk_level],
                ]);
            }

            if ($child->isDirty('school_status') && $child->school_status === 'enrolled') {
                // Log school enrollment for reporting
                AuditLog::create([
                    'action' => 'child_enrolled_school',
                    'entity_type' => 'child',
                    'entity_id' => $child->id,
                    'new_values' => [
                        'school_name' => $child->school_name,
                        'school_grade' => $child->school_grade,
                    ],
                ]);
            }
        });
    }

    // ==================== RELATIONS ====================

    public function producer(): BelongsTo
    {
        return $this->belongsTo(Producer::class);
    }

    public function riskAssessments(): HasMany
    {
        return $this->hasMany(RiskAssessment::class);
    }

    public function remediationPlans(): HasMany
    {
        return $this->hasMany(RemediationPlan::class);
    }

    public function complaints(): HasMany
    {
        return $this->hasMany(Complaint::class);
    }

    public function createdBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }

    // ==================== SCOPES ====================

    public function scopeActive($query)
    {
        return $query->where('is_active', true);
    }

    public function scopeInactive($query)
    {
        return $query->where('is_active', false);
    }

    public function scopeOutOfSchool($query)
    {
        return $query->where('school_status', '!=', 'enrolled')
            ->where('school_status', '!=', 'not_school_age')
            ->where('school_status', '!=', 'completed');
    }

    public function scopeEnrolled($query)
    {
        return $query->where('school_status', 'enrolled');
    }

    public function scopeHighRisk($query)
    {
        return $query->whereIn('risk_level', ['high', 'critical']);
    }

    public function scopeMediumRisk($query)
    {
        return $query->where('risk_level', 'medium');
    }

    public function scopeWorkingOnFarm($query)
    {
        return $query->where('is_working_on_farm', true);
    }

    public function scopeOfAge($query, int $minAge, ?int $maxAge = null)
    {
        $today = Carbon::today();
        
        $query->whereRaw(
            "EXTRACT(year FROM age(?, date_of_birth)) >= ?",
            [$today, $minAge]
        );

        if ($maxAge !== null) {
            $query->whereRaw(
                "EXTRACT(year FROM age(?, date_of_birth)) <= ?",
                [$today, $maxAge]
            );
        }

        return $query;
    }

    public function scopeNeedsAssessment($query)
    {
        return $query->whereNull('next_assessment_date')
            ->orWhere('next_assessment_date', '<=', Carbon::today());
    }

    // ==================== ACCESSORS ====================

    /**
     * Get child's full name.
     */
    public function getFullNameAttribute(): string
    {
        return "{$this->first_name} {$this->last_name}";
    }

    /**
     * Calculate child's age.
     */
    public function getAgeAttribute(): int
    {
        if (!$this->date_of_birth) {
            return 0;
        }

        return Carbon::parse($this->date_of_birth)->age;
    }

    /**
     * Get age category.
     */
    public function getAgeCategoryAttribute(): string
    {
        $age = $this->age;

        if ($age < 6) {
            return 'early_childhood';
        } elseif ($age < 12) {
            return 'middle_childhood';
        } elseif ($age < 15) {
            return 'early_adolescent';
        } elseif ($age < 18) {
            return 'late_adolescent';
        } else {
            return 'adult';
        }
    }

    /**
     * Check if child is of working age (15+).
     */
    public function getIsOfWorkingAgeAttribute(): bool
    {
        return $this->age >= 15;
    }

    /**
     * Check if child is of school age (6-17).
     */
    public function getIsOfSchoolAgeAttribute(): bool
    {
        return $this->age >= 6 && $this->age < 18;
    }

    // ==================== METHODS ====================

    /**
     * Check if child is at risk.
     */
    public function isAtRisk(): bool
    {
        return in_array($this->risk_level, ['medium', 'high', 'critical']);
    }

    /**
     * Check if child requires remediation.
     */
    public function requiresRemediation(): bool
    {
        return in_array($this->risk_level, ['high', 'critical'])
            || $this->is_working_on_farm
            || in_array($this->school_status, ['dropped_out', 'never_enrolled']);
    }

    /**
     * Check if child needs immediate intervention.
     */
    public function needsImmediateIntervention(): bool
    {
        return $this->risk_level === 'critical'
            || ($this->age < 12 && $this->is_working_on_farm)
            || in_array('pesticide_application', $this->dangerous_tasks_performed ?? [])
            || in_array('pesticide_mixing', $this->dangerous_tasks_performed ?? []);
    }

    /**
     * Get latest risk assessment.
     */
    public function getLatestRiskAssessmentAttribute()
    {
        return $this->riskAssessments()
            ->orderBy('assessment_date', 'desc')
            ->first();
    }

    /**
     * Get active remediation plan.
     */
    public function getActiveRemediationPlanAttribute()
    {
        return $this->remediationPlans()
            ->whereIn('status', ['in_progress', 'approved', 'pending_approval'])
            ->orderBy('created_at', 'desc')
            ->first();
    }

    /**
     * Check if child has active remediation plan.
     */
    public function hasActiveRemediationPlan(): bool
    {
        return $this->remediationPlans()
            ->whereIn('status', ['in_progress', 'approved', 'pending_approval'])
            ->exists();
    }

    /**
     * Get dangerous tasks as array.
     */
    public function getDangerousTasksAttribute(): array
    {
        return $this->dangerous_tasks_performed ?? [];
    }

    /**
     * Add dangerous task.
     */
    public function addDangerousTask(string $task): void
    {
        $tasks = $this->dangerous_tasks_performed ?? [];
        
        if (!in_array($task, $tasks)) {
            $tasks[] = $task;
            $this->dangerous_tasks_performed = $tasks;
            $this->save();
        }
    }

    /**
     * Remove dangerous task.
     */
    public function removeDangerousTask(string $task): void
    {
        $tasks = $this->dangerous_tasks_performed ?? [];
        $this->dangerous_tasks_performed = array_diff($tasks, [$task]);
        $this->save();
    }

    /**
     * Update school status and related fields.
     */
    public function enrollInSchool(string $schoolName, ?string $grade = null, ?float $distance = null): void
    {
        $this->school_status = 'enrolled';
        $this->school_name = $schoolName;
        
        if ($grade) {
            $this->school_grade = $grade;
        }
        
        if ($distance !== null) {
            $this->school_distance_km = $distance;
        }
        
        $this->save();

        // Log enrollment
        AuditLog::create([
            'action' => 'child_enrolled',
            'entity_type' => 'child',
            'entity_id' => $this->id,
            'new_values' => [
                'school_name' => $schoolName,
                'grade' => $grade,
            ],
        ]);
    }

    /**
     * Mark child as dropped out.
     */
    public function markAsDroppedOut(string $reason = null): void
    {
        $this->school_status = 'dropped_out';
        $this->save();

        AuditLog::create([
            'action' => 'child_dropped_out',
            'entity_type' => 'child',
            'entity_id' => $this->id,
            'new_values' => ['reason' => $reason],
        ]);
    }

    /**
     * Get risk history.
     */
    public function getRiskHistoryAttribute(): array
    {
        return $this->riskAssessments()
            ->orderBy('assessment_date', 'desc')
            ->get()
            ->map(function ($assessment) {
                return [
                    'date' => $assessment->assessment_date,
                    'score' => $assessment->overall_risk_score,
                    'level' => $assessment->overall_risk_level,
                    'type' => $assessment->assessment_type,
                ];
            });
    }

    /**
     * Calculate risk score based on assessment data.
     */
    public function calculateRiskScore(array $assessmentData): float
    {
        return app(\App\Services\RiskScoringService::class)
            ->calculateTotalRiskScore(array_merge($assessmentData, [
                'child' => $this,
                'producer' => $this->producer,
            ]));
    }
}
```

---

## 4. PHASE 4: SERVICES MÉTIER (Semaines 5-6)

### 4.1 RiskScoringService

```php
<?php

namespace App\Services;

use App\Models\Child;
use App\Models\Producer;
use App\Models\RiskAssessment;
use Illuminate\Support\Facades\DB;

class RiskScoringService
{
    /**
     * Calculate total risk score for a child.
     * Returns score 0-100 and risk level.
     */
    public function calculateTotalRiskScore(array $data): array
    {
        $child = $data['child'];
        $producer = $data['producer'];
        
        // Calculate sub-scores
        $ageRisk = $this->calculateAgeRisk($child->age, $child->gender);
        $educationRisk = $this->calculateEducationRisk($data['education'] ?? []);
        $workRisk = $this->calculateWorkRisk($data['work'] ?? []);
        $economicRisk = $this->calculateEconomicRisk($data['economic'] ?? []);
        $geographicRisk = $this->calculateGeographicRisk($data['geographic'] ?? []);
        $historyRisk = $this->calculateHistoryRisk($data['history'] ?? []);
        
        // Total score (0-100)
        $totalScore = $ageRisk + $educationRisk + $workRisk 
                    + $economicRisk + $geographicRisk + $historyRisk;
        
        // Determine risk level
        $riskLevel = $this->determineRiskLevel($totalScore);
        
        // Detailed risk factors for reporting
        $riskFactors = [
            'age_risk' => [
                'score' => round($ageRisk, 2),
                'max' => 25,
                'percentage' => round(($ageRisk / 25) * 100, 2),
            ],
            'education_risk' => [
                'score' => round($educationRisk, 2),
                'max' => 25,
                'percentage' => round(($educationRisk / 25) * 100, 2),
            ],
            'work_risk' => [
                'score' => round($workRisk, 2),
                'max' => 30,
                'percentage' => round(($workRisk / 30) * 100, 2),
            ],
            'economic_risk' => [
                'score' => round($economicRisk, 2),
                'max' => 10,
                'percentage' => round(($economicRisk / 10) * 100, 2),
            ],
            'geographic_risk' => [
                'score' => round($geographicRisk, 2),
                'max' => 5,
                'percentage' => round(($geographicRisk / 5) * 100, 2),
            ],
            'history_risk' => [
                'score' => round($historyRisk, 2),
                'max' => 5,
                'percentage' => round(($historyRisk / 5) * 100, 2),
            ],
        ];
        
        return [
            'total_score' => round($totalScore, 2),
            'risk_level' => $riskLevel,
            'risk_factors' => $riskFactors,
            'recommendations' => $this->generateRecommendations($riskFactors),
            'requires_remediation' => in_array($riskLevel, ['high', 'critical']),
            'requires_immediate_action' => $riskLevel === 'critical',
        ];
    }

    /**
     * Calculate age risk (0-25 points).
     */
    public function calculateAgeRisk(float $age, string $gender): float
    {
        $score = 0.0;
        
        if ($age < 12) {
            $score = 25.0; // Critical - below minimum working age
        } elseif ($age >= 12 && $age < 15) {
            $score = 18.0; // High risk
        } elseif ($age >= 15 && $age < 16) {
            $score = 10.0; // Medium risk
        } elseif ($age >= 16 && $age < 18) {
            $score = 3.0; // Low risk
        }
        
        // Gender vulnerability bonus for minors
        if ($gender === 'F' && $age < 18) {
            $score += 2.0;
        }
        
        return min($score, 25.0);
    }

    /**
     * Calculate education risk (0-25 points).
     */
    public function calculateEducationRisk(array $data): float
    {
        $score = 0.0;
        
        // School status (10 points max)
        $schoolStatus = $data['school_status'] ?? 'not_school_age';
        
        switch ($schoolStatus) {
            case 'enrolled':
                $score += 2.0;
                
                // Attendance rate bonus
                $attendanceRate = $data['attendance_rate'] ?? 0;
                if ($attendanceRate < 50) {
                    $score += 6.0;
                } elseif ($attendanceRate < 75) {
                    $score += 4.0;
                } elseif ($attendanceRate < 90) {
                    $score += 2.0;
                }
                break;
                
            case 'dropped_out':
                $score += 8.0;
                break;
                
            case 'never_enrolled':
                $score += 10.0;
                break;
                
            case 'completed':
                $score += 1.0;
                break;
        }
        
        // School distance (5 points max)
        $distance = $data['school_distance_km'] ?? 0;
        if ($distance > 5) {
            $score += 5.0;
        } elseif ($distance > 3) {
            $score += 3.0;
        } elseif ($distance > 1) {
            $score += 1.0;
        }
        
        // School supplies (5 points max)
        if (!($data['has_school_supplies'] ?? true)) {
            $score += 3.0;
        }
        if (!($data['has_uniform'] ?? true)) {
            $score += 2.0;
        }
        
        return min($score, 25.0);
    }

    /**
     * Calculate work risk (0-30 points) - MOST IMPORTANT.
     */
    public function calculateWorkRisk(array $data): float
    {
        $score = 0.0;
        
        // Is child working? (5 points base)
        if (!($data['is_working_on_farm'] ?? false)) {
            return 0.0;
        }
        
        $score += 5.0;
        
        // Work frequency (5 points max)
        $frequency = $data['work_frequency'] ?? 'never';
        switch ($frequency) {
            case 'daily':
                $score += 5.0;
                break;
            case 'regular':
                $score += 4.0;
                break;
            case 'occasional':
                $score += 2.0;
                break;
        }
        
        // Dangerous tasks (20 points max)
        $dangerousTasks = $data['dangerous_tasks_performed'] ?? [];
        $criticalTasks = [
            'pesticide_application' => 8.0,
            'pesticide_mixing' => 8.0,
            'chemical_handling' => 7.0,
            'machette_use' => 6.0,
            'couteau_use' => 5.0,
            'hache_use' => 6.0,
            'heavy_lifting_20kg_plus' => 5.0,
            'heavy_lifting_15kg_plus' => 4.0,
            'head_carrying' => 4.0,
            'night_work' => 6.0,
            'excessive_hours' => 5.0,
            'fire_clearing' => 5.0,
            'tree_felling' => 6.0,
            'climbing_trees' => 4.0,
            'water_carrying_long_distance' => 3.0,
        ];
        
        $taskScore = 0.0;
        foreach ($dangerousTasks as $task) {
            $taskScore += ($criticalTasks[$task] ?? 3.0);
        }
        $score += min($taskScore, 20.0);
        
        // Hours per day bonus
        $hoursPerDay = $data['hours_per_day'] ?? 0;
        if ($hoursPerDay > 8) {
            $score += 3.0;
        } elseif ($hoursPerDay > 6) {
            $score += 2.0;
        } elseif ($hoursPerDay > 4) {
            $score += 1.0;
        }
        
        // Health impact bonus
        $healthImpact = $data['health_impact'] ?? [];
        if (in_array('injuries', $healthImpact)) {
            $score += 3.0;
        }
        if (in_array('illness', $healthImpact)) {
            $score += 3.0;
        }
        if (in_array('fatigue', $healthImpact)) {
            $score += 2.0;
        }
        
        return min($score, 30.0);
    }

    /**
     * Calculate economic risk (0-10 points).
     */
    public function calculateEconomicRisk(array $data): float
    {
        $score = 0.0;
        
        // Income per capita
        $monthlyIncome = $data['monthly_income_xof'] ?? 0;
        $familySize = $data['family_size'] ?? 1;
        $incomePerCapita = $monthlyIncome / max($familySize, 1);
        
        if ($incomePerCapita < 30000) {
            $score += 4.0;
        } elseif ($incomePerCapita < 50000) {
            $score += 3.0;
        } elseif ($incomePerCapita < 75000) {
            $score += 1.0;
        }
        
        // Debt
        if ($data['has_debt'] ?? false) {
            $debtAmount = $data['debt_amount_xof'] ?? 0;
            if ($debtAmount > ($monthlyIncome * 6)) {
                $score += 2.0;
            } else {
                $score += 1.0;
            }
        }
        
        // Income sources
        $incomeSources = $data['income_sources'] ?? [];
        if (count($incomeSources) === 1) {
            $score += 2.0;
        } elseif (count($incomeSources) === 2) {
            $score += 1.0;
        }
        
        // Food security
        $foodSecurity = $data['food_security'] ?? 'secure';
        if ($foodSecurity === 'insecure') {
            $score += 2.0;
        } elseif ($foodSecurity === 'moderately_secure') {
            $score += 1.0;
        }
        
        return min($score, 10.0);
    }

    /**
     * Calculate geographic risk (0-5 points).
     */
    public function calculateGeographicRisk(array $data): float
    {
        $score = 0.0;
        
        // Farm isolation
        $isolation = $data['farm_isolation'] ?? 'accessible';
        if ($isolation === 'very_remote') {
            $score += 2.0;
        } elseif ($isolation === 'remote') {
            $score += 1.0;
        }
        
        // Services access
        $servicesAccess = $data['services_access'] ?? 'good';
        if ($servicesAccess === 'very_poor') {
            $score += 2.0;
        } elseif ($servicesAccess === 'poor') {
            $score += 1.0;
        }
        
        // High risk zone
        if ($data['is_high_risk_zone'] ?? false) {
            $score += 1.0;
        }
        
        return min($score, 5.0);
    }

    /**
     * Calculate history risk (0-5 points).
     */
    public function calculateHistoryRisk(array $data): float
    {
        $score = 0.0;
        
        // Previous child labor cases
        $previousCases = $data['previous_child_labor_cases'] ?? 0;
        if ($previousCases > 2) {
            $score += 3.0;
        } elseif ($previousCases === 2) {
            $score += 2.0;
        } elseif ($previousCases === 1) {
            $score += 1.0;
        }
        
        // Previous compliance rate
        $complianceRate = $data['previous_compliance_rate'] ?? 100;
        if ($complianceRate < 50) {
            $score += 2.0;
        } elseif ($complianceRate < 75) {
            $score += 1.0;
        }
        
        // Active complaints
        if ($data['has_active_complaints'] ?? false) {
            $score += 2.0;
        }
        
        return min($score, 5.0);
    }

    /**
     * Determine risk level based on total score.
     */
    public function determineRiskLevel(float $score): string
    {
        // Get customizable thresholds from cooperative
        $thresholds = $this->getRiskThresholds();
        
        if ($score >= $thresholds['critical']) {
            return 'critical';
        } elseif ($score >= $thresholds['high']) {
            return 'high';
        } elseif ($score >= $thresholds['medium']) {
            return 'medium';
        } elseif ($score >= $thresholds['low']) {
            return 'low';
        }
        
        return 'none';
    }

    /**
     * Get risk thresholds (can be customized per cooperative).
     */
    private function getRiskThresholds(): array
    {
        // Default thresholds
        return [
            'critical' => 80,
            'high' => 60,
            'medium' => 40,
            'low' => 20,
        ];
    }

    /**
     * Generate recommendations based on risk factors.
     */
    public function generateRecommendations(array $riskFactors): array
    {
        $recommendations = [];
        
        // Age-based recommendations
        if ($riskFactors['age_risk']['percentage'] > 70) {
            $recommendations[] = [
                'category' => 'age',
                'priority' => 'high',
                'action' => 'Retirer immédiatement l\'enfant des travaux dangereux',
                'description' => 'L\'enfant est en dessous de l\'âge minimum légal pour travailler',
            ];
        }
        
        // Education-based recommendations
        if ($riskFactors['education_risk']['percentage'] > 70) {
            $recommendations[] = [
                'category' => 'education',
                'priority' => 'high',
                'action' => 'Inscrire ou réinscrire l\'enfant à l\'école',
                'description' => 'L\'enfant n\'est pas scolarisé ou a un taux de fréquentation très faible',
            ];
        }
        
        // Work-based recommendations
        if ($riskFactors['work_risk']['percentage'] > 70) {
            $recommendations[] = [
                'category' => 'work',
                'priority' => 'critical',
                'action' => 'Cesser immédiatement les tâches dangereuses',
                'description' => 'L\'enfant effectue des tâches dangereuses interdites par la loi',
            ];
        }
        
        // Economic-based recommendations
        if ($riskFactors['economic_risk']['percentage'] > 70) {
            $recommendations[] = [
                'category' => 'economic',
                'priority' => 'medium',
                'action' => 'Évaluer les besoins en soutien économique familial',
                'description' => 'La famille fait face à des difficultés économiques importantes',
            ];
        }
        
        return $recommendations;
    }

    /**
     * Process risk assessment and update child/producer records.
     */
    public function processAssessment(RiskAssessment $assessment): void
    {
        DB::transaction(function () use ($assessment) {
            // Calculate risk score
            $result = $this->calculateTotalRiskScore([
                'child' => $assessment->child,
                'producer' => $assessment->producer,
                'education' => $assessment->risk_factors['education'] ?? [],
                'work' => $assessment->risk_factors['work'] ?? [],
                'economic' => $assessment->risk_factors['economic'] ?? [],
                'geographic' => $assessment->risk_factors['geographic'] ?? [],
                'history' => $assessment->risk_factors['history'] ?? [],
            ]);
            
            // Update assessment with calculated values
            $assessment->overall_risk_score = $result['total_score'];
            $assessment->overall_risk_level = $result['risk_level'];
            $assessment->risk_factors = array_merge(
                $assessment->risk_factors ?? [],
                $result['risk_factors']
            );
            $assessment->save();
            
            // Update child's risk level
            $child = $assessment->child;
            $child->risk_score = $result['total_score'];
            $child->risk_level = $result['risk_level'];
            $child->risk_factors = $result['risk_factors'];
            $child->last_assessment_date = $assessment->assessment_date;
            $child->next_assessment_date = $this->calculateNextAssessmentDate($result['risk_level']);
            $child->save();
            
            // Update producer's risk level
            $assessment->producer->calculateRiskLevel();
            
            // Generate alerts if needed
            if ($result['requires_immediate_action']) {
                app(AlertService::class)->createCriticalAlert($assessment);
            }
            
            // Auto-generate remediation plan if needed
            if ($result['requires_remediation']) {
                app(RemediationPlanGenerator::class)->generateFromAssessment($assessment);
            }
        });
    }

    /**
     * Calculate next assessment date based on risk level.
     */
    private function calculateNextAssessmentDate(string $riskLevel): \Carbon\Carbon
    {
        $months = match($riskLevel) {
            'critical' => 1,
            'high' => 3,
            'medium' => 6,
            default => 12,
        };
        
        return \Carbon\Carbon::now()->addMonths($months);
    }
}
```

---

## 5. PHASE 5: API ENDPOINTS (Semaines 7-8)

### 5.1 Routes API

```php
<?php

// routes/api.php

use App\Http\Controllers\Api\V1\*Controller;
use Illuminate\Support\Facades\Route;

/*
|--------------------------------------------------------------------------
| API Routes
|--------------------------------------------------------------------------
*/

// Public routes (no authentication required)
Route::post('/auth/login', [AuthController::class, 'login']);
Route::post('/auth/register', [AuthController::class, 'register']);
Route::post('/complaints', [ComplaintController::class, 'store']); // Anonymous complaints

// Protected routes (authentication required)
Route::middleware('auth:sanctum')->group(function () {
    
    // Auth
    Route::post('/auth/logout', [AuthController::class, 'logout']);
    Route::get('/auth/me', [AuthController::class, 'me']);
    
    // Dashboard
    Route::get('/dashboard/summary', [DashboardController::class, 'summary']);
    Route::get('/dashboard/kpis', [DashboardController::class, 'kpis']);
    Route::get('/dashboard/map-data', [DashboardController::class, 'mapData']);
    Route::get('/dashboard/alerts', [DashboardController::class, 'alerts']);
    
    // Producers
    Route::apiResource('producers', ProducerController::class);
    Route::get('/producers/{producer}/children', [ProducerController::class, 'children']);
    Route::get('/producers/{producer}/assessments', [ProducerController::class, 'assessments']);
    Route::get('/producers/{producer}/visits', [ProducerController::class, 'visits']);
    Route::get('/producers/{producer}/remediation-plans', [ProducerController::class, 'remediationPlans']);
    Route::get('/producers/{producer}/traceability-status', [ProducerController::class, 'traceabilityStatus']);
    Route::post('/producers/{producer}/calculate-risk', [ProducerController::class, 'calculateRisk']);
    
    // Children
    Route::apiResource('children', ChildController::class);
    Route::get('/children/{child}/risk-history', [ChildController::class, 'riskHistory']);
    Route::get('/children/{child}/remediation-plans', [ChildController::class, 'remediationPlans']);
    Route::post('/children/{child}/enroll-school', [ChildController::class, 'enrollInSchool']);
    
    // Risk Assessments
    Route::apiResource('risk-assessments', RiskAssessmentController::class);
    Route::post('/risk-assessments/{assessment}/validate', [RiskAssessmentController::class, 'validate']);
    Route::post('/risk-assessments/calculate', [RiskAssessmentController::class, 'calculate']);
    Route::get('/risk-assessments/statistics', [RiskAssessmentController::class, 'statistics']);
    
    // Monitoring Visits
    Route::apiResource('monitoring-visits', MonitoringVisitController::class);
    Route::post('/monitoring-visits/{visit}/complete', [MonitoringVisitController::class, 'complete']);
    Route::get('/monitoring-visits/schedule', [MonitoringVisitController::class, 'schedule']);
    Route::post('/monitoring-visits/bulk-sync', [MonitoringVisitController::class, 'bulkSync']);
    
    // Remediation Plans
    Route::apiResource('remediation-plans', RemediationPlanController::class);
    Route::post('/remediation-plans/{plan}/approve', [RemediationPlanController::class, 'approve']);
    Route::post('/remediation-plans/{plan}/complete', [RemediationPlanController::class, 'complete']);
    Route::post('/remediation-plans/{plan}/escalate', [RemediationPlanController::class, 'escalate']);
    Route::get('/remediation-plans/{plan}/actions', [RemediationPlanController::class, 'actions']);
    Route::post('/remediation-plans/{plan}/actions', [RemediationPlanController::class, 'addAction']);
    Route::put('/remediation-plans/{plan}/actions/{action}', [RemediationPlanController::class, 'updateAction']);
    
    // Remediation Actions
    Route::apiResource('remediation-actions', RemediationActionController::class);
    Route::post('/remediation-actions/{action}/complete', [RemediationActionController::class, 'complete']);
    
    // Training Sessions
    Route::apiResource('training-sessions', TrainingController::class);
    Route::post('/training-sessions/{session}/complete', [TrainingController::class, 'complete']);
    Route::post('/training-sessions/{session}/register', [TrainingController::class, 'register']);
    Route::get('/training-sessions/statistics', [TrainingController::class, 'statistics']);
    
    // Traceability
    Route::get('/traceability/blocks', [TraceabilityController::class, 'index']);
    Route::post('/traceability/blocks', [TraceabilityController::class, 'store']);
    Route::put('/traceability/blocks/{block}/resolve', [TraceabilityController::class, 'resolve']);
    Route::get('/traceability/producer/{producer}/status', [TraceabilityController::class, 'producerStatus']);
    
    // Alerts
    Route::get('/alerts', [AlertController::class, 'index']);
    Route::get('/alerts/unread-count', [AlertController::class, 'unreadCount']);
    Route::get('/alerts/{alert}', [AlertController::class, 'show']);
    Route::put('/alerts/{alert}/acknowledge', [AlertController::class, 'acknowledge']);
    Route::put('/alerts/{alert}/resolve', [AlertController::class, 'resolve']);
    Route::put('/alerts/{alert}/escalate', [AlertController::class, 'escalate']);
    
    // Complaints (restricted access)
    Route::get('/complaints', [ComplaintController::class, 'index']);
    Route::get('/complaints/{complaint}', [ComplaintController::class, 'show']);
    Route::put('/complaints/{complaint}', [ComplaintController::class, 'update']);
    Route::post('/complaints/{complaint}/escalate', [ComplaintController::class, 'escalate']);
    
    // Reports
    Route::get('/reports/child-labor-summary', [ReportController::class, 'childLaborSummary']);
    Route::get('/reports/remediation-progress', [ReportController::class, 'remediationProgress']);
    Route::get('/reports/training-effectiveness', [ReportController::class, 'trainingEffectiveness']);
    Route::get('/reports/audit-trail', [ReportController::class, 'auditTrail']);
    Route::get('/reports/due-diligence', [ReportController::class, 'dueDiligence']);
    Route::post('/reports/export-pdf', [ReportController::class, 'exportPdf']);
    Route::post('/reports/export-excel', [ReportController::class, 'exportExcel']);
    
    // Sync (Mobile)
    Route::post('/sync/pull', [SyncController::class, 'pull']);
    Route::post('/sync/push', [SyncController::class, 'push']);
    Route::post('/sync/conflict/resolve', [SyncController::class, 'resolveConflict']);
    Route::get('/sync/status', [SyncController::class, 'status']);
    
    // Settings
    Route::get('/settings', [SettingsController::class, 'index']);
    Route::put('/settings', [SettingsController::class, 'update']);
});
```

---

## 6. PHASE 6: TESTS (Semaines 9-10)

### 6.1 Test Unitaire - RiskScoringService

```php
<?php

namespace Tests\Unit;

use App\Models\Child;
use App\Models\Producer;
use App\Services\RiskScoringService;
use Tests\TestCase;

class RiskScoringServiceTest extends TestCase
{
    private RiskScoringService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new RiskScoringService();
    }

    /** @test */
    public function it_calculates_critical_risk_for_child_under_12_working_with_pesticides()
    {
        $child = new Child([
            'age' => 10,
            'gender' => 'M',
            'school_status' => 'never_enrolled',
        ]);
        
        $producer = new Producer(['risk_level' => 'low']);
        
        $data = [
            'child' => $child,
            'producer' => $producer,
            'education' => [
                'school_status' => 'never_enrolled',
                'school_distance_km' => 0,
            ],
            'work' => [
                'is_working_on_farm' => true,
                'work_frequency' => 'daily',
                'dangerous_tasks_performed' => ['pesticide_application', 'machette_use'],
                'hours_per_day' => 8,
            ],
            'economic' => [
                'monthly_income_xof' => 50000,
                'family_size' => 5,
                'has_debt' => true,
            ],
            'geographic' => [
                'farm_isolation' => 'remote',
                'services_access' => 'poor',
            ],
            'history' => [
                'previous_child_labor_cases' => 1,
            ],
        ];
        
        $result = $this->service->calculateTotalRiskScore($data);
        
        $this->assertEquals('critical', $result['risk_level']);
        $this->assertGreaterThanOrEqual(80, $result['total_score']);
        $this->assertTrue($result['requires_remediation']);
        $this->assertTrue($result['requires_immediate_action']);
    }

    /** @test */
    public function it_calculates_low_risk_for_school_enrolled_child_not_working()
    {
        $child = new Child([
            'age' => 12,
            'gender' => 'F',
            'school_status' => 'enrolled',
        ]);
        
        $producer = new Producer(['risk_level' => 'low']);
        
        $data = [
            'child' => $child,
            'producer' => $producer,
            'education' => [
                'school_status' => 'enrolled',
                'attendance_rate' => 95,
                'school_distance_km' => 1,
                'has_school_supplies' => true,
                'has_uniform' => true,
            ],
            'work' => [
                'is_working_on_farm' => false,
                'work_frequency' => 'never',
                'dangerous_tasks_performed' => [],
            ],
            'economic' => [
                'monthly_income_xof' => 200000,
                'family_size' => 4,
                'has_debt' => false,
            ],
            'geographic' => [
                'farm_isolation' => 'accessible',
                'services_access' => 'good',
            ],
            'history' => [
                'previous_child_labor_cases' => 0,
            ],
        ];
        
        $result = $this->service->calculateTotalRiskScore($data);
        
        $this->assertEquals('none', $result['risk_level']);
        $this->assertLessThan(20, $result['total_score']);
        $this->assertFalse($result['requires_remediation']);
    }

    /** @test */
    public function it_calculates_age_risk_correctly()
    {
        // Under 12 - critical
        $this->assertEquals(25.0, $this->service->calculateAgeRisk(10, 'M'));
        
        // 12-14 - high
        $this->assertEquals(18.0, $this->service->calculateAgeRisk(13, 'M'));
        
        // 15 - medium
        $this->assertEquals(10.0, $this->service->calculateAgeRisk(15, 'M'));
        
        // 16-17 - low
        $this->assertEquals(3.0, $this->service->calculateAgeRisk(17, 'M'));
        
        // 18+ - none
        $this->assertEquals(0.0, $this->service->calculateAgeRisk(18, 'M'));
        
        // Gender bonus for girls
        $this->assertEquals(20.0, $this->service->calculateAgeRisk(13, 'F')); // 18 + 2
    }

    /** @test */
    public function it_calculates_work_risk_correctly()
    {
        // Not working
        $this->assertEquals(0.0, $this->service->calculateWorkRisk([
            'is_working_on_farm' => false,
        ]));
        
        // Working occasionally without dangerous tasks
        $score = $this->service->calculateWorkRisk([
            'is_working_on_farm' => true,
            'work_frequency' => 'occasional',
            'dangerous_tasks_performed' => [],
            'hours_per_day' => 2,
        ]);
        $this->assertEquals(7.0, $score); // 5 base + 2 occasional
        
        // Working daily with dangerous tasks
        $score = $this->service->calculateWorkRisk([
            'is_working_on_farm' => true,
            'work_frequency' => 'daily',
            'dangerous_tasks_performed' => ['pesticide_application', 'machette_use'],
            'hours_per_day' => 8,
        ]);
        $this->assertGreaterThanOrEqual(20.0, $score);
    }

    /** @test */
    public function it_determines_risk_level_correctly()
    {
        $this->assertEquals('critical', $this->service->determineRiskLevel(85));
        $this->assertEquals('high', $this->service->determineRiskLevel(65));
        $this->assertEquals('medium', $this->service->determineRiskLevel(45));
        $this->assertEquals('low', $this->service->determineRiskLevel(25));
        $this->assertEquals('none', $this->service->determineRiskLevel(10));
    }
}
```

### 6.2 Test Feature - Remediation Plan

```php
<?php

namespace Tests\Feature;

use App\Models\Child;
use App\Models\Producer;
use App\Models\RiskAssessment;
use App\Models\RemediationPlan;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class RemediationPlanTest extends TestCase
{
    use RefreshDatabase;

    /** @test */
    public function it_auto_generates_remediation_plan_for_high_risk_child()
    {
        $producer = Producer::factory()->create(['risk_level' => 'high']);
        $child = Child::factory()->create([
            'producer_id' => $producer->id,
            'risk_level' => 'high',
            'school_status' => 'dropped_out',
            'is_working_on_farm' => true,
        ]);
        
        $assessment = RiskAssessment::factory()->create([
            'producer_id' => $producer->id,
            'child_id' => $child->id,
            'overall_risk_level' => 'high',
            'overall_risk_score' => 75,
        ]);
        
        $response = $this->postJson('/api/v1/risk-assessments/' . $assessment->id . '/generate-remediation-plan', [], [
            'Authorization' => 'Bearer ' . Sanctum::actingAs(User::factory()->create()),
        ]);
        
        $response->assertStatus(201);
        
        $this->assertDatabaseHas('remediation_plans', [
            'producer_id' => $producer->id,
            'child_id' => $child->id,
            'status' => 'draft',
            'triggered_by' => $assessment->id,
        ]);
    }

    /** @test */
    public function it_approves_remediation_plan_and_starts_implementation()
    {
        $plan = RemediationPlan::factory()->create(['status' => 'pending_approval']);
        $supervisor = User::factory()->create(['role' => 'supervisor']);
        
        $response = $this->postJson('/api/v1/remediation-plans/' . $plan->id . '/approve', [
            'approved' => true,
            'comments' => 'Plan approuvé. Commencer la mise en œuvre immédiatement.',
        ], [
            'Authorization' => 'Bearer ' . Sanctum::actingAs($supervisor),
        ]);
        
        $response->assertStatus(200);
        
        $plan->refresh();
        $this->assertEquals('approved', $plan->status);
        $this->assertEquals($supervisor->id, $plan->approved_by);
        $this->assertNotNull($plan->approved_at);
    }

    /** @test */
    public function it_escalates_overdue_remediation_plan()
    {
        $plan = RemediationPlan::factory()->create([
            'status' => 'in_progress',
            'expected_completion_date' => now()->subDays(60),
        ]);
        
        // Create overdue action
        $plan->actions()->create([
            'action_type' => 'school_enrollment',
            'description' => 'Enroll child in school',
            'planned_date' => now()->subDays(30),
            'status' => 'overdue',
        ]);
        
        // Run escalation check
        $this->artisan('remediation:check-escalation');
        
        $plan->refresh();
        $this->assertEquals('escalated', $plan->status);
        
        $this->assertDatabaseHas('alerts', [
            'alert_type' => 'remediation_failure',
            'source_entity' => 'remediation_plan',
            'source_id' => $plan->id,
            'status' => 'new',
        ]);
    }
}
```

---

## 7. PHASE 7: DÉPLOIEMENT (Semaines 11-12)

### 7.1 Configuration Production

```bash
# 1. Serveur de production (Ubuntu 20.04+)
sudo apt update
sudo apt upgrade -y

# 2. Installer PHP 8.2 et extensions
sudo apt install php8.2 php8.2-cli php8.2-fpm php8.2-pgsql php8.2-gd php8.2-mbstring php8.2-xml php8.2-bcmath php8.2-redis -y

# 3. Installer PostgreSQL 15
sudo apt install postgresql postgresql-contrib -y

# 4. Installer Redis
sudo apt install redis-server -y

# 5. Installer Nginx
sudo apt install nginx -y

# 6. Installer Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install nodejs -y

# 7. Installer Composer
curl -sS https://getcomposer.org/installer | php
sudo mv composer.phar /usr/local/bin/composer

# 8. Cloner le projet
git clone <repository-url> /var/www/cacaoguard
cd /var/www/cacaoguard

# 9. Installer les dépendances
composer install --no-dev --optimize-autoloader
npm install
npm run build

# 10. Configurer l'environnement
cp .env.example .env
php artisan key:generate

# 11. Configurer la base de données
sudo -u postgres psql
CREATE DATABASE cacaoguard;
CREATE USER cacaoguard_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE cacaoguard TO cacaoguard_user;
\q

# 12. Lancer les migrations
php artisan migrate --force

# 13. Configurer les permissions
sudo chown -R www-data:www-data /var/www/cacaoguard
sudo chmod -R 775 /var/www/cacaoguard/storage

# 14. Configurer Nginx
sudo nano /etc/nginx/sites-available/cacaoguard

# 15. Configurer SSL avec Let's Encrypt
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com

# 16. Configurer Supervisor pour les queues
sudo apt install supervisor -y
sudo nano /etc/supervisor/conf.d/cacaoguard.conf

# 17. Démarrer les services
sudo systemctl restart php8.2-fpm
sudo systemctl restart nginx
sudo systemctl restart redis-server
sudo systemctl restart supervisor

# 18. Configurer le cron pour les tâches planifiées
crontab -e
* * * * * cd /var/www/cacaoguard && php artisan schedule:run >> /dev/null 2>&1
```

### 7.2 Configuration Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;
    root /var/www/cacaoguard/public;

    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";

    index index.php;

    charset utf-8;

    location / {
        try_files $uri $uri/ /index.php?$query_string;
    }

    location = /favicon.ico { access_log off; log_not_found off; }
    location = /robots.txt  { access_log off; log_not_found off; }

    error_page 404 /index.php;

    location ~ \.php$ {
        fastcgi_pass unix:/var/run/php/php8.2-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
        include fastcgi_params;
    }

    location ~ /\.(?!well-known).* {
        deny all;
    }
}
```

### 7.3 Configuration Supervisor

```ini
[program:cacaoguard-worker]
process_name=%(program_name)s_%(process_num)02d
command=php /var/www/cacaoguard/artisan queue:work database --sleep=3 --tries=3 --max-time=3600
autostart=true
autorestart=true
stopasuser=false
killasgroup=true
user=www-data
numprocs=2
redirect_stderr=true
stdout_logfile=/var/www/cacaoguard/storage/logs/worker.log
stopwaitsecs=3600
```

---

## 8. CHECKLIST DE DÉPLOIEMENT

### Pré-déploiement
- [ ] Toutes les migrations créées et testées
- [ ] Tous les modèles implémentés avec relations
- [ ] Tous les services métier développés
- [ ] Toutes les API endpoints fonctionnels
- [ ] Tests unitaires et d'intégration passants (>80% coverage)
- [ ] Documentation API complète
- [ ] Manuel d'utilisation rédigé

### Déploiement
- [ ] Serveur configuré (PHP, PostgreSQL, Redis, Nginx)
- [ ] SSL installé et configuré
- [ ] Base de données créée et migrée
- [ ] Variables d'environnement configurées
- [ ] Stockage (MinIO/S3) configuré
- [ ] Queues et workers configurés
- [ ] Tâches planifiées configurées
- [ ] Sauvegardes automatiques configurées
- [ ] Monitoring configuré

### Post-déploiement
- [ ] Tests de smoke exécutés
- [ ] Données de test seedées
- [ ] Utilisateurs initiaux créés
- [ ] Formation des utilisateurs prévue
- [ ] Support technique organisé
- [ ] Plan de maintenance établi

---

## 9. RESSOURCES NÉCESSAIRES

### Équipe de Développement
- 1 Chef de projet / Product Owner
- 2 Développeurs Backend (Laravel/Node.js)
- 2 Développeurs Frontend (React.js)
- 1 Développeur Mobile (Flutter)
- 1 DevOps Engineer
- 1 QA Engineer

### Infrastructure
- Serveur de production: 4 vCPU, 8GB RAM, 100GB SSD
- Base de données: PostgreSQL 15+ (2GB RAM dédiée)
- Cache: Redis 7+ (1GB RAM)
- Stockage: MinIO ou S3 (100GB minimum)
- CDN pour assets statiques

### Coûts Estimés (Mensuel)
- Hébergement: $100-200
- Stockage: $20-50
- Bande passante: $10-30
- SSL: Gratuit (Let's Encrypt)
- **Total: ~$150-300/mois**

---

## 10. SUPPORT ET MAINTENANCE

### Maintenance Préventive
- Mises à jour de sécurité hebdomadaires
- Sauvegardes quotidiennes
- Monitoring des performances
- Nettoyage des logs mensuel

### Support Utilisateur
- Hotline: +225 XX XX XX XX XX
- Email: support@cacaoguard.ci
- Documentation en ligne: docs.cacaoguard.ci
- Formation initiale: 3 jours
- Formation continue: 1 jour/trimestre

---

Cette feuille de route fournit un plan complet pour le développement et le déploiement du module de lutte contre le travail des enfants. Chaque phase est conçue pour être itérative et adaptable aux besoins spécifiques des coopératives ivoiriennes.