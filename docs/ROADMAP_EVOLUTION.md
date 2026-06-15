# AgriVision Pro — Feuille de route d'évolution (analyse CTO)

> Réponse à `docs/PROPOSITION D'AMELIORATION.txt`. Analyse des 5 modules proposés
> pour passer d'un « logiciel agricole » à une **plateforme intégrée de conformité,
> traçabilité et durabilité** pour coopératives cacao.
>
> Dernière mise à jour : **2026-05-31**.

---

## Décision immédiate (livrée cette session, en autonomie)

✅ **Module #5 — Tableau de bord direction** : livré de bout en bout (endpoint
`GET /dashboard/direction` + page `direction.html`).

**Pourquoi celui-ci en premier, seul et sans validation préalable :**
- **Lecture seule** : aucune écriture, aucune migration → risque quasi nul.
- **Aucune dépendance externe** (contrairement au satellite avancé).
- **Valorise immédiatement** tout ce qui est déjà construit (EUDR, SSRTE, FarmForce,
  volumes, certification) en une vue exécutive unique.
- **Réutilise le cloisonnement multi-tenant** corrigé en début de session.

Indicateurs consolidés : périmètre (producteurs/plantations/ha), conformité EUDR
(taux + statuts + score moyen), protection de l'enfant (enfants suivis, risque élevé,
scolarisation, blocages traçabilité, suspicions), revenu vital (taux d'atteinte du
seuil, revenu net moyen), volumes & taux certifié, alertes ouvertes.

---

## Analyse des 5 modules proposés

| # | Module | Valeur | Effort | Risque | Dépendance externe |
|---|---|---|---|---|---|
| 1 | Traçabilité cacao (lots, QR, mouvements, entrepôts) | ⭐⭐⭐⭐⭐ | Élevé | Moyen (schéma) | Non |
| 2 | Achats producteurs (bons, pesées, **paiements**) | ⭐⭐⭐⭐⭐ | Élevé | **Élevé** ($) | Non |
| 3 | Certification (RA, FT, Cocoa Horizons…) | ⭐⭐⭐⭐ | Moyen | Moyen | Non |
| 4 | Satellite avancé (NDVI/NDMI/alertes) | ⭐⭐⭐⭐ | Moyen | Faible | **Oui (GEE/Sentinel)** |
| 5 | **Tableau de bord direction** | ⭐⭐⭐⭐ | Faible | **Faible** | Non | ✅ FAIT |

### Séquencement recommandé (après validation client)

