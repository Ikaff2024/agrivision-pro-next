# AgriVision Pro — Contexte de reprise de session

> **Pour l'utilisateur** : upload ce fichier au début de toute nouvelle session Claude pour reprendre le projet sans perte de contexte.
> **Date du dernier commit** : 3 mai 2026
> **Statut global** : Sprint Reports R1 100% livré. Sprint Honnêteté-Offline livré (mitigation). Sprint Offline V1.6 EN COURS (Phases 1-2 livrées en prod, Phases 3-6 à venir). Production stable.

---

## 🎯 Qui je suis et ce que je fais

Je m'appelle **YEO ISSA**, propriétaire de **IKAFFANAN LTD** (Côte d'Ivoire). Je construis **AgriVision Pro**, une plateforme SaaS de gestion agronomique pour coopératives cacaoyères ivoiriennes (extension Afrique prévue : Cameroun, Ghana, Nigeria).

**Mon rôle** : business owner non-technique. Je délègue toutes les décisions techniques à Claude qui agit comme **CTO virtuel autonome** ("C'est toi le lead").

**Mes préférences de travail** (à respecter absolument) :
- Je n'édite JAMAIS le code à la main
- Depuis Sprint Reports R1 : **scripts Python purs** lancés via `python script.py` sont préférés aux blocs PowerShell complexes (les heredocs PS imbriqués cassent l'échappement des guillemets)
- **Backup auto** avant chaque modification de fichier
- **Vérifications systématiques** après modif (mojibake check + éléments présents)
- **Tag Git** avant chaque sprint sensible
- **Tester en prod avant commit**, jamais l'inverse
- Recommandations claires (1 voie unique), pas de menus à options
- Explications sans jargon — je suis non-technique
- ⚠️ **Important** : je commite parfois en autonomie sans envoyer de capture. **Toute nouvelle session doit commencer par `git log --oneline -10`** pour voir l'état réel.

---

## 🏗️ Stack en production

| Composant | Tech | URL |
|---|---|---|
| Backend | FastAPI + PostgreSQL | `https://handsome-wisdom-production-d83b.up.railway.app` |
| Frontend | HTML/JS vanilla PWA + IndexedDB (V1.6) | `https://agri-vision-pro.com` |
| ML | EfficientNet-B0 sur HF Space | `https://ikaff2026-agrivision-plant-disease.hf.space` |
| GitHub | Repo (renommé majuscules) | `https://github.com/Ikaff2024/AgriVision-Pro` |
| Domaine | Cloudflare DNS | agri-vision-pro.com |
| Déploiement | Railway (auto sur push main, Dockerfile) + Netlify (drag&drop manuel) | — |

⚠️ **Note remote git** : le remote local pointe encore sur l'ancienne URL minuscules `agrivision-pro` (chaque push retourne un message "This repository moved"). À corriger un jour : `git remote set-url origin https://github.com/Ikaff2024/AgriVision-Pro.git`

**Auth** : JWT avec refresh token, multi-tenant par coopérative (`coop_id` dans le token), 4 rôles : admin / agronomist / technician / viewer.

---

## ✅ Modules fonctionnels en production

1. **Authentification** : login, register, refresh token, JWT (désactivée - accès libre)
2. **Protection de l'enfant (CacaoGuard)** : gestion des enfants, évaluation des risques, alertes, statistiques
2. **Plantations** : CRUD, GPS, plant_count, propriétaire — **garde-fou superficie 0.25 ≤ ha ≤ 500** (R1d)
3. **Diagnostics agronomiques** : 4 modules (maladies, âge, pluviométrie, ombrage), score global, historique
4. **Recommandations actionables** : `recommendations.py` avec priorités Urgent/Important/Conseil
5. **Agroforesterie** : inventaire d'espèces, calcul carbone (tCO₂/ha), score conformité
6. **NDVI Satellite** : Sentinel-2 via Statistical API + **interprétation Anti-Détracteur** (R1d)
7. **Météo automatique** : Open-Meteo (gratuit, sans clé)
8. **Détection ML maladies** : photo cabosse → prédiction via Hugging Face (4 classes : healthy, phytophthora, monilia, black_pod)
9. **Conseil Agronome IA** : LLM analysant le tout (le bouton "Pro")
10. **Dashboard coopérative** : KPIs agrégés, top plantations
11. **Carte** : visualisation géo des plantations
12. **Module Récoltes** (Phase 1 livrée le 25/04/2026)
13. **Rapport PDF de plantation** (Sprint Reports R1, livré le 28/04, finalisé 02/05/2026)
14. **Garde-fous Anti-Détracteur** (Sprint R1d, livré 01/05/2026)
15. **Bandeau réseau honnête** (Sprint Honnêteté-Offline, livré 03/05/2026)
16. ⏳ **Mode offline (lecture)** (Sprint V1.6 Phases 1-2 livrées 03/05/2026, Phases 3-6 à venir)

---

## 🌾 Module Récoltes — Détail technique (Phase 1)

### Backend (commit `a10fe90`)
- **Modèle SQLAlchemy `Harvest`** dans `app/db/models.py` :
  - Champs : id, plantation_id (FK), harvest_date, quantity_kg, quality (Bonne/Moyenne/Defauts), price_per_kg_fcfa, season (auto), notes, is_historical, created_at, created_by_user_id
  - Relation cascade delete-orphan côté Plantation
- **5 endpoints REST** dans `app/api/routes.py` :
  - `POST /plantations/{id}/harvests` (admin/agronomist)
  - `GET /plantations/{id}/harvests` (filtres `?year=` `?season=`)
  - `GET /plantations/{id}/harvests/stats`
  - `PUT /harvests/{id}` (admin/agronomist)
  - `DELETE /harvests/{id}` (admin uniquement)
- **Helpers** : `compute_season(date)` retourne "grande" (oct-jan), "petite" (avr-juin), "intersaison" (autres)
- **Tests** : `tests/test_harvests.py` — 59 tests pytest, tous verts

### Frontend (commit `fa2d226`)
- **Carte résumé "Récoltes"** sur `plantation_detail.html`
- **Page `harvests.html`** complète (611 lignes)
- **Sidebar** : nouveau lien "Recoltes"
- **Service Worker** : bumpé à `avp-v2.7`

---

## 📄 Sprint Reports R1 — Détail technique (livré 28/04, finalisé 02/05/2026)

### R1a — Backend PDF (`0b85c7e` puis `c2187b1`)
- `app/services/__init__.py` + `app/services/reports.py` (Jinja2 + WeasyPrint)
- `app/templates/plantation_report.html` (6 pages, design AgriVision vert+jaune, A4 portrait)
- Endpoint `GET /plantations/{plantation_id}/report.pdf` — admin/agronomist only, multi-tenant cooperative isolation, StreamingResponse + filename UTF-8 RFC5987
- 8 tests dans `tests/test_reports.py` (mock WeasyPrint via `sys.modules`)
- `requirements.txt` augmenté : `weasyprint==63.1`, `jinja2==3.1.4`

### R1a-fix1 — Bascule Dockerfile (`4605c22`)
- Problème : `nixpacks.toml` n'installait pas fiablement Cairo/Pango → `OSError` au runtime
- Solution : `Dockerfile` explicite `python:3.12-slim-bookworm` avec apt-get install des libs

### R1a-fix2 — Recommandations vides (`c2187b1`)
- Bug : `reports.py` appelait `build_recommendations()` avec kwargs inventés
- Fix : aligner sur la signature exacte (`module_results=[], inputs={}, global_score, global_risk`)

### R1b — Bouton frontend "Générer PDF"
- Bouton `btn-outline`, visible admin/agronomist, fonction `downloadPlantationReport()`

---

## 🛡️ Sprint R1d — Garde-fous Anti-Détracteur (livré 01/05/2026, finalisé 02/05)

**Problème métier** : Un détracteur peut décrédibiliser le produit en créant une "plantation" sur sa maison (ex: 0.0025 ha avec coordonnées GPS de domicile) et obtenir un diagnostic agricole absurde sur un toit en tôle.

### 3 niveaux de défense livrés

#### Niveau 1 — Validation Pydantic superficie
- `PlantationCreate.hectares = Field(None, gt=0.25, le=500)`

#### Niveau 2 — Helper `_interpret_ndvi(ndvi)` dans `app/api/routes.py`

```python
def _interpret_ndvi(ndvi: float) -> dict:
    if ndvi <= 0.35:    # R1d-fix2 : étendu de 0.30 à 0.35 (couvre 0.304 réel de la maison du PO)
        return {"status": "CRITICAL_LOW", "label": "Indéterminée",
                "confidence": "low", "message": "Le satellite Sentinel-2 mesure..."}
    if ndvi <= 0.50:
        return {"status": "STRESSED", "label": "Stressée", "confidence": "high", "message": None}
    if ndvi <= 0.70:
        return {"status": "MODERATE", "label": "Modérée", "confidence": "high", "message": None}
    return {"status": "HEALTHY", "label": "Saine", "confidence": "high", "message": None}
```

Endpoints satellite enrichis : `/plantations/{id}/satellite` + `/satellite/ndvi` retournent `ndvi_label`, `confidence`, `warning_message`.

#### Niveau 3 — UI / PDF
- **`frontend/satellite.html`** : `showResult(data)` → bandeau jaune si `data.confidence === 'low'`
- **PDF** : encart `{% if ndvi_warning %}` avant les recommandations

### Tests R1d : 17 tests dans `tests/test_anti_detractor.py` — tous passants

### Itérations du sprint

| Commit | Date | Contenu |
|---|---|---|
| `db77a5c` | 29/04 | R1d initial |
| `7020269` | 01/05 | R1d-fix1 : seuil inclusif `<= 0.30` |
| `4ab5f9f` | 02/05 | (chore) suppression Guides obsolètes + UX map.html |
| (fix2)    | 02/05 | R1d-fix2 : seuil étendu à `<= 0.35` |
| `73fb685` | 02/05 | R1c-1+2 : restoration accents français + .gitignore enrichi |

---

## 🧹 Sprint R1c — Finalisation (livré 02/05/2026)

- **R1c-1** : Restoration accents français dans `_interpret_ndvi`
- **R1c-2** : Enrichissement du `.gitignore`
- **R1c-3** : Update de ce fichier `AGRIVISION_CONTEXT.md`
- **R1c-5** : Guide Utilisateur v1.4 → v1.5

**Tag git de clôture** : `sprint-r1-complete-2026-05-02`

---

## 🌐 Sprint Honnêteté-Offline (livré 03/05/2026, commit `5b98760`)

**Problème observé en prod** : en mode avion, le shell de l'app se charge depuis le SW cache et la liste des plantations s'affiche, MAIS cliquer sur n'importe quelle plantation déclenche *"Erreur de chargement"* sans contexte. Crée une **fausse impression de mode offline** qui dégrade la confiance.

**Solution mitigation** (avant de livrer un vrai mode offline) :

1. **`authFetch()` catch handler** différencie par `navigator.onLine` :
   - Offline : *"Hors ligne — Reconnectez-vous pour accéder à vos données."*
   - Server down : *"Serveur inaccessible. Réessayez dans un instant."*

2. **Nouvelle fonction `setupNetworkBanner()`** dans `auth.js` :
   - Bandeau jaune persistant en haut quand `navigator.onLine === false`
   - Events `online`/`offline` pour mises à jour instantanées
   - Appelée comme première ligne de `initApp(page)`

Le Guide Utilisateur v1.5 indique déjà *"AgriVision Pro nécessite une connexion internet. Mode hors ligne natif prévu V2."* → ce commit aligne le comportement de l'app sur la promesse documentée.

---

## ⚙️ Sprint Offline V1.6 — EN COURS (démarré 03/05/2026)

**Décision stratégique CTO** : passer du Sprint Honnêteté-Offline (mitigation) à un **vrai mode offline complet**, parce qu'en zones cacao ivoiriennes, **80% du temps en plantation est sans réseau**. Le mode offline n'est PAS un nice-to-have, c'est le **différenciateur produit central**.

### Niveau visé : 🥈 Niveau 2 — Lecture + écriture offline + synchro auto
- L'agronome peut **consulter** une fiche plantation en plantation (lecture)
- L'agronome peut **saisir** un nouveau diagnostic offline (écriture)
- L'app **synchronise automatiquement** au retour de connexion
- Indicateur visuel : *"X saisies en attente de synchro"*
- Pas d'app native pour l'instant (Niveau 3 reporté V2)

### 4 décisions techniques validées

| Décision | Choix |
|---|---|
| **A** Stratégie cache lectures | **A2 — Stale While Revalidate** (cache immédiat + refresh background) |
| **B** Identifiants saisies offline | **B1 — UUID v4** (`local_xxxxxxxx`) |
| **C** Erreurs de synchro | **C2 — Skip and continue** (l'erreur reste en queue, les autres passent) |
| **D** Photos offline | **D1 — Compression auto** (800px max, JPEG 70%, ~150 KB/photo) |

### Phases du sprint

| Phase | Statut | Date | Livrable |
|---|---|---|---|
| **P1** Module IndexedDB centralisé (`avp-offline.js`) | ✅ **Livré + testé en prod** | 03/05/2026 | `frontend/avp-offline.js` (467 lignes), `window.AVPOffline` exposé, IndexedDB `avp_offline_db` v1 avec 4 stores |
| **P2** Page Plantations en mode offline (SWR) | ✅ **Livré, à valider en mode avion** | 03/05/2026 | `plantations.html` modifié : `load()` utilise `AVPOffline.cacheGet/cacheSet` + empty state offline |
| **P3** Pages détail offline (plantation_detail, diagnostic, agroforestry, harvests) | ⏳ À venir | — | ~1 jour de dev |
| **P4** Saisie offline + queue de synchro (le cœur) | ⏳ À venir | — | ~2 jours de dev — **Phase la plus risquée** |
| **P5** Endpoint backend `/sync/batch` + idempotence | ⏳ À venir | — | ~0.5 jour de dev |
| **P6** UI synchro + tests E2E mode avion documentés | ⏳ À venir | — | ~1 jour de dev |

**Effort total estimé** : 6 jours de dev. **Décision timing : 🅱️ — démarrer pilote en parallèle**, livrer le mode offline pendant les 3 mois pilote (devient un événement à mi-parcours pour les coops).

### Module `AVPOffline` — API publique exposée

```javascript
window.AVPOffline = {
  // Lectures
  swrFetch(endpoint, options),       // Stale-While-Revalidate
  cacheGet(endpoint),                // Récupérer depuis cache
  cacheSet(endpoint, data),          // Forcer mise en cache
  
  // Écritures (Phase 4 et plus)
  enqueueWrite(method, endpoint, body, label),
  getQueue(), getQueueStats(), syncQueue(),
  
  // Photos (Phase 4)
  compressImage(blob, 800, 0.7), savePhoto, getPhoto, deletePhoto,
  
  // Utilitaires
  getStats(), clearAll(), isReady,
};
```

### Auto-sync sur événement `online`

Le module écoute `window.addEventListener('online', ...)` et déclenche `syncQueue()` automatiquement. Toast utilisateur si helper `window.toast` disponible : *"X saisie(s) envoyée(s) au serveur."*

---

## 📜 Historique récent des commits (à connaître)

```
5b98760  fix(network): honest offline messaging instead of fake offline mode
73fb685  chore: restore French accents in NDVI helper + enrich .gitignore (R1c)
4ab5f9f  chore: cleanup obsolete docs and UX micro-fix in map.html
7020269  fix(safety): NDVI threshold inclusive (Sprint R1d-fix1)
db77a5c  feat(safety): add Anti-Detractor safeguards (Sprint R1d)
207691c  fix: satellite — statut CRITICAL NDVI + bouton GPS coordonnées
c2187b1  fix(reports): correct build_recommendations() signature in PDF generation
0b85c7e  feat(reports): add PDF download endpoint + WeasyPrint + 8 tests
4605c22  fix(infra): switch from nixpacks to Dockerfile for Cairo/Pango reliability
dd70c75  fix(encoding): ftfy mass-fix of 1639 unicode mojibakes
6bce6ff  fix(encoding): byte-level fix of 179 mojibakes in routes.py
96907c9  feat: AgriVision Pro v1.0.0
d97be0b  Merge feature/harvests-frontend: Phase 1 Recoltes - frontend complet
fa2d226  feat(harvests): full frontend module
a10fe90  feat(harvests): add Harvest model + 5 REST endpoints + 59 tests
```

**Tags Git de backup en place** :
- `backup-before-density-2026-04-23`
- `backup-before-harvests-2026-04-24`
- `backup-before-encoding-fix-2026-04-25`
- `backup-before-harvests-frontend-2026-04-25`
- `backup-before-r1a-fix2-2026-04-28`
- `backup-before-r1d-2026-04-29`
- ⭐ **`sprint-r1-complete-2026-05-02`** (clôture officielle Sprint R1)

---

## 🎯 INSIGHTS STRATÉGIQUES (audit du 03/05/2026)

> Suite à un audit des fichiers projet (notamment `CacaoPilot_OS` et `Swollen_shoot`), 5 insights majeurs ont été identifiés. **Ces documents sont à garder en référence active** — pas à laisser dormir.

### Insight 1 — Le pricing actuel est sous-évalué d'un facteur 15-25x

**Aujourd'hui** : Starter 10€, Pro 25€, Cooperative 100€ par mois.

**Recommandation `CacaoPilot_OS`** (alignée marché concurrentiel Farmforce/Sourcetrace) :
- Tier 1 "Essentiel Coop" : **150-300€/mois** (15x)
- Tier 2 "Traçabilité Pro" : **600-1500€/mois** (24x)
- Tier 3 "EUDR Enterprise" : **2500-5000€/mois** (25x)

**Pourquoi cet écart est légitime** : la cible business (coop avec budgets ONG/GIZ/certifications), pas particulier. EUDR change la donne — une coop non-conforme perd des **millions €**, payer 600€/mois est de l'achat de survie.

**Action** : Garder les 3 mois pilote gratuits, **revoir le pricing avant la fin du pilote** (cf ticket `FEATURE-PRICING-01`).

### Insight 2 — EUDR est l'angle de vente N°1

**Date butoir EUDR** :
- **30 décembre 2026** pour les grandes entreprises
- **30 juin 2027** pour les PME

Il reste **~7 mois** avant la 1ère deadline. Timing parfait : assez pour vendre l'urgence, pas assez pour que les coops soient déjà équipées.

**Modules manquants aujourd'hui dans AgriVision Pro** :
- ❌ Score EUDR par parcelle
- ❌ Chaîne de custody (récoltes → lots → livraisons)
- ❌ Export DDS (Due Diligence Statement)
- ❌ Polygones de parcelles (juste des points GPS aujourd'hui — Leaflet.draw existe mais sous-utilisé)

**Action** : EPIC `FEATURE-EUDR-01` à planifier après Sprint Offline V1.6.

### Insight 3 — Le Sprint Offline V1.6 est validé stratégiquement

`CacaoPilot_OS` mentionne explicitement *"PWA offline-first, stockage local IndexedDB, synchronisation différée"* comme **différenciateur clé**. Ce qu'on construit en V1.6 est aligné.

**Mais** : le doc ajoute *"résolution de conflits"* qu'on n'a pas dans notre plan actuel (notre stratégie : "skip and continue"). À traiter post-V1.6 (cf ticket `FEATURE-OFFLINE-CONFLICT-01`).

### Insight 4 — WhatsApp / vocal pour adoption locale

Citation `CacaoPilot_OS` : *"Beaucoup d'utilisateurs ne veulent pas saisir de longs formulaires. Résumé vocal ; notifications WhatsApp ; assistant vocal simple ; français simple."*

WhatsApp = 95%+ des smartphones en CI. Mode vocal en français ivoirien rendrait l'app accessible aux agents non-lettrés. **Feature post-pilote, à mentionner en démo comme roadmap.**

### Insight 5 — Module ML Swollen Shoot manquant (critique)

Le modèle ML actuel couvre 4 classes (healthy, phytophthora, monilia, black_pod). **Le CSSVD (Cocoa Swollen Shoot Virus Disease) n'y est pas**. Or c'est **la maladie #1 du cacao en Côte d'Ivoire** (200 000 ha infectés selon CCC, sujet politique national).

Si une coop pilote demande *"L'IA détecte-t-elle le Swollen Shoot ?"* → réponse "non" = point faible compétitif majeur.

**Solution identifiée** dans `Swollen_shoot` : dataset **KaraAgroAI** (17 703 images, 3 classes incluant CSSVD), papier arXiv 2024 reproductible, alternative Roboflow.

**Action** : ticket `FEATURE-ML-CSSVD-01` post-pilote (3-5 jours d'effort).

### Insight 6 — Repositionnement nominal pas urgent

`CacaoPilot_OS` propose : `AgriVision Pro = module diagnostic` + `CacaoPilot OS = plateforme complète`. **Pas urgent** de renommer maintenant. **Garder AgriVision Pro** comme nom de plateforme jusqu'à un repositionnement business clair (post-pilote, après vraie traction).

---

## 🐛 Tickets ouverts (backlog)

### Tickets techniques pré-existants

| ID | Titre | Sévérité | Notes |
|---|---|---|---|
| **BUG-AGRO-01** | Validation Pydantic agroforestry `count_per_hectare > 0` + calcul carbone par âge | Moyenne | 3 tests pytest en failure permanente. Pré-existant. |
| **BUG-DIAG-01** | Score 25/100 mais `risk_level` "Faible" — recalibrage moteur | Moyenne | Observable dans tous les PDFs générés. |
| **BUG-RECO-01** | Endpoint `/diagnostics/{id}/recommendations` passe `shade=None` et `age=None` au lieu d'utiliser les valeurs DB | Faible | Découvert en R1a-fix2. |
| **BUG-DETAIL-01** | Erreur JS *"Cannot read properties of undefined (reading 'detail')"* sur diagnostic.html en mode hors ligne | Faible | À corriger pendant Sprint Offline V1.6 Phase 3. |
| **BUG-OFFLINE-01** | Mode offline annoncé partiel (mitigation R1 livrée, vrai offline V1.6 en cours) | ✅ En traitement | Sprint Offline V1.6 |
| **FEATURE-GPS-01** | Validation bbox géographique par pays (CI lat [4.3, 10.8], lon [-8.6, -2.5]) | Faible | Niveau 3 du R1d, différé. |
| **CHORE-REMOTE-01** | Renommer le remote git pour pointer sur l'URL avec majuscules | Très faible | Bruit cosmétique. |

### ⭐ Tickets stratégiques NOUVEAUX (suite audit `CacaoPilot_OS` + `Swollen_shoot`)

| ID | Titre | Sévérité | Source | Timing | Effort |
|---|---|---|---|---|---|
| **FEATURE-EUDR-01** (EPIC) | Module EUDR : polygonisation parcelles + score conformité par parcelle + export DDS PDF + chaîne custody | **🔴 Très Haute** | `CacaoPilot_OS` | Après Sprint Offline V1.6 | 2-3 semaines |
| **FEATURE-PRICING-01** | Revoir grille tarifaire : passer de 10/25/100€ à 150/600/2500€ avant fin du pilote | **🔴 Haute (business)** | `CacaoPilot_OS` | Avant fin du pilote | 1 jour (doc commercial) |
| **FEATURE-ML-CSSVD-01** | Étendre le modèle ML pour détecter le Swollen Shoot (5e classe) avec dataset KaraAgroAI | 🟠 Haute | `Swollen_shoot` | Post-pilote | 3-5 jours |
| **FEATURE-CHAIN-CUSTODY-01** | Chaîne de custody : Lots + Livraisons (extension Récoltes vers EUDR) | 🟠 Haute | `CacaoPilot_OS` | Après EUDR | 1 semaine |
| **FEATURE-OFFLINE-CONFLICT-01** | Résolution de conflits dans la synchro offline (`last_modified_at` + détection serveur) | 🟡 Moyenne | `CacaoPilot_OS` | Après Sprint Offline V1.6 | 1 jour |
| **FEATURE-WHATSAPP-01** | Notifications WhatsApp pour alertes urgentes + résumés vocaux | 🟡 Moyenne | `CacaoPilot_OS` | V2 | 1-2 semaines |

---

## 📋 Roadmap restante (priorisée)

### 🔴 Sprint en cours — Sprint Offline V1.6
**Démarré 03/05/2026**, Phases 1-2 livrées en prod. Phases 3-6 à venir (~4-5 jours de dev restants).

### 🔴 Sprint suivant — EPIC EUDR (`FEATURE-EUDR-01`)
**Très haute priorité business**. Décomposition :
1. Polygonisation des parcelles (Leaflet.draw existant, à exploiter sérieusement)
2. Croisement géo avec carte forêt 2020 (Hansen Global Forest Change accessible publiquement)
3. Score EUDR par parcelle (algo similaire à `_interpret_ndvi`)
4. Chaîne de custody : extension Récoltes → Lots → Livraisons
5. Export DDS PDF (réutilise WeasyPrint)
**Estimation : 2-3 semaines**

### 🟡 Sprint R2 — Conseil Agronome IA dans le PDF
- Endpoint existant : `POST /plantations/{id}/ai-advice` (utilise `anthropic==0.40.0`)
- Considérations : gating tier (Pro+ uniquement), cache, fallback gracieux, latence (3-8s → 15-25s)
- **Estimation : 2-3h**

### 🟡 Sprint Pricing & Démos
- Refonte commerciale (Insight 1) : passage à 150/600/2500€/mois
- Préparation slides EUDR pour les démos (Insight 2)
- **Estimation : 1-2 jours non-tech**

### 🟢 Sprint ML CSSVD (`FEATURE-ML-CSSVD-01`)
- Téléchargement dataset KaraAgroAI (17 703 images)
- Augmentation + fine-tuning EfficientNet-B0 (5 classes)
- Tests + déploiement HF Space
- **Estimation : 3-5 jours**

### 🟢 V2 — Améliorations différées
- WhatsApp notifications + vocal (`FEATURE-WHATSAPP-01`)
- App native Android via Capacitor.js (Niveau 3 offline)
- **Cloudinary** pour le stockage images
- **Ratio prorata temporis** pour la barre de progression des récoltes

### 🟢 Avant le premier client payant
- **Railway upgrade** Hobby ($5/mois) → Pro ($20/mois)
- Mise à jour du `Guide_Client.docx` avec sections EUDR + Mode offline

---

## 💼 Modèle business (en cours de révision suite à l'audit)

### Pricing actuel (V1)
- **Starter** 10€/mois, **Pro** 25€/mois, **Coopérative** 100€/mois

### Pricing recommandé V2 (post-pilote, cf `FEATURE-PRICING-01`)
- **Essentiel Coop** : 150-300€/mois
- **Traçabilité Pro** : 600-1500€/mois
- **EUDR Enterprise** : 2500-5000€/mois ou contrat annuel

### Cibles
- 2 premiers clients coopératives : **3 mois pilote gratuit**
- Chemin vers 100K€ ARR : **20 coopératives à 300-800€/mois OU 3-5 contrats institutionnels annuels** (cf `CacaoPilot_OS`)
- **Démos** : via Microsoft Teams screen-sharing, 8 étapes sur ~20-25 min

---

## 🤖 Pour Claude — comportement attendu

1. **Si la session démarre par "On reprend AgriVision"** : confirmer le contexte avec `git log --oneline -10` puis demander où on en est, proposer un plan d'action
2. **Avant tout sprint sensible** : créer un tag Git de backup
3. **Avant toute modif de fichier** : créer un `.backup` local
4. **Après toute modif** : vérifier mojibake + éléments ajoutés
5. **Avant tout commit** : tester en prod
6. **Pour tout patcher de code** : Python pur > PowerShell complexe (cf. Pattern 1 ci-dessous)
7. **Tu commits parfois en autonomie** : envoyer une capture après commit
8. **Pour les fichiers à demander** : `frontend/auth.js` (design system), `frontend/avp-offline.js` (module offline V1.6), `frontend/plantation_detail.html` (patterns fiche détail), `app/api/routes.py` (source de vérité backend)
9. **Mon environnement** : Windows 10/11, PowerShell, navigateur Edge, dossier projet `C:\Users\YEO ISSA\Agrivision_ Pro\`
10. **Style des réponses** : tableaux + checkmarks visuels, plans d'action numérotés clairs, blocs PowerShell prêts à coller (mais pas trop complexes), diagnostics visuels, ton sérieux mais chaleureux, emojis pertinents (🎯 ✅ ⚠️ 🌱 🛡️)
11. **Si un fichier important n'a pas été regardé depuis longtemps** : le re-vérifier proactivement (ex: `CacaoPilot_OS` qui est resté inexploité plusieurs semaines)

---

## ⚠️ Pièges connus à éviter absolument

### 1. PowerShell + UTF-8
- **JAMAIS** `Set-Content -Encoding UTF8` (cause double-encodage et mojibake)
- **TOUJOURS** :
  ```powershell
  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText((Resolve-Path $file).Path, $content, $utf8NoBom)
  ```

### 2. PowerShell + apostrophes/guillemets
- **NE PAS** utiliser de heredocs PowerShell imbriqués avec `\"` qui s'échappent mal
- **PRÉFÉRER** des **scripts Python purs** lancés via `python script.py` (avec backup et rollback intégrés)

### 3. Service Worker (cache)
- À chaque modif frontend critique, **bumper la version** dans `sw.js` (`CACHE_VERSION = 'avp-vX.X'`)
- Solution rapide : Chrome DevTools → Application → Service Workers → Unregister

### 4. Railway
- `PORT` injecté = **8080**
- `Base.metadata.create_all()` dans le startup event > Alembic
- **Dockerfile** explicite (pas nixpacks). Cairo/Pango/Pixbuf via apt-get
- Premier build après bascule = ~3-6 min, sinon ~90s

### 5. Netlify
- **Drag & drop** = méthode qui marche
- L'intégration GitHub a déjà causé des erreurs `frontend/frontend` path

### 6. CORS
- `ALLOWED_ORIGINS` géré via Railway env vars

### 7. Sentinel-2 NDVI
- **Statistical API** marche, **Process API** plante
- `dataMask` output requis, SCL en DN, B04/B08 en REFLECTANCE
- Sentinel-2 renvoie des valeurs précises (ex: 0.304) que le frontend arrondit (0.30). Toujours raisonner sur la valeur backend exacte.

### 8. Différence "disease_risk" vs "ML detection"
- `disease_risk.py` : conditions **climatiques** favorables aux maladies
- ML detection (HF Space) : **présence réelle** sur photo
- Ne PAS confondre

### 9. Module recommendations
Signature exacte de `build_recommendations()` :
```python
build_recommendations(
    module_results: List[Dict],   # liste vide acceptée
    inputs: Dict,
    global_score: float,
    global_risk: str,              # "LOW" | "MEDIUM" | "HIGH" en MAJUSCULES
)
```

### 10. Encodage de routes.py
- Maintenant en UTF-8 propre depuis Sprint 0-bis (commit `dd70c75`)
- Lecture sécurisée : `encoding="utf-8-sig"` (tolère un BOM occasionnel)
- Écriture : toujours en `utf-8` sans BOM

### 11. ⭐ NOUVEAU — Module offline `AVPOffline`
- Charger `avp-offline.js` **AVANT** `auth.js` dans toutes les pages HTML
- Ne PAS appeler `AVPOffline.cacheGet/cacheSet` avant que `await AVPOffline.isReady` ne soit résolu (en pratique, c'est instantané, mais pour les tests unitaires)
- En Phase 4-5 : la queue offline génère des UUID v4 préfixés `local_` qu'il faut reconcilier côté backend après synchro

---

## 🛠️ Méthodes éprouvées pour modifier des fichiers

### Pattern 1 (RECOMMANDÉ) — Script Python avec rollback
```python
from pathlib import Path
import shutil, ast

src = Path("chemin/du/fichier.py")
backup = src.with_name(src.name + ".backup-NOM-DATE")
shutil.copy2(src, backup)

text = src.read_text(encoding="utf-8-sig")

old = """ANCIEN CONTENU EXACT"""
new = """NOUVEAU CONTENU"""

if old in text:
    text = text.replace(old, new, 1)
    try:
        ast.parse(text.lstrip("\ufeff"))   # Validation syntax
        src.write_text(text, encoding="utf-8")
        print("[OK]")
    except SyntaxError as e:
        shutil.copy2(backup, src)   # Rollback
        print(f"[FAIL] {e}")
else:
    print("[FAIL] Ancre non trouvée")
```

### Pattern 2 — Vérification mojibake
```powershell
$check = [System.IO.File]::ReadAllText($file, [System.Text.Encoding]::UTF8)
$mojibake = 0
@('Ã©', 'Ã¨', 'Ã ', 'Ã´', 'â€"', 'â€™', 'Ã§') | ForEach-Object {
    $mojibake += [regex]::Matches($check, [regex]::Escape($_)).Count
}
if ($mojibake -eq 0) { Write-Host "Encodage OK" -ForegroundColor Green }
else { Write-Host "$mojibake mojibake(s)" -ForegroundColor Red }
```

---

## 📁 Structure du projet

- **Racine** : `C:\Users\YEO ISSA\Agrivision_ Pro\` (espace dans le nom !)
- **Backend** :
  - `app\api\routes.py` (PAS `app\routes.py`)
  - `app\db\models.py`
  - `app\services\reports.py` ⭐ R1a
  - `app\templates\plantation_report.html` ⭐ R1a
  - `main.py` à la racine
- **Frontend** :
  - `index.html`, `plantations.html`, `plantation_detail.html`, `diagnostic.html`, `analytics.html`, `map.html`, `satellite.html`, `agroforestry.html`, `harvests.html`, `admin.html`, `login.html`, `register.html`
  - `auth.js` ⭐ (design system + sidebar + API wrapper + Sprint Honnêteté-Offline)
  - ⭐ NOUVEAU **`avp-offline.js`** (Sprint Offline V1.6 Phase 1)
  - `ai-advice.js`, `sw.js` (Service Worker)
  - `AgriVision_Pro_Guide_Utilisateur_v1_5_0.docx` (Guide unique post-cleanup R1c)
- **Tests** : `tests\` avec `conftest.py` — total **185 tests pytest** (3 failures BUG-AGRO-01)
- **Infra** : `Dockerfile`, `.dockerignore`, `railway.json`, `requirements.txt`, `.gitignore`
- **Documents stratégiques** ⭐ NOUVEAU :
  - `CacaoPilot_OS` (1896 lignes) — brief stratégique complet, à garder en référence active
  - `Swollen_shoot` — datasets ML CSSVD pour `FEATURE-ML-CSSVD-01`
  - `AGRIVISION_CONTEXT.md` (ce fichier)

---

## 📞 Pour démarrer une nouvelle session

Phrase type :
> *"Tu agis en CTO de mon projet AgriVision Pro. Je joins le fichier `AGRIVISION_CONTEXT.md`. Sprint Reports R1 est livré, Sprint Honnêteté-Offline est livré, Sprint Offline V1.6 est en cours (Phases 1-2 livrées en prod, Phases 3-6 à venir). On continue le sprint en cours OU [autre sujet]."*

Et joindre ce fichier + les fichiers du projet à modifier.

---

## 📍 Localisation des livrables (sessions Claude)

Tous dans `/mnt/user-data/outputs/` :
- `/sprint_reports_r1a/` — backend PDF, template, requirements, Dockerfile
- `/sprint_reports_r1b/` — bouton frontend
- `/sprint_reports_r1a_fix2/` — patcher recommandations
- `/sprint_r1d/` — patches R1d + R1d-fix1 + R1d-fix2 + tests anti-detractor
- `/sprint_r1c/` — patch_r1c_fix_accents.py, patch_r1c_gitignore.py, AGRIVISION_CONTEXT.md, Guide v1.5
- `/sprint_offline/` — patch_offline_messaging.py (Sprint Honnêteté-Offline)
- `/sprint_offline_v1_6/` ⭐ NOUVEAU — `avp-offline.js`, `plantations.html` patché Phase 2, patcher P2
- `/AGRIVISION_HANDOVER.md` — version condensée pour reprise inter-session
- `/AGRIVISION_CONTEXT.md` — ce fichier (version maintenue)

---

*Fichier mis à jour le 3 mai 2026 par Claude (CTO virtuel) après livraison Sprint Honnêteté-Offline + Sprint Offline V1.6 Phases 1-2 + audit stratégique CacaoPilot_OS et Swollen_shoot. À mettre à jour après chaque sprint majeur.*
# ===========================================================================
# SPRINT OFFLINE V1.6 — CLÔTURE OFFICIELLE (09 mai 2026)
# ===========================================================================
# 
# Ce bloc est à coller à la fin de AGRIVISION_CONTEXT.md, juste avant
# la section "Roadmap" ou "Backlog" si elle existe, sinon en fin de fichier.
# 
# Tag Git : sprint-offline-v1.6-complete-2026-05-09
# ===========================================================================

## 🌱 Sprint Offline V1.6 — LIVRÉ EN PRODUCTION ✅

**Date de clôture** : 09 mai 2026
**Tag Git** : `sprint-offline-v1.6-complete-2026-05-09`
**Statut** : 95% livré (Phase 5 sautée par décision CTO, Phase 6 reportée post-pilote)

### Phases livrées

| # | Phase | Commit | Statut |
|---|---|---|---|
| 1 | Module IndexedDB centralisé `AVPOffline` (cache_get + queue_writes + photos + meta) | `0467922` | ✅ PROD |
| 2 | Page `plantations.html` en SWR | `cbbd08a` + `6eab1cc` (bump SW) | ✅ PROD testé mode avion |
| 3a | Page `plantation_detail.html` en SWR + fix Service Worker v3.0 | `9b814c7` + `6ab1cc` | ✅ PROD testé mode avion |
| 3b | Pages `diagnostic.html`, `harvests.html`, `agroforestry.html` en SWR | `e876b7d` | ✅ PROD testé |
| 4 | Saisie diagnostic offline (queue + auto-sync à reconnexion) | `b38a9e7` | ✅ PROD testé E2E |
| 5 | ~~Backend `/sync/batch`~~ | — | ⏭️ SAUTÉ (non nécessaire au pilote) |
| 6 | ~~Page synchronisation dédiée + journal~~ | — | ⏭️ REPORTÉ post-pilote |

### Service Worker

`avp-v2.0` → `avp-v3.2` avec **3 fixes critiques** dans v3.0 (commit `6ab1cc` zone) :
1. Filtre des schemes non-HTTP au début du fetch handler (bloque chrome-extension://, data:, blob:)
2. Helper `safeCachePut()` pour wrapper `cache.put()` en try/catch silencieux
3. Helper `matchCache()` avec `ignoreSearch:true` en fallback (sert `/page.html?id=X` depuis `/page.html` précaché)

### Capacités utilisateur livrées

**En lecture (5 pages offline)** :
- Liste des plantations
- Détail d'une plantation (info, GPS, diagnostics, récoltes, agroforesterie, recommandations)
- Page diagnostic (sélecteurs pré-remplis, agroforesterie chargée)
- Page récoltes (liste + stats)
- Page agroforesterie (inventaire + carbon banner)

**En écriture (1 action offline)** :
- Saisie d'un diagnostic complet en mode avion
- Mise en queue IndexedDB avec ID local `local_xxxxx`
- Affichage stub immédiat (header jaune-orangé + récap inputs + ⏳ "En attente de synchronisation")
- Badge dynamique bottom-right "X action(s) en attente"
- **Auto-flush à la reconnexion** via listener `online` (Phase 1 infrastructure)
- Toast de confirmation "X saisie(s) envoyée(s) au serveur"

### Apprentissages clés (à garder pour V2)

#### Pattern 4 — Vérification mojibake fiable
`Get-Content -Raw` lit en Windows-1252 par défaut sur Windows = **faux positifs garantis** sur les fichiers UTF-8 français. Méthode fiable :
```powershell
$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path $file).Path)
$utf8 = [System.Text.Encoding]::UTF8.GetString($bytes)
```

#### Pattern 5 — Test mode avion DevTools : pièges à éviter
Pour tester l'offline d'un Service Worker correctement, il faut **DÉCOCHER 3 cases** dans DevTools :
- ❌ "Disable cache" dans Network (sinon bypass du SW pour le main document)
- ❌ "Update on reload" dans Application > Service Workers
- ❌ "Bypass for network" dans Application > Service Workers

Sans ces 3 décochages, le SW est ignoré et on voit l'écran natif Edge `ERR_INTERNET_DISCONNECTED` même si tout est correctement caché en IndexedDB.

#### Pattern 6 — Service Worker : 3 fixes obligatoires pour real offline
Tout SW qui veut servir une PWA en mode avion DOIT :
1. **Filtrer les schemes non-HTTP** au début du `fetch` event handler
2. **Wrapper `cache.put()` en try/catch silencieux** (les extensions Chrome plantent dessus)
3. **Match cache avec `{ignoreSearch: true}` en fallback** (pour servir `/page.html?id=X` depuis `/page.html` précaché)

#### Pattern 7 — `navigator.onLine` ment souvent
Détection offline fiable = **`!navigator.onLine` + try/catch sur `fetch()`**. Les 2 ensemble. `navigator.onLine` peut renvoyer `true` sur un WiFi sans Internet, ou rester `false` sur certaines connexions captives.

### Tickets backlog ouverts pendant le sprint

| ID | Sévérité | Titre | Origine |
|---|---|---|---|
| `BUG-OFFLINE-DEDUP-01` | Moyenne | Déduplication queue offline (3 entrées identiques observées en test E2E) | Test Phase 4 du 09/05/2026 |
| `FEATURE-OFFLINE-WRITE-HARVESTS` | Basse | Étendre la queue offline aux POST/PUT/DELETE de `harvests.html` | Phase 4b post-pilote |
| `FEATURE-OFFLINE-WRITE-PLANTCOUNT` | Basse | Étendre la queue offline au PUT plant_count | Phase 4b post-pilote |
| `FEATURE-OFFLINE-PHOTO-ML` | Basse | Photo cabosse offline avec retry séparé sur HF Space | V2 |
| `FEATURE-SYNC-DASHBOARD` | Basse | Page de synchronisation dédiée (journal, retry manuel, vue queue) | V2 |

### Fix repo GitHub (à faire à un moment)

Le repo a été renommé/déplacé. Les push affichent un warning :
```
remote: This repository moved. Please use the new location:
remote:   https://github.com/Ikaff2024/agrivision-pro.git
```

À corriger un jour avec :
```powershell
git remote set-url origin https://github.com/Ikaff2024/agrivision-pro.git
git remote -v
```

### Prochaine session — Sprint EUDR-01a

Le sprint Offline V1.6 étant clos, le **prochain sprint majeur est EUDR-01a** (`FEATURE-EUDR-01` du backlog).

Découpage proposé en 3 sous-sprints :
- **EUDR-01a** : Polygones parcelles (Leaflet.draw activé sérieusement) + score EUDR de base (5 règles simples) + badge Conforme/À vérifier/Non conforme — **~1 semaine**
- **EUDR-01b** : Intégration Hansen Global Forest Change pour détection déforestation post-2020 — **~1 semaine**
- **EUDR-01c** : Export DDS PDF (Due Diligence Statement) — **~3-4 jours**

**Effort total** : ~2.5 semaines, en 3 livraisons valorisables séparément.

**Pourquoi c'est le bon prochain sprint** : c'est l'argument commercial #1 pour signer des coopératives avant la deadline EUDR du 30/12/2026 (grandes entreprises) / 30/06/2027 (PME). Le sprint Offline rendait le produit utilisable terrain ; le sprint EUDR le rend vendable.

# ===========================================================================
# SPRINT CACAOGUARD P0 + P1 — CLÔTURE OFFICIELLE (27 mai 2026)
# ===========================================================================
#
# Tag Git : cacaoguard-p0-p1-complete-2026-05-27
# Branche : codex/cacaoguard-fusion (agrivision-pro-next)
# Voir aussi : LIVRAISON_CACAOGUARD_P1.md à la racine
# ===========================================================================

## 🛡️ Sprint CacaoGuard P0 + P1 — LIVRÉ ✅

**Date de clôture** : 27 mai 2026
**Statut** : Backend déployé Railway, frontend prêt zip Netlify, 280 tests verts
**Périmètre** : Mise en conformité totale du module CacaoGuard avec la spec
client `IMPLEMENTATION_ROADMAP.md` (section 5.1)

### 7 chantiers livrés

| ID | Chantier | Backend | Frontend |
|---|---|---|---|
| CG-1.3 | Scoring risque 6 facteurs v2.0 (vs 4 facteurs v1) | ✅ | ✅ (simulateur + bouton "Recalculer cote serveur") |
| CG-1.1 | Module Complaints / Signalements EUDR | ✅ 5 endpoints | ✅ Nouvelle page complaints.html |
| CG-1.2 | Workflow remediation complet (approve/complete/escalate + actions CRUD) | ✅ 9 endpoints | ✅ 5 modales dans remediation.html |
| CG-1.4 | Audit trail consolidé | ✅ 2 endpoints | ✅ Section dans compliance.html |
| CG-2.1 | Producer drill-down (6 endpoints) | ✅ | ✅ Panneau synthese dans producer_profile.html |
| CG-2.2 | Notifications in-app | ✅ 6 endpoints + table | ✅ Badge global dans auth.js |
| CG-2.3 | Sync mobile (idempotent par op_id) | ✅ 4 endpoints + table | ⚠️ Stub frontend (Idempotency-Key UUID) |

### Nouveaux endpoints API (30 au total)

Visibles dans https://agrivision-api-production.up.railway.app/docs (111 endpoints au total apres livraison) :
- `/complaints` (5 routes) — hotline signalement
- `/cacaoguard/reports/audit-trail` + `/summary` — chronologie pour audit
- `/cacaoguard/notifications/*` (6 routes) — feed in-app
- `/cacaoguard/sync/*` (4 routes) — pull/push offline avec idempotence
- `/remediation/plans/{id}/{approve,complete,escalate}` + actions CRUD (8 routes)
- `/children/{id}/calculate-risk` — recalcul live (admin/auditeur)
- `/producers/{id}/{children,assessments,visits,remediation-plans,complaints,traceability-status,calculate-risk}` (7 routes)

### Nouveaux modeles SQL

- `notifications` (UniqueConstraint user_id+alert_id, idempotence)
- `sync_operation_logs` (UNIQUE op_id, idempotence stricte)

### Migrations Alembic

- `0005_notifications.py`
- `0006_sync_operation_logs.py` (renumerotee depuis 0005 lors de l'integration)
- Chaine finale : `0001 -> ... -> 0004_ssrte_forms -> 0005_notifications -> 0006_sync_operation_logs`

### Methodologie scoring v2.0

7 facteurs sur 100 pts (vs 4 facteurs mal calibres en v1) :
- age (0-25), school (0-25), work (0-20), dangerous_tasks (0-10) — intrinseques
- economic (0-10) — derive de `FarmForceAssessment.return_per_family_day_cfa` / `profit_cfa`
- geographic (0-5) — derive de `Child.school_distance_km` ou fallback `SsrteCommunityProfile.nearest_school_distance_km`
- history (0-5) — derive du nombre d'evaluations HIGH/CRITICAL anterieures pour l'enfant

Seuils risk_level (alignes avec la spec et descendu de 5-15 pts vs v1) :
- CRITICAL >= 70, HIGH >= 50, MEDIUM >= 30, LOW >= 15

Stamp `methodology_version="2.0"` sur chaque RiskAssessment cree apres cette PR.

### Patterns / decisions architecturales

1. **Audit trail sans double-log** : reconstruit la chronologie a partir des sources existantes (PrivacyAccessLog + RemediationPlan.approved_at + Alert.escalated_at + TraceabilityBlock.created_at + Child.created_at). Pas de table dediee, pas de risque de desynchronisation.

2. **Notifications avec fan-out lazy** : NotificationItem creee a la demande au prochain GET, avec UniqueConstraint user_id+alert_id pour idempotence. Pas de queue de notification a l'emission Alert (decoupage propre).

3. **Sync mobile pull/push** :
   - Pull avec delta optionnel (`last_sync_at`)
   - Push idempotent par op_id (UUID client). Permet rejouer un /sync/push sans dupliquer cote serveur.
   - 4 op_types supportes : create_visit, complete_visit, create_complaint, complete_action
   - conflict/resolve : MVP server_wins, client doit refetch

4. **Frontend global notifications widget** : ajoute dans auth.js, visible sur TOUTES les pages CacaoGuard via initApp(). Polling 60s sur /notifications/unread-count.

### Service Worker

Bumped `avp-v3.10-staging-api` -> `avp-v4.0-cacaoguard-p1`. Ajout de `/complaints.html` aux STATIC_ASSETS precaches.

### Frontend deploy

Zip pret a deposer : `agrivision-frontend-cacaoguard-p1.zip` (225 KB, 60+ fichiers) a la racine.

### Backlog ouvert post-CG-P1

| ID | Titre | Sévérité | Effort |
|---|---|---|---|
| `FEATURE-CG-REPORTS-01` | Rapports avances (child-labor-summary, training-effectiveness, export Excel) | Moyenne | 1-2 jours |
| `FEATURE-CG-SCOPING-01` | Filtrage fin par cooperative sur notifications/sync (multi-tenant) | Moyenne | 0.5 jour |
| `FEATURE-CG-MOBILE-01` | App mobile native Capacitor pour exploiter `/sync/*` | Haute (V2) | 1 semaine |
| `CHORE-CG-ALEMBIC-01` | Migration Alembic dediee au lieu de Base.metadata.create_all pour les 2 nouvelles tables | Faible | 0.5 jour |
| `FEATURE-CG-COMPLAINTS-OFFLINE-01` | Etendre la queue offline a /complaints (signalement terrain) | Moyenne | 0.5 jour |

### Tests

- 280 tests pytest verts (106 nouveaux pour CG-P0+P1)
- 3 tests test_agroforestry.py pre-casses (chip spawned, sans rapport CacaoGuard)
- Mojibake check OK sur tous les fichiers livres

### Prochain sprint recommande

**EPIC EUDR-01** comme prevu dans le backlog initial. Toutes les briques CacaoGuard sont en place pour supporter le module EUDR (audit trail + tracabilite + chaine de responsabilite).

# ===========================================================================
# SPRINT EUDR-01a — CLÔTURE OFFICIELLE (27 mai 2026)
# ===========================================================================
#
# Tag Git : eudr-01a-complete-2026-05-27
# Branche : codex/cacaoguard-fusion (agrivision-pro-next)
# Voir aussi : LIVRAISON_EUDR_01a.md a la racine
# ===========================================================================

## 🛡️ Sprint EUDR-01a — LIVRÉ ✅

**Date de cloture** : 27 mai 2026
**Statut** : Backend live Railway, frontend zip pret Netlify, 318 tests verts
**Perimetre** : Premier livrable EPIC FEATURE-EUDR-01 (argument commercial #1
avant deadline 30/12/2026 grandes entreprises / 30/06/2027 PME)

### Livrables

| Composant | Fichier | Statut |
|---|---|---|
| Moteur scoring 5 regles | `app/eudr/scoring.py` | ✅ |
| 4 endpoints API | `app/api/eudr_routes.py` | ✅ |
| Dashboard EUDR coop | `frontend/eudr.html` | ✅ |
| Badge fiche plantation | `frontend/plantation_detail.html` (carte EUDR ajoutee) | ✅ |
| Colonne liste plantations | `frontend/plantations.html` (col EUDR + batch load) | ✅ |
| Sidebar globale | `frontend/auth.js` (lien EUDR) | ✅ |
| Tests scoring | `tests/test_eudr_scoring.py` (28 cas) | ✅ |
| Tests endpoints | `tests/test_eudr_routes.py` (10 cas) | ✅ |

### 5 regles de scoring (methodologie `eudr-1.0a`)

| ID | Regle | Logique |
|---|---|---|
| R1 | `polygon_valid` | Polygone GeoJSON >= 3 sommets enregistre dans PlantationBoundary |
| R2 | `area_matches` | `abs(area_geo - declared_hectares) / declared <= 0.20` (tolerance 20%) |
| R3 | `gps_in_cocoa_zone` | Tous les sommets du polygone (ou point GPS si pas de polygone) dans bbox CI cacao (4.3-10.8N, -8.6 a -2.5E) |
| R4 | `recent_inspection` | Inspection (table existante) ou MonitoringVisit CacaoGuard < 365 jours |
| R5 | `no_active_traceability_block` | Pas de TraceabilityBlock actif sur le producteur (lecture cross-module CacaoGuard) |

Seuils : score >=4 = conforme (vert), 2-3 = a_verifier (orange), 0-1 = non_conforme (rouge).

### Reutilisation infrastructure existante

- `PlantationBoundary` (table existante depuis Sprint #0) avec `geojson`, `area_hectares`, `points_count` -> aucune migration SQL
- `POST /plantations/{id}/boundary` (existant) avec `_calculate_area_hectares` Spherical Excess -> reutilise tel quel
- `Inspection` (table existante AgriVision) -> lecture pour R4
- `TraceabilityBlock` (CacaoGuard) -> lecture cross-module pour R5
- Leaflet.draw deja active dans `map.html` -> aucun travail frontend pour le dessin

### Endpoints API (4 nouveaux)

```
GET  /plantations/{id}/eudr-score    # detail complet 5 regles
GET  /plantations/{id}/eudr-status   # badge condense
GET  /eudr/cooperative-summary       # KPIs agreges coop
GET  /eudr/plantations               # liste triee (risk/score/name)
```

Scoping cooperative + role gating (admin/agronomist/technician). Viewer interdit.

### Service Worker

Bumped `avp-v4.0-cacaoguard-p1` -> `avp-v4.1-eudr-01a`. Ajout `/eudr.html` aux STATIC_ASSETS.

### Frontend deploy

`agrivision-frontend-eudr-01a.zip` (230 KB, 62+ fichiers) a la racine. Ignore par git (gitignore mis a jour).

### Tests

318 tests verts (38 nouveaux EUDR + 280 existants). Mojibake check OK.

### Roadmap EUDR restante

- **EUDR-01b** : Croisement Hansen Global Forest Change pour deforestation post-2020 (~1 semaine). Transforme le score "5 regles techniques" en preuve reglementaire auditable.
- **EUDR-01c** : Export DDS PDF (Due Diligence Statement) reutilisant WeasyPrint (~3-4 jours). Livrable final pour les exportateurs.

Avec 01a + 01b + 01c, AgriVision Pro couvrira 100% du process EUDR.

# ===========================================================================
# SPRINT EUDR-01c — CLÔTURE OFFICIELLE (27 mai 2026)
# ===========================================================================
#
# Tag Git : eudr-01c-complete-2026-05-27
# Branche : codex/cacaoguard-fusion (agrivision-pro-next)
# Voir aussi : LIVRAISON_EUDR_01c.md a la racine
# ===========================================================================

## 📄 Sprint EUDR-01c — LIVRÉ ✅

**Date de cloture** : 27 mai 2026 (meme jour que 01a)
**Statut** : Backend live Railway, frontend zip pret Netlify, 330 tests verts
**Decision CTO** : 01c avant 01b car evite la dependance GDAL/rasterio cote
Railway et livre immediatement la valeur commerciale (document que les
operateurs remettent aux autorites).

### Livrables

| Composant | Fichier | Statut |
|---|---|---|
| Template DDS Jinja2 (5 sections + attestation) | `app/templates/eudr_dds_report.html` | ✅ |
| Service generation PDF | `app/services/eudr_reports.py` | ✅ |
| Endpoint streaming PDF | `app/api/eudr_routes.py` (`GET .../eudr-dds.pdf`) | ✅ |
| Bouton "Telecharger DDS" fiche plantation | `frontend/plantation_detail.html` | ✅ |
| Bouton DDS dashboard EUDR (par ligne) | `frontend/eudr.html` | ✅ |
| Tests pytest (12 cas) | `tests/test_eudr_dds.py` | ✅ |

### Format DDS

Reference : `DDS-YYYY-XXXX` (annee + id plantation padde sur 4)
Methodologie : etiquette `eudr-1.0a` dans le PDF

5 sections :
1. Identification parcelle (noms, superficies, GPS centroide)
2. Verdict de conformite (banniere coloree + score X/5)
3. Detail des 5 regles (table)
4. Polygone parcellaire (extrait GeoJSON tronque 800 char + metadata)
5. Liens cooperative (coop, code producteur, derniere inspection, blocage CG)

Plus : attestation art. 8 EUDR + zone signature + footer legal.

### Reutilisation infrastructure

- `_jinja_env`, `_pdf_escape`, `slugify` de `app/services/reports.py`
- Pattern fallback PDF natif (sans Cairo/Pango) similaire a `cacaoguard_report`
- Endpoint StreamingResponse + filename UTF-8 RFC5987 (pattern Sprint R1)
- WeasyPrint deja en prod via Dockerfile (libs C installees apt-get)

### Service Worker

Bumped `avp-v4.1-eudr-01a` -> `avp-v4.2-eudr-01c-dds`.

### Frontend deploy

`agrivision-frontend-eudr-01c.zip` (231 KB) a la racine. Ignore par git.

### Tests

330 tests verts (12 nouveaux + 318 existants). Tests :
- build_dds_context : champs requis + operator custom + sans polygone
- generate_dds_pdf : avec WeasyPrint mocke + fallback sans WeasyPrint
- dds_filename : format
- Endpoint : admin OK / agronomist OK / technician 403 / 404 / 401

### Roadmap restante

- **EUDR-01b** : Hansen Global Forest Change deforestation post-2020.
  Demande GDAL/rasterio cote backend. Reportable apres validation commerciale
  de 01a + 01c (le DDS PDF est deja exportable pour les demos).

### Argumentaire commercial cle

Avec 01a (scoring) + 01c (DDS PDF), le pitch passe de "on calcule un score" a
"vous telechargez le document officiel pour les douanes UE en un clic".
Demo recommandee : ouvrir plantation -> "Telecharger DDS" -> ouvrir PDF.