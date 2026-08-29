# Tests E2E & vidéos de démo — AgriVision Pro (Playwright)

Tests « bout en bout » qui pilotent un vrai navigateur sur l'application, pour :
- **non-régression** : détecter les bugs de parcours (ceux trouvés à la main lors des tests) ;
- **vidéos de démo** : chaque exécution enregistre une vidéo `.webm` du parcours.

## Ce qui est couvert

| Fichier | Scénario |
|---|---|
| `tests/smoke.spec.ts` | La page de connexion se charge (sanity) |
| `tests/demo.spec.ts` | **Connexion → Plantation → Producteur → Analyse satellite (NDVI) → EUDR** |
| `tests/eudr.spec.ts` | **Conformité EUDR → génération + téléchargement du DDS PDF** (vérifie la signature `%PDF`) |
| `tests/eudr_pack.spec.ts` | **Pack de diligence raisonnée EUDR par lot** (ZIP, signature `PK`) |
| `tests/eudr_readiness.spec.ts` | **Panneau « Prêt pour l'EUDR »** : blocages et filtre de la table |
| `tests/deforestation.spec.ts` | **Contrôle satellite de déforestation** (GFW → règle EUDR R6) |
| `tests/boundary.spec.ts` | **Délimitation de parcelle → conformité EUDR (`has_polygon` false→true) → DDS PDF** |
| `tests/harvest.spec.ts` | **Saisie récolte avec n° de reçu d'achat**, et **le tableau survit à la perte du CDN du graphique** |
| `tests/import.spec.ts` | **Import d'un registre Excel + annulation du lot** (via l'UI) |
| `tests/achats.spec.ts` | **Enregistrement d'un achat producteur** (non-membre, poids, prix, n° de bon) |
| `tests/payments.spec.ts` | **Soldes dûs par producteur puis règlement groupé** |
| `tests/lot_passport.spec.ts` | **Traçabilité : parcelle → récolte → lot → passeport de lot PDF** |
| `tests/twin.spec.ts` | **Jumeau de parcelle** : synthèse et alertes sur la fiche plantation |
| `tests/veille.spec.ts` | **Veille Marché** : chargement et dégradation gracieuse sans clé IA |
| `tests/xss_complaints.spec.ts` | **Non-régression sécurité** : un signalement public piégé ne s'exécute pas dans la console admin |

## Déterminisme

Chaque test ouvre sa **propre coopérative jetable** via l'API et crée toutes ses
données : aucun test ne dépend d'un autre, de l'ordre d'exécution, d'une base
pré-peuplée ni d'une donnée de production. Un test passe donc seul comme dans la
suite complète, sur une base vierge comme sur une base déjà utilisée.

Les gestes communs vivent dans `tests/helpers/session.ts` — un seul point de
vérité, pour qu'un changement produit sur la connexion ou la navigation se
corrige à un endroit et non dans quinze specs :

| Fonction | Rôle |
|---|---|
| `openSession(request, slug)` | crée la coopérative jetable et renvoie le jeton |
| `loginViaUI(page, session)` | connexion par le formulaire ; vérifie le 200, la sortie de `login.html` et le jeton posé — **sans** figer la page d'arrivée, qui dépend du rôle |
| `openModule(page, mod)` | ouvre un module par le menu, en dépliant au besoin son pilier repliable |
| `pickInCombo(page, host, value)` | choisit une valeur dans une liste cherchable `AVPCombo` (qui a remplacé les `<select>` des grandes listes) |

Le scénario `demo` prépare ses données via l'API (compte + parcelle géolocalisée), puis
déroule le parcours **via l'interface** (c'est ce que filme la vidéo).

## Prérequis

- **Node.js ≥ 18** (testé sur v24)
- **Python 3** (sert le frontend en local) — *ou* viser un staging distant via `AVP_BASE_URL`
- Un backend joignable sur `AVP_API_URL` (par défaut l'instance locale sur 8010).
  Aucune clé externe n'est requise : sans clé, les fournisseurs satellite et IA
  renvoient un résultat de repli déterministe (« à vérifier », jamais « conforme »).

## Installation

```bash
cd e2e
npm install
npm run install:browser   # télécharge Chromium pour Playwright
```

## Lancer

Un backend éphémère doit tourner sur `127.0.0.1:8010` (c'est ce que fait la CI) :

```bash
SECRET_KEY=dev DATABASE_URL="" uvicorn main:app --host 127.0.0.1 --port 8010
```

```bash
# Mode local (défaut) : sert ../frontend et vise le backend éphémère local
npm test

# Voir le rapport HTML (vidéos incluses)
npm run report

# En mode visible (fenêtre navigateur)
npm run test:headed
```

### Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `AVP_BASE_URL` | `http://127.0.0.1:5510` (servi en local) | Frontend à tester. Mettre l'URL Netlify de staging pour viser le déploiement. |
| `AVP_API_URL` | `http://127.0.0.1:8010` | Backend. Par défaut l'instance **locale éphémère** : viser un autre environnement est un choix explicite, jamais un oubli de variable. |
| `AVP_PORT` | `5510` | Port du serveur statique local (déjà dans l'allowlist CORS du backend). |
| `AVP_TEST_EMAIL` / `AVP_TEST_PASSWORD` | *(vide)* | Réutiliser un compte existant (démo « riche »). Sinon une **coopérative jetable** est créée à chaque run. |

Exemple — viser directement le staging Netlify :

```bash
AVP_BASE_URL="https://VOTRE-SITE.netlify.app" AVP_TEST_EMAIL="admin@coop.ci" AVP_TEST_PASSWORD="••••" npm test
```

## Où sont les vidéos ?

- `test-results/**/video.webm` (une par test)
- `playwright-report/` (rapport HTML navigable, ouvre les vidéos/traces) — `npm run report`

### Convertir en MP4 partageable (WhatsApp / PowerPoint)

Les `.webm` se lisent dans un navigateur ; pour un partage commercial, convertir en `.mp4` (H.264)
avec **ffmpeg** :

```bash
# une vidéo
ffmpeg -i "test-results/demo-.../video.webm" -c:v libx264 -pix_fmt yuv420p -movflags +faststart demo.mp4

# toutes les vidéos -> dossier mp4/
mkdir -p mp4
find test-results -name video.webm | while read -r f; do \
  name=$(basename "$(dirname "$f")"); \
  ffmpeg -y -i "$f" -c:v libx264 -pix_fmt yuv420p -movflags +faststart "mp4/${name%%-*}.mp4"; done
```

> ⚠️ Sans `AVP_TEST_EMAIL`, chaque test **crée une coopérative jetable** (`E2E <slug> <timestamp>`)
> sur le backend visé. C'est sans conséquence sur l'instance locale éphémère, qui est jetée avec le
> job ; si vous visez un environnement partagé via `AVP_API_URL`, ces coopératives y resteront.

## Idées d'extensions (prochaines passes)

- **Dessin Leaflet** réel sur la carte (clics/`quickSquare`) : `boundary.spec.ts` couvre la chaîne
  métier (tracé→conformité→DDS) via l'endpoint de délimitation ; le dessin sur la carte lui-même
  reste vérifié manuellement (interaction canvas peu déterministe en CI).
- Convertir une `.webm` en `.mp4` (ffmpeg) pour partage commercial / Loom.
- Workflow CI : publier l'E2E **en commentaire de PR** + nommer les artefacts vidéo par date.
