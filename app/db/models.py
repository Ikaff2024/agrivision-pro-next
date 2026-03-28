from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class Cooperative(Base):
    __tablename__ = "cooperatives"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    country = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    users = relationship("User", back_populates="cooperative")
    plantations = relationship("Plantation", back_populates="cooperative")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String)
    cooperative_id = Column(Integer, ForeignKey("cooperatives.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cooperative = relationship("Cooperative", back_populates="users")


class Plantation(Base):
    __tablename__ = "plantations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    owner_name = Column(String)
    country = Column(String)
    region = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    hectares = Column(Float, nullable=True)
    cooperative_id = Column(Integer, ForeignKey("cooperatives.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cooperative = relationship("Cooperative", back_populates="plantations")
    diagnostics = relationship("Diagnostic", back_populates="plantation")


class Diagnostic(Base):
    __tablename__ = "diagnostics"

    id = Column(Integer, primary_key=True, index=True)
    plantation_id = Column(Integer, ForeignKey("plantations.id"), nullable=False)

    country = Column(String, index=True)
    region = Column(String, nullable=True)
    humidity_pct = Column(Float)
    rainfall_mm_month = Column(Float)
    avg_temp_c = Column(Float)
    plantation_age_years = Column(Float, nullable=True)
    shade_tree_density_pct = Column(Float, nullable=True)

    global_score = Column(Float)
    global_risk_level = Column(String)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    plantation = relationship("Plantation", back_populates="diagnostics")
