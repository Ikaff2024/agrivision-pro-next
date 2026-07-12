"""Analyse géométrique (classe SIG via shapely) : validité + chevauchement de parcelles.

Contrôle EUDR : polygone invalide (rejet) et double-mapping (fraude/double comptage).
"""
import json

from app.auth.auth_service import create_access_token
from app.db.models import Cooperative, Plantation, PlantationBoundary, Producer, User
from app.services.twin import build_twin, compute_alerts
from tests.conftest import TestingSessionLocal


def _sq(lng0, lat0, d=0.01):
    """Carré GeoJSON de côté d degrés, coin bas-gauche (lng0, lat0)."""
    return json.dumps({"type": "Polygon", "coordinates": [[
        [lng0, lat0], [lng0 + d, lat0], [lng0 + d, lat0 + d], [lng0, lat0 + d], [lng0, lat0],
    ]]})


BOWTIE = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]})


def _auth(user):
    return {"Authorization": "Bearer " + create_access_token(
        {"sub": user.email, "role": user.role, "coop_id": user.cooperative_id})}


def _seed(polys, coop="Coop Geo", email="geo@test.ci"):
    """polys = liste de (name, geojson|None). Renvoie (coop_id, {name: pid}, auth)."""
    db = TestingSessionLocal()
    try:
        c = Cooperative(name=coop, country="CI"); db.add(c); db.flush()
        user = User(email=email, password_hash="x", role="admin", cooperative_id=c.id)
        prod = Producer(cooperative_id=c.id, nom_complet="Kouassi", is_active=True)
        db.add_all([user, prod]); db.flush()
        ids = {}
        for name, gj in polys:
            p = Plantation(name=name, owner_name="K", country="CI", region="Soubre",
                           latitude=5.78, longitude=-6.58, hectares=1.0,
                           cooperative_id=c.id, producer_id=prod.id)
            db.add(p); db.flush()
            if gj:
                db.add(PlantationBoundary(plantation_id=p.id, geojson=gj, area_hectares=1.0,
                                          points_count=5, method="manual"))
            ids[name] = p.id
        db.commit()
        return c.id, ids, _auth(user)
    finally:
        db.close()


# ── Validation de géométrie (unitaire) ───────────────────────────────────────

def test_validate_geometry_valid_and_invalid():
    from app.services.geo import validate_geometry
    ok = validate_geometry(_sq(-6.59, 5.78))
    assert ok["available"] and ok["valid"] is True
    bad = validate_geometry(BOWTIE)
    assert bad["available"] and bad["valid"] is False
    assert "self-intersection" in bad["reason"].lower()
    assert bad["repairable"] is True


# ── Chevauchement (endpoints) ────────────────────────────────────────────────

def test_overlap_detected_between_two_plots(client):
    # A et B se chevauchent (B décalé d'un demi-côté) ; C est loin → aucun conflit.
    _, ids, auth = _seed([
        ("Parcelle A", _sq(-6.590, 5.780)),
        ("Parcelle B", _sq(-6.585, 5.785)),      # recouvre un quart de A
        ("Parcelle C", _sq(-6.400, 5.900)),      # ailleurs
    ])
    r = client.get("/geo/overlaps", headers=auth)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["available"] is True
    assert d["count"] == 1                        # une seule paire (A,B)
    pair = d["pairs"][0]
    names = {pair["a"]["name"], pair["b"]["name"]}
    assert names == {"Parcelle A", "Parcelle B"}
    assert pair["overlap_ha"] > 0 and pair["overlap_pct"] > 1


def test_geo_check_single_plot(client):
    _, ids, auth = _seed([
        ("Parcelle A", _sq(-6.590, 5.780)),
        ("Parcelle B", _sq(-6.585, 5.785)),
    ], coop="Coop Geo Single", email="geo.single@test.ci")
    r = client.get(f"/plantations/{ids['Parcelle A']}/geo-check", headers=auth)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["validity"]["valid"] is True
    assert d["count"] == 1 and d["overlaps"][0]["name"] == "Parcelle B"


def test_no_overlap_when_disjoint(client):
    _, ids, auth = _seed([
        ("P1", _sq(-6.590, 5.780)),
        ("P2", _sq(-6.400, 5.900)),
    ], coop="Coop Geo Disjoint", email="geo.disj@test.ci")
    d = client.get("/geo/overlaps", headers=auth).json()
    assert d["count"] == 0


# ── Intégration au Jumeau (alerte) ───────────────────────────────────────────

def test_twin_flags_overlap_and_invalid(client):
    coop_id, ids, auth = _seed([
        ("Parcelle A", _sq(-6.590, 5.780)),
        ("Parcelle B", _sq(-6.585, 5.785)),
        ("Parcelle Tordue", BOWTIE),
    ], coop="Coop Geo Twin", email="geo.twin@test.ci")
    db = TestingSessionLocal()
    try:
        pa = db.query(Plantation).filter(Plantation.id == ids["Parcelle A"]).first()
        twin = build_twin(db, pa)
        assert twin["geometry"]["available"] is True
        assert twin["geometry"]["overlap_count"] >= 1
        assert "plot_overlap" in {a["code"] for a in compute_alerts(twin)}

        pt = db.query(Plantation).filter(Plantation.id == ids["Parcelle Tordue"]).first()
        twin_t = build_twin(db, pt)
        assert twin_t["geometry"]["valid"] is False
        assert "geometry_invalid" in {a["code"] for a in compute_alerts(twin_t)}
    finally:
        db.close()


# ── Cloisonnement + auth ─────────────────────────────────────────────────────

def test_overlaps_cooperative_scoped(client):
    # Coop A a un chevauchement ; coop B ne doit rien voir.
    _seed([("A1", _sq(-6.590, 5.780)), ("A2", _sq(-6.585, 5.785))],
          coop="Coop Geo A", email="geo.a@test.ci")
    _, _, auth_b = _seed([("B1", _sq(-6.100, 5.100))], coop="Coop Geo B", email="geo.b@test.ci")
    d = client.get("/geo/overlaps", headers=auth_b).json()
    assert d["count"] == 0


def test_geo_requires_auth(client):
    assert client.get("/geo/overlaps").status_code == 401
    assert client.get("/plantations/1/geo-check").status_code == 401


def test_graceful_degradation_without_shapely(client, monkeypatch):
    """Si shapely est indisponible, tout renvoie available=False sans casser l'appli."""
    import app.services.geo as geo
    monkeypatch.setattr(geo, "_shapely", lambda: False)
    _, ids, auth = _seed([("Parcelle A", _sq(-6.590, 5.780)), ("Parcelle B", _sq(-6.585, 5.785))],
                         coop="Coop Geo NoLib", email="geo.nolib@test.ci")
    d = client.get("/geo/overlaps", headers=auth).json()
    assert d["available"] is False and d["count"] == 0
    # Le jumeau reste fonctionnel, juste sans bloc géo.
    db = TestingSessionLocal()
    try:
        pa = db.query(Plantation).filter(Plantation.id == ids["Parcelle A"]).first()
        twin = build_twin(db, pa)
        assert twin["geometry"]["available"] is False
        assert isinstance(compute_alerts(twin), list)   # pas de crash
    finally:
        db.close()
