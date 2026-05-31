from app.db.models import Cooperative, Plantation, Producer, User
from tests.conftest import TestingSessionLocal


def _seed_producer_and_plantation():
    db = TestingSessionLocal()
    try:
        coop = Cooperative(name="Coop SSRTE", country="CI")
        producer = Producer(
            cooperative=coop,
            nom_complet="Kouadio SSRTE",
            code_yeyasso="SSRTE-001",
            localite="Yeyasso",
            section="Section A",
            is_active=True,
        )
        plantation = Plantation(
            name="Parcelle SSRTE",
            owner_name="Kouadio SSRTE",
            country="Cote d'Ivoire",
            region="Yeyasso",
            hectares=3.2,
            cooperative=coop,
            producer=producer,
        )
        user = User(
            email="ssrte.admin@test.ci",
            password_hash="x",
            role="admin",
            cooperative=coop,
            is_active=True,
        )
        db.add_all([coop, producer, plantation, user])
        db.commit()
        return producer.id, plantation.id
    finally:
        db.close()


def test_ssrte_community_profile_can_be_created(client):
    response = client.post("/ssrte/communities", json={
        "locality": "Yeyasso",
        "section": "Section A",
        "interview_date": "2026-05-26",
        "respondent_name": "Chef village",
        "respondent_role": "Leader communautaire",
        "school_available": True,
        "nearest_school_distance_km": 1.5,
        "has_child_protection_committee": True,
        "risks_identified": ["descolarisation", "travaux dangereux"],
    })

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["locality"] == "Yeyasso"
    assert data["school_available"] is True


def test_ssrte_household_profile_scores_risk(client):
    producer_id, _ = _seed_producer_and_plantation()

    response = client.post("/ssrte/households", json={
        "producer_id": producer_id,
        "interview_date": "2026-05-26",
        "household_size": 8,
        "children_count": 4,
        "school_age_children_count": 3,
        "enrolled_children_count": 1,
        "vulnerabilities": ["revenu faible", "maladie"],
        "child_work_declarations": [
            {"child": "A", "task": "machette", "dangerous": True},
            {"child": "B", "task": "ramassage cabosses"},
        ],
        "school_constraints": ["distance", "frais scolaires"],
        "consent_given": True,
    })

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["producer_id"] == producer_id
    assert data["risk_score"] >= 60
    assert data["risk_level"] in {"high", "critical"}


