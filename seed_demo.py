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

Démo "passage à l'échelle" (parcelles en masse, sans délimitation) — pour le moment
"Générer les délimitations manquantes" de la vidéo :
    AVP_DEMO_XL_PARCELS=300 python seed_demo.py        # 300 parcelles XL en fin de seed complet
    AVP_SEED_XL_ONLY=1 AVP_DEMO_XL_PARCELS=300 python seed_demo.py   # XL seul, coop existante
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
# Parcelles « XL » supplémentaires (avec GPS + superficie, SANS délimitation) pour la démo
# « passage à l'échelle » et le moment « Générer les délimitations manquantes ».
# 0 = désactivé → le seed standard (8 parcelles) est inchangé.
XL_PARCELS = int(os.getenv("AVP_DEMO_XL_PARCELS", "0") or 0)

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


def seed_ssrte(pmap, plants):
    """Fiches SSRTE A/B/C RENSEIGNÉES (réutilisable ; AVP_SEED_SSRTE_ONLY=1)."""
    if not pmap:
        print("   ⚠ Aucun producteur — lancez d'abord le seed principal.")
        return
    names = list(pmap)
    risky = "Kouassi Yao" if "Kouassi Yao" in pmap else names[0]
    safe = "Konan Aka" if "Konan Aka" in pmap else (names[1] if len(names) > 1 else names[0])
    risky_pid, safe_pid = pmap[risky], pmap[safe]
    # ── SSRTE : fiches A / B / C INTÉGRALEMENT RENSEIGNÉES ──────────────────────
    # Objectif : des fiches « spécimen » complètes (tous les champs), exportables en
    # PDF pour démontrer la couverture des sections SSRTE. Données 100 % FICTIVES.
    SPEC = "SPÉCIMEN — données fictives à des fins de démonstration (aucune personne réelle)."
    AGENT, AGENT_CODE = "Agent SSRTE Démo", "AG-014"
    COOP = "Coopérative Démo Cacao 2026"
    today_s = date.today().isoformat()

    def sig(name, role):
        return {"signed_by": name, "role": role, "signed_at": datetime.utcnow().isoformat(),
                "method": "typed_name", "device_id": "demo-tablette-01"}

    # Fiche A — profil de la LOCALITÉ (A.01 → A.20).
    post("/ssrte/communities", {
        "locality": "Gnamangui", "section": "Méagui-Centre", "sub_prefecture": "Méagui",
        "supplier": COOP, "interview_date": today_s,
        "respondent_name": "Kouadio N'Dri", "respondent_role": "Chef de communauté",
        "collection_agent_name": AGENT, "collection_agent_code": AGENT_CODE,
        "gps_start": "5.621500,-6.780100", "time_start": "08:15",
        "gps_end": "5.621700,-6.780400", "time_end": "10:05",
        "school_available": True,
        "nearest_school_distance_km": 4,
        "has_child_protection_committee": True,
        "services_available": {
            "electricite": True, "electricity_origin": "réseau national (CIE)",
            "eau_potable": False, "water_distance": "1,2 km (forage villageois)",
            "centre_sante": True, "transport": False, "marche": True,
            "secondary_classes_count": 0, "secondary_school_distance_km": 18,
            "org_state": "Direction régionale de l'Éducation",
            "org_ngo": "ONG locale de protection de l'enfance",
            "org_other": "Comité villageois de veille",
        },
        "schools": [
            {"nom": "EPP Gnamangui", "niveau": "primaire", "distance_km": 4, "cantine": False,
             "effectif": 240, "enseignants": 6},
            {"nom": "Collège de Méagui", "niveau": "secondaire", "distance_km": 18, "cantine": True,
             "effectif": 900, "enseignants": 28},
        ],
        "committee_members": [
            {"name": "Kouadio N'Dri", "role": "Président du comité de protection", "contact": "07 00 00 00 01"},
            {"name": "Aya Traoré", "role": "Enseignante / point focal enfants", "contact": "07 00 00 00 02"},
            {"name": "Yao Brou", "role": "Représentant des jeunes", "contact": "07 00 00 00 03"},
        ],
        "risks_identified": ["déscolarisation", "travail des enfants en récolte",
                              "éloignement du collège", "absence d'état civil pour certains enfants"],
        "section_notes": {
            "services": "Pas de classes secondaires sur place ; le collège le plus proche est à 18 km.",
            "protection": "Comité de protection actif, réunions mensuelles.",
            "general": "L'éloignement du collège est le principal facteur de déscolarisation.",
        },
        "notes": SPEC,
    }, "ssrte_communities")

    # Fiche B — profil du MÉNAGE (B.01 → B.29) : cas À RISQUE, entièrement renseigné.
    post("/ssrte/households", {
        "producer_id": risky_pid, "interview_date": today_s, "interviewer_name": AGENT,
        "supplier": COOP, "sub_prefecture": "Méagui", "locality": "Gnamangui",
        "collection_agent_code": AGENT_CODE, "producer_ssrte_code": "SSRTE-PR-0148",
        "gps_start": "5.621900,-6.779800", "time_start": "10:20", "time_end": "11:35",
        "survey_type": "complet", "producer_available": True, "unavailable_reason": None,
        "visited_person_status": "chef de ménage",
        "household_size": 7, "children_count": 4,
        "school_age_children_count": 3, "enrolled_children_count": 1,
        "household_members": [
            {"nom": "Kouassi Yao", "relation": "chef de ménage", "sexe": "M", "age": 44,
             "scolarise": False, "travaille": True, "activite": "cacaoculteur"},
            {"nom": "Affoué Kouassi", "relation": "épouse", "sexe": "F", "age": 38,
             "scolarise": False, "travaille": True, "activite": "vivrier / commerce"},
            {"nom": "Awa Kouassi", "relation": "fille", "sexe": "F", "age": 14,
             "scolarise": False, "travaille": True, "activite": "travaux de plantation"},
            {"nom": "Yao Kouassi", "relation": "fils", "sexe": "M", "age": 8,
             "scolarise": True, "travaille": False, "activite": "élève (CE1)"},
            {"nom": "Akissi Kouassi", "relation": "fille", "sexe": "F", "age": 5,
             "scolarise": False, "travaille": False, "activite": "non scolarisable"},
        ],
        "child_work_declarations": [
            {"enfant": "Awa Kouassi", "age": 14, "tache": "usage de machette",
             "frequence": "régulière", "moment": "après-midi et week-end", "remuneree": False},
        ],
        "vulnerabilities": ["revenu sous le seuil vital", "déscolarisation d'un enfant",
                             "éloignement de l'école secondaire"],
        "school_constraints": ["éloignement du collège", "coût de la scolarité",
                                "besoin de main-d'œuvre familiale"],
        "farm_info": {"parcelles": 2, "superficie_ha": 4.5, "production_kg_an": 1800,
                       "culture_principale": "cacao", "cultures_secondaires": ["vivrier", "banane plantain"]},
        "housing_type": "traditionnel",
        "household_assets": ["moto", "télévision", "téléphone portable"],
        "external_workers_count": 2, "daily_workers_count": 1,
        "non_daily_workers": [
            {"nom": "Traoré Sidiki", "origine": "hors localité", "type": "saisonnier",
             "duree": "campagne", "remuneration": "à la tâche"},
        ],
        "allow_worker_interview": True,
        "section_notes": {
            "menage": "Un enfant de 14 ans déscolarisé, déclaré participant aux travaux.",
            "exploitation": "2 parcelles, 4,5 ha, production 1 800 kg/an.",
            "economie": "Revenu net estimé sous le seuil de revenu vital.",
        },
        "consent_given": True,
        "signature_data": sig("Kouassi Yao", "chef de ménage"),
        "notes": SPEC,
    }, "ssrte_households")

    # Fiche B — cas SAIN (contrôle), également renseigné.
    post("/ssrte/households", {
        "producer_id": safe_pid, "interview_date": today_s, "interviewer_name": AGENT,
        "supplier": COOP, "sub_prefecture": "Méagui", "locality": "Méagui",
        "collection_agent_code": AGENT_CODE, "producer_ssrte_code": "SSRTE-PR-0152",
        "gps_start": "5.615200,-6.771300", "time_start": "13:40", "time_end": "14:35",
        "survey_type": "complet", "producer_available": True, "visited_person_status": "chef de ménage",
        "household_size": 5, "children_count": 3,
        "school_age_children_count": 2, "enrolled_children_count": 2,
        "household_members": [
            {"nom": "Konan Aka", "relation": "chef de ménage", "sexe": "M", "age": 39,
             "scolarise": False, "travaille": True, "activite": "cacaoculteur"},
            {"nom": "Adjoua Konan", "relation": "fille", "sexe": "F", "age": 10,
             "scolarise": True, "travaille": False, "activite": "élève (CM1)"},
            {"nom": "Kouamé Konan", "relation": "fils", "sexe": "M", "age": 7,
             "scolarise": True, "travaille": False, "activite": "élève (CP2)"},
        ],
        "child_work_declarations": [],
        "vulnerabilities": [],
        "school_constraints": [],
        "farm_info": {"parcelles": 3, "superficie_ha": 6.0, "production_kg_an": 3200,
                       "culture_principale": "cacao", "cultures_secondaires": ["hévéa"]},
        "housing_type": "en dur",
        "household_assets": ["moto", "réfrigérateur", "téléphone portable", "télévision"],
        "external_workers_count": 3, "daily_workers_count": 2,
        "non_daily_workers": [],
        "allow_worker_interview": True,
        "section_notes": {"menage": "Tous les enfants en âge scolaire sont scolarisés.",
                           "economie": "Revenu net au-dessus du seuil de revenu vital."},
        "consent_given": True,
        "signature_data": sig("Konan Aka", "chef de ménage"),
        "notes": SPEC,
    }, "ssrte_households")

    # Fiche C — VISITE de plantation (C.01 → C.12) : cas avec SUSPICION, complet.
    if plants:
        risky_plant = next((p for p in plants if p.get("producer_id") == risky_pid), plants[0])
        post("/ssrte/plantation-visits", {
            "plantation_id": risky_plant["id"], "producer_id": risky_pid,
            "visit_date": today_s, "interviewer_name": AGENT,
            "supplier": COOP, "section": "Méagui-Centre", "sub_prefecture": "Méagui",
            "locality": risky_plant.get("region") or "Gnamangui",
            "collection_agent_code": AGENT_CODE, "producer_ssrte_code": "SSRTE-PR-0148",
            "gps_location": "5.622400,-6.781900", "gps_accuracy": 6.0,
            "captured_latitude": 5.6224, "captured_longitude": -6.7819, "captured_accuracy_m": 6.0,
            "client_reported_at": datetime.utcnow().isoformat(),
            "time_start": "15:05", "time_end": "16:10",
            "adults_count": 2, "daily_workers_count": 1, "allow_worker_interview": True,
            "children_present_count": 1, "non_household_children_count": 0, "non_household_children": [],
            "children_observed": [
                {"prenom": "Awa", "age": 14, "sexe": "F", "lien": "fille du producteur",
                 "tache": "usage de machette", "scolarise": False, "equipement_protection": False},
            ],
            "adults_observed": [
                {"nom": "Kouassi Yao", "role": "producteur", "age": 44},
                {"nom": "Affoué Kouassi", "role": "conjointe", "age": 38},
            ],
            "workers_present": [
                {"nom": "Traoré Sidiki", "type": "journalier", "origine": "hors localité", "age": 27},
            ],
            "dangerous_tasks_observed": ["usage de machette", "port de charges lourdes"],
            "suspected_child_labor": True,
            "immediate_actions_taken": ("Retrait immédiat de l'enfant de la tâche dangereuse ; "
                                         "sensibilisation du chef de ménage ; ouverture d'un plan de remédiation "
                                         "et signalement au comité de protection."),
            "checklist_data": {"equipement_protection": False, "eau_potable_sur_site": False,
                                "trousse_premiers_secours": False, "pesticides_stockes_securise": False,
                                "panneau_interdiction_enfants": False},
            "section_notes": {"observations": "Enfant de 14 ans observé maniant une machette.",
                               "suites": "Cas transmis à la remédiation ; blocage de traçabilité déclenché."},
            "photos": [],
            "consent_given": True,
            "producer_signature_data": sig("Kouassi Yao", "producteur"),
            "assessor_signature_data": sig(AGENT, "agent SSRTE"),
            "notes": SPEC,
        }, "ssrte_visits")

    # Fiche C — cas CONFORME (contrôle).
    if len(plants) > 1:
        safe_plant = next((p for p in plants if p.get("producer_id") == safe_pid), plants[1])
        post("/ssrte/plantation-visits", {
            "plantation_id": safe_plant["id"], "producer_id": safe_pid,
            "visit_date": today_s, "interviewer_name": AGENT,
            "supplier": COOP, "section": "Méagui-Centre", "sub_prefecture": "Méagui",
            "locality": safe_plant.get("region") or "Méagui",
            "collection_agent_code": AGENT_CODE, "producer_ssrte_code": "SSRTE-PR-0152",
            "gps_location": "5.615900,-6.772400", "gps_accuracy": 5.0,
            "captured_latitude": 5.6159, "captured_longitude": -6.7724, "captured_accuracy_m": 5.0,
            "client_reported_at": datetime.utcnow().isoformat(),
            "time_start": "16:40", "time_end": "17:30",
            "adults_count": 3, "daily_workers_count": 2, "allow_worker_interview": True,
            "children_present_count": 0, "non_household_children_count": 0, "non_household_children": [],
            "children_observed": [], "adults_observed": [{"nom": "Konan Aka", "role": "producteur", "age": 39}],
            "workers_present": [{"nom": "Koffi Bini", "type": "journalier", "origine": "localité", "age": 31}],
            "dangerous_tasks_observed": [], "suspected_child_labor": False,
            "immediate_actions_taken": "Aucune action requise — situation conforme.",
            "checklist_data": {"equipement_protection": True, "eau_potable_sur_site": True,
                                "trousse_premiers_secours": True, "pesticides_stockes_securise": True,
                                "panneau_interdiction_enfants": True},
            "section_notes": {"observations": "Aucun enfant présent ; équipements de protection disponibles."},
            "photos": [],
            "consent_given": True,
            "producer_signature_data": sig("Konan Aka", "producteur"),
            "assessor_signature_data": sig(AGENT, "agent SSRTE"),
            "notes": SPEC,
        }, "ssrte_visits")



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

    seed_ssrte(pmap, plants)

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

    # ── Revenu vital (FarmForce) — ANTI-DOUBLON : un seul bilan par producteur/campagne.
    # net = revenus − coûts − dépenses ménage. Seuil par défaut = 2 360 000 FCFA.
    _ff_seen = set()   # (producer_id, campaign) déjà évalués (existants + créés ici)
    try:
        for a in (client.get(f"{API}/farmforce/assessments", headers=h()).json() or []):
            _ff_seen.add((a.get("producer_id"), a.get("campaign_label")))
    except Exception:
        pass

    def ff_once(producer_id, payload):
        key = (producer_id, payload.get("campaign_label"))
        if producer_id is None or key in _ff_seen:
            return
        payload["producer_id"] = producer_id
        post("/farmforce/assessments", payload, "farmforce")
        _ff_seen.add(key)

    ff_once(risky_pid, {
        "campaign_label": "2025-2026", "localite": "Gnamangui",
        "revenue_items": [{"label": "Vente cacao", "revenue_cfa": 1800000}],
        "cost_items": [{"label": "Intrants + main-d'œuvre", "cost_cfa": 600000}],
        "household_expense_items": [{"label": "Alimentation/éducation/santé", "amount_cfa": 500000}],
        "notes": "Revenu net sous le seuil vital — accompagnement requis.",
    })   # net = 700 000 → « écart »
    ff_once(safe_pid, {
        "campaign_label": "2025-2026", "localite": "Méagui",
        "revenue_items": [{"label": "Vente cacao", "revenue_cfa": 4500000}],
        "cost_items": [{"label": "Intrants + main-d'œuvre", "cost_cfa": 1000000}],
        "household_expense_items": [{"label": "Alimentation/éducation/santé", "amount_cfa": 600000}],
        "notes": "Revenu net au-dessus du seuil vital.",
    })   # net = 2 900 000 → « atteint »

    # ── VOLUME DÉMO ICI : population d'enfants sur TOUS les niveaux de risque ──
    # Pour que la « Distribution risque enfant » et le rapport de due diligence
    # soient réalistes (pas 2 enfants). Répartis sur les producteurs existants.
    child_profiles = [
        # (prénom, âge, sexe, scolarité, travaille, fréquence, tâches dangereuses)
        ("Awa", 15, "F", "dropped_out", True, "regular", ["usage de machette", "épandage de pesticides"]),   # critique/élevé
        ("Sékou", 14, "M", "dropped_out", True, "regular", ["port de charges lourdes"]),                        # élevé
        ("Fatou", 12, "F", "enrolled", True, "occasional", ["port de charges lourdes"]),                         # moyen
        ("Ibrahim", 13, "M", "never_enrolled", True, "occasional", []),                                          # moyen/élevé
        ("Mariam", 10, "F", "enrolled", True, "occasional", []),                                                 # faible/moyen
        ("Yaya", 11, "M", "enrolled", False, "never", []),                                                       # faible
        ("Aïcha", 8, "F", "enrolled", False, "never", []),                                                       # aucun/faible
        ("Moussa", 9, "M", "enrolled", False, "never", []),                                                      # aucun
        ("Salif", 16, "M", "dropped_out", True, "regular", ["usage de machette"]),                              # élevé
        ("Rokia", 13, "F", "enrolled", True, "occasional", ["épandage de pesticides"]),                          # moyen/élevé
    ]
    extra_children = 0
    for i, (fn, age, sex, school, working, freq, tasks) in enumerate(child_profiles):
        owner = names[i % len(names)]
        payload = {
            "producer_id": pmap[owner], "first_name": fn, "last_name": owner.split()[0],
            "date_of_birth": yrs_ago(age), "gender": sex,
            "school_status": school, "is_working_on_farm": working, "work_frequency": freq,
        }
        if school == "enrolled":
            payload["school_name"] = "EPP du village"
        if tasks:
            payload["dangerous_tasks_performed"] = tasks
        cc = post("/children", payload, "children")
        if cc and cc.get("id"):
            post(f"/children/{cc['id']}/calculate-risk", {}, "child_risk_calc")
            extra_children += 1

    # ── Signalements (griefs) : un cas grave (crée une alerte) + un cas moyen ──
    post("/complaints", {
        "complaint_type": "child_labor", "severity": "high",
        "description": "Signalement d'un enfant aperçu à la machette sur une parcelle, par un agent de terrain.",
        "producer_id": risky_pid, "source": "field_agent",
    }, "complaints")
    post("/complaints", {
        "complaint_type": "other", "severity": "medium",
        "description": "Conditions de travail à vérifier lors de la prochaine visite de suivi.",
        "producer_id": safe_pid, "source": "anonymous",
    }, "complaints")

    # ── Visites de monitoring supplémentaires (planifiées) ──
    for i, owner in enumerate(names[:4]):
        post("/monitoring/visits", {
            "producer_id": pmap[owner],
            "scheduled_date": (today + timedelta(days=7 * (i + 1))).isoformat(),
            "visit_type": "routine", "priority": "medium",
            "observations": "Visite de suivi planifiée (tournée de sensibilisation).",
        }, "monitoring_visits")

    # ── Sessions de formation supplémentaires (types variés) ──
    for title, ttype in [
        ("Bonnes pratiques agroforestières", "economic_empowerment"),
        ("Sécurité d'usage des pesticides", "other"),
        ("Scolarisation et retrait du travail dangereux", "child_protection"),
    ]:
        post("/training/sessions", {
            "title": title, "training_type": ttype,
            "scheduled_date": today.isoformat(), "location": "Méagui", "village": "Méagui",
            "trainer_organization": "ICI", "expected_participants": 20,
            "topics_covered": [title],
        }, "training_sessions")

    # ── Revenu vital : d'autres ménages (mélange réaliste) — sur des producteurs
    # DISTINCTS (jamais risky/safe) et jamais déjà évalués (anti-doublon via ff_once).
    li_mix = [
        (2200000, 700000, 500000),   # net 1 000 000 → écart
        (5200000, 1100000, 700000),  # net 3 400 000 → atteint
        (2600000, 800000, 500000),   # net 1 300 000 → écart
        (4800000, 900000, 600000),   # net 3 300 000 → atteint
        (3600000, 800000, 500000),   # net 2 300 000 → écart (proche du seuil)
    ]
    li_candidates = [n for n in names if n not in (risky, safe)]
    for (rev, cost, hh), owner in zip(li_mix, li_candidates):
        ff_once(pmap[owner], {
            "campaign_label": "2025-2026",
            "localite": "Méagui",
            "revenue_items": [{"label": "Vente cacao", "revenue_cfa": rev}],
            "cost_items": [{"label": "Intrants + main-d'œuvre", "cost_cfa": cost}],
            "household_expense_items": [{"label": "Alimentation/éducation/santé", "amount_cfa": hh}],
        })

    print(f"  • Protection enfant : {2 + extra_children} enfants sur tous les niveaux de risque")
    print(f"  • Revenu vital : 7 ménages (mix atteint/écart) · SSRTE + Certification + blocage ({risky})")
    print(f"  • Signalements, visites planifiées et formations supplémentaires ajoutés")


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


