"""
import_routes.py
==================
Endpoints REST pour l'import de registres cooperatives (Sprint #0).

  POST /import/excel    : upload + import complet en base (role admin)
  GET  /import/preview  : non disponible (preview se fait via POST dry_run)

Le fichier uploade est ecrit dans un repertoire temporaire, parse, puis
insere. Le fichier temporaire est supprime a la fin.
"""
import os
import tempfile
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User
from app.auth.auth_service import get_current_user
from app.importers.cooperative_registry import parse_registry
from app.importers.registry_loader import load_registry

logger = logging.getLogger("agrivision.importer")

router = APIRouter(prefix="/import", tags=["import"])

# Taille maximale acceptee : 50 Mo
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/excel")
async def import_excel(
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="Si true, parse et renvoie un apercu sans inserer"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Importe un registre cooperative Excel.

    - dry_run=true  : parse le fichier et renvoie un apercu (aucune ecriture DB)
    - dry_run=false : parse ET insere en base (UPSERT par code)

    Reserve au role admin.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")

    if not current_user.cooperative_id:
        raise HTTPException(
            status_code=400,
            detail="Votre compte n'est associe a aucune cooperative.",
        )

    filename = file.filename or "registre.xlsx"
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400,
            detail="Format non supporte. Fournissez un fichier .xlsx ou .xls.",
        )

    # Lire le contenu en verifiant la taille
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Fichier trop volumineux (max {MAX_UPLOAD_BYTES // (1024*1024)} Mo).",
        )

    # Ecrire dans un fichier temporaire
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # --- Parsing ---
        parse_result = parse_registry(tmp_path, filename=filename)

        if parse_result.errors:
            return {
                "status": "error",
                "stage": "parsing",
                "errors": parse_result.errors,
            }

        # --- Mode apercu (dry_run) ---
        if dry_run:
            sample_producers = [
                {
                    "code_yeyasso": p.code_yeyasso,
                    "nom_complet": p.nom_complet,
                    "sexe": p.sexe,
                    "projet": p.projet,
                    "section": p.section,
                }
                for p in parse_result.producers[:5]
            ]
            return {
                "status": "preview",
                "summary": parse_result.summary(),
                "sample_producers": sample_producers,
            }

        # --- Insertion reelle ---
        report = load_registry(
            parse_result, db,
            cooperative_id=current_user.cooperative_id,
            fichier_source=filename,
        )

        status = "error" if report.errors else "success"
        return {
            "status": status,
            "report": report.as_dict(),
        }

    except Exception as e:
        logger.error("Erreur import Excel : %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'import : {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
