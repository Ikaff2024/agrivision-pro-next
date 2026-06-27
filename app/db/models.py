from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy import JSON
from sqlalchemy.sql import func
from app.db.database import Base

# Import des modèles sociaux (CacaoGuard) pour les relations
# Les modèles sont définis dans models_social.py mais les relations
# sont ajoutées ici pour éviter les imports circulaires


class Cooperative(Base):
    __tablename__ = "cooperatives"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, index=True)
    country    = Column(String)
    is_active  = Column(Boolean, default=True, nullable=False)
    # Plan d'abonnement (feature-gating). Defaut 'enterprise' = tout active,
    # afin de ne rien changer tant qu'un plan n'est pas explicitement assigne.
    plan       = Column(String, default="enterprise", nullable=False)
    # Logo de la coopérative (data-URI base64) affiché sur les PDF. Stocké en base
    # → pas d'hébergement externe ; intégré directement dans les documents générés.
    logo_data  = Column(Text, nullable=True)
    # Réglages d'affichage du logo sur les PDF (ajustables par l'admin).
    logo_size  = Column(String, default="md", nullable=False)      # sm | md | lg
    logo_plaque = Column(Boolean, default=True, nullable=False)    # pastille blanche derrière le logo
    # Identités des responsables de la coopérative (président, directeur, gérant…).
    # Liste de {name, role, phone} — affichable sur les états officiels.
    managers   = Column(JSON, nullable=True)
    # Volet SOCIAL (travail enfant) dissocié de l'EUDR : par défaut un cas social
    # AVERTIT mais ne bloque pas l'export. Une coop dont l'acheteur l'exige peut
    # ACTIVER le blocage social à l'export (dérogation admin possible).
    enforce_social_export_block = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    users      = relationship("User", back_populates="cooperative")
    plantations = relationship("Plantation", back_populates="cooperative")


class User(Base):
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, index=True)
    email          = Column(String, unique=True, index=True)
    password_hash  = Column(String)
    role           = Column(String)
    cooperative_id = Column(Integer, ForeignKey("cooperatives.id"))
    is_active      = Column(Boolean, default=True, nullable=False)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    cooperative = relationship("Cooperative", back_populates="users")
    assigned_plantations = relationship("PlantationAssignment", foreign_keys="PlantationAssignment.technician_id", back_populates="technician")
    substitutions_as_absent = relationship("TechnicianSubstitution", foreign_keys="TechnicianSubstitution.absent_technician_id", back_populates="absent_technician")
    substitutions_as_substitute = relationship("TechnicianSubstitution", foreign_keys="TechnicianSubstitution.substitute_technician_id", back_populates="substitute_technician")


class Plantation(Base):
    __tablename__ = "plantations"

    id             = Column(Integer, primary_key=True, index=True)
    name           = Column(String, index=True)
    owner_name     = Column(String)
    country        = Column(String)
    region         = Column(String, nullable=True)
    latitude       = Column(Float, nullable=True)
    longitude      = Column(Float, nullable=True)
    hectares       = Column(Float, nullable=True)
    plant_count    = Column(Integer, nullable=True)
    cooperative_id = Column(Integer, ForeignKey("cooperatives.id"), nullable=True)
    producer_id    = Column(Integer, ForeignKey("producers.id"), nullable=True, index=True)
    # Lot d'import (UUID) si cette plantation a ete creee par un import de registre.
    # Permet d'annuler un import errone en ciblant uniquement ses entites.
    import_batch_id = Column(String, nullable=True, index=True)
    # Dérogation export (admin) : autorise l'expédition malgré une non-conformité EUDR.
    # Tracée : motif + email de l'admin + date. NULL = pas de dérogation active.
    export_waiver_reason = Column(Text, nullable=True)
    export_waiver_by     = Column(String, nullable=True)
    export_waiver_at     = Column(DateTime(timezone=True), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    # Cache du score EUDR (P1 — passage à l'échelle) : évite de recalculer en boucle
    # dans les agrégats (dashboard / readiness / summary / liste). Rafraîchi à la mutation
    # (délimitation, contrôle déforestation) + recompute en masse / paresseux.
    eudr_score        = Column(Integer, nullable=True)
    eudr_max_score    = Column(Integer, nullable=True)
    eudr_status       = Column(String(20), nullable=True, index=True)
    eudr_color        = Column(String(10), nullable=True)
    eudr_has_polygon  = Column(Boolean, nullable=True)
    eudr_rules_failed = Column(JSON, nullable=True)
    eudr_computed_at  = Column(DateTime(timezone=True), nullable=True)

    cooperative  = relationship("Cooperative", back_populates="plantations")
    producer     = relationship("Producer", back_populates="plantations")
    certification_links = relationship("PlantationCertification", back_populates="plantation", cascade="all, delete-orphan")
    inspections  = relationship("Inspection", back_populates="plantation", cascade="all, delete-orphan")
    assignment   = relationship("PlantationAssignment", back_populates="plantation", uselist=False, cascade="all, delete-orphan")
    diagnostics  = relationship("Diagnostic", back_populates="plantation")
    boundary     = relationship("PlantationBoundary", back_populates="plantation", uselist=False)
    deforestation_checks = relationship("DeforestationCheck", back_populates="plantation", cascade="all, delete-orphan")
    agro_records = relationship("AgroforestryRecord", back_populates="plantation")
    harvests     = relationship("Harvest", back_populates="plantation", cascade="all, delete-orphan")
    ssrte_visits = relationship("SsrtePlantationVisit", back_populates="plantation", cascade="all, delete-orphan")


class Diagnostic(Base):
    __tablename__ = "diagnostics"

    id                    = Column(Integer, primary_key=True, index=True)
    plantation_id         = Column(Integer, ForeignKey("plantations.id"), nullable=False)
    country               = Column(String, index=True)
    region                = Column(String, nullable=True)
    humidity_pct          = Column(Float)
    rainfall_mm_month     = Column(Float)
    avg_temp_c            = Column(Float)
    plantation_age_years  = Column(Float, nullable=True)
    shade_tree_density_pct = Column(Float, nullable=True)
    global_score          = Column(Float)
    global_risk_level     = Column(String)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())

    plantation = relationship("Plantation", back_populates="diagnostics")


