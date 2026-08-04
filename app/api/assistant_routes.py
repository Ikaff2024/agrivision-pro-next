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
# Rôles habilités à ENSEIGNER des faits à Aya et à corriger ses réponses.
_TEACH_ROLES = {"admin", "agronomist", "gestionnaire"}
_CAP = 60  # bornage des listes d'entités dans l'instantané
_MEM_CAP = 40          # nb max de faits mémoire injectés dans le contexte
_MEM_CHARS_CAP = 4000  # bornage caractères (maîtrise du coût tokens)

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
    "• CONTRÔLE DÉFORESTATION (satellite Global Forest Watch, données réelles) : détecte une PERTE de forêt "
    "survenue APRÈS le 31/12/2020 à l'endroit indiqué. « 0 alerte » = aucune déforestation récente ICI — ce "
    "n'est PAS un jugement de qualité, et PAS un détecteur de « zone cacaoyère » : une position urbaine (ex. "
    "Bingerville) renvoie logiquement 0 alerte, ce n'est pas un bug. Pour une démo montrant une détection : "
    "Cavally (6.45,-7.72), Scio (6.60,-7.40) ou Goin-Débé (6.35,-7.55). Le pré-contrôle prévient aussi quand "
    "une position sans déforestation a un couvert végétal très faible (urbain/sol nu) : « ne ressemble pas à une parcelle ». "
    "On peut vérifier TOUTES les parcelles d'un coup : bouton « Vérifier la déforestation (toutes) » (page EUDR, "
    "admin/agronome) — traitement par lots avec barre de progression, ignore les parcelles déjà vérifiées < 30 j.\n"
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
    "non-membre pas en récolte (blocage). PHOTO facultative du producteur (fiche ▸ Éditer) pour "
    "identification / carte producteur : image redimensionnée automatiquement, avec CONSENTEMENT explicite "
    "du producteur (donnée personnelle, retirable à tout moment) ; réservée aux rôles admin/agronome/technicien/gestionnaire.\n"
    "• Opérations : bouton « Pré-contrôle EUDR » (déforestation AVANT achat), « Palmarès des parcelles » "
    "(à redresser / modèles), et le volume non tracé distingue le volume RETENU pour cas social.\n"
    "• IA : bouton « Interpréter avec l'IA » sur plusieurs modules + « Aya : proposer un plan de formation » "
    "(menu Formation). Recherche cherchable (taper quelques lettres) sur les grandes listes.\n"
    "• VEILLE MARCHÉ : prix réels (cours mondial ICE New York + prix bord-champ officiel CCC) et "
    "actualités de la filière ; un sélecteur « Âge de l'info » (Toutes / 7 j / 30 j / 3 / 6 / 12 mois) "
    "restreint les actualités aux plus récentes. La synthèse IA est en cache (régénérée au « Rafraîchir », "
    "réservé admin/agronome). La veille réglementaire EUDR/durabilité est en bas de la même page.\n"
    "• Signalements : le déclarant n'a PAS besoin de compte. Un agent consigne le cas (anonyme possible) ; "
    "et un LIEN/QR PUBLIC (Signalements ▸ Lien public) permet à la communauté de signaler elle-même SANS "
    "compte — le signalement arrive dans la bonne coopérative.\n"
    "• Formation : émargement réel — rechercher les producteurs PRÉSENTS (présence = signature), score "
    "post-test facultatif, note d'efficacité ; fonctionne hors ligne.\n"
    "• SENS DES SCORES : en agroforesterie (ombrage, diversité, carbone, conformité) plus le score est élevé "
    "MIEUX c'est ; au diagnostic agronomique le « score global » est un RISQUE : plus il est élevé MOINS c'est "
    "bon (0 sain, 100 critique). Le carbone agroforestier est une ESTIMATION (non certifié).\n"
    "• PROTECTION ENFANT vs FICHES SSRTE : les fiches SSRTE sont la MÉTHODE d'enquête (formulaires officiels "
    "A localité / B ménage / C visite, auditables, cycle brouillon→clôture) — elles COLLECTENT. La Protection "
    "de l'enfant (CacaoGuard) est le SUIVI vivant : registre des enfants + calcul du risque + remédiation + "
    "blocage — elle AGIT. SSRTE alimente → Protection de l'enfant agit (l'un mesure, l'autre traite). "
    "Fiche B / B.29 : on peut joindre la vraie PHOTO du chef de ménage (rouvrir la fiche brouillon ▸ « Ajouter »), "
    "avec CONSENTEMENT explicite (donnée personnelle, retirable) ; elle apparaît dans le PDF de la Fiche B.\n"
    "• CACAOGUARD (tableau de bord) : les COMPTEURS en haut sont CLIQUABLES (drill-down) et ouvrent leur détail — "
    "Producteurs, Enfants, Risque élevé (liste filtrée élevé/critique), Visites (monitoring), Plans (remédiation), "
    "Blocages (conformité), F1 ménage / Fiche C / Suspicions (fiches SSRTE, bon onglet), Revenu vital & Marge "
    "négative (comptes). « Alertes ouvertes » fait défiler jusqu'à la liste des alertes de la page.\n"
    "• PRIORITÉS D'ENQUÊTE (risque précoce) : la page Protection enfant a un bouton « 🔮 Priorités d'enquête » "
    "qui classe les MÉNAGES par risque précoce de travail d'enfant à partir des signaux déjà saisis (tâche "
    "dangereuse, enfant déscolarisé/qui travaille, écart au revenu vital, signalement), en AFFICHANT les "
    "facteurs. C'est une AIDE À L'ENQUÊTE qui priorise les visites — jamais un verdict ni un blocage.\n"
    "• MÉMOIRE D'AYA : la direction (admin/agronome/gestionnaire) peut m'ENSEIGNER des faits propres à "
    "la coopérative (bouton « 🧠 Mémoire d'Aya » sur ma page) — prix plancher, zones sensibles, jours de "
    "collecte… Je m'en sers pour répondre selon la réalité de VOTRE coopérative, et un 👍/👎 sous chaque "
    "réponse m'aide à m'améliorer.\n"
    "• CONFLITS DE DÉLIMITATION (anti-fraude/EUDR) : le bouton « Conflits de délimitation » (page "
    "Plantations) détecte les parcelles dont les POLYGONES SE CHEVAUCHENT (double-mapping = même terre "
    "déclarée deux fois), avec surface et % de recouvrement ; un polygone invalide (auto-intersection) est "
    "aussi signalé car il fait rejeter un dossier EUDR. Ces contrôles apparaissent aussi en alertes du Jumeau.\n"
    "• EXPORT SIG : le bouton « Export SIG » (page Plantations) télécharge les parcelles au format GeoJSON "
    "(dépôt de géolocalisation EUDR), KML (Google Earth) ou Shapefile .zip (certificateurs / QGIS), cloisonné "
    "à la coopérative.\n"
    "• MODE HORS-LIGNE (tournée sans réseau) : avant de partir, cliquer « ☁️⤓ Préparer le hors-ligne » "
    "(menu latéral) télécharge les écrans essentiels sur l'appareil. Sur le terrain on peut SAISIR sans "
    "réseau — achats, protection enfant, signalements, récoltes, monitoring, fiches SSRTE, diagnostics — "
    "chaque saisie est mise en file locale (pastille ☁️ « X à envoyer ») puis envoyée AUTOMATIQUEMENT au "
    "retour du réseau (même app fermée sur Chrome/Android). Les saisies restent rattachées à leur auteur : "
    "jamais envoyées sous un autre compte sur un appareil partagé. Voir guide §9.F."
)


