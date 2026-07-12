"""Export SIG des parcelles — GeoJSON (EUDR), KML (Google Earth), Shapefile (certif.)."""
import io
import json
import zipfile

from app.auth.auth_service import create_access_token
from app.db.models import Cooperative, Plantation, PlantationBoundary, Producer, User
from tests.conftest import TestingSessionLocal

POLY = json.dumps({"type": "Polygon", "coordinates": [[
    [-6.59, 5.78], [-6.58, 5.78], [-6.58, 5.79], [-6.59, 5.79], [-6.59, 5.78]]]})


def _auth(u):
    return {"Authorization": "Bearer " + create_access_token(
        {"sub": u.email, "role": u.role, "coop_id": u.cooperative_id})}


def _seed(coop="Coop Export", email="exp@test.ci"):
    """Une parcelle POLYGONE (délimitée) + une parcelle POINT (GPS seul)."""
    db = TestingSessionLocal()
    try:
        c = Cooperative(name=coop, country="CI"); db.add(c); db.flush()
        u = User(email=email, password_hash="x", role="admin", cooperative_id=c.id)
        pr = Producer(cooperative_id=c.id, nom_complet="Koffi Yao", is_active=True)
        db.add_all([u, pr]); db.flush()
        p1 = Plantation(name="Parcelle Poly", owner_name="Koffi", country="CI", region="Soubre",
                        latitude=5.785, longitude=-6.585, hectares=2.0,
                        cooperative_id=c.id, producer_id=pr.id)
        p2 = Plantation(name="Parcelle Point", owner_name="Koffi", country="CI", region="Meagui",
                        latitude=5.90, longitude=-6.40, hectares=1.0,
                        cooperative_id=c.id, producer_id=pr.id)
        db.add_all([p1, p2]); db.flush()
        db.add(PlantationBoundary(plantation_id=p1.id, geojson=POLY, area_hectares=2.0,
                                  points_count=5, method="manual"))
        db.commit()
        return c.id, _auth(u)
    finally:
        db.close()


def test_export_geojson(client):
    _, auth = _seed()
    r = client.get("/geo/export.geojson", headers=auth)
    assert r.status_code == 200, r.text
    assert "geo+json" in r.headers["content-type"]
    assert ".geojson" in r.headers.get("content-disposition", "")
    fc = json.loads(r.content)
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 2
    types = {f["geometry"]["type"] for f in fc["features"]}
    assert types == {"Polygon", "Point"}
    poly = next(f for f in fc["features"] if f["geometry"]["type"] == "Polygon")
    assert poly["properties"]["name"] == "Parcelle Poly"
    assert poly["properties"]["producer"] == "Koffi Yao"


def test_export_kml(client):
    _, auth = _seed(coop="Coop Export KML", email="exp.kml@test.ci")
    r = client.get("/geo/export.kml", headers=auth)
    assert r.status_code == 200, r.text
    body = r.content.decode("utf-8")
    assert "<kml" in body and "<Polygon>" in body and "<Point>" in body
    assert "Parcelle Poly" in body


def test_export_shapefile_zip(client):
    _, auth = _seed(coop="Coop Export SHP", email="exp.shp@test.ci")
    r = client.get("/geo/export.shp.zip", headers=auth)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    # Deux couches attendues (polygones + points), chacune avec .shp/.dbf/.prj.
    assert "parcelles_polygones.shp" in names and "parcelles_polygones.prj" in names
    assert "parcelles_points.shp" in names
    # Relecture pyshp : la couche polygone contient bien 1 enregistrement nommé.
    import shapefile
    r_shp = zf.read("parcelles_polygones.shp"); r_dbf = zf.read("parcelles_polygones.dbf")
    r_shx = zf.read("parcelles_polygones.shx")
    reader = shapefile.Reader(shp=io.BytesIO(r_shp), dbf=io.BytesIO(r_dbf), shx=io.BytesIO(r_shx))
    assert reader.numRecords == 1
    assert reader.record(0)["name"] == "Parcelle Poly"


def test_export_cooperative_scoped(client):
    _, auth_a = _seed(coop="Coop Export A", email="exp.a@test.ci")
    _, auth_b = _seed(coop="Coop Export B", email="exp.b@test.ci")
    fc_b = json.loads(client.get("/geo/export.geojson", headers=auth_b).content)
    # B ne voit que SES 2 parcelles (pas celles de A) → total 2, pas 4.
    assert len(fc_b["features"]) == 2


def test_export_requires_auth(client):
    assert client.get("/geo/export.geojson").status_code == 401
    assert client.get("/geo/export.kml").status_code == 401
    assert client.get("/geo/export.shp.zip").status_code == 401
