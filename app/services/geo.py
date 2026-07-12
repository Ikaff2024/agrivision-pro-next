"""
Analyse géométrique des parcelles (capacités « classe SIG », moteur GEOS via shapely).

Deux contrôles à forte valeur EUDR, à partir des polygones DÉJÀ tracés :
  1. VALIDITÉ de géométrie — un polygone auto-intersecté / dégénéré fait rejeter un
     dossier EUDR. On le détecte et on l'explique.
  2. CHEVAUCHEMENT de parcelles (double-mapping) — deux parcelles dont les polygones
     se superposent = risque de fraude / double comptage. On mesure la surface et le
     pourcentage de recouvrement.

DÉGRADATION PROPRE : si `shapely` n'est pas installé, toutes les fonctions renvoient
`available=False` (jamais d'exception) — l'appli continue de tourner sans le module géo.
"""
from __future__ import annotations

import json
import math
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import Plantation, PlantationBoundary

# Seuils explicables : on ignore les micro-chevauchements (bord/sommet commun).
OVERLAP_MIN_HA = 0.01
OVERLAP_MIN_PCT = 1.0


def _shapely():
    """Import paresseux de shapely ; None si indisponible (dégradation propre)."""
    try:
        import shapely  # noqa: F401
        from shapely.geometry import shape  # noqa: F401
        return True
    except Exception:
        return False


def geo_available() -> bool:
    return _shapely()


# ── Surface géodésique (hectares) — même formule sphérique que le reste de l'appli ──
def _ring_area_ha(coords) -> float:
    if not coords or len(coords) < 3:
        return 0.0
    R = 6371000.0
    rad = math.pi / 180.0
    s = 0.0
    n = len(coords)
    for i in range(n):
        j = (i + 1) % n
        lon1, lat1 = coords[i][0] * rad, coords[i][1] * rad
        lon2, lat2 = coords[j][0] * rad, coords[j][1] * rad
        s += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2))
    return abs(s) * R * R / 2 / 10000.0


def _poly_area_ha(geom) -> float:
    """Surface (ha) d'un (Multi)Polygon shapely, via ses anneaux extérieurs/trous."""
    gt = geom.geom_type
    if gt == "Polygon":
        area = _ring_area_ha(list(geom.exterior.coords))
        for ring in geom.interiors:
            area -= _ring_area_ha(list(ring.coords))
        return max(area, 0.0)
    if gt in ("MultiPolygon", "GeometryCollection"):
        return sum(_poly_area_ha(g) for g in geom.geoms if g.geom_type == "Polygon")
    return 0.0


def _parse(geojson) -> Optional[dict]:
    if not geojson:
        return None
    if isinstance(geojson, str):
        try:
            return json.loads(geojson)
        except Exception:
            return None
    return geojson if isinstance(geojson, dict) else None


def _to_geom(geojson):
    """Construit une géométrie shapely depuis un GeoJSON géométrie ou Feature. None si KO."""
    from shapely.geometry import shape
    d = _parse(geojson)
    if not d:
        return None
    if d.get("type") == "Feature":
        d = d.get("geometry")
    if not d or "coordinates" not in d:
        return None
    try:
        return shape(d)
    except Exception:
        return None


def validate_geometry(geojson) -> dict:
    """Valide un polygone. Renvoie available/valid/reason (+ tentative de réparation)."""
    if not _shapely():
        return {"available": False, "reason": "module géo non disponible"}
    geom = _to_geom(geojson)
    if geom is None:
        return {"available": True, "valid": False, "reason": "Géométrie absente ou illisible."}
    if geom.is_valid:
        return {"available": True, "valid": True, "reason": None}
    # Invalide : expliquer + indiquer si réparable.
    reason = "Polygone invalide"
    try:
        from shapely.validation import explain_validity
        reason = explain_validity(geom)
    except Exception:
        pass
    repairable = False
    try:
        from shapely.validation import make_valid
        repairable = make_valid(geom).is_valid
    except Exception:
        pass
    return {"available": True, "valid": False, "reason": reason, "repairable": repairable}


