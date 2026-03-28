"""
Script de peuplement de la base de données avec des données de démonstration.
Usage : python seed_data.py

Prérequis : avoir appliqué les migrations Alembic (alembic upgrade head)
et créé au moins un utilisateur admin via POST /auth/register.
"""
import sys
import os
import random
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.db.database import SessionLocal
from app.db.models import Cooperative, Plantation, Diagnostic


def generate_random_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(days=random.randrange(delta.days))


def get_realistic_coordinates():
    """Coordonnées GPS réalistes pour les zones cacaoyères de Côte d'Ivoire."""
    lat = round(random.uniform(5.0, 7.5), 6)
    lon = round(random.uniform(-7.5, -5.5), 6)
    return lat, lon


def seed_database():
    db = SessionLocal()
    try:
        # Créer une coopérative de démo si elle n'existe pas
        coop = db.query(Cooperative).filter_by(name="Coop Démo CI").first()
        if not coop:
            coop = Cooperative(name="Coop Démo CI", country="Côte d'Ivoire")
            db.add(coop)
            db.commit()
            db.refresh(coop)
            print(f"Coopérative créée : {coop.name} (id={coop.id})")
        else:
            print(f"Coopérative existante : {coop.name} (id={coop.id})")

        if db.query(Plantation).filter_by(cooperative_id=coop.id).count() > 0:
            print("Des plantations existent déjà pour cette coopérative. Abandon.")
            return

        regions = ["Soubré", "Daloa", "San-Pédro", "Man", "Agboville", "Abengourou"]
        risk_levels = ["LOW", "MEDIUM", "HIGH"]

        print("Création de 30 plantations...")
        plantations = []
        for i in range(1, 31):
            lat, lon = get_realistic_coordinates()
            p = Plantation(
                name=f"Plantation {chr(random.randint(65, 90))}-{random.randint(100, 999)}",
                owner_name=f"Producteur {i}",
                country="Côte d'Ivoire",
                region=random.choice(regions),
                latitude=lat,
                longitude=lon,
                hectares=round(random.uniform(2.0, 15.0), 2),
                cooperative_id=coop.id,  # toujours rattachée à une coopérative
            )
            db.add(p)
            db.commit()
            db.refresh(p)
            plantations.append(p)

        print("Génération de l'historique de diagnostics (6 mois)...")
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=180)
        count = 0

        for p in plantations:
            for _ in range(random.randint(2, 5)):
                target_risk = random.choices(risk_levels, weights=[60, 30, 10])[0]
                if target_risk == "LOW":
                    score = random.uniform(80, 100)
                    rain = random.uniform(80, 150)
                elif target_risk == "MEDIUM":
                    score = random.uniform(40, 79)
                    rain = random.uniform(150, 200)
                else:
                    score = random.uniform(0, 39)
                    rain = random.uniform(10, 70)

                diag = Diagnostic(
                    plantation_id=p.id,
                    country=p.country,
                    region=p.region,
                    humidity_pct=round(random.uniform(60.0, 95.0), 1),
                    rainfall_mm_month=round(rain, 1),
                    avg_temp_c=round(random.uniform(25.0, 32.0), 1),
                    plantation_age_years=random.randint(3, 30),
                    shade_tree_density_pct=random.randint(0, 70),
                    global_score=round(score, 1),
                    global_risk_level=target_risk,
                    created_at=generate_random_date(start, now),
                )
                db.add(diag)
                count += 1

        db.commit()
        print(f"Succès : {len(plantations)} plantations, {count} diagnostics créés.")

    except Exception as e:
        db.rollback()
        print(f"Erreur : {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
