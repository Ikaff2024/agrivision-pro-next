# ── Stage 1 : dépendances ─────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Dépendances système minimales pour psycopg2 et compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2 : image finale ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Sécurité : utilisateur non-root
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Dépendances runtime PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copier les packages installés du builder
COPY --from=builder /install /usr/local

# Copier le code source
COPY --chown=appuser:appuser . .

# Créer le dossier uploads
RUN mkdir -p uploads && chown appuser:appuser uploads

# Passer à l'utilisateur non-root
USER appuser

# Variables d'environnement par défaut (override via docker-compose / .env)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

EXPOSE 8000

# Healthcheck intégré
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Démarrage : appliquer les migrations puis lancer l'API
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT"]