def test_ssrte_ficheb_pdf_download(client):
    producer_id, _ = _seed_producer_and_plantation()
    created = client.post("/ssrte/households", json={
        "producer_id": producer_id,
        "household_size": 3,
        "household_members": [
            {"name": "Yao Chef", "relation": "Chef de menage", "sex": "M", "birth_year": 1980},
        ],
        "consent_given": True,
    }).json()
    r = client.get(f"/ssrte/households/{created['id']}/ficheb.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert "FicheB_" in r.headers.get("content-disposition", "")


def test_ssrte_ficheb_pdf_not_found(client):
    r = client.get("/ssrte/households/99999/ficheb.pdf")
    assert r.status_code == 404


def test_ssrte_fichea_services_and_pdf(client):
    """La Fiche A stocke l'acces aux services + comite et s'exporte en PDF."""
    created = client.post("/ssrte/communities", json={
        "locality": "Yapleu",
        "section": "Man",
        "school_available": True,
        "nearest_school_distance_km": 1.5,
        "has_child_protection_committee": True,
        "committee_members": [{"name": "Yao Coordinateur"}],
        "risks_identified": ["descolarisation"],
        "services_available": {
            "population": 1200, "locality_type": "Village",
            "road_access": True, "electricity": False, "water_point": True,
            "health_structure": False, "primary_school": True,
        },
    }).json()
    assert created["services_available"]["population"] == 1200
    assert created["services_available"]["road_access"] is True
    assert created["committee_members"][0]["name"] == "Yao Coordinateur"

    r = client.get(f"/ssrte/communities/{created['id']}/fichea.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert "FicheA_" in r.headers.get("content-disposition", "")


def test_ssrte_fichea_pdf_not_found(client):
    r = client.get("/ssrte/communities/99999/fichea.pdf")
    assert r.status_code == 404


def test_ssrte_fichec_pdf_and_structured_children(client):
    """La Fiche C stocke les enfants structures et s'exporte en PDF."""
    producer_id, plantation_id = _seed_producer_and_plantation()
    created = client.post("/ssrte/plantation-visits", json={
        "plantation_id": plantation_id,
        "producer_id": producer_id,
        "children_observed": [
            {"name": "Koffi Junior", "age": 13, "household_member": False,
             "hazardous_tasks": ["Recolte machette/faucille"]},
        ],
        "dangerous_tasks_observed": ["Recolte machette/faucille"],
        "suspected_child_labor": True,
        "consent_given": True,
    }).json()
    visit_id = created["id"]
    assert len(created["children_observed"]) == 1
    assert created["children_observed"][0]["hazardous_tasks"] == ["Recolte machette/faucille"]

    r = client.get(f"/ssrte/plantation-visits/{visit_id}/fichec.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert "FicheC_" in r.headers.get("content-disposition", "")


def test_ssrte_fichec_pdf_not_found(client):
    r = client.get("/ssrte/plantation-visits/99999/fichec.pdf")
    assert r.status_code == 404


def test_ssrte_household_persists_members(client):
    """Le tableau des membres du menage (Fiche B) est stocke et relu."""
    producer_id, _ = _seed_producer_and_plantation()
    members = [
        {"name": "Yao Chef", "relation": "Chef de menage", "sex": "M",
         "birth_year": 1980, "birth_certificate": "Oui", "occupation": "Producteur (cacao)",
         "school_status": "Non scolarise", "school_level": "Primaire", "present": False,
         "hazardous_tasks": []},
        {"name": "Aya Enfant", "relation": "Fils/fille", "sex": "F",
         "birth_year": 2014, "birth_certificate": "Non", "occupation": "Eleve/Etudiant",
         "school_status": "Scolarise", "school_level": "Primaire", "present": True,
         "hazardous_tasks": ["Recolte machette/faucille", "Port de charges lourdes"]},
    ]
    response = client.post("/ssrte/households", json={
        "producer_id": producer_id,
        "household_size": 2,
        "children_count": 1,
        "school_age_children_count": 1,
        "enrolled_children_count": 1,
        "household_members": members,
        "child_work_declarations": [
            {"child": "Aya Enfant", "task": "Recolte machette/faucille, Port de charges lourdes", "dangerous": True},
        ],
        "consent_given": True,
    })
    assert response.status_code == 201, response.text
    data = response.json()
    assert len(data["household_members"]) == 2
    aya = [m for m in data["household_members"] if m["name"] == "Aya Enfant"][0]
    assert aya["hazardous_tasks"] == ["Recolte machette/faucille", "Port de charges lourdes"]
    # Une tache dangereuse declaree => risque non nul.
    assert data["risk_score"] > 0


def test_ssrte_plantation_visit_creates_alert_on_suspicion(client):
    _, plantation_id = _seed_producer_and_plantation()

    response = client.post("/ssrte/plantation-visits", json={
        "plantation_id": plantation_id,
        "visit_date": "2026-05-26",
        "checklist_data": {"children_observed": True, "tasks_checked": True},
        "children_observed": [{"name": "A", "age": 13, "observation": "present sur parcelle"}],
        "dangerous_tasks_observed": ["machette"],
        "suspected_child_labor": True,
        "consent_given": True,
    })

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["plantation_id"] == plantation_id
    assert data["producer_id"] is not None
    assert data["suspected_child_labor"] is True

    alerts = client.get("/alerts?source_entity=ssrte_plantation_visits")
    assert alerts.status_code == 200
    assert any(a["source_entity"] == "ssrte_plantation_visits" for a in alerts.json())

    compliance = client.get("/compliance/traceability")
    assert compliance.status_code == 200
    blocks = compliance.json()["active_blocks"]
    assert len(blocks) == 1
    assert blocks[0]["block_reason"] == "child_labor_case"
    assert "SSRTE" in blocks[0]["block_description"]


def test_ssrte_fichea_schools_table_persists(client):
    """Le tableau detaille des ecoles (A.22-A.29) est stocke, relu et exporte."""
    schools = [
        {"name": "EPP Yeyasso", "type": "Publique", "built_by": "Etat",
         "classrooms": 6, "teachers_total": 5, "teachers_certified": 4,
         "students_boys": 80, "students_girls": 70,
         "canteen": True, "canteen_meals_per_week": 5, "canteen_cost_per_ration": 100,
         "latrines": True, "latrines_separated": True, "gps": "7.4N,7.5W"},
    ]
    created = client.post("/ssrte/communities", json={
        "locality": "Yeyasso",
        "schools": schools,
    }).json()
    assert len(created["schools"]) == 1
    assert created["schools"][0]["name"] == "EPP Yeyasso"
    assert created["schools"][0]["classrooms"] == 6

    r = client.get(f"/ssrte/communities/{created['id']}/fichea.pdf")
    assert r.status_code == 200, r.text
    assert r.content[:5] == b"%PDF-"


def test_ssrte_fichea_full_questionnaire_coverage(client):
    """La Fiche A capture l'identification admin, GPS/heures, details indicateurs et remarques."""
    created = client.post("/ssrte/communities", json={
        "locality": "Yeyasso",
        "section": "Man",
        "supplier": "Fournisseur X",
        "sub_prefecture": "Sous-pref Y",
        "collection_agent_code": "AG-007",
        "collection_agent_name": "Agent Kone",
        "gps_start": "7.41, -7.55",
        "time_start": "08:30",
        "gps_end": "7.41, -7.55",
        "time_end": "10:15",
        "school_available": True,
        "services_available": {
            "electricity": True, "electricity_origin": ["raccordement solaire"],
            "water_point": True, "water_distance": "100 à 500 mètres",
            "child_labor_orgs": True, "org_state": "Comite local", "org_ngo": "ONG Z",
            "secondary_classes_count": "0", "secondary_school_distance_km": 4.5,
        },
        "schools": [{
            "name": "EPP Yeyasso", "type": "Formelle", "built_by": "ICI",
            "classrooms": 6, "teachers_titulaires": 4, "teachers_benevoles": 1,
            "students_boys": 80, "students_girls": 70,
            "canteen": True, "canteen_service_per_week": "2-3", "canteen_cost": "Gratuit",
            "latrines": True, "latrines_separated": True, "gps": "7.4,-7.5",
        }],
        "section_notes": {"identification": "RAS", "services": "Eau a surveiller"},
    }).json()
    assert created["collection_agent_name"] == "Agent Kone"
    assert created["time_start"] == "08:30"
    assert created["services_available"]["water_distance"] == "100 à 500 mètres"
    assert created["schools"][0]["teachers_titulaires"] == 4
    assert created["section_notes"]["services"] == "Eau a surveiller"

    r = client.get(f"/ssrte/communities/{created['id']}/fichea.pdf")
    assert r.status_code == 200, r.text
    assert r.content[:5] == b"%PDF-"


def test_ssrte_ficheb_farm_info_persists(client):
    """Les informations exploitation (B.16-B.23) sont stockees, relues et exportees."""
    producer_id, _ = _seed_producer_and_plantation()
    farm_info = {
        "cocoa_parcels": 2, "cocoa_area_ha": 3.5, "cocoa_production_kg": 900,
        "coffee_parcels": 1, "coffee_area_ha": 1.0, "coffee_production_kg": 200,
    }
    created = client.post("/ssrte/households", json={
        "producer_id": producer_id,
        "farm_info": farm_info,
        "consent_given": True,
    }).json()
    assert created["farm_info"]["cocoa_parcels"] == 2
    assert created["farm_info"]["coffee_production_kg"] == 200

    r = client.get(f"/ssrte/households/{created['id']}/ficheb.pdf")
    assert r.status_code == 200, r.text
    assert r.content[:5] == b"%PDF-"


def test_ssrte_fichec_adults_and_workers_persist(client):
    """Les adultes (C.10a) et travailleurs non-journaliers (C.10c) sont stockes et exportes."""
    producer_id, plantation_id = _seed_producer_and_plantation()
    created = client.post("/ssrte/plantation-visits", json={
        "plantation_id": plantation_id,
        "producer_id": producer_id,
        "adults_observed": [{"name": "Yao Pere", "relation": "Chef de menage", "age": 45}],
        "workers_present": [{"name": "Koffi Ouvrier", "status": "permanent", "phone": "0700000000"}],
        "consent_given": True,
    }).json()
    assert created["adults_observed"][0]["name"] == "Yao Pere"
    assert created["workers_present"][0]["status"] == "permanent"

    r = client.get(f"/ssrte/plantation-visits/{created['id']}/fichec.pdf")
    assert r.status_code == 200, r.text
    assert r.content[:5] == b"%PDF-"


def test_ssrte_summary_counts_forms(client):
    producer_id, plantation_id = _seed_producer_and_plantation()
    client.post("/ssrte/communities", json={"locality": "Yeyasso"})
    client.post("/ssrte/households", json={"producer_id": producer_id})
    client.post("/ssrte/plantation-visits", json={"plantation_id": plantation_id})

    summary = client.get("/ssrte/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert data["community_profiles"] == 1
    assert data["household_profiles"] == 1
    assert data["plantation_visits"] == 1


def test_ssrte_forms_are_in_due_diligence_report(client):
    producer_id, plantation_id = _seed_producer_and_plantation()
    client.post("/ssrte/communities", json={"locality": "Yeyasso"})
    client.post("/ssrte/households", json={
        "producer_id": producer_id,
        "school_age_children_count": 2,
        "enrolled_children_count": 1,
        "child_work_declarations": [{"child": "A", "task": "machette", "dangerous": True}],
    })
    client.post("/ssrte/plantation-visits", json={
        "plantation_id": plantation_id,
        "suspected_child_labor": True,
        "dangerous_tasks_observed": ["machette"],
    })

    report = client.get("/compliance/report")
    assert report.status_code == 200, report.text
    data = report.json()
    assert data["indicators"]["ssrte_community_profiles"] == 1
    assert data["indicators"]["ssrte_household_profiles"] == 1
    assert data["indicators"]["ssrte_plantation_visits"] == 1
    assert data["indicators"]["ssrte_suspected_child_labor_visits"] == 1
    assert "ssrte_plantation_visits" in data["audit_evidence"]
    assert len(data["recent_ssrte_households"]) == 1
    assert len(data["recent_ssrte_plantation_visits"]) == 1