class PlantationBoundary(Base):
    """DÃ©limitation gÃ©ographique d'une plantation (polygone GeoJSON)."""
    __tablename__ = "plantation_boundaries"

    id             = Column(Integer, primary_key=True, index=True)
    plantation_id  = Column(Integer, ForeignKey("plantations.id"), nullable=False, unique=True)
    geojson        = Column(Text, nullable=False)          # GeoJSON string du polygone
    area_hectares  = Column(Float, nullable=True)          # Superficie calculÃ©e
    points_count   = Column(Integer, nullable=True)        # Nombre de points du polygone
    method         = Column(String, default="manual")      # "manual" | "gps_track"
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    plantation = relationship("Plantation", back_populates="boundary")


class DeforestationCheck(Base):
    """Controle de deforestation d'une plantation (cadre EUDR-01b).

    Stocke le resultat d'une verification d'absence de deforestation post
    31/12/2020 (date butoir EUDR). La source peut etre un calcul automatique
    (Hansen Global Forest Change / Global Forest Watch) une fois l'integration
    branchee, ou une saisie manuelle / constat terrain en attendant.
    """
    __tablename__ = "deforestation_checks"

    id               = Column(Integer, primary_key=True, index=True)
    plantation_id    = Column(Integer, ForeignKey("plantations.id"), nullable=False, index=True)
    check_date       = Column(DateTime(timezone=True), nullable=True)
    source           = Column(String, nullable=True)   # hansen_gfc | gfw | field_visit | manual
    verdict          = Column(String, nullable=False, default="inconclusive")  # clear | deforestation_detected | inconclusive
    forest_loss_year = Column(Integer, nullable=True)  # annee de perte de couvert detectee (si applicable)
    notes            = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    plantation = relationship("Plantation", back_populates="deforestation_checks")


class AgroforestryRecord(Base):
    """Inventaire des arbres d'agroforesterie d'une plantation."""
    __tablename__ = "agroforestry_records"

    id                = Column(Integer, primary_key=True, index=True)
    plantation_id     = Column(Integer, ForeignKey("plantations.id"), nullable=False)
    species_name      = Column(String, nullable=False)
    count_per_hectare = Column(Float, nullable=True)
    avg_age_years     = Column(Float, nullable=True)

    plantation = relationship("Plantation", back_populates="agro_records")


class Harvest(Base):
    """
    Recolte enregistree pour une plantation.
    Permet de constituer l'historique de production et de croiser
    avec les diagnostics agronomiques pour mesurer l'impact reel.
    """
    __tablename__ = "harvests"

    id                 = Column(Integer, primary_key=True, index=True)
    plantation_id      = Column(Integer, ForeignKey("plantations.id"), nullable=False, index=True)
    harvest_date       = Column(DateTime(timezone=True), nullable=False, index=True)
    quantity_kg        = Column(Float, nullable=False)
    quality            = Column(String, nullable=False)
    price_per_kg_fcfa  = Column(Float, nullable=True)
    season             = Column(String, nullable=True)
    notes              = Column(Text, nullable=True)
    is_historical      = Column(Boolean, default=False, nullable=False)
    created_at         = Column(DateTime(timezone=True), server_default=func.now())
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Sprint #0 - Phase 0.1.a-4 : champs commerciaux (livraison)
    certification_id   = Column(Integer, ForeignKey("certifications.id"), nullable=True, index=True)
    campagne_id        = Column(Integer, ForeignKey("campagnes.id"), nullable=True, index=True)
    numero_recu_achat  = Column(String, nullable=True)
    nbre_sacs          = Column(Integer, nullable=True)
    is_conventional    = Column(Boolean, default=False, nullable=False)
    # Tracabilite physique : lot auquel cette recolte est affectee
    lot_id             = Column(Integer, ForeignKey("lots.id"), nullable=True, index=True)

    plantation = relationship("Plantation", back_populates="harvests")
    created_by = relationship("User")
    certification = relationship("Certification")
    campagne      = relationship("Campagne")
    lot           = relationship("Lot", back_populates="harvests")


class AiUsage(Base):
    """
    Trace chaque appel reussi au module Conseil agronomique IA (API Claude).
    Une ligne = un appel facture (tokens reellement consommes), ce qui permet
    d'estimer le cout de revient mensuel par cooperative.

    Le cout en USD est fige a l'enregistrement (grille tarifaire du moment),
    de sorte qu'un changement de tarif ulterieur ne reecrit pas l'historique.
    """
    __tablename__ = "ai_usage"

    id             = Column(Integer, primary_key=True, index=True)
    cooperative_id = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=True)
    plantation_id  = Column(Integer, ForeignKey("plantations.id"), nullable=True)
    feature        = Column(String, default="ai_advice", nullable=False)  # extensible : autres usages IA
    model          = Column(String, nullable=False)
    input_tokens   = Column(Integer, default=0, nullable=False)
    output_tokens  = Column(Integer, default=0, nullable=False)
    cost_usd       = Column(Float, default=0.0, nullable=False)
    created_at     = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    cooperative = relationship("Cooperative")


