#!/usr/bin/env python3
"""
Seed de données de DÉMONSTRATION pour AgriVision Pro — via l'API (aucun accès DB requis).

Crée une coopérative de démo réaliste (filière cacao Côte d'Ivoire) avec des
données VARIÉES dans chaque module, pour les tests et les démos :
producteurs/plantations (GPS + polygones), diagnostics, récoltes (2 campagnes),
agroforesterie, contrôles déforestation (mix), achats (paiements mixtes), lots
+ mouvements. Les parcelles sont volontairement dans des états différents
(conforme, à délimiter, déforestation détectée, rendement faible…) pour que
l'EUDR, le tableau « Prêt pour l'EUDR » et le Jumeau montrent du contenu riche.

Usage :
    AVP_API_URL=https://agrivision-api-production.up.railway.app python seed_demo.py
Identifiants de démo créés (par défaut) :
    email : demo@agrivision-pro.com   mot de passe : DemoAgriVision2026!
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timedelta

import httpx

# Console UTF-8 (Windows cp1252 sinon plante sur les accents/flèches).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API = os.getenv("AVP_API_URL", "https://agrivision-api-production.up.railway.app").rstrip("/")
EMAIL = os.getenv("AVP_DEMO_EMAIL", "demo@agrivision-pro.com")
PASSWORD = os.getenv("AVP_DEMO_PASSWORD", "DemoAgriVision2026!")
COOP = os.getenv("AVP_DEMO_COOP", "Coopérative Démo Yeyasso")

client = httpx.Client(timeout=60.0)
_token = None
_count: dict = {}


def bump(k, n=1):
    _count[k] = _count.get(k, 0) + n


def h():
    return {"Authorization": f"Bearer {_token}", "Content-Type": "application/json"}


def post(path, payload, label):
    r = client.post(f"{API}{path}", headers=h(), json=payload)
    if r.status_code not in (200, 201):
        print(f"   ⚠ {label}: HTTP {r.status_code} {r.text[:120]}")
        return None
    bump(label)
    return r.json()


def square_geojson(lat, lon, ha):
    half = math.sqrt(ha * 10000) / 2
    dlat = half / 111320
    dlon = half / (111320 * math.cos(math.radians(lat)))
    ring = [
        [lon - dlon, lat - dlat], [lon + dlon, lat - dlat],
        [lon + dlon, lat + dlat], [lon - dlon, lat + dlat], [lon - dlon, lat - dlat],
    ]
    return json.dumps({"type": "Polygon", "coordinates": [ring]})


# Producteurs/parcelles (ceinture cacao CI) — états variés pour la démo.
# (nom, région, lat, lon, ha, profil)
FARMERS = [
    ("Kouassi Yao",      "Soubré",    5.78, -6.59, 3.2, "full"),
    ("Konan Aka",        "Méagui",    5.62, -6.78, 2.5, "full"),
    ("Yao Koffi",        "San-Pédro", 4.95, -6.55, 4.1, "full"),
    ("N'Guessan Adjoua", "Soubré",    5.81, -6.61, 1.8, "no_boundary"),
    ("Brou Amani",       "Méagui",    5.59, -6.81, 3.0, "deforestation"),
    ("Tanoh Affoué",     "Gagnoa",    6.05, -5.95, 2.2, "no_diagnostic"),
    ("Kouamé Akissi",    "Daloa",     6.88, -6.45, 5.0, "low_yield"),
    ("Diby Serge",       "Soubré",    5.75, -6.57, 2.8, "no_harvest"),
]

AGRO_SPECIES = [
    ("Gliricidia sepium", "Gliricidi", "intermediate", 18, 4),
    ("Albizzia adianthifolia", "Albizzia", "superior", 9, 12),
    ("Persea americana", "Avocatier", "intermediate", 6, 8),
]


def login_or_register():
    global _token
    r = client.post(f"{API}/auth/register", json={
        "email": EMAIL, "password": PASSWORD, "role": "admin",
        "cooperative_name": COOP, "country": "CI",
    })
    if r.status_code in (200, 201):
        print(f"✓ Coopérative créée : {COOP}")
    elif r.status_code == 400:
        print(f"ℹ Compte démo déjà présent ({EMAIL}) — connexion (les données seront ajoutées).")
    else:
        print(f"✗ Register: HTTP {r.status_code} {r.text[:160]}")
    lr = client.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if lr.status_code != 200:
        print(f"✗ Login impossible: {lr.status_code} {lr.text[:160]}")
        sys.exit(1)
    _token = lr.json()["access_token"]


def main():
    print(f"=== Seed démo AgriVision Pro → {API} ===")
    login_or_register()

    harvest_ids = []
    for name, region, lat, lon, ha, profile in FARMERS:
        p = post("/plantations", {
            "name": f"Parcelle {name.split()[0]} {region}", "owner_name": name,
            "country": "Côte d'Ivoire", "region": region, "hectares": ha,
            "latitude": lat, "longitude": lon,
        }, "plantations")
        if not p:
            continue
        pid = p["id"]

        # Délimitation (sauf profil "no_boundary")
        if profile != "no_boundary":
            post(f"/plantations/{pid}/boundary",
                 {"geojson": square_geojson(lat, lon, ha), "method": "manual"}, "boundaries")

        # Diagnostic agronomique (sauf "no_diagnostic")
        if profile != "no_diagnostic":
            post(f"/cacao/diagnostic?plantation_id={pid}", {
                "country": "CI", "region": region,
                "rainfall_mm_month": 110 + (hash(name) % 80),
                "humidity_pct": 70 + (hash(name) % 20),
                "avg_temp_c": 25 + (hash(region) % 4),
                "plantation_age_years": 8 + (hash(name) % 25),
                "shade_tree_density_pct": 25 + (hash(name) % 40),
            }, "diagnostics")

        # Récoltes : 2 campagnes (sauf "no_harvest"). "low_yield" => faible kg/ha.
        if profile != "no_harvest":
            base = (120 if profile == "low_yield" else 600) * ha
            for season, when, factor in [
                ("2024-2025", datetime(2025, 1, 20), 0.9),
                ("2025-2026", datetime(2026, 1, 18), 1.0),
            ]:
                kg = round(base * factor, 1)
                hv = post(f"/plantations/{pid}/harvests", {
                    "harvest_date": when.isoformat(), "quantity_kg": kg, "quality": "Bonne",
                    "season": season, "price_per_kg_fcfa": 1500,
                    "nbre_sacs": int(kg // 65), "numero_recu_achat": f"REC-{season[:4]}-{pid:03d}",
                    "is_historical": season == "2024-2025",
                }, "harvests")
                if hv and hv.get("id") and season == "2025-2026":
                    harvest_ids.append(hv["id"])

        # Agroforesterie (parcelles délimitées)
        if profile in ("full", "low_yield"):
            for sp, local, layer, dens, age in AGRO_SPECIES[: 1 + (pid % 3)]:
                post(f"/plantations/{pid}/agroforestry", {
                    "species_name": sp, "local_name": local, "layer": layer,
                    "count_per_hectare": dens, "avg_age_years": age,
                }, "agroforestry")

        # Contrôle déforestation : mix selon profil
        if profile == "deforestation":
            post(f"/plantations/{pid}/deforestation-check",
                 {"verdict": "deforestation_detected", "source": "field_visit",
                  "forest_loss_year": 2022}, "deforestation_checks")
        elif profile in ("full", "low_yield"):
            post(f"/plantations/{pid}/deforestation-check",
                 {"verdict": "clear", "source": "field_visit"}, "deforestation_checks")

        print(f"  • {name} ({region}, {ha} ha) — profil {profile}")

    # Producteurs (auto-créés) → achats avec statuts de paiement variés
    prods = client.get(f"{API}/producers?limit=5000", headers=h())
    producers = prods.json() if prods.status_code == 200 else []
    for i, pr in enumerate(producers[:6]):
        net = 200 + i * 40
        post("/purchases", {
            "producer_id": pr["id"], "receipt_number": f"BON-DEMO-{pr['id']:03d}",
            "season": "2025-2026", "gross_weight_kg": net + 5, "tare_kg": 5,
            "net_weight_kg": net, "bag_count": int(net // 65) + 1,
            "price_per_kg_fcfa": 1500, "quality": "Bonne", "buyer_name": "Acheteur Démo",
            "payment_status": "paid" if i % 2 == 0 else "pending",
        }, "purchases")

    # Entrepôt + lots (traçabilité) + mouvements
    wh = post("/warehouses", {"name": "Magasin central Soubré", "location": "Soubré"}, "warehouses")
    if harvest_ids:
        lot = post("/lots", {"season": "2025-2026",
                             "warehouse_id": wh["id"] if wh else None,
                             "harvest_ids": harvest_ids[:4]}, "lots")
        if lot and lot.get("id"):
            post(f"/lots/{lot['id']}/movements",
                 {"movement_type": "warehouse_in",
                  "to_warehouse_id": wh["id"] if wh else None}, "lot_movements")
            post(f"/lots/{lot['id']}/movements", {"movement_type": "seal"}, "lot_movements")
        # un 2e lot
        if len(harvest_ids) > 4:
            post("/lots", {"season": "2025-2026", "harvest_ids": harvest_ids[4:]}, "lots")

    print("\n=== Résumé du seed ===")
    for k in sorted(_count):
        print(f"  {k:18}: {_count[k]}")
    print(f"\n✓ Démo prête. Connexion : {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    main()
