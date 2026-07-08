"""Assistant « mes données » — Q&A en langage naturel ANCRÉ sur un instantané.

Sécurité : le LLM ne génère JAMAIS de requête SQL. On construit côté serveur un
instantané COMPACT et CLOISONNÉ par coopérative (réutilise les agrégats existants :
KPI direction, couverture certification + listes ciblées), puis le fournisseur
sélectionné (OpenRouter…) répond UNIQUEMENT à partir de cet instantané.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.auth_service import get_current_user
from app.db.database import get_db
from app.db.models import Plantation, Producer, User

router = APIRouter(tags=["Assistant IA"])

# Les RÉPONSES DONNÉES (instantané) restent réservées à la direction (admin/agronome,
# qui alimente l'instantané). L'AIDE À L'UTILISATION est ouverte à tous les rôles.
_DATA_ROLES = {"admin", "agronomist"}
_CAP = 60  # bornage des listes d'entités dans l'instantané

# Guide d'utilisation COMPACT (où trouver / comment faire) — sert l'aide à la prise
# en main. Mis à jour avec les fonctions : tenir synchronisé avec frontend/guide.
PLATFORM_GUIDE = (
    "AgriVision Pro — plateforme de conformité/traçabilité cacao. Navigation par piliers :\n"
    "• PILOTER : Dashboard (vue d'ensemble, adaptée au plan), Direction (KPI + bouton « Synthèse IA »), "
    "Aya · Assistant IA (cette page), Rapports, Veille Marché (prix réels + synthèse ; la veille EUDR/durabilité est en bas de cette page).\n"
    "• PRODUIRE : Plantations (fiche parcelle, certifications, contrôle déforestation), Producteurs "
    "(« Nouveau producteur », édition, Export CSV), Diagnostic (analyse agronomique + « Conseil IA »), "
    "Carte (bouton « Délimiter une parcelle » pour tracer le polygone), Satellite (NDVI), "
    "Agroforesterie (espèces + bilan PDF), Récoltes, Parcelles à risque.\n"
    "• TRACER : Achats, Traçabilité lots (créer un lot, affecter des récoltes, sceller, expédier, "
    "passeport PDF, dérogation export admin), Certification (couverture par standard, échéances, "
    "registre + export CSV, affectation en masse, audits & non-conformités avec « Rédiger (IA) »).\n"
    "• PROTÉGER : CacaoGuard, Protection enfant (recensement + « Évaluer un enfant »), Fiches SSRTE, "
    "EUDR (conformité parcellaire, DDS, contrôle déforestation), Conformité, Revenu vital (livret), "
    "Monitoring (visites terrain géolocalisées), Remédiation (plans + actions, bouton « Suggérer (IA) »), "
    "Signalements, Formation.\n"
    "• CONFIGURATION : Admin (membres, profil & responsables de la coopérative, logo, blocage social optionnel), Aide/Guide.\n"
    "Actions clés : tracer une parcelle → Carte ▸ Délimiter ; générer un DDS → fiche plantation ▸ carte EUDR ▸ Télécharger DDS ; "
    "contrôle déforestation → fiche plantation ou menu EUDR ; créer/expédier un lot → Traçabilité lots ; "
    "choisir le fournisseur IA → page propriétaire (owner).\n"
    "Règles : l'EUDR = 5 critères ENVIRONNEMENTAUX (polygone, superficie cohérente, GPS en zone cacao, "
    "inspection < 12 mois, pas de déforestation post-2020). Le volet SOCIAL (travail des enfants) est "
    "DISSOCIÉ de l'EUDR : signalé par défaut, ne bloque l'export que si la coopérative l'active. "
    "Le menu/dashboard s'adapte au plan d'abonnement de la coopérative.\n"
    "\nFAITS CLÉS (réponds avec ces chiffres EXACTS, ne sois pas évasive) :\n"
    "• Diagnostic par PHOTO (menu Diagnostic, rôle admin/technicien) : un modèle IA (EfficientNet-B0, "
    "spécifique cacao) reconnaît 3 MALADIES de la cabosse — pourriture noire (black pod), moniliose, "
    "phytophthora (pourriture brune) — plus l'état SAIN ; un pré-filtre vérifie d'abord que la photo est bien du cacao.\n"
    "• Diagnostic AGRONOMIQUE (sans photo) : calcule un score de RISQUE de maladies fongiques selon "
    "l'environnement (humidité, pluviométrie, température, ombrage, âge) — c'est un indicateur de risque, "
    "PAS une identification de maladie.\n"
    "• Agroforesterie : bibliothèque de 18 espèces d'ombrage ; stock carbone ESTIMÉ (allométrie FAO/IPCC "
    "simplifiée, non certifié) ; scores ombrage/diversité/carbone/conformité.\n"
    "• Revenu vital : le seuil (« revenu vital ») est éditable par coopérative dans Administration ▸ Profil "
    "de la coopérative ; défaut 2 360 000 FCFA/an.\n"
    "• Producteurs : la catégorie est OBLIGATOIRE à la création — membre (récolte) ou non-membre (achat) ; "
    "reclassement EN MASSE possible (bouton « Classer en masse »). Un membre ne peut pas être en achat, un "
    "non-membre pas en récolte (blocage).\n"
    "• Opérations : bouton « Pré-contrôle EUDR » (déforestation AVANT achat), « Palmarès des parcelles » "
    "(à redresser / modèles), et le volume non tracé distingue le volume RETENU pour cas social.\n"
    "• IA : bouton « Interpréter avec l'IA » sur plusieurs modules + « Aya : proposer un plan de formation » "
    "(menu Formation). Recherche cherchable (taper quelques lettres) sur les grandes listes.\n"
    "• Signalements : le déclarant n'a PAS besoin de compte. Un agent consigne le cas (anonyme possible) ; "
    "et un LIEN/QR PUBLIC (Signalements ▸ Lien public) permet à la communauté de signaler elle-même SANS "
    "compte — le signalement arrive dans la bonne coopérative.\n"
    "• Formation : émargement réel — rechercher les producteurs PRÉSENTS (présence = signature), score "
    "post-test facultatif, note d'efficacité ; fonctionne hors ligne.\n"
    "• SENS DES SCORES : en agroforesterie (ombrage, diversité, carbone, conformité) plus le score est élevé "
    "MIEUX c'est ; au diagnostic agronomique le « score global » est un RISQUE : plus il est élevé MOINS c'est "
    "bon (0 sain, 100 critique). Le carbone agroforestier est une ESTIMATION (non certifié)."
)


class AssistantQuestion(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


def _build_snapshot(db: Session, current_user: User) -> dict:
    """Instantané compact et cloisonné des données de la coopérative."""
    from app.api.dashboard_routes import direction_dashboard
    from app.api.certification_routes import certification_coverage

    kpis = direction_dashboard(db, current_user)          # périmètre, EUDR, social, revenu vital, volumes
    coverage = certification_coverage(db, current_user)   # couverture par standard

    coop_id = current_user.cooperative_id
    pq = db.query(Plantation)
    if coop_id is not None:
        pq = pq.filter(Plantation.cooperative_id == coop_id)

    non_conf = [
        {"parcelle": p.name, "region": p.region}
        for p in pq.filter(Plantation.eudr_status == "non_conforme").limit(_CAP).all()
    ]
    a_verifier = [
        {"parcelle": p.name, "region": p.region}
        for p in pq.filter(Plantation.eudr_status == "a_verifier").limit(_CAP).all()
    ]

    # Producteurs sous blocage social actif (CacaoGuard).
    blocked = []
    try:
        from app.db.models_social import BlockStatus, TraceabilityBlock
        bq = (
            db.query(Producer.nom_complet, TraceabilityBlock.block_reason)
            .join(TraceabilityBlock, TraceabilityBlock.producer_id == Producer.id)
            .filter(TraceabilityBlock.status == BlockStatus.ACTIVE)
        )
        if coop_id is not None:
            bq = bq.filter(Producer.cooperative_id == coop_id)
        blocked = [
            {"producteur": nom, "motif": getattr(r, "value", str(r)) if r else None}
            for nom, r in bq.limit(_CAP).all()
        ]
    except ImportError:
        pass

    return {
        "perimetre": kpis.get("perimeter"),
        "eudr": {
            **(kpis.get("eudr") or {}),
            "parcelles_non_conformes": non_conf,
            "parcelles_a_verifier": a_verifier,
            "note_listes": f"listes plafonnées à {_CAP} éléments" if len(non_conf) == _CAP else None,
        },
        "protection_enfant": {
            **(kpis.get("child_protection") or {}),
            "producteurs_sous_blocage": blocked,
        },
        "revenu_vital": kpis.get("living_income"),
        "volumes": kpis.get("volume"),
        "certification": coverage.get("certifications"),
        "alertes_ouvertes": (kpis.get("alerts") or {}).get("open"),
    }


@router.post("/assistant/ask")
def assistant_ask(
    data: AssistantQuestion,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assistant : aide à l'utilisation (tous rôles) + réponses chiffrées sur les
    données (réservées à la direction)."""
    # Données : seulement pour la direction (l'instantané vient du tableau direction).
    if current_user.role in _DATA_ROLES:
        snapshot_json = json.dumps(_build_snapshot(db, current_user), ensure_ascii=False, default=str)
    else:
        snapshot_json = ("non disponible pour votre rôle (les réponses chiffrées sur les données "
                         "sont réservées à la direction) — répondre uniquement aux questions d'utilisation.")
    prompt = (
        "Tu es Aya, l'assistante IA de la plateforme AgriVision Pro (cacao, Côte d'Ivoire). "
        "Si on te demande ton nom, tu es Aya. Tu as DEUX rôles :\n"
        "1) AIDE À L'UTILISATION : explique où trouver une fonction et comment réaliser une action, "
        "en t'appuyant sur le GUIDE.\n"
        "2) DONNÉES : réponds aux questions chiffrées EXCLUSIVEMENT à partir de l'INSTANTANÉ "
        "(déjà cloisonné à cette coopérative) ; si l'info n'y figure pas (ou instantané non disponible), "
        "dis-le et n'invente aucun chiffre ; précise quand une liste est plafonnée.\n"
        "Réponds en français, de façon concise et structurée.\n\n"
        f"QUESTION : {data.question.strip()}\n\n"
        f"GUIDE :\n{PLATFORM_GUIDE}\n\n"
        f"INSTANTANÉ (données) :\n{snapshot_json}"
    )
    try:
        from app.services import llm_client
        out = llm_client.chat(db, prompt, max_tokens=600, temperature=0.2)
    except llm_client.LLMNotConfigured as ex:
        raise HTTPException(status_code=502, detail=str(ex))
    except Exception as ex:  # noqa: BLE001
        import httpx as _httpx
        if isinstance(ex, _httpx.HTTPError):
            raise HTTPException(status_code=502, detail=f"Fournisseur IA injoignable : {type(ex).__name__}.")
        raise

    try:
        from app.db.models import AiUsage
        from app.services.ai_cost import compute_cost_usd
        it_, ot_ = out.get("input_tokens", 0), out.get("output_tokens", 0)
        db.add(AiUsage(
            cooperative_id=current_user.cooperative_id, user_id=current_user.id,
            plantation_id=None, feature="assistant",
            model=out.get("model", ""), input_tokens=it_, output_tokens=ot_,
            cost_usd=compute_cost_usd(it_, ot_, out.get("model")),
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

    return {"answer": (out.get("text") or "").strip(), "model": out.get("model")}