# ── Chargement des polygones d'une coopérative ────────────────────────────────
def _load_coop_polys(db: Session, coop_id: int, exclude_pid: Optional[int] = None):
    """[(plantation, geom_valide), …] pour toutes les parcelles délimitées de la coop."""
    rows = (
        db.query(Plantation, PlantationBoundary.geojson)
        .join(PlantationBoundary, PlantationBoundary.plantation_id == Plantation.id)
        .filter(Plantation.cooperative_id == coop_id)
        .all()
    )
    out = []
    for pl, gj in rows:
        if exclude_pid is not None and pl.id == exclude_pid:
            continue
        geom = _to_geom(gj)
        if geom is None or geom.is_valid is False:
            # On répare à la volée pour l'analyse (sans écrire en base).
            if geom is not None:
                try:
                    from shapely.validation import make_valid
                    geom = make_valid(geom)
                except Exception:
                    geom = None
        if geom is not None and not geom.is_empty:
            out.append((pl, geom))
    return out


def _overlap_record(pl_other, inter_ha, area_self_ha) -> dict:
    pct = round(inter_ha / area_self_ha * 100, 1) if area_self_ha > 0 else None
    return {
        "plantation_id": pl_other.id,
        "name": pl_other.name,
        "producer_name": None,
        "overlap_ha": round(inter_ha, 4),
        "overlap_pct": pct,
    }


def find_overlaps(db: Session, plantation: Plantation) -> dict:
    """Chevauchements d'UNE parcelle avec les autres de sa coopérative."""
    if not _shapely():
        return {"available": False, "reason": "module géo non disponible"}
    if plantation.cooperative_id is None:
        return {"available": True, "overlaps": [], "count": 0}
    boundary = plantation.boundary
    self_geom = _to_geom(boundary.geojson) if boundary else None
    if self_geom is None:
        return {"available": True, "overlaps": [], "count": 0, "reason": "Parcelle non délimitée."}
    if not self_geom.is_valid:
        try:
            from shapely.validation import make_valid
            self_geom = make_valid(self_geom)
        except Exception:
            pass
    area_self = _poly_area_ha(self_geom)
    overlaps = []
    for pl_other, geom in _load_coop_polys(db, plantation.cooperative_id, exclude_pid=plantation.id):
        if not self_geom.intersects(geom):
            continue
        try:
            inter = self_geom.intersection(geom)
        except Exception:
            continue
        inter_ha = _poly_area_ha(inter)
        pct = (inter_ha / area_self * 100) if area_self > 0 else 0
        if inter_ha >= OVERLAP_MIN_HA and pct >= OVERLAP_MIN_PCT:
            overlaps.append(_overlap_record(pl_other, inter_ha, area_self))
    overlaps.sort(key=lambda o: o["overlap_ha"], reverse=True)
    return {"available": True, "overlaps": overlaps, "count": len(overlaps)}


def build_coop_overlaps(db: Session, coop_id: Optional[int]) -> dict:
    """Toutes les paires de parcelles qui se chevauchent dans la coopérative.

    Utilise un index spatial (STRtree) → ne teste que les candidats dont les
    emprises se recoupent : scalable à des milliers de parcelles. FAIL-CLOSED.
    """
    if not _shapely():
        return {"available": False, "reason": "module géo non disponible", "pairs": [], "count": 0}
    if coop_id is None:
        return {"available": True, "pairs": [], "count": 0, "total_delimited": 0}
    polys = _load_coop_polys(db, coop_id)
    if len(polys) < 2:
        return {"available": True, "pairs": [], "count": 0, "total_delimited": len(polys)}

    from shapely import STRtree
    geoms = [g for _, g in polys]
    tree = STRtree(geoms)
    areas = [_poly_area_ha(g) for g in geoms]

    seen = set()
    pairs = []
    for i, (pl_i, gi) in enumerate(polys):
        for j in tree.query(gi):
            if j <= i:
                continue
            gj = geoms[j]
            if not gi.intersects(gj):
                continue
            try:
                inter_ha = _poly_area_ha(gi.intersection(gj))
            except Exception:
                continue
            if inter_ha < OVERLAP_MIN_HA:
                continue
            pl_j = polys[j][0]
            smaller = min(areas[i], areas[j]) or 0
            pct = round(inter_ha / smaller * 100, 1) if smaller > 0 else None
            if pct is not None and pct < OVERLAP_MIN_PCT:
                continue
            key = (min(pl_i.id, pl_j.id), max(pl_i.id, pl_j.id))
            if key in seen:
                continue
            seen.add(key)
            pairs.append({
                "a": {"plantation_id": pl_i.id, "name": pl_i.name},
                "b": {"plantation_id": pl_j.id, "name": pl_j.name},
                "overlap_ha": round(inter_ha, 4),
                "overlap_pct": pct,
            })
    pairs.sort(key=lambda p: p["overlap_ha"], reverse=True)
    return {"available": True, "pairs": pairs, "count": len(pairs), "total_delimited": len(polys)}
