# =============================================================================
# AgriVision Pro - Dockerfile pour Railway
# =============================================================================
# Pourquoi un Dockerfile plutot que nixpacks ?
#   WeasyPrint depend de librairies systeme C (Cairo, Pango, GDK-Pixbuf,
#   Fontconfig...) dont l'installation via nixpacks s'est averee non-fiable.
#   Un Dockerfile garantit un environnement reproductible et explicite.
#
# Image de base : python 3.12 slim (Debian Bookworm) — ~50 Mo, recente, stable.
# =============================================================================
FROM python:3.12-slim-bookworm

# Variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# ──────────────────────────────────────────────────────────────────────────────
# Installation des libs systeme requises par WeasyPrint
# (Liste validee par la doc officielle :
#  https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)
# ──────────────────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        # Libs C requises par WeasyPrint
        libcairo2 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
        # Fonts pour rendu correct du texte FR (accents, ligatures)
        fonts-liberation \
        fonts-dejavu-core \
        fonts-noto-core \
        fontconfig \
        # libpq pour psycopg2-binary (Postgres)
        libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

# ──────────────────────────────────────────────────────────────────────────────
# Installation des dependances Python
# ──────────────────────────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ──────────────────────────────────────────────────────────────────────────────
# Copie du code applicatif
# ──────────────────────────────────────────────────────────────────────────────
COPY . .

# ──────────────────────────────────────────────────────────────────────────────
# Demarrage : Railway injecte la variable PORT (typiquement 8080)
# ──────────────────────────────────────────────────────────────────────────────
EXPOSE 8080
CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