# ── Démo « passage à l'échelle » : parcelles en masse, sans délimitation ──────
# Régions cacao (centroïdes) pour disperser les parcelles XL de façon plausible.
XL_REGIONS = [
    ("Soubré", 5.78, -6.59), ("Méagui", 5.62, -6.78), ("San-Pédro", 4.95, -6.55),
    ("Gagnoa", 6.05, -5.95), ("Daloa", 6.88, -6.45), ("Divo", 5.84, -5.36),
    ("Issia", 6.49, -6.59),
]
XL_PRENOMS = ["Kouassi", "Konan", "Yao", "Koffi", "Adjoua", "Akissi", "Aya", "Affoué",
              "Brou", "Amani", "N'Guessan", "Tanoh", "Diby", "Aké", "Kouamé", "Kouadio",
              "Kouakou", "Assé", "Aboa", "Gnagne", "Tapé", "Djaha", "Bla", "Séri"]
XL_NOMS = ["Yao", "Koffi", "Konan", "Kouassi", "Aka", "Adjoua", "N'Dri", "Gnamien",
           "Kouadio", "Assi", "Brou", "Diby", "Tanoh", "Amani", "Akissi", "Béh"]


def seed_xl_parcels(n: int):
    """Crée `n` parcelles supplémentaires (GPS + superficie, SANS délimitation).

    But : montrer le « passage à l'échelle » (liste paginée qui tient) et surtout
    donner un gros compteur « à délimiter » qui tombe à 0 en un clic via le bouton
    « Générer les délimitations manquantes » (démo vidéo). Léger (ni diagnostic ni
    récolte) et idempotent : réutilise les noms déjà créés (relançable sans doublon).
    """
    existing = {pl.get("name") for pl in _plantations() if pl.get("name")}
    created = 0
    for i in range(n):
        region, clat, clon = XL_REGIONS[i % len(XL_REGIONS)]
        pl_name = f"Parcelle XL {i + 1:04d} {region}"
        if pl_name in existing:
            continue
        # GPS dispersé autour du centroïde régional (~ ±0.15°, reste dans la zone cacao).
        lat = round(clat + ((i * 37) % 100 - 50) / 333.0, 6)
        lon = round(clon + ((i * 53) % 100 - 50) / 333.0, 6)
        ha = round(0.5 + ((i * 7) % 45) / 10.0, 2)   # ~0.5 → ~5 ha
        owner = f"{XL_PRENOMS[i % len(XL_PRENOMS)]} {XL_NOMS[(i // 3) % len(XL_NOMS)]}"
        # PAS d'appel /boundary → la parcelle apparaît « à délimiter » (cible du bouton de masse).
        post("/plantations", {
            "name": pl_name, "owner_name": owner,
            "country": "Côte d'Ivoire", "region": region, "hectares": ha,
            "latitude": lat, "longitude": lon,
        }, "plantations_xl")
        created += 1
        if created % 50 == 0:
            print(f"   … {created}/{n} parcelles XL créées")
    print(f"  • {created} parcelle(s) XL créée(s) — sans délimitation (à générer en masse)")


