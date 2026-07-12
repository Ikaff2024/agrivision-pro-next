"""
Export SIG des parcelles d'une coopérative — GeoJSON, KML, Shapefile.

Objectif : donner aux coopératives leurs données de géolocalisation dans les formats
standard attendus par l'EUDR (GeoJSON), Google Earth (KML) et les certificateurs /
outils SIG (Shapefile). Léger : GeoJSON/KML en Python pur ; Shapefile via `pyshp`
(pur Python, PAS de GDAL). Dégradation propre : Shapefile renvoie None si pyshp absent.

Chaque parcelle est exportée en POLYGONE si elle est délimitée, sinon en POINT
(GPS), avec des attributs utiles (nom, producteur, région, surface, statut EUDR).
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import Cooperative, Plantation, PlantationBoundary, Producer

WGS84_PRJ = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,'
    '298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", (s or "cooperative")).strip("_")[:40] or "cooperative"


def coop_slug(db: Session, coop_id: Optional[int]) -> str:
    if coop_id is None:
        return "cooperative"
    c = db.query(Cooperative.name).filter(Cooperative.id == coop_id).first()
    return _slug(c[0] if c else "cooperative")


def _polygon_coords(geojson):
    """Renvoie les anneaux [[ [lng,lat], ... ]] d'un GeoJSON Polygon, sinon None."""
    if not geojson:
        return None
    try:
        d = json.loads(geojson) if isinstance(geojson, str) else geojson
    except Exception:
        return None
    if isinstance(d, dict) and d.get("type") == "Feature":
        d = d.get("geometry")
    if isinstance(d, dict) and d.get("type") == "Polygon" and d.get("coordinates"):
        return d["coordinates"]
    return None


def _features(db: Session, coop_id: int) -> list[dict]:
    """Liste normalisée : {props, geom_type, coordinates} par parcelle exportable."""
    rows = (
        db.query(Plantation, PlantationBoundary.geojson, Producer.nom_complet)
        .outerjoin(PlantationBoundary, PlantationBoundary.plantation_id == Plantation.id)
        .outerjoin(Producer, Producer.id == Plantation.producer_id)
        .filter(Plantation.cooperative_id == coop_id)
        .all()
    )
    feats = []
    for pl, gj, producer_name in rows:
        props = {
            "id": pl.id,
            "name": pl.name or "",
            "producer": producer_name or (pl.owner_name or ""),
            "region": pl.region or "",
            "hectares": round(float(pl.hectares), 4) if pl.hectares is not None else None,
            "eudr": getattr(pl, "eudr_status", None) or "",
            "country": pl.country or "",
        }
        rings = _polygon_coords(gj)
        if rings:
            feats.append({"props": props, "geom_type": "Polygon", "coordinates": rings})
        elif pl.latitude is not None and pl.longitude is not None:
            feats.append({"props": props, "geom_type": "Point",
                          "coordinates": [float(pl.longitude), float(pl.latitude)]})
    return feats


# ── GeoJSON ───────────────────────────────────────────────────────────────────
def export_geojson(db: Session, coop_id: Optional[int]) -> dict:
    feats = _features(db, coop_id) if coop_id is not None else []
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature",
             "geometry": {"type": f["geom_type"], "coordinates": f["coordinates"]},
             "properties": f["props"]}
            for f in feats
        ],
    }


# ── KML ────────────────────────────────────────────────────────────────────────
def _kml_escape(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _kml_coords_ring(ring) -> str:
    return " ".join(f"{c[0]},{c[1]},0" for c in ring)


def export_kml(db: Session, coop_id: Optional[int]) -> str:
    feats = _features(db, coop_id) if coop_id is not None else []
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>']
    for f in feats:
        p = f["props"]
        desc = (f"Producteur : {p['producer']} | Région : {p['region']} | "
                f"Surface : {p['hectares']} ha | EUDR : {p['eudr']}")
        parts.append("<Placemark>")
        parts.append(f"<name>{_kml_escape(p['name'])}</name>")
        parts.append(f"<description>{_kml_escape(desc)}</description>")
        if f["geom_type"] == "Polygon":
            outer = f["coordinates"][0]
            parts.append("<Polygon><outerBoundaryIs><LinearRing><coordinates>"
                         f"{_kml_coords_ring(outer)}"
                         "</coordinates></LinearRing></outerBoundaryIs></Polygon>")
        else:
            c = f["coordinates"]
            parts.append(f"<Point><coordinates>{c[0]},{c[1]},0</coordinates></Point>")
        parts.append("</Placemark>")
    parts.append("</Document></kml>")
    return "\n".join(parts)


# ── Shapefile (pyshp, sans GDAL) ───────────────────────────────────────────────
def shapefile_available() -> bool:
    try:
        import shapefile  # noqa: F401
        return True
    except Exception:
        return False


def _write_layer(zf: zipfile.ZipFile, base: str, feats: list[dict], kind: str):
    """Écrit un jeu .shp/.shx/.dbf/.prj dans le zip pour un type de géométrie donné."""
    import shapefile
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    stype = shapefile.POLYGON if kind == "Polygon" else shapefile.POINT
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=stype)
    w.field("id", "N", 10)
    w.field("name", "C", 80)
    w.field("producer", "C", 80)
    w.field("region", "C", 60)
    w.field("hectares", "N", 12, 4)
    w.field("eudr", "C", 20)
    for f in feats:
        p = f["props"]
        if kind == "Polygon":
            w.poly(f["coordinates"])
        else:
            w.point(f["coordinates"][0], f["coordinates"][1])
        w.record(p["id"], p["name"], p["producer"], p["region"],
                 p["hectares"] if p["hectares"] is not None else 0, p["eudr"])
    w.close()
    zf.writestr(f"{base}.shp", shp.getvalue())
    zf.writestr(f"{base}.shx", shx.getvalue())
    zf.writestr(f"{base}.dbf", dbf.getvalue())
    zf.writestr(f"{base}.prj", WGS84_PRJ)


def export_shapefile_zip(db: Session, coop_id: Optional[int]) -> Optional[bytes]:
    """Zip contenant un shapefile de polygones et/ou de points. None si pyshp absent."""
    if not shapefile_available():
        return None
    feats = _features(db, coop_id) if coop_id is not None else []
    polys = [f for f in feats if f["geom_type"] == "Polygon"]
    points = [f for f in feats if f["geom_type"] == "Point"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if polys:
            _write_layer(zf, "parcelles_polygones", polys, "Polygon")
        if points:
            _write_layer(zf, "parcelles_points", points, "Point")
        if not polys and not points:
            # Zip non vide (évite un fichier corrompu côté client).
            zf.writestr("README.txt", "Aucune parcelle geolocalisee a exporter.")
    return buf.getvalue()
