# AgriVision Pro — Document de reprise (handoff)

> **But.** Permettre de reprendre le projet dans une nouvelle session **sans rien perdre** :
> contexte, état actuel, ce qui a été livré, ce qui reste, et les pièges connus.
> Lire aussi : `README.md`, `AGRIVISION_CONTEXT.md`, `docs/SSRTE_GAP_ANALYSIS.md`.

Dernière mise à jour : **2026-05-31** · Branche : **`codex/cacaoguard-fusion`** · Dernier commit : **`4a7f6f6`**.

> **MAJ 2026-05-31** : ✅ backlog **#1** (cloisonnement CacaoGuard par coopérative) **fait** ;
> ✅ backlog **#2 SSRTE COMPLET** : après audit ligne par ligne des 3 PDF officiels, **tous les
> champs des questionnaires** Fiches A/B/C sont capturés (admin, GPS/heures, listes de choix,
> blocs répétables écoles/membres/travailleurs/enfants hors ménage V01-V10, remarques par section,
> affichage conditionnel). Modèle + API + PDF + UI mobile. Reste à confirmer au feedback client.
> ✅ **Mot de passe oublié (SMTP)** : `/auth/forgot-password` + `/auth/reset-password` + pages front
> (lien valable 1 h, usage unique, anti-énumération, fallback admin lockout). Activer en branchant les
> variables `SMTP_*` sur Railway (cf. backlog #4).
> ✅ **Tableau de bord direction** (proposition d'amélioration #5) : `GET /dashboard/direction` +
> `direction.html` — vue exécutive read-only, scopée coopérative (EUDR, enfants, revenu vital,
> volumes/certif, alertes). Voir `docs/ROADMAP_EVOLUTION.md` pour la suite (lots, achats, certif, satellite).
> ✅ **Satellite avancé — abstraction** (#4) : `app/satellite/provider.py` (NDVI/NDMI, séries
> temporelles, déforestation) + endpoints `/satellite/*` + UI avancée. Fallback simulation sans clé,
> bascule auto sur **Copernicus Data Space** (gratuit) via `SENTINEL_CLIENT_ID/SECRET` et
> **Global Forest Watch** via `GFW_API_KEY`. GEE écarté (licence commerciale payante).
> ✅ **Activé et vérifié en live (2026-05-31)** : clés Copernicus + GFW posées sur Railway,
> NDVI/NDMI/séries + alertes déforestation réelles fonctionnelles. Piège : en-tête GFW
> `x-api-key` sensible à la casse (→ `http.client`, pas urllib). Coût : 0 €.
> ✅ **Traçabilité des lots (#1)** : modèles Warehouse/Lot/LotMovement + `Harvest.lot_id`,
> endpoints `/warehouses` `/lots` `/lots/merge` `/lots/{id}/passport` `/lots/{id}/movements`,
> page `lots.html`. Code lot auto, mouvements, fusion, passeport (compo + EUDR + blocages),
> **refus CacaoGuard** si producteur bloqué. Cloisonné coop. 7 tests.
> ✅ **Achats producteurs (#2)** : `PurchaseRecord` (bon d'achat + pesée brut/tare/net + montant),
> génère une récolte traçable (→ lots). Endpoints `/purchases*`, page `achats.html`. Suivi
> paiement **comptable** (pending/paid), pas d'exécution financière (à cadrer). Cloisonné coop. 7 tests.

---

## 1. Règles d'or (À RESPECTER ABSOLUMENT)

- **Remote git** : pousser **uniquement** sur `origin` = **`Ikaff2024/agrivision-pro-next`**.
  ❌ **NE JAMAIS** pousser sur la prod (`AgriVision-Pro`) sans instruction explicite du client.
- **Ne pas toucher la PROD** tant que la version staging n'est pas validée stable.
- Toujours : **tests verts** (`python -m pytest -q`) **avant** un `git push`.

## 2. Environnements

| Élément | Staging (NEXT — où l'on travaille) | Prod (NE PAS TOUCHER) |
|---|---|---|
| Frontend | https://agrivision-pro-next.netlify.app (Netlify) | agri-vision-pro.com |
| Backend API | https://agrivision-api-production.up.railway.app (Railway) | handsome-wisdom-production-d83b.up.railway.app |
| Repo | Ikaff2024/agrivision-pro-next | AgriVision-Pro |
| Base de données | **PostgreSQL** `agrivision-db` (Railway) | (séparée) |

- **Déploiement = automatique au `git push origin HEAD`** : Railway redéploie le backend, Netlify le frontend (~2-3 min).
- **Vérifier la santé** : ouvrir `…railway.app/health` → doit afficher `"database":"postgresql","persistent":true`.
  (Si `"database":"sqlite"` → DATABASE_URL non branché = données éphémères, voir §7.)
- ⚠️ Le **moteur (API Railway)** n'a pas de page d'accueil : ouvrir sa racine `/` affiche `{"detail":"Not Found"}`, c'est **normal**. L'appli s'utilise via l'URL **Netlify**.

## 3. Architecture technique

- **Backend** : FastAPI + SQLAlchemy 2.0 + PostgreSQL. `main.py` exécute des **migrations idempotentes** au démarrage (ALTER TABLE … IF NOT EXISTS) — voir le `lifespan`.
- **Frontend** : HTML/JS **vanilla** (pas de build). `auth.js` est chargé sur toutes les pages (sidebar, refresh de jeton, modal changement de mot de passe). PWA + Service Worker (`sw.js`).
- **PDF** : WeasyPrint + **fallback natif** (pas de dépendance Cairo) dans `app/services/*_reports.py`.
- **Tests** : ~417 tests pytest. Tout vert au commit `4a7f6f6`.

## 4. Commandes utiles

```bash
# Tests (toute la suite)
python -m pytest -q
# Un module
python -m pytest tests/test_cacaoguard.py -q
# Déployer (auto Railway + Netlify)
git push origin HEAD
# Santé du backend staging
#   ouvrir https://agrivision-api-production.up.railway.app/health
# Lire un PDF généré (Windows, local) : pypdfium2 (déjà installé)
```

**Pièges environnement (Windows)** : `bash` n'a pas toujours `grep/find/python` fiables → utiliser les outils dédiés (Grep/Read) ou PowerShell. **WeasyPrint n'est pas installé en local** (Cairo absent) → en test, le fallback PDF est utilisé ; le vrai rendu se fait sur Railway. Le **classifieur de sécurité** bloque les suppressions SQL de masse (normal).

## 5. Ce qui a été livré (session du 30/05/2026)

- 🟢 **Persistance des données** : PostgreSQL branché (fin de la perte au F5 / recréation de compte). `/health` enrichi.
- **Plantations** : producteur auto-créé/lié à la création ; **édition** d'une plantation (`PUT /plantations/{id}` + bouton « Modifier »).
- **Évaluation risque** : filtre **producteur → enfants** (évite de défiler des milliers d'enfants).
- **Auth** : refresh proactif du jeton (anti-déconnexion 2 h) ; **changer son mot de passe** (icône clé, tous rôles) ; rappel : réinitialisation par admin déjà existante (`PUT /admin/members/{id}/reset-password`).
- **EUDR-01b** : 6ᵉ règle « pas de déforestation post-2020 » (modèle `DeforestationCheck`, endpoint, UI, DDS) ; méthodologie **`eudr-1.1b`** (score /6).
- **Agroforesterie** : validation densité > 0 + âge des arbres persisté/utilisé (calcul carbone).
- **FarmForce / Livret de suivi** : vivrier/élevage, dépenses ménage, **revenu net**, **verdict revenu vital** (seuil `LIVING_INCOME_BENCHMARK_CFA`), édition, **PDF**, import Excel (déjà présent).
- **SSRTE** : Fiches A/B/C avec saisie structurée (membres, enfants, tâches dangereuses **en cases à cocher tactiles**), alertes + blocage, et **3 PDF**.
- **Import registre** Fairtrade (`/import/excel`) : **déjà implémenté**, validé sur serveur (≈7000 producteurs en ~45 s, pas de timeout). UI : page `import.html` / Administration.
- **Filtre technicien** : un technicien ne voit que ses parcelles + filtre « Mes plantations attribuées » — **déjà implémenté**.
- **PDF** : DDS, Livret, Fiches A/B/C alignés sur la charte du rapport plantation.
- **Guide client mis à jour** : `OneDrive/Documents/AgriVision_Pro_Guide_Client_MAJ_Mai2026.docx` (+ `.pdf`).

## 6. RESTE À FAIRE (backlog priorisé)

1. ✅ **FAIT (2026-05-31) — Cloisonnement des rapports CacaoGuard par coopérative** (bug multi-tenant).
   Les compteurs sont **globaux** au lieu d'être limités à la coopérative de l'utilisateur
   (ex. la page Rapports affiche ~7000 producteurs alors que la coop n'en a qu'un).
   - Fichiers : `app/api/cacaoguard_routes.py` → `get_cacaoguard_summary` ;
     `app/api/cacaoguard_ops_routes.py` → `build_due_diligence_report` (+ endpoints `/compliance/report` et `.pdf`).
   - Scoper par `cooperative_id` (sous-requêtes `Producer.id` / `Plantation.id`).
     ⚠️ **`Alert` n'a pas de `producer_id`** (polymorphe `source_entity`/`source_id`) → laisser global ou résoudre la source.
   - Gérer `cooperative_id=None` (tests appellent sans auth) : soit fallback global, soit ajouter l'auth aux tests (`tests/test_cacaoguard.py`).
   - **Une tentative a été faite puis ANNULÉE** (`git checkout`) car non finalisée → repartir propre. Une **puce de tâche** a été créée pour ça.

2. **🟠 SSRTE — compléter les fiches** (voir `docs/SSRTE_GAP_ANALYSIS.md`) :
   - ✅ **COMPLET (2026-05-31)** : audit des 3 PDF officiels puis couverture de **tous** les champs.
     P1 (écoles/exploitation/adultes-travailleurs), P2 (origine élec, distance eau, noms orgs, classes
     secondaires, GPS/heures) et P3 (admin : fournisseur, sous-préfecture, codes agent, code SSRTE) **faits**.
     \+ enfants hors ménage V01-V10 (Fiche C), statut de visite (Fiche B), remarques par section, UI conditionnelle.
     Modèle + API + PDF + UI mobile. **À valider au feedback client** (granularité remarques, libellés de choix).

3. **🟡 EUDR-01b — détection déforestation automatique** : le **cadre** est fait ; il manque la **source satellite** (Hansen Global Forest Change / Global Forest Watch via Google Earth Engine) → nécessite **clés API / quotas** à fournir.

4. **🟡 Mot de passe oublié par email** (self-service à la connexion) : nécessite un **service SMTP**. Couvre le cas de l'**admin unique** en lockout. (Contournement actuel : avoir 2 admins par coop.)

5. **🧹 Nettoyage des données de test** : la coopérative **« Import Test Coop » (id 2)** contient ~7000 producteurs/plantations de test (l'import a été validé dessus). Inoffensif (isolé), mais visible dans le rapport non cloisonné (cf. point 1). Suppression bloquée par le garde-fou de sécurité → nécessite **go explicite**. La coop **1 « Copa Cabana »** est la vraie donnée de test du client — **ne pas y toucher**.

6. **🔐 Rotation du mot de passe PostgreSQL** : l'URL de connexion (`DATABASE_PUBLIC_URL`) a transité par le chat lors d'un diagnostic → **régénérer le mot de passe** dans Railway (`agrivision-db` → Settings/Variables) ; `DATABASE_URL` se met à jour automatiquement.

7. **📱 Polish mobile** ciblé après tests terrain réels (tracer polygone EUDR au doigt, tableaux denses).

8. **🚀 Promotion vers PROD** : préparer une **checklist** (sauvegarde DB prod, diff migrations, ordre de déploiement, points de vigilance). **Uniquement sur feu vert explicite du client.**

## 7. Configuration Railway (rappel critique)

Le backend bascule sur **SQLite éphémère** si `DATABASE_URL` n'est pas défini → **données perdues à chaque déploiement**. Sur le service `agrivision-api` :
- Variable **`DATABASE_URL`** = l'URL **interne** de la base (`postgresql://…@agrivision-db.railway.internal:5432/railway`).
- Variables utiles : `LIVING_INCOME_BENCHMARK_CFA` (défaut 2 360 000), `ALLOWED_ORIGINS`, `ACCESS_TOKEN_EXPIRE_MINUTES` (120), `SECRET_KEY`.

## 8. Pièges & décisions connus

- **1er inscrit d'une coopérative = Administrateur forcé** (les suivants prennent le rôle demandé, sauf admin).
- **Multi-tenant par `cooperative_id`** : producteurs/plantations correctement cloisonnés ; **rapports CacaoGuard NON** (cf. backlog #1).
- **Service Worker** : `skipWaiting()` + `clients.claim()` → les déploiements s'activent sans fermer tous les onglets. Un **badge de version** est affiché en bas de `map.html`.
- **EUDR** : méthodologie `eudr-1.1b`, score **/6**, conforme ≥ 80 %.
- **Producteurs créés automatiquement** depuis `owner_name` à la création/édition d'une plantation (`_find_or_create_producer`).

## 9. Carte des fichiers clés

```
main.py                              # app FastAPI + migrations au démarrage
app/db/database.py                   # DATABASE_URL → Postgres / fallback SQLite
app/db/models.py                     # Plantation, Producer, Diagnostic, Harvest,
                                     #   PlantationBoundary, DeforestationCheck, AgroforestryRecord, FarmForceAssessment…
app/db/models_social.py              # CacaoGuard/SSRTE : Child, Alert, MonitoringVisit,
                                     #   RemediationPlan, TraceabilityBlock, Ssrte*Profile/Visit…
app/auth/auth_routes.py              # register/login/refresh/change-password
app/api/routes.py                    # plantations (CRUD), diagnostic, agroforesterie, admin members
app/api/eudr_routes.py               # score EUDR, DDS PDF, contrôle déforestation
app/api/farmforce_routes.py          # livret de suivi + revenu vital + PDF + import Excel
app/api/ssrte_routes.py              # Fiches A/B/C + PDF
app/api/cacaoguard_routes.py         # /cacaoguard/summary  (⚠ non cloisonné)
app/api/cacaoguard_ops_routes.py     # due-diligence report (⚠ non cloisonné), monitoring, remediation
app/api/import_routes.py             # /import/excel (registre coopérative)
app/importers/cooperative_registry.py + registry_loader.py   # parsing + chargement du registre
app/services/*_reports.py            # génération PDF (eudr, farmforce, ssrte, reports)
app/templates/*_report.html          # gabarits PDF
frontend/*.html + auth.js + sw.js    # interface (vanilla)
docs/SSRTE_GAP_ANALYSIS.md           # écarts détaillés des fiches SSRTE
```
