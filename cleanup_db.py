"""
cleanup_db.py — Nettoyage des diagnostics image corrompus en DB.

Diagnostics corrompus = créés par l'ancienne route /diagnostic/image
qui écrivait humidity_pct=0, rainfall_mm_month=0, avg_temp_c=0 en DB.

Exécution sur Railway :
    python cleanup_db.py

Le script est idempotent — peut être relancé sans danger.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from app.db.database import SessionLocal
from app.db.models import Diagnostic

def main():
    db = SessionLocal()
    try:
        # Identifier les diagnostics corrompus
        # Critère : humidity=0 ET rainfall=0 ET temp=0
        # (impossible en conditions réelles — le CacaoEngine refuse ces valeurs)
        corrupted = db.query(Diagnostic).filter(
            Diagnostic.humidity_pct == 0.0,
            Diagnostic.rainfall_mm_month == 0.0,
            Diagnostic.avg_temp_c == 0.0,
        ).all()

        if not corrupted:
            print("✅ Aucun diagnostic corrompu trouvé — base propre.")
            return

        print(f"🔍 {len(corrupted)} diagnostic(s) corrompu(s) trouvé(s) :")
        for d in corrupted:
            print(f"   ID={d.id} | plantation_id={d.plantation_id} "
                  f"| score={d.global_score} | risk={d.global_risk_level} "
                  f"| créé={d.created_at}")

        # Confirmation
        print(f"\n⚠️  Suppression de {len(corrupted)} enregistrement(s)...")
        for d in corrupted:
            db.delete(d)
        db.commit()

        print(f"✅ {len(corrupted)} diagnostic(s) corrompu(s) supprimé(s) avec succès.")

        # Vérification post-nettoyage
        remaining = db.query(Diagnostic).filter(
            Diagnostic.humidity_pct == 0.0,
            Diagnostic.rainfall_mm_month == 0.0,
            Diagnostic.avg_temp_c == 0.0,
        ).count()
        print(f"✅ Vérification : {remaining} diagnostic(s) corrompu(s) restant(s).")

    except Exception as e:
        db.rollback()
        print(f"❌ Erreur : {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
