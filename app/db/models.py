from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base


class Cooperative(Base):
    __tablename__ = "cooperatives"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, index=True)
    country    = Column(String)
    is_active  = Column(Boolean, default=True, nullable=False)
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
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    cooperative  = relationship("Cooperative", back_populates="plantations")
    producer     = relationship("Producer", back_populates="plantations")
    certification_links = relationship("PlantationCertification", back_populates="plantation", cascade="all, delete-orphan")
    inspections  = relationship("Inspection", back_populates="plantation", cascade="all, delete-orphan")
    diagnostics  = relationship("Diagnostic", back_populates="plantation")
    boundary     = relationship("PlantationBoundary", back_populates="plantation", uselist=False)
    agro_records = relationship("AgroforestryRecord", back_populates="plantation")
    harvests     = relationship("Harvest", back_populates="plantation", cascade="all, delete-orphan")


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


class AgroforestryRecord(Base):
    """Inventaire des arbres d'agroforesterie d'une plantation."""
    __tablename__ = "agroforestry_records"

    id                = Column(Integer, primary_key=True, index=True)
    plantation_id     = Column(Integer, ForeignKey("plantations.id"), nullable=False)
    species_name      = Column(String, nullable=False)
    count_per_hectare = Column(Float, nullable=True)

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

    plantation = relationship("Plantation", back_populates="harvests")
    created_by = relationship("User")


class Producer(Base):
    """
    Producteur membre d'une cooperative cacao.
    Entite creee au Sprint #0 (module cooperative). Avant ce sprint,
    le proprietaire etait un simple champ texte Plantation.owner_name.
    """
    __tablename__ = "producers"

    id                      = Column(Integer, primary_key=True, index=True)
    cooperative_id          = Column(Integer, ForeignKey("cooperatives.id"), nullable=True, index=True)

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
