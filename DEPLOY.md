# AgriVision Pro — Guide de déploiement

## Développement local avec Docker

### Prérequis
- Docker Desktop installé et démarré
- Fichier `.env` configuré (depuis `.env.example`)

### Lancer la stack complète
```bash
# Démarrer API + PostgreSQL
docker compose up -d

# Démarrer avec pgAdmin (interface DB graphique)
docker compose --profile dev up -d

# Voir les logs en temps réel
docker compose logs -f api

# Vérifier que tout tourne
docker compose ps
```

### Accès
| Service  | URL                        |
|----------|----------------------------|
| API      | http://localhost:8000      |
| Docs     | http://localhost:8000/docs |
| pgAdmin  | http://localhost:5050      |

### Peupler la base
```bash
docker compose exec api python seed_data.py
```

### Arrêter la stack
```bash
docker compose down          # Arrêter (données conservées)
docker compose down -v       # Arrêter + supprimer les volumes
```

---

## CI/CD GitHub Actions

### Configuration des secrets GitHub

Dans ton dépôt GitHub → Settings → Secrets and variables → Actions :

| Secret              | Valeur                                    |
|---------------------|-------------------------------------------|
| `DOCKER_USERNAME`   | Ton identifiant Docker Hub                |
| `DOCKER_PASSWORD`   | Token Docker Hub (Settings → Security)   |
| `SECRET_KEY`        | Clé JWT de production (64 chars random)  |

### Pipeline automatique
- **Push sur `develop`** → Tests uniquement
- **Push sur `main`** → Tests + Build Docker + Déploiement

---

## Déploiement Production — Railway (recommandé)

Railway est la solution la plus simple pour déployer FastAPI + PostgreSQL.

### Étapes

1. **Créer un compte** sur [railway.app](https://railway.app)

2. **Nouveau projet** → "Deploy from GitHub repo" → sélectionner ton repo

3. **Ajouter PostgreSQL** → "+ New" → "Database" → "PostgreSQL"

4. **Variables d'environnement** dans Railway :
```
SECRET_KEY=<ta_cle_jwt_64_chars>
DATABASE_URL=${{Postgres.DATABASE_URL}}
ALLOWED_ORIGINS=https://ton-frontend.netlify.app
ACCESS_TOKEN_EXPIRE_MINUTES=120
```

5. **Déploiement automatique** à chaque push sur `main`

6. **Récupérer l'URL** → Settings → Domains → Generate Domain

### Activer le déploiement automatique dans CI
Dans `.github/workflows/ci.yml`, ajouter le secret `RAILWAY_TOKEN` et décommenter :
```yaml
- name: Deploy sur Railway
  uses: bervProject/railway-deploy@main
  with:
    railway_token: ${{ secrets.RAILWAY_TOKEN }}
    service: agrivision-api
```

---

## Déploiement Production — Render (alternative gratuite)

1. **Créer un compte** sur [render.com](https://render.com)

2. **New Web Service** → connecter le repo GitHub

3. **Paramètres** :
   - Environment: `Docker`
   - Dockerfile path: `./Dockerfile`

4. **Ajouter PostgreSQL** → New → PostgreSQL

5. **Variables d'environnement** :
```
SECRET_KEY=<ta_cle_jwt_64_chars>
DATABASE_URL=<url_postgresql_render>
ALLOWED_ORIGINS=https://ton-frontend.netlify.app
```

6. **Deploy Hook** → copier l'URL et ajouter comme secret GitHub `RENDER_DEPLOY_HOOK`

---

## Mise à jour du frontend pour la production

Dans `frontend/auth.js`, ligne 1 :
```javascript
// Remplacer :
const API_BASE = 'http://localhost:8000';

// Par l'URL de production :
const API_BASE = 'https://ton-api.railway.app';
```

Puis déployer le frontend sur Netlify :
1. Glisser-déposer le dossier `frontend/` sur [app.netlify.com](https://app.netlify.com)
2. Récupérer l'URL Netlify
3. Ajouter cette URL dans `ALLOWED_ORIGINS` côté API

---

## Checklist production

- [ ] `SECRET_KEY` aléatoire de 64 caractères minimum
- [ ] `DATABASE_URL` pointe vers PostgreSQL (pas SQLite)
- [ ] `ALLOWED_ORIGINS` contient uniquement les domaines frontend autorisés
- [ ] Dockerfile build sans erreur : `docker build -t agrivision-api .`
- [ ] Tests passent : `pytest tests/ -v`
- [ ] Migrations appliquées : `alembic upgrade head`
- [ ] Healthcheck répond : `GET /health → {"status": "ok"}`
- [ ] Logs configurés (pas de print() en production)

---

## Commandes utiles Docker

```bash
# Reconstruire l'image après modification du code
docker compose build api

# Accéder au shell du conteneur API
docker compose exec api bash

# Lancer les tests dans le conteneur
docker compose exec api pytest tests/ -v

# Appliquer une nouvelle migration
docker compose exec api alembic upgrade head

# Voir les logs PostgreSQL
docker compose logs db

# Inspecter la base de données
docker compose exec db psql -U agrivision_user -d agrivision
```