1. **Traçabilité des lots** (#1) — ✅ **livré (2026-05-31)**. Modèles `Warehouse`, `Lot`
   (code auto `LOT-AAAA-NNNNN`, statut open/sealed/shipped/merged/blocked, poids/sacs dérivés),
   `LotMovement` (journal : creation/warehouse_in/seal/export_out/merge_in/split_out/adjustment),
   lien `Harvest.lot_id`. Endpoints `/warehouses`, `/lots` (CRUD + filtres), `/lots/{id}/affect-harvests`,
   `/lots/{id}/movements`, `/lots/merge`, `/lots/{id}/passport`. **Intégration CacaoGuard** : refus 409
   d'affecter une récolte dont le producteur a un blocage de traçabilité ACTIF. UI `lots.html`
   (liste, création, détail+passeport+mouvements+statuts, entrepôts). Cloisonné coopérative. 7 tests.
   **Reste possible** : QR code imprimable du passeport (génération image), split de lot, lien achats.
2. **Achats producteurs** (#2) — ✅ **livré (2026-05-31, hors exécution financière)**.
   `PurchaseRecord` (producteur, plantation, bon d'achat, pesée brut/tare/net, prix/kg,
   montant, qualité, campagne). Génère automatiquement une `Harvest` traçable (→ volumes → lots).
   Endpoints `/purchases` (GET/POST + filtres), `/purchases/summary`, `/purchases/{id}`,
   `/purchases/{id}/mark-paid`. Suivi de paiement **comptable uniquement** (statut pending/paid),
   signale les producteurs sous blocage CacaoGuard. UI `achats.html`. Cloisonné coop. 7 tests.
   ⚠️ **Reste à cadrer avec le client** : l'**exécution financière** réelle (virements / mobile
   money / intégration bancaire) n'est PAS implémentée — décision produit + conformité requise.
3. **Certification** (#3) — ✅ **livré (2026-05-31)**. Modèles `CertificationAudit`
   (planned/in_progress/completed, résultat pass/conditional/fail, score) et `NonConformity`
   (sévérité minor/major/critical, action corrective, échéance, statut, détection retard).
   Endpoints `/certifications` (référentiel), `/certification-audits` (+ `/complete`),
   `/non-conformities` (+ PATCH résolution), `/certification/summary`. UI `certification.html`.
   Cloisonné coop. 6 tests. Étend le `Certification`/`PlantationCertification` existant.
4. **Satellite avancé** (#4) — ✅ **abstraction livrée (2026-05-31)**. `app/satellite/provider.py`
   expose `get_indices` (NDVI+NDMI), `get_timeseries` (séries mensuelles) et
   `get_deforestation_signal`, avec **fallback simulation déterministe** (fonctionne
   sans clé) et **bascule automatique** sur Copernicus dès que `SENTINEL_CLIENT_ID/SECRET`
   sont définis (l'intégration CDSE NDVI ponctuelle existait déjà). Endpoints
   `/satellite/indices|timeseries|deforestation|status` + `/satellite/plantations/{id}/advanced`
   (cloisonné coop). UI : carte « Analyse avancée » dans `satellite.html` (NDMI, sparklines
   NDVI/NDMI, statut déforestation). On a délibérément **écarté Google Earth Engine** (licence
   commerciale payante) au profit de Copernicus Data Space + GFW (gratuits).
   ✅ **Terminé et vérifié en live (2026-05-31)** : NDVI, NDMI et séries mensuelles réels via
   Copernicus (`SENTINEL_CLIENT_ID/SECRET`) ; **alertes de déforestation réelles** via Global
   Forest Watch (`GFW_API_KEY`, dataset `gfw_integrated_alerts`, post-2020 = seuil EUDR).
   ⚠️ Piège résolu : la GFW Data API exige l'en-tête `x-api-key` **en minuscules** (urllib le
   capitalise → 403) ; les appels GFW passent donc par `http.client`. Coût total : **0 €**.

---

## Plans d'abonnement / feature-gating (livré 2026-05-31, fondation)

Système de paliers par coopérative, **non-cassant** (défaut `enterprise` = tout activé).
- **Catalogue central** : `app/services/plans.py` — `CATEGORY_OF` (module→catégorie) et
  `PLAN_CATEGORIES` (plan→catégories). **Seul fichier à éditer** pour ajuster le découpage.
- **Catégories** : `core` (agronomie), `compliance` (conformité/durabilité),
  `commercial` (achats/lots/certif), `premium` (satellite, FarmForce).
- **Plans** : starter (core) · compliance (+conformité) · pro (+commercial) · enterprise (tout).
- **Modèle** : `Cooperative.plan` (défaut `enterprise`), migration idempotente.
- **API** : `GET /me`, `GET /me/features` (plan + modules autorisés), `PATCH /cooperatives/{id}/plan` (admin).
- **Frontend** : `auth.js` masque les modules de menu hors plan + redirige si page non autorisée.
- **Garde-fou API** : `require_module("...")` (dans `plan_routes.py`) prêt à protéger les routes
  côté serveur **quand le découpage business sera figé** (non appliqué massivement pour rester non-cassant).

**Reste à décider (business)** : noms/prix des paliers et répartition fine des modules ;
puis activer `require_module` sur les routes des modules payants pour une vraie protection API
(aujourd'hui le gating est au niveau menu/UX).

## Principes d'architecture à respecter pour la suite

- **Multi-tenant strict** : tout nouvel agrégat scopé par `cooperative_id`
  (cf. correctif CacaoGuard de cette session).
- **Migrations idempotentes** au démarrage (`ALTER TABLE … IF NOT EXISTS`), jamais
  de migration destructive automatique.
- **PDF** : WeasyPrint + fallback natif (pas de dépendance Cairo en CI/Windows).
- **Tests verts avant tout push** ; push **uniquement** sur `origin`
  (`codex/cacaoguard-fusion`), jamais sur la prod sans feu vert explicite.
- **Aucune action destructive ni manipulation d'argent** sans validation explicite.

---

## Passage à l'échelle — grandes coopératives (7000+ parcelles)

> Identifié 2026-06-14 sur le cas réel **YEYASSO (~7000 parcelles)**. **Non bloquant pour la démo**
> (coop démo = 8 parcelles), mais **prérequis avant l'onboarding en prod d'une grosse coop.**

**Constat (vérifié dans le code) :**
- **Affichage** : `producers.html` demande `limit=5000` (backend plafonné à 5000) ; liste EUDR plafonnée à 1000
  (`app/api/eudr_routes.py`). Au-delà, des parcelles deviennent invisibles. Le backend producteurs **sait déjà
  paginer** (`skip`+`limit`, `app/api/producer_routes.py`) mais le frontend ne s'en sert pas. ⚠️ Rendre 7000
  lignes tuerait le navigateur de toute façon → il faut paginer/filtrer, pas « monter la limite ».
- **Perf (le vrai bloquant)** : le score EUDR est **recalculé à la volée, parcelle par parcelle, dans une
  boucle**. Le dashboard direction parcourt **toutes** les plantations et appelle `compute_eudr_score` sur
  chacune (~4-5 requêtes/parcelle) → à 7000, **~30 000+ requêtes par chargement** → lent / timeout.

**Avancement (2026-06-14) — livré ET déployé sur `codex/cacaoguard-fusion` :**
1. **P1 — scoring à l'échelle** ✅ **FAIT** : score EUDR mis en cache sur la parcelle (colonnes `eudr_*`),
   les agrégats (dashboard / EUDR summary / readiness / liste) **lisent le cache** ; refresh à la
   délimitation + au contrôle déforestation ; `POST /eudr/recompute` (recompute en masse, après un gros
   import). Code : `app/eudr/score_cache.py`. Mesure : **638 ms → 16 ms (~×40)** sur 800 parcelles (SQLite mémoire).
2. **P2 — pagination + filtres serveur** ✅ **producteurs + plantations FAIT** : producteurs paginés
   (`/producers/count` + skip/limit, pager UI) ; plantations via `/plantations?paginated=true` enrichi
   (score/risque/EUDR **en ligne** depuis le cache P1) + filtre `risk`. **Reste** : transformer les `<select>`
   producteurs de children / FarmForce / SSRTE (`?limit=1000`) en **sélecteurs cherchables** (ne gêne qu'à ~7000).
3. **P3 — actions en masse** 🚧 **EN COURS** : ✅ **génération des délimitations manquantes en masse**
   (`POST /plantations/boundaries/generate-missing` — par lots de 500, carré « generated » depuis GPS +
   superficie déclarés ; bouton dans le panneau « Prêt pour l'EUDR » qui boucle jusqu'à épuisement) ;
   re-contrôle en masse déjà dispo en backend (`POST /eudr/recompute`, P1). **Reste** : bouton UI de
   recompute + déclenchement automatique après un gros import, et dérogation export en lot — toujours par
   lots, jamais 1-à-1.

> ℹ️ Le **gel démo est levé** (le client passe par un entretien téléphonique, pas de démo immédiate) : on
> déploie de nouveau normalement sur `codex/cacaoguard-fusion`. P1 + P2 (producteurs + plantations) + le
> regroupement du menu par 4 piliers sont **en prod** (SW v4.53). P3 : génération des délimitations
> manquantes en masse livrée et déployée le 2026-06-15.

> La **philosophie de contrôle** est déjà la bonne (agrégat dashboard + drill-down filtré + regroupement
> « Prêt pour l'EUDR » par type de manque) : on agit sur le **sous-ensemble** non conforme, pas sur les 7000.

**Méthode de travail recommandée** : développer sur une **branche dédiée** (PAS `codex/cacaoguard-fusion`
qui est déployée), committer normalement (checkpoints + sauvegarde sur `origin` + tests), et **fusionner
après la démo**. Railway/Netlify ne déploient que `codex/cacaoguard-fusion` → une branche feature = **zéro
risque pour la démo** tout en gardant l'historique et la CI. (À éviter : un gros tas de modifications **non
committées** en local pendant des jours — pas de points de restauration, risque de perte.)
