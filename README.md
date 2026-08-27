# AgriVision Pro — CacaoEngine API

Plateforme de gestion de plantations de cacao. API FastAPI + moteur agronomique déterministe + frontend HTML.

---

## Arborescence

```
agrivision-pro/
├── main.py                         # Point d'entrée FastAPI
├── requirements.txt
├── alembic.ini                     # Configuration migrations
├── seed_data.py                    # Données de démonstration
├── .env.example                    # Template variables d'environnement
│
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_baseline.py       # Migration initiale
│
├── app/
│   ├── db/
│   │   ├── database.py            # Connexion SQLAlchemy
│   │   └── models.py              # Modèles ORM
│   ├── auth/
│   │   ├── auth_service.py        # JWT, hash passwords
│   │   └── auth_routes.py         # POST /auth/register, /auth/login
│   ├── api/
│   │   └── routes.py              # Toutes les routes métier
│   ├── cacao_engine/
│   │   ├── engine.py              # Orchestrateur du moteur
│   │   ├── inputs.py              # Schéma d'entrée (Pydantic)
│   │   ├── outputs.py             # Schéma de sortie
│   │   ├── rules/
│   │   │   └── thresholds.py      # Règles de scoring
│   │   └── modules/
│   │       ├── disease_risk.py
│   │       ├── plantation_age.py
│   │       ├── rainfall_balance.py
│   │       └── shade_balance.py
│   ├── ml/
│   │   └── image_diagnosis.py     # Analyse d'image (stub ML)
│   └── satellite/
│       └── ndvi_service.py        # Service NDVI (stub satellite)
│
├── frontend/                      # Interface HTML
│   ├── index.html
│   ├── login.html / register.html
│   ├── plantations.html / plantation_detail.html
│   ├── diagnostic.html
│   ├── map.html / analytics.html / satellite.html
│   └── auth.js
│
└── tests/
    ├── conftest.py                # Fixtures pytest (DB in-memory)
    ├── test_auth.py
    ├── test_plantations.py
    ├── test_diagnostic.py
    └── test_cacao_engine.py
```

---

## Installation

### 1. Prérequis
- Python 3.11+
- pip

### 2. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 3. Configurer l'environnement
```bash
cp .env.example .env
```
Générer une `SECRET_KEY` sécurisée :
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Coller la valeur dans `.env`.

### 4. Appliquer les migrations
```bash
alembic upgrade head
```

### 5. Démarrer l'API
```bash
uvicorn main:app --reload
```
L'API est disponible sur `http://localhost:8000`.
Documentation interactive : `http://localhost:8000/docs`

---

## Premier utilisateur

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@ma-coop.ci",
    "password": "motdepasse",
    "role": "admin",
    "cooperative_name": "Ma Coopérative",
    "country": "Côte d Ivoire"
  }'
```

Rôles disponibles : `admin`, `agronomist`, `technician`.

---

## Données de démonstration

```bash
python seed_data.py
```
Crée 30 plantations et ~100 diagnostics associés à une coopérative de démo.

---

## Tests

```bash
pytest tests/ -v
```
Les tests utilisent une base SQLite en mémoire — aucun impact sur la DB réelle.

---

## Migrations

Toute modification du schéma passe par Alembic — **ne jamais modifier la base directement**.

```bash
# Créer une migration après modification des modèles
alembic revision --autogenerate -m "description"

# Appliquer
alembic upgrade head

# Revenir en arrière
alembic downgrade -1
```

---

## Variables d'environnement

| Variable | Obligatoire | Description |
|---|---|---|
| `SECRET_KEY` | Oui | Clé de signature JWT (min. 32 chars aléatoires) |
| `ENVIRONMENT` | Non | `development` \| `test` \| `production`. **Défaut : `production`** — toute valeur absente, vide ou inconnue est traitée comme la production (fail-closed) |
| `DATABASE_URL` | Non | URL PostgreSQL — SQLite local si absent |
| `ALLOWED_ORIGINS` | Non | Origines CORS autorisées (virgule-séparées) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Non | Durée du token JWT (défaut : 120) |

> **`ENVIRONMENT` est une variable de sécurité.** Seules les valeurs
> `development` et `test` desserrent une protection : c'est le seul cas où
> `POST /auth/forgot-password` renvoie le lien de réinitialisation dans sa
> réponse HTTP (dépannage d'un admin unique verrouillé). Ne jamais poser
> `development` ou `test` sur un serveur accessible depuis Internet.

---

## Rôles et permissions

| Endpoint | admin | agronomist | technician |
|---|:---:|:---:|:---:|
| POST /plantations | ✅ | ❌ | ❌ |
| GET /plantations | ✅ | ✅ | ✅ |
| POST /cacao/diagnostic | ✅ | ✅ | ❌ |
| POST /diagnostic/image | ✅ | ❌ | ✅ |
| GET /map/* | ✅ | ✅ | ✅ |
| GET /satellite/* | ✅ | ✅ | ✅ |
