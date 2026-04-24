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
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    cooperative  = relationship("Cooperative", back_populates="plantations")
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
