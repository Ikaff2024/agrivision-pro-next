#!/bin/sh
echo "=== Création des tables ==="
python -c "
from app.db.database import engine, Base
import app.db.models
Base.metadata.create_all(bind=engine)
print('Tables OK')
"
echo "=== Démarrage API ==="
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