class PlatformSetting(Base):
    """Réglages plateforme clé→valeur (niveau IKAFFANAN LTD, propriétaire).

    Permet de modifier au runtime des paramètres globaux sans redéploiement ni
    accès aux variables d'environnement (ex. fournisseur IA + modèle du Conseil
    agronomique). Une clé = une ligne. Les SECRETS (clés API) restent en variables
    d'environnement — on ne stocke jamais de clé ici.
    """
    __tablename__ = "platform_settings"

    key        = Column(String, primary_key=True, index=True)
    value      = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MarketCache(Base):
    """Dernière bonne charge de veille marché (actualités + synthèse), persistée.

    Permet aux actualités de SURVIVRE à un redémarrage/redéploiement : si l'appel
    Claude échoue après un redéploiement (cache mémoire vidé), on ressert cette
    dernière bonne charge au lieu d'afficher une page sans actualités. Données
    globales (non liées à une coopérative) → une seule ligne maintenue.
    """
    __tablename__ = "market_cache"

    id         = Column(Integer, primary_key=True, index=True)
    payload    = Column(Text, nullable=False)   # JSON de la charge veille
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class ImportBatch(Base):
    """
    Trace un import de registre cooperative (un fichier = un lot).
    Permet d'afficher l'historique des imports et d'annuler un import errone
    en supprimant uniquement les entites (producteurs/plantations) qu'il a creees,
    avec garde-fou : refus si des donnees derivees existent (recoltes, diagnostics...).
    """
    __tablename__ = "import_batches"

    id                  = Column(Integer, primary_key=True, index=True)
    batch_uuid          = Column(String, unique=True, index=True, nullable=False)
    cooperative_id      = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)
    user_id             = Column(Integer, ForeignKey("users.id"), nullable=True)  # auteur de l'import
    fichier_source      = Column(String, nullable=True)
    campaign            = Column(String, nullable=True)
    producers_created   = Column(Integer, default=0, nullable=False)
    plantations_created = Column(Integer, default=0, nullable=False)
    status              = Column(String, default="active", nullable=False)  # active | cancelled
    created_at          = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    cancelled_at        = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    cooperative = relationship("Cooperative")


class Producer(Base):
    """
    Producteur membre d'une cooperative cacao.
    Entite creee au Sprint #0 (module cooperative). Avant ce sprint,
    le proprietaire etait un simple champ texte Plantation.owner_name.
    """
    __tablename__ = "producers"

    id                      = Column(Integer, primary_key=True, index=True)
    cooperative_id          = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)
    # Lot d'import (UUID) si ce producteur a ete cree par un import de registre.
    import_batch_id         = Column(String, nullable=True, index=True)

    # Identite
    nom_complet             = Column(String, nullable=False, index=True)
    sexe                    = Column(String, nullable=True)          # "H" | "F" | None
    date_naissance          = Column(DateTime(timezone=True), nullable=True)
    telephone               = Column(String, nullable=True)

    # Codes d'identification
    code_yeyasso            = Column(String, nullable=True, index=True)   # code interne cooperative (universel)
    code_saco               = Column(String, nullable=True)               # identifiant chez l'exportateur SACO
    recepisse               = Column(String, nullable=True)               # recepisse reconnaissance

    # Piece d'identite
    piece_identite_numero   = Column(String, nullable=True)
    piece_identite_nature   = Column(String, nullable=True)               # CNI, passeport, ...

    # Rattachement geographique / organisationnel
    section                 = Column(String, nullable=True)              # regroupement geographique niveau 2
    localite                = Column(String, nullable=True)              # village
    formateur_interne_nom   = Column(String, nullable=True)              # texte libre (resolution FK -> User differee)

    # Geolocalisation domicile (optionnel)
    latitude                = Column(Float, nullable=True)
    longitude               = Column(Float, nullable=True)

    # Metadonnees
    is_active               = Column(Boolean, default=True, nullable=False)
    created_at              = Column(DateTime(timezone=True), server_default=func.now())

    cooperative = relationship("Cooperative")
    plantations = relationship("Plantation", back_populates="producer")
    household_members = relationship("HouseholdMember", back_populates="producer", cascade="all, delete-orphan")
    formation_participations = relationship("FormationParticipant", back_populates="producer", cascade="all, delete-orphan")
    income_records  = relationship("IncomeRecord", back_populates="producer", cascade="all, delete-orphan")
    expense_records = relationship("ExpenseRecord", back_populates="producer", cascade="all, delete-orphan")
    labor_records   = relationship("LaborRecord", back_populates="producer", cascade="all, delete-orphan")
    input_costs     = relationship("InputCost", back_populates="producer", cascade="all, delete-orphan")
    farmforce_assessments = relationship("FarmForceAssessment", back_populates="producer", cascade="all, delete-orphan")

    # Relations sociales (CacaoGuard) - defined here to avoid circular imports
    # These relationships link Producer to the social monitoring models in models_social.py
    children = relationship("Child", back_populates="producer", cascade="all, delete-orphan", lazy="select")
    risk_assessments = relationship("RiskAssessment", back_populates="producer", cascade="all, delete-orphan", lazy="select")
    monitoring_visits = relationship("MonitoringVisit", back_populates="producer", cascade="all, delete-orphan", lazy="select")
    remediation_plans = relationship("RemediationPlan", back_populates="producer", cascade="all, delete-orphan", lazy="select")
    traceability_blocks = relationship("TraceabilityBlock", back_populates="producer", cascade="all, delete-orphan", lazy="select")
    complaints = relationship("Complaint", back_populates="producer", lazy="select")
    ssrte_household_profiles = relationship("SsrteHouseholdProfile", back_populates="producer", cascade="all, delete-orphan", lazy="select")
    ssrte_plantation_visits = relationship("SsrtePlantationVisit", back_populates="producer", cascade="all, delete-orphan", lazy="select")


