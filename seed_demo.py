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
from datetime import date, datetime, timedelta

import httpx

# Console UTF-8 (Windows cp1252 sinon plante sur les accents/flèches).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API = os.getenv("AVP_API_URL", "https://agrivision-api-production.up.railway.app").rstrip("/")
EMAIL = os.getenv("AVP_DEMO_EMAIL", "demo@agrivision-pro.com")
PASSWORD = os.getenv("AVP_DEMO_PASSWORD", "DemoAgriVision2026!")
COOP = os.getenv("AVP_DEMO_COOP", "Coopérative Démo Cacao")

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


def _producer_map() -> dict:
    """Map nom_complet → id des producteurs EXISTANTS (via l'API)."""
    r = client.get(f"{API}/producers?limit=5000", headers=h())
    rows = r.json() if r.status_code == 200 else []
    m = {}
    for pr in rows:
        nm = pr.get("nom_complet") or pr.get("name") or pr.get("full_name")
        if nm and pr.get("id"):
            m.setdefault(nm, pr["id"])
    return m


def _plantations() -> list:
    """Plantations EXISTANTES (gère le mode brut et le mode paginé)."""
    r = client.get(f"{API}/plantations?limit=5000", headers=h())
    rows = r.json() if r.status_code == 200 else []
    if isinstance(rows, dict):
        rows = rows.get("items", [])
    return rows