class AssistantQuestion(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


def _load_memory(db: Session, coop_id, limit: int = _MEM_CAP):
    """Faits enseignés ACTIFS de la coopérative (cloisonné). Ordre : récents d'abord."""
    from app.db.models import AyaMemory
    q = db.query(AyaMemory).filter(AyaMemory.is_active.is_(True))
    if coop_id is not None:
        q = q.filter(AyaMemory.cooperative_id == coop_id)
    else:
        q = q.filter(AyaMemory.cooperative_id.is_(None))
    return q.order_by(AyaMemory.created_at.desc()).limit(limit).all()


def _format_memory(rows) -> str:
    if not rows:
        return "aucun fait enseigné pour l'instant."
    out, total = [], 0
    for r in rows:
        line = f"- [{r.category}] {r.content}"
        total += len(line)
        if total > _MEM_CHARS_CAP:
            break
        out.append(line)
    return "\n".join(out)


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
    memory_txt = _format_memory(_load_memory(db, current_user.cooperative_id))
    prompt = (
        "Tu es Aya, l'assistante IA de la plateforme AgriVision Pro (cacao, Côte d'Ivoire). "
        "Si on te demande ton nom, tu es Aya. Tu as TROIS sources :\n"
        "1) AIDE À L'UTILISATION : explique où trouver une fonction et comment réaliser une action, "
        "en t'appuyant sur le GUIDE.\n"
        "2) DONNÉES : réponds aux questions chiffrées EXCLUSIVEMENT à partir de l'INSTANTANÉ "
        "(déjà cloisonné à cette coopérative) ; si l'info n'y figure pas (ou instantané non disponible), "
        "dis-le et n'invente aucun chiffre ; précise quand une liste est plafonnée.\n"
        "3) MÉMOIRE COOPÉRATIVE : des faits enseignés par l'équipe de CETTE coopérative. Considère-les "
        "comme vrais pour elle (prix, zones, pratiques…) et utilise-les pour personnaliser tes réponses. "
        "En cas de conflit sur un CHIFFRE, l'INSTANTANÉ prime ; sinon la MÉMOIRE fait foi.\n"
        "Réponds en français, de façon concise et structurée.\n\n"
        f"QUESTION : {data.question.strip()}\n\n"
        f"GUIDE :\n{PLATFORM_GUIDE}\n\n"
        f"MÉMOIRE COOPÉRATIVE (faits enseignés par l'équipe) :\n{memory_txt}\n\n"
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


# ── Mémoire d'Aya (faits enseignés) & feedback ────────────────────────────────

class MemoryIn(BaseModel):
    content: str = Field(..., min_length=3, max_length=500)
    category: str = Field("general", max_length=40)


class FeedbackIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    answer: str = Field("", max_length=8000)
    rating: int = Field(..., ge=-1, le=1)          # +1 (👍) / -1 (👎) / 0
    correction: str | None = Field(None, max_length=1000)


@router.get("/assistant/memory")
def list_memory(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Faits enseignés (actifs) de la coopérative de l'utilisateur — cloisonné."""
    rows = _load_memory(db, current_user.cooperative_id, limit=200)
    return [
        {
            "id": r.id, "content": r.content, "category": r.category,
            "source": r.source, "created_by": r.created_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "can_edit": current_user.role in _TEACH_ROLES,
        }
        for r in rows
    ]


@router.post("/assistant/memory", status_code=201)
def add_memory(
    data: MemoryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enseigner un fait à Aya (réservé à la direction). Cloisonné à la coopérative."""
    if current_user.role not in _TEACH_ROLES:
        raise HTTPException(status_code=403, detail="Réservé à la direction (admin/agronome/gestionnaire).")
    from app.db.models import AyaMemory
    row = AyaMemory(
        cooperative_id=current_user.cooperative_id,
        content=data.content.strip(),
        category=(data.category or "general").strip() or "general",
        source="manual",
        created_by=getattr(current_user, "email", None),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.delete("/assistant/memory/{mem_id}")
def delete_memory(
    mem_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Oublier un fait (suppression douce). Cloisonné : on ne touche que sa coopérative."""
    if current_user.role not in _TEACH_ROLES:
        raise HTTPException(status_code=403, detail="Réservé à la direction (admin/agronome/gestionnaire).")
    from app.db.models import AyaMemory
    row = db.query(AyaMemory).filter(AyaMemory.id == mem_id).first()
    if not row or row.cooperative_id != current_user.cooperative_id:
        raise HTTPException(status_code=404, detail="Fait introuvable.")
    row.is_active = False
    db.commit()
    return {"ok": True}


@router.post("/assistant/feedback", status_code=201)
def add_feedback(
    data: FeedbackIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retour 👍/👎 sur une réponse d'Aya. Une correction saisie par un rôle habilité
    devient AUSSI un fait de mémoire (source='correction') — humain-dans-la-boucle."""
    from app.db.models import AyaFeedback, AyaMemory
    fb = AyaFeedback(
        cooperative_id=current_user.cooperative_id,
        user_id=current_user.id,
        question=data.question.strip(),
        answer=(data.answer or "").strip() or None,
        rating=data.rating,
        correction=(data.correction.strip() if data.correction else None),
    )
    db.add(fb)
    learned = False
    if data.correction and data.correction.strip() and current_user.role in _TEACH_ROLES:
        db.add(AyaMemory(
            cooperative_id=current_user.cooperative_id,
            content=data.correction.strip(),
            category="correction",
            source="correction",
            created_by=getattr(current_user, "email", None),
        ))
        learned = True
    db.commit()
    return {"ok": True, "learned": learned}