class Certification(Base):
    """
    Standard de conformite / certification (Fairtrade, Rainforest Alliance,
    EUDR, ARS 1000, ...). Cree au Sprint #0 - Phase 0.1.a-2.

    IMPORTANT : "FT-RA" dans les fichiers Excel n'est PAS une certification,
    c'est une double certification. Une plantation FT-RA recoit 2 liens
    PlantationCertification : un vers FT, un vers RA.
    """
    __tablename__ = "certifications"

    id           = Column(Integer, primary_key=True, index=True)
    code         = Column(String, unique=True, nullable=False, index=True)  # FT, RA, EUDR, ARS_1000
    nom_complet  = Column(String, nullable=False)                            # "Fairtrade", ...
    organisme    = Column(String, nullable=True)                             # FLOCERT, ...
    actif        = Column(Boolean, default=True, nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    plantation_links = relationship("PlantationCertification", back_populates="certification")


class PlantationCertification(Base):
    """
    Table de liaison M-N entre Plantation et Certification.
    Une plantation peut etre certifiee sous plusieurs standards simultanement.
    """
    __tablename__ = "plantation_certifications"

    id               = Column(Integer, primary_key=True, index=True)
    plantation_id    = Column(Integer, ForeignKey("plantations.id"), nullable=False, index=True)
    certification_id = Column(Integer, ForeignKey("certifications.id"), nullable=False, index=True)
    date_obtention   = Column(DateTime(timezone=True), nullable=True)
    date_expiration  = Column(DateTime(timezone=True), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    plantation    = relationship("Plantation", back_populates="certification_links")
    certification = relationship("Certification", back_populates="plantation_links")


class Campagne(Base):
    """
    Campagne agricole cacao (typiquement Octobre annee N -> Septembre N+1).
    Permet d'organiser livraisons et donnees par campagne, et de gerer
    l'import multi-campagnes (un registre Excel par campagne).
    """
    __tablename__ = "campagnes"

    id             = Column(Integer, primary_key=True, index=True)
    cooperative_id = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)
    libelle        = Column(String, nullable=False, index=True)   # ex: "2025-2026"
    date_debut     = Column(DateTime(timezone=True), nullable=True)
    date_fin       = Column(DateTime(timezone=True), nullable=True)
    est_courante   = Column(Boolean, default=False, nullable=False)
    fichier_source = Column(String, nullable=True)                 # nom du registre Excel importe
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    cooperative = relationship("Cooperative")


class HouseholdMember(Base):
    """
    Membre du menage d'un producteur. Permet de tracer la composition
    familiale et de savoir qui travaille sur l'exploitation ou contribue
    au revenu du menage. Donnees issues du Cocoa Farmer Income Tool
    (Fairtrade) et utiles au suivi du travail des enfants.
    """
    __tablename__ = "household_members"

    id                        = Column(Integer, primary_key=True, index=True)
    producer_id               = Column(Integer, ForeignKey("producers.id"), nullable=False, index=True)
    nom                       = Column(String, nullable=True)
    lien_famille              = Column(String, nullable=True)   # conjoint, enfant, frere, ...
    age                       = Column(Integer, nullable=True)
    sexe                      = Column(String, nullable=True)   # H | F
    occupation                = Column(String, nullable=True)   # agriculteur, etudiant, ...
    scolarise                 = Column(Boolean, nullable=True)
    travaille_sur_exploitation = Column(Boolean, default=False, nullable=False)
    pct_temps_agricole        = Column(Integer, nullable=True)  # 0-100 si travaille sur exploitation
    contribue_revenu_menage   = Column(Boolean, default=False, nullable=False)
    created_at                = Column(DateTime(timezone=True), server_default=func.now())

    producer = relationship("Producer", back_populates="household_members")


class Inspection(Base):
    """
    Inspection ou audit d'une plantation, interne ou externe,
    rattachee a une certification donnee.
    """
    __tablename__ = "inspections"

    id               = Column(Integer, primary_key=True, index=True)
    plantation_id    = Column(Integer, ForeignKey("plantations.id"), nullable=False, index=True)
    certification_id = Column(Integer, ForeignKey("certifications.id"), nullable=True, index=True)
    type             = Column(String, nullable=False, default="INTERNE")  # INTERNE | EXTERNE
    date             = Column(DateTime(timezone=True), nullable=True)
    inspecteur_nom   = Column(String, nullable=True)
    resultat         = Column(String, nullable=True)   # CONFORME | NON_CONFORME | EN_ATTENTE | MAJEURE | MINEURE
    commentaires     = Column(Text, nullable=True)
    document_url     = Column(String, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    plantation    = relationship("Plantation", back_populates="inspections")
    certification = relationship("Certification")


class FormationSession(Base):
    """
    Session de formation / sensibilisation organisee par la cooperative.
    Correspond a la feuille "Registre Formation et Sensibilisation"
    du registre YEYASSO.
    """
    __tablename__ = "formation_sessions"

    id              = Column(Integer, primary_key=True, index=True)
    cooperative_id  = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)
    date            = Column(DateTime(timezone=True), nullable=True)
    lieu            = Column(String, nullable=True)
    thematique      = Column(String, nullable=True)   # ARS 1000, EUDR, travail enfants, GAP, ...
    formateur_nom   = Column(String, nullable=True)
    nb_participants = Column(Integer, nullable=True)
    duree_heures    = Column(Float, nullable=True)
    document_url    = Column(String, nullable=True)   # feuille de presence scannee
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    cooperative  = relationship("Cooperative")
    participants = relationship("FormationParticipant", back_populates="session",
                                cascade="all, delete-orphan")


class FormationParticipant(Base):
    """Lien M-N entre une session de formation et un producteur participant."""
    __tablename__ = "formation_participants"

    id                   = Column(Integer, primary_key=True, index=True)
    formation_session_id = Column(Integer, ForeignKey("formation_sessions.id"), nullable=False, index=True)
    producer_id          = Column(Integer, ForeignKey("producers.id"), nullable=False, index=True)
    signature_present    = Column(Boolean, default=False, nullable=False)
    created_at           = Column(DateTime(timezone=True), server_default=func.now())

    session  = relationship("FormationSession", back_populates="participants")
    producer = relationship("Producer", back_populates="formation_participations")


class IncomeRecord(Base):
    """
    Revenu d'un producteur pour un mois donne et un type de produit.
    Source : Cocoa Farmer Income Tool (Fairtrade), feuille "2.entrees".
    La campagne agricole va d'Octobre (mois 10) a Septembre (mois 9).
    """
    __tablename__ = "income_records"

    id             = Column(Integer, primary_key=True, index=True)
    producer_id    = Column(Integer, ForeignKey("producers.id"), nullable=False, index=True)
    campagne_id    = Column(Integer, ForeignKey("campagnes.id"), nullable=True, index=True)
    mois           = Column(Integer, nullable=True)    # 1-12 (campagne : 10,11,12,1..9)
    type_revenu    = Column(String, nullable=False)    # CACAO|CAFE|AUTRE_CULTURE|ALIMENT_BASE|VIVRIERE|ELEVAGE|AUTRE
    produit        = Column(String, nullable=True)     # "petit cola", "tomate", ...
    unite_mesure   = Column(String, nullable=True)     # kg, sac, ...
    quantite       = Column(Float, nullable=True)
    prix_unitaire  = Column(Float, nullable=True)      # CFA
    revenu         = Column(Float, nullable=True)      # CFA (quantite * prix_unitaire)
    notes          = Column(Text, nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    producer = relationship("Producer", back_populates="income_records")
    campagne = relationship("Campagne")


class ExpenseRecord(Base):
    """
    Depense du menage d'un producteur, par trimestre.
    Source : Cocoa Farmer Income Tool, feuille "5.depenses du menage".
    """
    __tablename__ = "expense_records"

    id           = Column(Integer, primary_key=True, index=True)
    producer_id  = Column(Integer, ForeignKey("producers.id"), nullable=False, index=True)
    campagne_id  = Column(Integer, ForeignKey("campagnes.id"), nullable=True, index=True)
    trimestre    = Column(Integer, nullable=True)      # 1-4
    categorie    = Column(String, nullable=False)      # ALIMENTATION|EDUCATION|SANTE|AUTRE
    montant_cfa  = Column(Float, nullable=True)
    notes        = Column(Text, nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    producer = relationship("Producer", back_populates="expense_records")
    campagne = relationship("Campagne")


class LaborRecord(Base):
    """
    Main d'oeuvre mobilisee par un producteur pour un mois donne.
    Source : Cocoa Farmer Income Tool, feuille "4.main d'oeuvre".
    Distingue main d'oeuvre familiale et embauchee.
    """
    __tablename__ = "labor_records"

    id                       = Column(Integer, primary_key=True, index=True)
    producer_id              = Column(Integer, ForeignKey("producers.id"), nullable=False, index=True)
    campagne_id              = Column(Integer, ForeignKey("campagnes.id"), nullable=True, index=True)
    mois                     = Column(Integer, nullable=True)   # 1-12
    journees_familial        = Column(Float, nullable=True)
    journees_familial_cacao  = Column(Float, nullable=True)     # sous-ensemble dedie au cacao
    journees_embauche        = Column(Float, nullable=True)
    journees_embauche_cacao  = Column(Float, nullable=True)
    salaire_journalier       = Column(Float, nullable=True)     # CFA
    autres_services          = Column(String, nullable=True)
    frais_service            = Column(Float, nullable=True)     # CFA
    lies_cacao               = Column(Boolean, default=True, nullable=False)
    created_at               = Column(DateTime(timezone=True), server_default=func.now())

    producer = relationship("Producer", back_populates="labor_records")
    campagne = relationship("Campagne")


class InputCost(Base):
    """
    Cout d'un intrant, outil/equipement ou metayage pour un producteur.
    Source : Cocoa Farmer Income Tool, feuille "3.couts".
    """
    __tablename__ = "input_costs"

    id                    = Column(Integer, primary_key=True, index=True)
    producer_id           = Column(Integer, ForeignKey("producers.id"), nullable=False, index=True)
    campagne_id           = Column(Integer, ForeignKey("campagnes.id"), nullable=True, index=True)
    categorie             = Column(String, nullable=False)   # INTRANT|OUTIL_EQUIPEMENT|METAYAGE|AUTRE_AGRICOLE
    produit               = Column(String, nullable=True)    # engrais, fiente, machette, ...
    unite_mesure          = Column(String, nullable=True)
    quantite              = Column(Float, nullable=True)
    cout_total            = Column(Float, nullable=True)     # CFA
    valeur_subventionnee  = Column(Float, nullable=True)     # CFA, 0 si non subventionne
    duree_vie_ans         = Column(Integer, nullable=True)   # pour outils uniquement
    lies_cacao            = Column(Boolean, default=True, nullable=False)
    notes                 = Column(Text, nullable=True)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())

    producer = relationship("Producer", back_populates="input_costs")
    campagne = relationship("Campagne")


class FarmForceAssessment(Base):
    """
    Formulaire annuel Farm Force / compte d'exploitation producteur.

    Le PDF client couvre menage, parcelles, ventes, couts, vivrier, betail,
    travail familial, main-d'oeuvre embauchee et resultat. Les lignes restent
    en JSON structure pour conserver la fidelite au formulaire papier.
    """
    __tablename__ = "farmforce_assessments"

    id = Column(Integer, primary_key=True, index=True)
    producer_id = Column(Integer, ForeignKey("producers.id"), nullable=False, index=True)
    campagne_id = Column(Integer, ForeignKey("campagnes.id"), nullable=True, index=True)
    campaign_label = Column(String, nullable=False, index=True)
    localite = Column(String, nullable=True)
    pr_code = Column(String, nullable=True)

    household_members = Column(JSON, nullable=True)
    parcels = Column(JSON, nullable=True)
    revenue_items = Column(JSON, nullable=True)
    cost_items = Column(JSON, nullable=True)
    family_labor_items = Column(JSON, nullable=True)
    hired_labor_items = Column(JSON, nullable=True)
    food_security_items = Column(JSON, nullable=True)
    household_expense_items = Column(JSON, nullable=True)  # depenses menage (alimentation/education/sante/autre)
    notes = Column(Text, nullable=True)

    total_revenue_cfa = Column(Float, default=0, nullable=False)
    total_cost_cfa = Column(Float, default=0, nullable=False)
    profit_cfa = Column(Float, default=0, nullable=False)
    total_household_expenses_cfa = Column(Float, default=0, nullable=False)  # depenses du menage
    net_income_cfa = Column(Float, default=0, nullable=False)  # profit - depenses menage (revenu disponible)
    family_labor_days = Column(Float, default=0, nullable=False)
    hired_labor_days = Column(Float, default=0, nullable=False)
    return_per_family_day_cfa = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    producer = relationship("Producer", back_populates="farmforce_assessments")
    campagne = relationship("Campagne")


class PlantationAssignment(Base):
    """
    Attribution d'une plantation a un technicien (Sprint #1).
    Une plantation a au plus une attribution active a la fois.
    L'attribution peut etre desactivee (is_active=False) sans etre
    supprimee, pour conserver l'historique.
    """
    __tablename__ = "plantation_assignments"

    id             = Column(Integer, primary_key=True, index=True)
    plantation_id  = Column(Integer, ForeignKey("plantations.id"), nullable=False, index=True)
    technician_id  = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    assigned_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_at    = Column(DateTime(timezone=True), server_default=func.now())
    is_active      = Column(Boolean, default=True, nullable=False)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    plantation  = relationship("Plantation", back_populates="assignment")
    technician  = relationship("User", foreign_keys=[technician_id],
                               back_populates="assigned_plantations")
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])