def seed_social_compliance():
    """CacaoGuard (protection enfant + ops terrain), SSRTE et Certification.

    S'appuie sur les producteurs/plantations EXISTANTS récupérés via l'API :
    exécutable seul sur une coop déjà initialisée (AVP_SEED_SOCIAL_ONLY=1) SANS
    dupliquer les données de base. Construit une histoire cohérente :
    un cas de travail d'enfant → évaluation → visite → remédiation → blocage de
    traçabilité, plus un cas sain, du SSRTE et un audit de certification.
    """
    pmap = _producer_map()
    plants = _plantations()
    if not pmap:
        print("   ⚠ Aucun producteur — lancez d'abord le seed principal.")
        return
    today = date.today()

    def yrs_ago(n):
        return date(today.year - n, today.month, min(today.day, 28)).isoformat()

    names = list(pmap)
    risky = "Kouassi Yao" if "Kouassi Yao" in pmap else names[0]
    safe = "Konan Aka" if "Konan Aka" in pmap else (names[1] if len(names) > 1 else names[0])
    risky_pid, safe_pid = pmap[risky], pmap[safe]

    # ── Protection de l'enfance (CacaoGuard) ──
    at_risk_child = None
    c = post("/children", {
        "producer_id": risky_pid, "first_name": "Aya", "last_name": risky.split()[0],
        "date_of_birth": yrs_ago(13), "gender": "F",
        "school_status": "dropped_out", "is_working_on_farm": True,
        "work_frequency": "regular",
        "dangerous_tasks_performed": ["port de charges lourdes", "usage de machette"],
    }, "children")
    if c and c.get("id"):
        at_risk_child = c["id"]
        post(f"/children/{c['id']}/calculate-risk", {}, "child_risk_calc")
        post("/children/assessments", {
            "child_id": c["id"], "assessment_type": "initial",
            "overall_risk_score": 78, "overall_risk_level": "high",
            "risk_factors": {"travail": "régulier", "scolarisation": "déscolarisé"},
            "notes": "Cas détecté lors d'une visite terrain — suivi requis.",
        }, "risk_assessments")

    c2 = post("/children", {
        "producer_id": safe_pid, "first_name": "Koffi", "last_name": safe.split()[0],
        "date_of_birth": yrs_ago(9), "gender": "M",
        "school_status": "enrolled", "school_name": "EPP du village",
        "is_working_on_farm": False, "work_frequency": "never",
    }, "children")
    if c2 and c2.get("id"):
        post(f"/children/{c2['id']}/calculate-risk", {}, "child_risk_calc")

    # ── Opérations CacaoGuard : monitoring, remédiation, formation, blocage ──
    post("/monitoring/visits", {
        "producer_id": risky_pid, "scheduled_date": today.isoformat(),
        "visit_type": "follow_up", "priority": "high",
        "observations": "Visite de suivi du cas de travail d'enfant.",
    }, "monitoring_visits")
    if at_risk_child:
        post("/remediation/plans", {
            "child_id": at_risk_child, "priority": "high",
            "main_objective": "Retour à l'école et arrêt du travail dangereux",
            "planned_actions": [{"action": "Réinscription scolaire", "responsable": "Assistant social"}],
            "expected_completion_date": (today + timedelta(days=90)).isoformat(),
        }, "remediation_plans")
    post("/training/sessions", {
        "title": "Sensibilisation à la protection de l'enfance",
        "training_type": "child_protection", "scheduled_date": today.isoformat(),
        "location": "Soubré", "village": "Soubré",
        "trainer_organization": "ICI", "expected_participants": 25,
        "topics_covered": ["Travail des enfants", "Importance de la scolarisation"],
    }, "training_sessions")
    post("/compliance/blocks", {
        "producer_id": risky_pid, "block_reason": "child_labor_case",
        "block_description": "Cas de travail d'enfant en cours d'investigation — traçabilité suspendue.",
        "expected_resolution_date": (today + timedelta(days=60)).isoformat(),
    }, "traceability_blocks")

    # ── SSRTE : profil communauté, ménages, visites de plantation ──
    post("/ssrte/communities", {
        "locality": "Soubré", "section": "Soubré-Centre", "sub_prefecture": "Soubré",
        "respondent_name": "Notable du village", "respondent_role": "Chef de communauté",
    }, "ssrte_communities")
    for owner in (risky, safe):
        post("/ssrte/households", {
            "producer_id": pmap[owner], "locality": "Soubré",
            "interviewer_name": "Agent SSRTE Démo",
        }, "ssrte_households")
    for pl in plants[:2]:
        post("/ssrte/plantation-visits", {
            "plantation_id": pl["id"], "producer_id": pl.get("producer_id"),
            "interviewer_name": "Agent SSRTE Démo", "locality": pl.get("region"),
        }, "ssrte_visits")

    # ── Certification : audit interne complété + non-conformité ──
    audit = post("/certification-audits", {
        "audit_type": "internal", "auditor_name": "Auditeur Démo",
        "auditor_body": "Ecocert", "scope": "Rainforest Alliance 2020",
        "notes": "Audit interne annuel de la coopérative.",
    }, "certification_audits")
    if audit and audit.get("id"):
        post(f"/certification-audits/{audit['id']}/complete",
             {"result": "pass", "score_pct": 87}, "audits_completed")
        post("/non-conformities", {
            "audit_id": audit["id"], "severity": "minor",
            "description": "Fiches de présence aux formations incomplètes pour 2 sections.",
            "corrective_action": "Compléter les registres sous 30 jours.",
            "responsible": "Responsable conformité",
        }, "non_conformities")

    # ── Revenu vital (FarmForce) : un ménage SOUS le seuil (risky) + un AU-DESSUS (safe) ──
    # net = revenus − coûts − dépenses ménage. Seuil par défaut = 2 360 000 FCFA.
    post("/farmforce/assessments", {
        "producer_id": risky_pid, "campaign_label": "2025-2026", "localite": "Soubré",
        "revenue_items": [{"label": "Vente cacao", "revenue_cfa": 1800000}],
        "cost_items": [{"label": "Intrants + main-d'œuvre", "cost_cfa": 600000}],
        "household_expense_items": [{"label": "Alimentation/éducation/santé", "amount_cfa": 500000}],
        "notes": "Revenu net sous le seuil vital — accompagnement requis.",
    }, "farmforce")   # net = 700 000 → « écart »
    post("/farmforce/assessments", {
        "producer_id": safe_pid, "campaign_label": "2025-2026", "localite": "Méagui",
        "revenue_items": [{"label": "Vente cacao", "revenue_cfa": 4500000}],
        "cost_items": [{"label": "Intrants + main-d'œuvre", "cost_cfa": 1000000}],
        "household_expense_items": [{"label": "Alimentation/éducation/santé", "amount_cfa": 600000}],
        "notes": "Revenu net au-dessus du seuil vital.",
    }, "farmforce")   # net = 2 900 000 → « atteint »

    print(f"  • Protection enfant : cas à risque ({risky}) + cas sain ({safe})")
    print(f"  • Revenu vital : 1 ménage en écart + 1 atteint · SSRTE + Certification + blocage ({risky})")