def cleanup_demo(apply: bool = False):
    """Nettoie la coop : 1 seul livret revenu vital par (producteur, campagne) — le
    1er non vide — et supprime les fiches SSRTE VIDES (anciens passages). Ne touche
    JAMAIS aux fiches finalisées. En dry-run (apply=False) : n'affiche que le compte."""
    from collections import defaultdict
    tag = "APPLIQUÉ" if apply else "SIMULATION (dry-run)"
    print(f"— Nettoyage démo : {tag} —")

    def _del(ep, rid):
        if not apply:
            return True
        r = client.delete(f"{API}{ep}/{rid}", headers=h())
        return r.status_code in (200, 204)

    # FarmForce : garder le 1er livret NON VIDE par (producteur, campagne).
    try:
        assessments = client.get(f"{API}/farmforce/assessments", headers=h()).json() or []
    except Exception:
        assessments = []
    groups = defaultdict(list)
    for a in assessments:
        groups[(a.get("producer_id"), a.get("campaign_label"))].append(a)
    keep = set()
    for lst in groups.values():
        nonzero = [a for a in lst if float(a.get("net_income_cfa") or 0) > 0]
        if nonzero:
            keep.add(min(nonzero, key=lambda a: a["id"])["id"])
    ff_del = [a for a in assessments if a["id"] not in keep]
    for a in ff_del:
        _del("/farmforce/assessments", a["id"])

    # SSRTE : supprimer les fiches VIDES (draft) — celles sans contenu réel.
    ssrte_del = 0
    for d in (client.get(f"{API}/ssrte/communities", headers=h()).json() or []):
        if d.get("status") == "draft" and not d.get("risks_identified") and not d.get("services_available"):
            if _del("/ssrte/communities", d["id"]):
                ssrte_del += 1
    for d in (client.get(f"{API}/ssrte/households", headers=h()).json() or []):
        if d.get("status") == "draft" and d.get("household_size") in (None, 0):
            if _del("/ssrte/households", d["id"]):
                ssrte_del += 1
    for d in (client.get(f"{API}/ssrte/plantation-visits", headers=h()).json() or []):
        if d.get("status") == "draft" and d.get("adults_count") is None and not d.get("dangerous_tasks_observed"):
            if _del("/ssrte/plantation-visits", d["id"]):
                ssrte_del += 1

    print(f"  • Revenu vital : {len(ff_del)} livret(s) en doublon/vide {'supprimés' if apply else 'à supprimer'}")
    print(f"  • SSRTE : {ssrte_del} fiche(s) vide(s) {'supprimées' if apply else 'à supprimer'}")
    if not apply:
        print("  → Relancez avec AVP_SEED_CLEANUP=apply pour appliquer.")