class TechnicianSubstitution(Base):
    """
    Remplacement temporaire d'un technicien par un autre (Sprint #1).
    Pendant la periode [date_debut, date_fin], le remplacant voit les
    parcelles du technicien absent en plus des siennes.

    Un remplacement est "actif" si is_active = True ET la date du jour
    est comprise entre date_debut et date_fin.
    """
    __tablename__ = "technician_substitutions"

    id                       = Column(Integer, primary_key=True, index=True)
    cooperative_id           = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)
    absent_technician_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    substitute_technician_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date_debut               = Column(DateTime(timezone=True), nullable=False)
    date_fin                 = Column(DateTime(timezone=True), nullable=False)
    motif                    = Column(String, nullable=True)
    created_by_id            = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active                = Column(Boolean, default=True, nullable=False)
    created_at               = Column(DateTime(timezone=True), server_default=func.now())

    cooperative          = relationship("Cooperative")
    absent_technician    = relationship("User", foreign_keys=[absent_technician_id],
                                        back_populates="substitutions_as_absent")
    substitute_technician = relationship("User", foreign_keys=[substitute_technician_id],
                                         back_populates="substitutions_as_substitute")
    created_by           = relationship("User", foreign_keys=[created_by_id])


# ─────────────────────────────────────────────────────────────────────────────
# Tracabilite physique du cacao (lots, entrepots, mouvements) — module #1
# ─────────────────────────────────────────────────────────────────────────────