def seed_certifications():
    """Affecte des certifications aux parcelles (alimente le filtre certification).

    Idempotent : repasse sur les parcelles EXISTANTES (peu importe qu'elles
    viennent d'être créées ou non) et n'ajoute pas de lien en double.
    """
    profile_by_owner = {f[0]: f[5] for f in FARMERS}  # owner_name -> profil
    cert_map = {"full": ["FT", "RA"], "low_yield": ["RA"], "no_boundary": ["FT"]}
    n = 0
    for pl in _plantations():
        for code in cert_map.get(profile_by_owner.get(pl.get("owner_name")), []):
            if post(f"/plantations/{pl['id']}/certifications", {"code": code}, "plantation_certifications"):
                n += 1
    print(f"  • Certifications affectées aux parcelles : {n} lien(s) FT/RA")


def main():
    social_only = os.getenv("AVP_SEED_SOCIAL_ONLY", "").lower() in ("1", "true", "yes")
    certs_only = os.getenv("AVP_SEED_CERTS_ONLY", "").lower() in ("1", "true", "yes")
    print(f"=== Seed démo AgriVision Pro → {API} ===")
    login_or_register()

    if certs_only:
        print("Mode : certifications uniquement (coop existante, idempotent).")
        seed_certifications()
        print(f"\n✓ Certifications affectées. Connexion : {EMAIL} / {PASSWORD}")
        return

    if social_only:
        print("Mode : social / conformité uniquement (coop existante, pas de duplication).")
        seed_social_compliance()
        print("\n=== Résumé du seed ===")
        for k in sorted(_count):
            print(f"  {k:18}: {_count[k]}")
        print(f"\n✓ Données sociales/conformité ajoutées. Connexion : {EMAIL} / {PASSWORD}")
        return

    harvest_ids = []
    # Idempotence : si une parcelle du même nom existe déjà (run antérieur),
    # on la réutilise au lieu de la dupliquer.
    existing_pl = {pl.get("name"): pl["id"] for pl in _plantations() if pl.get("id")}
    for name, region, lat, lon, ha, profile in FARMERS:
        pl_name = f"Parcelle {name.split()[0]} {region}"
        if pl_name in existing_pl:
            pid = existing_pl[pl_name]
            # On récupère une récolte 2025-2026 pour l'étape lots, sans rien recréer.
            try:
                hvs = client.get(f"{API}/plantations/{pid}/harvests", headers=h()).json()
                for hv in (hvs if isinstance(hvs, list) else []):
                    if hv.get("season") == "2025-2026" and hv.get("id"):
                        harvest_ids.append(hv["id"]); break
            except Exception:
                pass
            print(f"  • {name} ({region}) — déjà présent, ignoré (pas de doublon)")
            continue
        p = post("/plantations", {
            "name": pl_name, "owner_name": name,
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

    # Certifications des parcelles (alimente le filtre certification)
    seed_certifications()

    # Données sociales / conformité (CacaoGuard, SSRTE, Certification)
    seed_social_compliance()

    print("\n=== Résumé du seed ===")
    for k in sorted(_count):
        print(f"  {k:18}: {_count[k]}")
    print(f"\n✓ Démo prête. Connexion : {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    main()