def main():
    social_only = os.getenv("AVP_SEED_SOCIAL_ONLY", "").lower() in ("1", "true", "yes")
    cleanup_mode = os.getenv("AVP_SEED_CLEANUP", "").lower()
    certs_only = os.getenv("AVP_SEED_CERTS_ONLY", "").lower() in ("1", "true", "yes")
    xl_only = os.getenv("AVP_SEED_XL_ONLY", "").lower() in ("1", "true", "yes")
    ssrte_only = os.getenv("AVP_SEED_SSRTE_ONLY", "").lower() in ("1", "true", "yes")
    print(f"=== Seed démo AgriVision Pro → {API} ===")
    login_or_register()

    if cleanup_mode in ("1", "true", "yes", "dry", "apply"):
        cleanup_demo(apply=(cleanup_mode == "apply"))
        print(f"\n✓ Nettoyage terminé. Connexion : {EMAIL} / {PASSWORD}")
        return

    if ssrte_only:
        print("Mode : fiches SSRTE A/B/C uniquement (coop existante, sans duplication du reste).")
        seed_ssrte(_producer_map(), _plantations())
        print("\n=== Résumé du seed ===")
        for k in sorted(_count):
            print(f"  {k:18}: {_count[k]}")
        print(f"\n✓ Fiches SSRTE ajoutées. Connexion : {EMAIL} / {PASSWORD}")
        return

    if certs_only:
        print("Mode : certifications uniquement (coop existante, idempotent).")
        seed_certifications()
        print(f"\n✓ Certifications affectées. Connexion : {EMAIL} / {PASSWORD}")
        return

    if xl_only:
        n = XL_PARCELS or 300
        print(f"Mode : parcelles XL uniquement ({n}) — coop existante, sans duplication.")
        seed_xl_parcels(n)
        print("\n=== Résumé du seed ===")
        for k in sorted(_count):
            print(f"  {k:18}: {_count[k]}")
        print(f"\n✓ Parcelles XL ajoutées. Connexion : {EMAIL} / {PASSWORD}")
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