class Warehouse(Base):
    """Entrepot / magasin de stockage du cacao d'une cooperative."""
    __tablename__ = "warehouses"

    id             = Column(Integer, primary_key=True, index=True)
    cooperative_id = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)
    name           = Column(String, nullable=False)
    location       = Column(String, nullable=True)
    capacity_kg    = Column(Float, nullable=True)
    is_active      = Column(Boolean, default=True, nullable=False)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id  = Column(Integer, ForeignKey("users.id"), nullable=True)

    cooperative = relationship("Cooperative")


class Lot(Base):
    """
    Lot de cacao : unite de tracabilite physique regroupant des recoltes/achats.
    Statuts : open (en constitution) -> sealed (scelle) -> shipped (expedie).
    blocked = bloque (cas CacaoGuard / non-conformite).
    """
    __tablename__ = "lots"

    id               = Column(Integer, primary_key=True, index=True)
    cooperative_id   = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)
    code             = Column(String, unique=True, nullable=False, index=True)
    season           = Column(String, nullable=True, index=True)
    certification_id = Column(Integer, ForeignKey("certifications.id"), nullable=True, index=True)
    warehouse_id     = Column(Integer, ForeignKey("warehouses.id"), nullable=True, index=True)
    status           = Column(String, default="open", nullable=False, index=True)
    total_weight_kg  = Column(Float, default=0, nullable=False)
    bag_count        = Column(Integer, default=0, nullable=False)
    exporter         = Column(String, nullable=True)   # acheteur/exportateur (ex. OCEAN-SA)
    external_ref     = Column(String, nullable=True)   # n° de lot export / connaissement
    notes            = Column(Text, nullable=True)
    parent_lot_id    = Column(Integer, ForeignKey("lots.id"), nullable=True, index=True)  # fusion
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())
    created_by_id    = Column(Integer, ForeignKey("users.id"), nullable=True)

    cooperative   = relationship("Cooperative")
    certification = relationship("Certification")
    warehouse     = relationship("Warehouse")
    harvests      = relationship("Harvest", back_populates="lot")
    movements     = relationship("LotMovement", back_populates="lot",
                                 cascade="all, delete-orphan",
                                 order_by="LotMovement.created_at")


