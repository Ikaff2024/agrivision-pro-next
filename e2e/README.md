# Tests E2E & vidéos de démo — AgriVision Pro (Playwright)

Tests « bout en bout » qui pilotent un vrai navigateur sur l'application, pour :
- **non-régression** : détecter les bugs de parcours (ceux trouvés à la main lors des tests) ;
- **vidéos de démo** : chaque exécution enregistre une vidéo `.webm` du parcours.

## Ce qui est couvert

| Fichier | Scénario |
|---|---|
| `tests/smoke.spec.ts` | La page de connexion se charge (sanity) |
| `tests/demo.spec.ts` | **Connexion → Plantation → Producteur → Analyse satellite (NDVI réel) → EUDR** |
| `tests/eudr.spec.ts` | **Conformité EUDR → génération + téléchargement du DDS PDF** (vérifie la signature `%PDF`) |
| `tests/harvest.spec.ts` | **Saisie récolte avec n° de reçu d'achat** (Point #4) |
| `tests/boundary.spec.ts` | **Délimitation de parcelle → conformité EUDR (`has_polygon` false→true) → DDS PDF** |
| `tests/import.spec.ts` | **Import d'un registre Excel + annulation du lot** (Point #3, via l'UI) |
| `tests/achats.spec.ts` | **Enregistrement d'un achat producteur** (sélection producteur, poids, prix, n° de bon) |
| `tests/lot_passport.spec.ts` | **Traçabilité : parcelle → récolte → lot → passeport de lot PDF** (signature `%PDF`) |

Le scénario `demo` prépare ses données via l'API (compte + parcelle géolocalisée), puis
déroule le parcours **via l'interface** (c'est ce que filme la vidéo).

## Prérequis

- **Node.js ≥ 18** (testé sur v24)
- **Python 3** (sert le frontend en local) — *ou* viser un staging distant via `AVP_BASE_URL`
- Accès réseau au backend (Railway) — l'analyse satellite tape les vraies API gratuites.

## Installation

```bash
cd e2e
npm install
npm run install:browser   # télécharge Chromium pour Playwright
```

## Lancer

```bash
# Mode local (défaut) : sert ../frontend et vise l'API Railway réelle
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
| `AVP_API_URL` | `https://agrivision-api-production.up.railway.app` | Backend. |
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

> ⚠️ Sans `AVP_TEST_EMAIL`, chaque exécution **crée une coopérative jetable** (`E2E Demo <timestamp>`)
> sur le backend visé. Sur le staging, l'admin/IKAFFANAN peut la purger (module d'annulation d'import
> ou suppression coop). Pour éviter cela, réutiliser un compte de démo dédié.

## Idées d'extensions (prochaines passes)

- **Dessin Leaflet** réel sur la carte (clics/`quickSquare`) : `boundary.spec.ts` couvre la chaîne
  métier (tracé→conformité→DDS) via l'endpoint de délimitation ; le dessin sur la carte lui-même
  reste vérifié manuellement (interaction canvas peu déterministe en CI).
- Convertir une `.webm` en `.mp4` (ffmpeg) pour partage commercial / Loom.
- Workflow CI : publier l'E2E **en commentaire de PR** + nommer les artefacts vidéo par date.
