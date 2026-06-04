"""
Pack de diligence raisonnée EUDR par lot (livrable acheteur / exportateur).

Assemble, pour toutes les parcelles d'un lot, un ZIP contenant :
- DDS/<parcelle>.pdf      : le Due Diligence Statement de chaque parcelle ;
- parcelles.geojson       : la géométrie des polygones (FeatureCollection) ;
- recapitulatif.csv       : synthèse de conformité par parcelle (ouvrable Excel) ;
- LISEZ-MOI.txt           : description du contenu + références du lot.

Réutilise le générateur DDS existant (app/services/eudr_reports.py) et le moteur
de scoring EUDR — aucune logique de conformité dupliquée.
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import DeforestationCheck, Harvest, Plantation, Producer
from app.eudr.scoring import compute_eudr_score
from app.services.eudr_reports import build_dds_context, dds_filename, generate_dds_pdf


def _latest_deforestation_verdict(db: Session, plantation_id: int) -> Optional[str]:
    last = (
        db.query(DeforestationCheck)
        .filter(DeforestationCheck.plantation_id == plantation_id)
        .order_by(DeforestationCheck.check_date.desc().nullslast(), DeforestationCheck.id.desc())
        .first()
    )
    return last.verdict if last else None


def _readme(lot, n_parcels: int) -> str:
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"Pack de diligence raisonnée EUDR — lot {lot.code}\n"
        f"Généré le {when} par AgriVision Pro.\n\n"
        f"Contenu ({n_parcels} parcelle(s)) :\n"
        f"- DDS/                : un Due Diligence Statement (PDF) par parcelle du lot ;\n"
        f"- parcelles.geojson   : géométries des polygones (à ouvrir dans un SIG) ;\n"
        f"- recapitulatif.csv   : synthèse de conformité par parcelle (Excel) ;\n\n"
        f"Document destiné à l'opérateur/importateur pour la traçabilité EUDR\n"
        f"(Règlement (UE) 2023/1115). Vérifiez la conformité de chaque parcelle\n"
        f"dans le récapitulatif et les DDS individuels.\n"
    )


def build_eudr_pack(db: Session, lot) -> Optional[tuple[bytes, str]]:
    """Construit le ZIP du pack EUDR d'un lot. Retourne (bytes, filename) ou None
    si le lot ne contient aucune parcelle."""
    harvests = db.query(Harvest).filter(Harvest.lot_id == lot.id).all()
    plant_ids = sorted({h.plantation_id for h in harvests if h.plantation_id})
    if not plant_ids:
        return None
    plantations = db.query(Plantation).filter(Plantation.id.in_(plant_ids)).all()
    if not plantations:
        return None
    producer_ids = {p.producer_id for p in plantations if p.producer_id}
    producers = (
        {p.id: p for p in db.query(Producer).filter(Producer.id.in_(producer_ids)).all()}
        if producer_ids else {}
    )

    features = []
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf, delimiter=";")
    writer.writerow([
        "Parcelle", "Producteur", "Superficie declaree (ha)", "Polygone",
        "Score EUDR", "Statut EUDR", "Deforestation",
    ])

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in plantations:
            score = compute_eudr_score(p, db)
            verdict = _latest_deforestation_verdict(db, p.id) or "non controle"
            producer = producers.get(p.producer_id) if p.producer_id else None

            pdf_bytes = generate_dds_pdf(build_dds_context(p, db))
            z.writestr(f"DDS/{dds_filename(p)}", pdf_bytes)

            boundary = p.boundary
            if boundary and boundary.geojson:
                try:
                    geom = json.loads(boundary.geojson)
                    if isinstance(geom, dict) and geom.get("type") == "Feature":
                        geom = geom.get("geometry")
                    if geom:
                        features.append({
                            "type": "Feature",
                            "geometry": geom,
                            "properties": {
                                "plantation": p.name,
                                "owner": p.owner_name,
                                "eudr_status": score.status,
                            },
                        })
                except (json.JSONDecodeError, TypeError):
                    pass

            writer.writerow([
                p.name or "", producer.nom_complet if producer else "",
                f"{p.hectares:.2f}" if p.hectares else "",
                "oui" if score.has_polygon else "non",
                f"{score.score}/{score.max_score}", score.status, verdict,
            ])

        z.writestr("parcelles.geojson", json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False, indent=2,
        ))
        # BOM UTF-8 pour qu'Excel affiche correctement les accents.
        z.writestr("recapitulatif.csv", "﻿" + csv_buf.getvalue())
        z.writestr("LISEZ-MOI.txt", _readme(lot, len(plantations)))

    return zip_buf.getvalue(), f"EUDR_{lot.code}.zip"