class LotMovement(Base):
    """
    Mouvement de tracabilite d'un lot (journal immuable).
    Types : creation, warehouse_in, transfer, merge_in, split_out,
    adjustment, export_out.
    """
    __tablename__ = "lot_movements"

    id                = Column(Integer, primary_key=True, index=True)
    lot_id            = Column(Integer, ForeignKey("lots.id", ondelete="CASCADE"), nullable=False, index=True)
    movement_type     = Column(String, nullable=False, index=True)
    quantity_kg       = Column(Float, default=0, nullable=False)
    from_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    to_warehouse_id   = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    reference         = Column(String, nullable=True)
    movement_metadata = Column(JSON, nullable=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_by_id     = Column(Integer, ForeignKey("users.id"), nullable=True)

    lot = relationship("Lot", back_populates="movements")


# ─────────────────────────────────────────────────────────────────────────────
# Achats producteurs (bons d'achat / pesees bord champ) — module #2
# ─────────────────────────────────────────────────────────────────────────────

class PurchaseRecord(Base):
    """
    Achat de cacao a un producteur (bord champ / reception magasin).

    Enregistre la pesee et le bon d'achat. Peut generer automatiquement une
    Harvest (rattachee a une plantation) afin d'alimenter les volumes et la
    tracabilite des lots. Le suivi de paiement est purement COMPTABLE
    (statut paye / en attente) : aucun mouvement d'argent n'est execute ici.
    """
    __tablename__ = "purchase_records"

    id               = Column(Integer, primary_key=True, index=True)
    cooperative_id   = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)
    producer_id      = Column(Integer, ForeignKey("producers.id"), nullable=False, index=True)
    plantation_id    = Column(Integer, ForeignKey("plantations.id"), nullable=True, index=True)
    harvest_id       = Column(Integer, ForeignKey("harvests.id"), nullable=True, index=True)

    receipt_number   = Column(String, nullable=True, index=True)   # numero du bon d'achat
    purchase_date    = Column(DateTime(timezone=True), nullable=False, index=True)
    season           = Column(String, nullable=True, index=True)
    certification_id = Column(Integer, ForeignKey("certifications.id"), nullable=True, index=True)
    quality          = Column(String, nullable=True)

    # Pesee
    gross_weight_kg  = Column(Float, nullable=True)   # poids brut (avec sacs)
    tare_kg          = Column(Float, default=0, nullable=False)  # tare (sacs)
    net_weight_kg    = Column(Float, nullable=False)  # poids net achete
    bag_count        = Column(Integer, default=0, nullable=False)

    # Montant
    price_per_kg_fcfa = Column(Float, nullable=True)
    total_amount_fcfa = Column(Float, default=0, nullable=False)

    # Suivi paiement (comptable uniquement)
    payment_status   = Column(String, default="pending", nullable=False, index=True)  # pending|paid|cancelled
    payment_date     = Column(DateTime(timezone=True), nullable=True)
    payment_method   = Column(String, nullable=True)  # cash|mobile_money|bank|autre

    buyer_name       = Column(String, nullable=True)  # agent acheteur
    notes            = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id    = Column(Integer, ForeignKey("users.id"), nullable=True)

    producer      = relationship("Producer")
    plantation    = relationship("Plantation")
    certification = relationship("Certification")
    harvest       = relationship("Harvest")


# ─────────────────────────────────────────────────────────────────────────────
# Certification : audits, non-conformites, actions correctives — module #3
# ─────────────────────────────────────────────────────────────────────────────

class CertificationAudit(Base):
    """
    Audit de certification (Rainforest Alliance, Fairtrade, Cocoa Horizons...).
    Statuts : planned -> in_progress -> completed. Resultat : pass | conditional | fail.
    """
    __tablename__ = "certification_audits"

    id               = Column(Integer, primary_key=True, index=True)
    cooperative_id   = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)
    certification_id = Column(Integer, ForeignKey("certifications.id"), nullable=True, index=True)
    audit_date       = Column(DateTime(timezone=True), nullable=False, index=True)
    audit_type       = Column(String, default="internal", nullable=False)  # internal|external|surveillance
    auditor_name     = Column(String, nullable=True)
    auditor_body     = Column(String, nullable=True)   # organisme certificateur
    scope            = Column(Text, nullable=True)
    status           = Column(String, default="planned", nullable=False, index=True)  # planned|in_progress|completed
    result           = Column(String, nullable=True)   # pass|conditional|fail
    score_pct        = Column(Float, nullable=True)
    notes            = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id    = Column(Integer, ForeignKey("users.id"), nullable=True)

    cooperative   = relationship("Cooperative")
    certification = relationship("Certification")
    non_conformities = relationship("NonConformity", back_populates="audit",
                                    cascade="all, delete-orphan")


