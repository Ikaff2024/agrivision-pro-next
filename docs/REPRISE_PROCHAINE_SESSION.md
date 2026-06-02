# Reprise — prochaine session (backlog issu des tests 2026-06-01)

> 4 points à traiter, préparés pour démarrer vite. Pour chacun : **constat** (avec références code),
> **approche proposée**, **décisions à confirmer**, **fichiers concernés**.
> Branche : `codex/cacaoguard-fusion`. Règle d'or : tests verts avant push, push **origin** uniquement.

---

## 1. 🔒 Inscription : seul l'admin crée des comptes sur une coopérative existante

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

## 2. 💰 Estimation du coût API par coopérative sur une période (dashboard propriétaire)

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

---

## 3. 🧹 Corriger un import de producteurs erroné (sans le faire un par un)

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

## 4. 🧾 Champ « N° de reçu d'achat » manquant dans la saisie Récoltes

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

## Notes générales pour la reprise
- **Tests** : `python -m pytest -q` (≈480 tests). Frontend : `tests/test_frontend_smoke.py` (badge SW = `map.html`).
- **SW** : bump `CACHE_VERSION` dans `frontend/sw.js` **et** le badge `build …` dans `frontend/map.html` à chaque lot front.
- **Déploiement** : `git push origin HEAD:codex/cacaoguard-fusion` (Railway + Netlify auto). Jamais la prod sans feu vert.
- Points de finition restants (audit) : centraliser `API_BASE` (P3, différé) ; ops (sauvegardes, domaine/HTTPS prod, rotation secrets, page statut).
- Voir aussi `docs/AUDIT_FINITION.md`, `docs/ROADMAP_EVOLUTION.md`, `docs/REPRISE_SESSION.md`.
