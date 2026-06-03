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
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Header
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User, ImportBatch, Producer, Plantation
from app.auth.auth_service import get_current_user
from app.importers.cooperative_registry import parse_registry
from app.importers.registry_loader import load_registry

logger = logging.getLogger("agrivision.importer")

router = APIRouter(prefix="/import", tags=["import"])

# Taille maximale acceptee : 50 Mo
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _check_owner_key(x_owner_key):
    """Verifie la cle proprietaire IKAFFANAN LTD (meme regle que les routes owner)."""
    owner_key = os.getenv("OWNER_API_KEY")
    if not owner_key:
        raise HTTPException(status_code=503, detail="OWNER_API_KEY non configurée sur le serveur.")
    if x_owner_key != owner_key:
        raise HTTPException(status_code=401, detail="Clé propriétaire invalide.")


def _blocking_dependencies(db: Session, plantation_ids, producer_ids) -> dict:
    """
    Recense les donnees derivees qui interdisent l'annulation d'un import
    (signe d'une utilisation reelle, par opposition aux entites creees par l'import).
    Retourne un dict {libelle: nombre} limite aux types effectivement presents.
    """
    from app.db.models import Harvest, Diagnostic, AgroforestryRecord, PlantationBoundary

    deps = {}
    if plantation_ids:
        deps["récoltes"] = db.query(func.count(Harvest.id)).filter(
            Harvest.plantation_id.in_(plantation_ids)).scalar() or 0
        deps["diagnostics"] = db.query(func.count(Diagnostic.id)).filter(
            Diagnostic.plantation_id.in_(plantation_ids)).scalar() or 0
        deps["inventaires agroforestiers"] = db.query(func.count(AgroforestryRecord.id)).filter(
            AgroforestryRecord.plantation_id.in_(plantation_ids)).scalar() or 0
        deps["délimitations de parcelle"] = db.query(func.count(PlantationBoundary.id)).filter(
            PlantationBoundary.plantation_id.in_(plantation_ids)).scalar() or 0
    if producer_ids:
        try:
            from app.db.models_social import Child
            deps["enfants suivis"] = db.query(func.count(Child.id)).filter(
                Child.producer_id.in_(producer_ids)).scalar() or 0
        except Exception:
            pass
    return {k: v for k, v in deps.items() if v}


def _guarded_cancel(db: Session, batch: ImportBatch, cancelled_by_user_id):
    """
    Annule un import : garde-fous puis suppression des entites du lot.
    Leve HTTPException(409) si l'annulation est interdite (donnees derivees).
    Retourne (producers_deleted, plantations_deleted).
    """
    if batch.status != "active":
        raise HTTPException(status_code=409, detail="Cet import a déjà été annulé.")

    plantations = db.query(Plantation).filter(
        Plantation.import_batch_id == batch.batch_uuid).all()
    producers = db.query(Producer).filter(
        Producer.import_batch_id == batch.batch_uuid).all()
    plantation_ids = [p.id for p in plantations]
    producer_ids = [p.id for p in producers]

    # Garde-fou : refus si des donnees derivees existent (message clair).
    deps = _blocking_dependencies(db, plantation_ids, producer_ids)
    if deps:
        detail = "Annulation impossible : des données dépendantes existent (" + \
            ", ".join(f"{n} {label}" for label, n in deps.items()) + \
            "). Supprimez-les d'abord ou corrigez les fiches une à une."
        raise HTTPException(status_code=409, detail=detail)

    # Suppression via ORM (laisse jouer les cascades delete-orphan).
    # Filet de securite : toute contrainte residuelle -> rollback + 409 clair.
    try:
        for pl in plantations:
            db.delete(pl)
        db.flush()
        for pr in producers:
            db.delete(pr)
        db.flush()
        batch.status = "cancelled"
        batch.cancelled_at = datetime.now(timezone.utc)
        batch.cancelled_by_user_id = cancelled_by_user_id
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.warning("Annulation import %s impossible : %s", batch.batch_uuid, e)
        raise HTTPException(
            status_code=409,
            detail="Annulation impossible : des données dépendent encore de cet import.",
        )

    return len(producers), len(plantations)


def _batch_to_dict(b: ImportBatch) -> dict:
    return {
        "batch_uuid": b.batch_uuid,
        "fichier_source": b.fichier_source,
        "campaign": b.campaign,
        "producers_created": b.producers_created,
        "plantations_created": b.plantations_created,
        "status": b.status,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "cancelled_at": b.cancelled_at.isoformat() if b.cancelled_at else None,
    }


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
            user_id=current_user.id,
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


# ─── Historique & annulation des imports ─────────────────────────────────────

@router.get("/batches")
def list_import_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Historique des imports de la cooperative de l'admin (plus recent d'abord)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")
    batches = (
        db.query(ImportBatch)
        .filter(ImportBatch.cooperative_id == current_user.cooperative_id)
        .order_by(ImportBatch.created_at.desc())
        .all()
    )
    return [_batch_to_dict(b) for b in batches]


@router.delete("/batches/{batch_uuid}")
def cancel_import_batch(
    batch_uuid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Annule un import errone : supprime UNIQUEMENT les producteurs/plantations
    crees par cet import. Admin, sur les imports de sa propre cooperative.
    Refuse si des donnees derivees existent (recoltes, diagnostics, enfants...).
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Droits administrateur requis.")
    batch = db.query(ImportBatch).filter(
        ImportBatch.batch_uuid == batch_uuid,
        ImportBatch.cooperative_id == current_user.cooperative_id,
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Import introuvable.")

    producers_deleted, plantations_deleted = _guarded_cancel(db, batch, current_user.id)
    return {
        "message": "Import annulé.",
        "batch_uuid": batch_uuid,
        "producers_deleted": producers_deleted,
        "plantations_deleted": plantations_deleted,
    }


@router.delete("/owner/batches/{batch_uuid}")
def owner_cancel_import_batch(
    batch_uuid: str,
    db: Session = Depends(get_db),
    x_owner_key: str = Header(None),
):
    """
    Annulation d'un import par le proprietaire IKAFFANAN (toutes cooperatives) :
    utile pour purger une coop de test. Memes garde-fous que l'annulation admin.
    """
    _check_owner_key(x_owner_key)
    batch = db.query(ImportBatch).filter(ImportBatch.batch_uuid == batch_uuid).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Import introuvable.")

    producers_deleted, plantations_deleted = _guarded_cancel(db, batch, None)
    return {
        "message": "Import annulé (propriétaire).",
        "batch_uuid": batch_uuid,
        "cooperative_id": batch.cooperative_id,
        "producers_deleted": producers_deleted,
        "plantations_deleted": plantations_deleted,
    }