class NonConformity(Base):
    """
    Non-conformite relevee (lors d'un audit ou en continu) + action corrective.
    Severite : minor | major | critical. Statut : open|in_progress|resolved|closed.
    """
    __tablename__ = "non_conformities"

    id                 = Column(Integer, primary_key=True, index=True)
    cooperative_id     = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)
    audit_id           = Column(Integer, ForeignKey("certification_audits.id", ondelete="CASCADE"), nullable=True, index=True)
    certification_id   = Column(Integer, ForeignKey("certifications.id"), nullable=True, index=True)
    reference          = Column(String, nullable=True)   # code/critere du referentiel
    severity           = Column(String, default="minor", nullable=False, index=True)
    description        = Column(Text, nullable=False)
    corrective_action  = Column(Text, nullable=True)     # plan d'action
    responsible        = Column(String, nullable=True)
    due_date           = Column(Date, nullable=True, index=True)   # echeance
    status             = Column(String, default="open", nullable=False, index=True)
    resolved_date      = Column(Date, nullable=True)
    resolution_notes   = Column(Text, nullable=True)
    created_at         = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id      = Column(Integer, ForeignKey("users.id"), nullable=True)

    cooperative   = relationship("Cooperative")
    audit         = relationship("CertificationAudit", back_populates="non_conformities")
    certification = relationship("Certification")


# ─────────────────────────────────────────────────────────────────────────────
# Veille réglementaire / marché — moteur IA agnostique (open-source).
# GLOBAL (pas par coopérative) : la veille est partagée, comme le cache marché.
# cf. docs/PLAN_MOTEUR_IA_AGNOSTIQUE.md
# ─────────────────────────────────────────────────────────────────────────────

class VeilleItem(Base):
    """Élément de veille brut récupéré d'une source (RSS/API), dédupliqué par hash.

    Corpus du pipeline RAG : on récupère les éléments récents pertinents puis un
    modèle (open-source via la passerelle agnostique) en fait la synthèse.
    """
    __tablename__ = "veille_items"

    id           = Column(Integer, primary_key=True, index=True)
    source_key   = Column(String(60), nullable=False, index=True)   # clé du registre de sources
    source_name  = Column(String(200), nullable=True)
    title        = Column(Text, nullable=False)
    url          = Column(Text, nullable=True)
    summary      = Column(Text, nullable=True)                      # extrait / description de la source
    content_hash = Column(String(64), nullable=False, unique=True, index=True)  # dédup (sha256)
    topics       = Column(JSON, nullable=True)                      # ["eudr","prix",...]
    lang         = Column(String(8), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at   = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class VeilleDigest(Base):
    """Synthèse de veille générée par le modèle (agnostique) à partir des items récents.

    Stockée pour cache (coût borné) + historique. `payload` = {résumé, points clés,
    impacts, sources}. `model` trace le fournisseur/modèle utilisé (auditabilité coût).
    """
    __tablename__ = "veille_digests"

    id           = Column(Integer, primary_key=True, index=True)
    topic        = Column(String(60), nullable=True, index=True)    # null = global
    payload      = Column(JSON, nullable=False)                     # synthèse structurée
    model        = Column(String(120), nullable=True)               # fournisseur / modèle
    item_count   = Column(Integer, nullable=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Géo-horodatage anti-fraude de la collecte terrain (visites, enquêtes).
# Table CENTRALE (polymorphe entity_type/entity_id) → réutilisable par tous les
# formulaires sans ALTER sur chaque table. `captured_at` = heure SERVEUR (non
# falsifiable) ; le GPS de l'appareil est comparé au lieu attendu (producteur /
# parcelle) pour signaler les saisies hors zone ou sans GPS.
# ─────────────────────────────────────────────────────────────────────────────

class FieldGeostamp(Base):
    __tablename__ = "field_geostamps"

    id                  = Column(Integer, primary_key=True, index=True)
    cooperative_id      = Column(Integer, nullable=True, index=True)
    entity_type         = Column(String(40), nullable=False, index=True)   # monitoring_visit | ssrte_plantation_visit | risk_assessment | diagnostic
    entity_id           = Column(Integer, nullable=False, index=True)

    # GPS capté par l'appareil au moment de la validation
    captured_latitude   = Column(Float, nullable=True)
    captured_longitude  = Column(Float, nullable=True)
    captured_accuracy_m = Column(Float, nullable=True)
    client_reported_at  = Column(DateTime(timezone=True), nullable=True)   # heure DÉCLARÉE par l'appareil (audit)
    captured_at         = Column(DateTime(timezone=True), server_default=func.now())  # heure SERVEUR (référence)

    # Lieu attendu (GPS connu du producteur / de la parcelle) au moment de la capture
    expected_latitude   = Column(Float, nullable=True)
    expected_longitude  = Column(Float, nullable=True)
    distance_m          = Column(Float, nullable=True)                     # haversine capturé ↔ attendu

    # Verdict d'intégrité : verified | far | no_fix | no_reference | overridden
    geo_status          = Column(String(20), nullable=False, default="no_fix", index=True)
    override_reason     = Column(Text, nullable=True)                      # motif si GPS indisponible (tracé)
    recorded_by         = Column(String(200), nullable=True)
