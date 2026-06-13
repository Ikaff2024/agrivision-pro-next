# Reprise — prochaine session

> **Dernière mise à jour : 2026-06-13.** Bilan de ce qui reste à traiter. Les points du
> backlog 2026-06-01 sont tous livrés (voir **Archive** en bas).
> Branche : `codex/cacaoguard-fusion`. Règle d'or : tests verts avant push, push **origin** uniquement.

---

## État au 2026-06-13 — ce qui reste à traiter

### 1. À caler avant la démo (opérationnel — propriétaire)
- **Vérifier le déploiement v4.45** (`avp-v4.45-ficheb-eco`) : frontend Netlify + migration backend Railway (les colonnes Fiche B éco s'ajoutent au démarrage via `ALTER TABLE … IF NOT EXISTS` dans `main.py`). Les nouveaux champs n'apparaissent qu'une fois le backend redéployé.
- **Lancer / vérifier le seed de démo** sur l'instance déployée : coop `demo2@agrivision-pro.com` / « Coopérative Démo Yeyasso 2026 » (`seed_demo.py`). Statut sur l'instance déployée à confirmer.
- **(Optionnel) activer DeepSeek/Qwen** via clés API (cf. §2) — sinon le Conseil IA reste sur Claude (très bien pour la démo).

### 2. Clés API du Conseil IA (multi-fournisseur) — variables Railway
Code : `app/ai_advisor.py` (`AI_PROVIDER` + `_OPENAI_PRESETS`). À saisir **par le propriétaire** dans Railway → Settings → Variables (jamais committées) :

| Fournisseur | `AI_PROVIDER` | Clé | Modèle défaut |
|---|---|---|---|
| Claude (défaut) | `anthropic` | `ANTHROPIC_API_KEY` | `AI_ADVISOR_MODEL` (`claude-sonnet-4-6`) |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| Qwen | `qwen` | `DASHSCOPE_API_KEY` | `qwen-plus` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` |

Surcharges : `AI_OPENAI_MODEL`, `AI_OPENAI_BASE_URL`, `AI_OPENAI_API_KEY`. Redéployer après modif. ⚠️ La **veille réglementaire** (recherche web) reste sur Claude quel que soit `AI_PROVIDER`.

### 3. Reporté d'un commun accord (prod, pas démo)
- **Photo réelle du chef de ménage (B.29)** : aujourd'hui `head_photo_ref` (`SsrteHouseholdProfile`) ne stocke qu'une *référence texte*. Implémenter l'upload d'image + stockage persistant + affichage dans le PDF. **Décision préalable** : stockage (Railway a un FS éphémère → volume persistant vs objet S3-compatible vs blob PostgreSQL). Confirmé 2026-06-13 : utile en prod, pas pour la démo, aucune urgence. (Chip de suivi + mémoire `project-ficheb-photo-upload`.)

### 4. Décisions produit / business (en attente client)
- **Achats — exécution financière réelle** (virements / mobile money / banque) : volontairement non implémenté (`PurchaseRecord` / `achats.html` gèrent le suivi comptable pending/paid uniquement). Décision produit + conformité requise. ⚠️ Aucun mouvement d'argent exécuté par l'assistant.
- **Plans d'abonnement** : figer noms/prix des paliers + répartition fine des modules (`app/services/plans.py`), puis activer la protection **API** `require_module` sur les modules payants (aujourd'hui le gating est au niveau menu/UX seulement, pas verrouillé côté serveur).

### 5. Améliorations techniques possibles (non urgentes)
- **Lots** : QR code imprimable du passeport, split de lot, lien achats↔lots (`app/api/lot_routes.py`, `frontend/lots.html`).
- **E2E Playwright** (`e2e/`) : scénarios EUDR complet → DDS PDF, import + annulation, récolte avec n° reçu ; GitHub Action post-déploiement (artefact vidéo) ; compte de démo dédié (`AVP_TEST_EMAIL`) au lieu de coops jetables.
- **Finitions** : centraliser `API_BASE` (P3) ; ops prod (sauvegardes — cf. `docs/BACKUP_DR.md`, domaine/HTTPS, rotation des secrets, page statut).
- **Données** : purger « Import Test Coop » (id 2) et statuer sur « Coop CAMER » (via `DELETE /import/owner/batches/{uuid}` si import tracé).

### Confirmé clos récemment (sessions juin 2026)
- **Fiche B — situation économique du ménage** (B.25 logement, B.26 possessions, B.18e entretien travailleurs, B.29 réf. photo) : modèle + migration + API + formulaire (saisie/édition/reset) + PDF (WeasyPrint + fallback) + test. SW `v4.45`, commit `a84e7dc`.
- **Modale « Nouveau signalement »** : règle CSS `.modal-overlay.active` manquante ajoutée dans `auth.js`.
- **Création directe d'un producteur** (bouton + modale + `POST /producers`) sans passer par une parcelle.
- **Entrepôt à la création du lot** : désormais **optionnel** + libellé explicatif (« sinon via Entrée magasin »).
- Filtre certification (producteurs + plantations) ; LLM multi-fournisseur ; création enfant identité d'abord (bloc évaluation facultatif) ; cockpit direction sur le dashboard ; « Parcelles à surveiller » (pires scores) au lieu de « diagnostics récents » ; édition brouillon→clôture SSRTE ; blocage export non conforme + dérogation admin ; rôle gestionnaire ; export composition lot (format YEYASSO) ; anti-sèche démo + DEMO_SCRIPT enrichi ; retrait des libellés internes (`methodology_version` / « eudr-1.1b »).

---

## Archive — backlog 2026-06-01 → 06-03 (tout livré)

## ✅ Avancement — session 2026-06-02

- **Point 1 (inscription admin-only)** : ✅ FAIT — auto-inscription sur coop existante bloquée (403),
  message frontend adapté, 9 fichiers de tests migrés vers `create_member_headers`, 2 tests ajoutés.
- **Point 2 (coût API IA par coop)** : ✅ FAIT — clarifié = coût réel des tokens **Claude** (module
  Conseil agronomique). Table `AiUsage`, tarif config serveur (défaut Sonnet 4 : 3/15 USD/M), conversion
  FCFA paramétrable, endpoints owner `/owner/ai-cost` + `/owner/cooperatives/{id}/ai-cost`, affichage
  `owner.html`. 9 tests dédiés (`tests/test_ai_cost.py`).
- **Point 4 (N° reçu d'achat en Récolte)** : ✅ FAIT — `numero_recu_achat` + `nbre_sacs` exposés au
  schéma `HarvestCreate` et au formulaire `harvests.html` (+ colonne tableau).
- **Point 3 (annuler un import erroné en masse)** : ✅ FAIT — `import_batch_id` sur Producer/Plantation +
  table `ImportBatch` ; `load_registry` tague les entités créées ; endpoints `GET /import/batches`,
  `DELETE /import/batches/{uuid}` (admin, scope coop) et `DELETE /import/owner/batches/{uuid}` (IKAFFANAN) ;
  garde-fou bloquant si données dérivées (récoltes/diagnostics/agroforesterie/délimitations/enfants) ;
  UI « Historique des imports » + bouton Annuler dans `import.html` (confirmation `avpConfirm`). 10 tests
  (`tests/test_import_batches.py`).
- **Tests** : 500 verts. **SW** bumpé `avp-v4.24-recu-cout-import` (sw.js + map.html).

**Décisions prises (Point 3, choix recommandés)** : peut annuler = **admin de la coop** (ses imports) **+
propriétaire IKAFFANAN** (toute coop, pour purger une coop de test) ; données dérivées → **blocage** avec
message clair (pas de cascade destructive). Reste à faire côté données (pas du code) : purger « Import Test
Coop » (id 2) et statuer sur « Coop CAMER » — désormais possible via `DELETE /import/owner/batches/{uuid}`
si ces données proviennent d'un import tracé (sinon nettoyage manuel).

---

## 1. 🔒 Inscription : seul l'admin crée des comptes sur une coopérative existante  ✅ FAIT

**Besoin** : empêcher que n'importe qui s'auto-inscrive dans une coopérative **déjà existante**
(et accède à des infos sans habilitation). La création de compte sur une coop existante doit
passer **uniquement** par l'administrateur.

**Constat (code actuel)** : `app/auth/auth_routes.py` → `register_user` :
- Coopérative **inexistante** → créée, l'inscrit devient **admin fondateur** (à GARDER).
- Coopérative **existante** → accepte aujourd'hui l'inscription publique avec un rôle (sauf admin). ❌ à bloquer.

**Approche proposée** :
- Dans `register_user`, si la coopérative **existe déjà** → renvoyer **403** :
  « L'inscription sur une coopérative existante se fait via son administrateur. »
- Garder la **création d'une nouvelle coopérative** ouverte (fondateur = admin).
- L'admin dispose déjà de **« Ajouter un membre »** (`admin.html` → `POST /admin/members`, mot de passe
  temporaire) : c'est le canal officiel. Vérifier que ce endpoint fonctionne et le mettre en avant.
- Frontend `register.html` : adapter le message (ex. « Pour rejoindre une coopérative existante,
  contactez votre administrateur »).

**Décisions à confirmer** :
- La création d'une **nouvelle** coopérative reste-t-elle 100 % ouverte au public ? (recommandé : oui).
- Faut-il une **validation** (l'IKAFFANAN approuve les nouvelles coops) ? (option plus stricte).

**Fichiers** : `app/auth/auth_routes.py`, `frontend/register.html`, `frontend/admin.html` (rappel du flux), `tests/test_auth.py`.

---

## 2. 💰 Estimation du coût API par coopérative sur une période (dashboard propriétaire)  ✅ FAIT

> **Clarification client** : « coût API » = coût de revient réel des appels à **l'API Claude** par le
> module Conseil agronomique IA (plus une coop l'utilise, plus la facture mensuelle monte). C'est
> mesurable au token près (l'API renvoie `usage.input_tokens`/`output_tokens`).
>
> **Implémenté** : table `AiUsage` (coop, user, plantation, modèle, tokens, `cost_usd` figé à
> l'enregistrement) ; `app/services/ai_cost.py` (tarifs Sonnet 4 par défaut, surchargeables par env
> `AI_COST_INPUT_PER_1M_USD` / `AI_COST_OUTPUT_PER_1M_USD` / `USD_TO_FCFA_RATE`) ; `get_ai_advice`
> renvoie `(result, usage)` et l'endpoint `/ai-advice` enregistre l'usage (best-effort) ; endpoints
> owner `GET /owner/ai-cost?from=&to=` (ventilé par coop) et `GET /owner/cooperatives/{id}/ai-cost` ;
> carte « Coût de revient IA » dans `owner.html` (période sélectionnable, USD + FCFA). Tests :
> `tests/test_ai_cost.py`. Le seul appel Claude est `app/ai_advisor.py` (GFW + Space HF restent gratuits).

<details><summary>Note historique (avant clarification)</summary>

**Besoin initial** : afficher dans l'espace propriétaire une estimation du coût API d'une coopérative.

**Besoin** : afficher dans l'espace propriétaire une **estimation du coût API** d'une coopérative
sur une période donnée.

**Constat** : il n'existe **aucun suivi d'usage par coopérative** persistant. Il y a un middleware
de timing (`main.py`, en-tête `X-Process-Time`) qui **logue** chaque requête mais ne stocke rien.
Les APIs externes branchées (Copernicus, Global Forest Watch) sont **gratuites** → le « coût API »
est surtout du **coût d'infrastructure/compute** (Railway) à **attribuer** par coopérative.

**À clarifier (important)** : que signifie « coût API » pour le client ?
- (a) **Coût d'usage interne** (nombre de requêtes / volume) attribué par coop, converti en €/FCFA via un tarif ?
- (b) **Coût des appels externes** (satellite, etc.) — aujourd'hui gratuits, donc ~0 ?
- (c) **Refacturation** d'un abonnement (lié aux plans) ?

**Approche proposée (si (a))** :
- Table légère `ApiUsage` (ou compteur) : `cooperative_id`, `date`, `endpoint_group`
  (ex. satellite / standard), `count`. Alimentée par le middleware (incrément asynchrone/léger).
- Modèle de tarif paramétrable (ex. `COST_PER_1000_REQUESTS`, `COST_PER_SATELLITE_CALL`).
- Endpoint owner `GET /owner/cooperatives/{id}/api-cost?from=&to=` → estimation sur la période.
- Affichage dans `owner.html` (période sélectionnable).

**Décisions à confirmer** : la base de coût (tarif), le périmètre (compute vs externe), la granularité
(par endpoint ou global). ⚠️ Veiller à ne **pas alourdir** chaque requête (incrément en mémoire +
flush périodique, ou comptage au niveau du log).

**Fichiers** : `main.py` (middleware), nouveau `app/api/usage_*` + modèle, `frontend/owner.html`.

</details>

---

## 3. 🧹 Corriger un import de producteurs erroné (sans le faire un par un)  ✅ FAIT

**Besoin** : après un import de fichier **erroné**, pouvoir **annuler/corriger en masse** (pas
producteur par producteur). Qui : **admin** de la coop et/ou **IKAFFANAN** ?

**Constat** : l'import (`/import/excel`) crée producteurs + plantations dans la coop, mais **sans
identifiant de lot d'import** → impossible de cibler « ce qui vient de cet import ». La suppression
de masse est par ailleurs **bloquée par le garde-fou de sécurité**. (Lié au nettoyage déjà noté de
« Import Test Coop » id 2 et « Coop CAMER ».)

**Approche proposée** :
- Ajouter une notion de **lot d'import** : colonne `import_batch_id` (UUID/horodatage) sur `Producer`
  et `Plantation`, renseignée à chaque import (`registry_loader`).
- Endpoint **annulation d'import** : `DELETE /import/batches/{batch_id}` (ou `/owner/...`) qui supprime
  **uniquement** les entités de ce lot, **avec garde-fous** (confirmation, comptage avant/après,
  refus si des données dérivées existent — récoltes, lots, fiches…).
- UI : page Import → « Historique des imports » avec un bouton **Annuler cet import** (admin) ;
  côté propriétaire, possibilité de purge d'une coop de test.

**Décisions à confirmer** :
- Qui a le droit d'annuler : **admin de la coop** (sur ses propres imports) et/ou **IKAFFANAN** ?
- Comportement si des **données dérivées** existent déjà (récoltes/lots créés à partir de ces
  plantations) : bloquer ? cascader ? (recommandé : bloquer + message clair).
- Profiter de ce chantier pour la **purge** de « Import Test Coop » (id 2) et statuer sur « Coop CAMER ».

**Fichiers** : `app/db/models.py` (Producer/Plantation + `import_batch_id`), `main.py` (migration),
`app/importers/registry_loader.py`, `app/api/import_routes.py`, `frontend/import.html`, tests.

---

## 4. 🧾 Champ « N° de reçu d'achat » manquant dans la saisie Récoltes  ✅ FAIT

**Besoin** : le guide indique de renseigner le **numéro du reçu d'achat** pour relier la récolte au
bon d'achat, mais **le champ n'existe pas** dans le formulaire de saisie Récoltes.

**Constat (confirmé)** :
- Le modèle `Harvest` **possède** `numero_recu_achat` et `nbre_sacs`.
- MAIS le schéma `HarvestCreate` (`app/api/routes.py`) **n'expose pas** ces champs (seulement
  date, quantité, qualité, prix, notes, is_historical) → le formulaire `harvests.html` ne les a pas.
- Le module **Achats** remplit déjà `numero_recu_achat` quand il génère une récolte (cohérent) ;
  c'est **uniquement la saisie manuelle de récolte** qui manque le champ.

**Approche proposée (simple)** :
- Ajouter `numero_recu_achat: Optional[str]` et `nbre_sacs: Optional[int]` à `HarvestCreate`
  + les passer au modèle dans `create_harvest`.
- Ajouter les 2 champs au formulaire `harvests.html`.
- Vérifier la cohérence avec le **guide** `frontend/guide/04_agroforesterie_recoltes.md` (déjà mentionné).

**Fichiers** : `app/api/routes.py` (`HarvestCreate`, `create_harvest`), `frontend/harvests.html`,
`tests/` (test création récolte avec reçu), guide 04 (déjà à jour).

---

## 5. 🎬 Tests E2E + vidéos de démo automatiques (Playwright)  ✅ FAIT (scaffold)

> **Implémenté (session 2026-06-03)** : dossier **`e2e/`** Playwright isolé (Node, n'impacte pas le
> backend Python). 2 specs **vertes** : `smoke.spec.ts` (page de connexion) et **`demo.spec.ts`**
> (parcours `Connexion → Plantation → Producteur → Analyse satellite NDVI réelle → EUDR`, 12 s).
> Stratégie : **setup via API** (compte + parcelle géolocalisée), **parcours via l'UI** (filmé).
> Le frontend de la branche est **servi en local** (port **5510**, déjà dans l'allowlist CORS) et l'API
> **Railway réelle** est injectée via `addInitScript` → teste les fichiers de la branche contre le vrai
> backend, sans dépendre du déploiement Netlify. **Vidéo `.webm` + rapport HTML** générés à chaque run.
> Réutilisable contre le staging Netlify via `AVP_BASE_URL`. Voir `e2e/README.md`.
>
> **Reste à faire (extensions)** : scénarios EUDR complet (tracé → conformité → **DDS PDF**), import +
> annulation de lot, récolte avec n° de reçu ; **GitHub Action** post-déploiement (artefact vidéo) ;
> compte de démo dédié pour éviter les coops jetables `E2E Demo …` (cf. `AVP_TEST_EMAIL`).

<details><summary>Note de conception (avant implémentation)</summary>

**Idée (validée)** : ajouter des tests **end-to-end** qui pilotent un vrai navigateur, pour
(a) **non-régression frontend** (on n'en a aucune aujourd'hui — seulement des smoke tests de présence
de fichiers) et (b) **vidéos de démo** auto-générées pour la vente/LinkedIn.

**Décision d'outil (CTO)** :
- ✅ **Playwright** — recommandé. Compatible avec notre frontend **vanilla** (pilote le navigateur réel).
  Enregistre **vidéo MP4 + captures + trace** nativement. Aurait détecté plusieurs bugs trouvés
  manuellement (import qui disparaît, dropdown vide, passeport non conforme).
- ❌ **Storybook** — non adapté (sert aux composants React/Vue ; on n'en a pas).
- 🟡 **Loom** — enregistrement manuel narré, pour démo commerciale (complémentaire, pas du test).
- 🟡 **Browser Use / OpenHands** — agent IA navigateur : bien pour explorer, mais non déterministe et
  coût LLM par run → **pas pour le CI** ni pour des vidéos reproductibles.

**Approche proposée** :
- Dossier `e2e/` (Node isolé, n'impacte pas le backend Python) avec Playwright.
- Scénario principal : `Connexion → Producteur → Parcelle → Satellite → EUDR → DDS PDF` → vidéo + captures.
- Cible : **staging** (compte de test + clés satellite déjà en place = vraie démo).
- Plus tard : **GitHub Action** post-déploiement (test de non-régression + artefact vidéo).

**Décisions à confirmer** : créer un **compte de test dédié** sur le staging ; accepter l'ajout de
**Node.js** comme outillage de test (isolé) ; où publier les vidéos (artefacts CI / drive).

**Fichiers** : nouveau `e2e/` (package.json, playwright.config, specs), éventuel workflow CI.

</details>

---

## Notes générales pour la reprise
- **Tests** : `python -m pytest -q` (≈480 tests). Frontend : `tests/test_frontend_smoke.py` (badge SW = `map.html`).
- **SW** : bump `CACHE_VERSION` dans `frontend/sw.js` **et** le badge `build …` dans `frontend/map.html` à chaque lot front.
- **Déploiement** : `git push origin HEAD:codex/cacaoguard-fusion` (Railway + Netlify auto). Jamais la prod sans feu vert.
- Points de finition restants (audit) : centraliser `API_BASE` (P3, différé) ; ops (sauvegardes, domaine/HTTPS prod, rotation secrets, page statut).
- Voir aussi `docs/AUDIT_FINITION.md`, `docs/ROADMAP_EVOLUTION.md`, `docs/REPRISE_SESSION.md`.
