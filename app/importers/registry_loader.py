"""
registry_loader.py
====================
Couche d'insertion en base des donnees parsees par cooperative_registry.

Insere en 3 vagues :
  1. Campagne (cree si absente)
  2. Producteurs (UPSERT par code_yeyasso : pas de doublon entre imports)
  3. Plantations + liens de certification (UPSERT par code_plantation)

Idempotent : relancer le meme import ne cree pas de doublons.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger("agrivision.importer")


import unicodedata


def _norm_projet(projet) -> str:
    """Normalise une valeur de projet : majuscules, sans accent, espaces nets."""
    if not projet:
        return ""
    s = str(projet).strip()
    nfkd = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in nfkd if not unicodedata.combining(c))
    return s.upper()


# Mapping PROJET (colonne Excel) -> liste de codes certification.
# Les cles sont normalisees (majuscules, sans accent). Ajustable apres
# confirmation du gerant. Une valeur inconnue est ignoree (la plantation
# est creee sans certification, signale en avertissement).
PROJET_CERTIFICATION_MAP = {
    "FT-RA":            ["FT", "RA"],
    "FT-DELICA":        ["FT"],          # Delica = programme acheteur, FT = certif
    "FT-GALLER":        ["FT"],          # Galler = programme acheteur, FT = certif
    "BIO":              ["BIO"],
    "CONVERSION BIO":   ["BIO"],         # en conversion : rattache a BIO
    # Clients/acheteurs sans certification (confirme par le gerant) :
    "SI":               [],          # Shared Impact = client, ventes non certifiees
    "ACT":              [],          # Action = client, ventes non certifiees
}


@dataclass
class ImportReport:
    campaign: str = None
    batch_uuid: str = None
    producers_created: int = 0
    producers_updated: int = 0
    plantations_created: int = 0
    plantations_updated: int = 0
    certifications_linked: int = 0
    deliveries_created: int = 0
    formation_participations_created: int = 0
    rows_skipped: int = 0
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    duration_seconds: float = 0.0

    def as_dict(self) -> dict:
        return {
            "campaign": self.campaign,
            "batch_uuid": self.batch_uuid,
            "producers_created": self.producers_created,
            "producers_updated": self.producers_updated,
            "plantations_created": self.plantations_created,
            "plantations_updated": self.plantations_updated,
            "certifications_linked": self.certifications_linked,
            "deliveries_created": self.deliveries_created,
            "formation_participations_created": self.formation_participations_created,
            "rows_skipped": self.rows_skipped,
            "warnings": self.warnings[:50],   # limite la taille de la reponse
            "warnings_total": len(self.warnings),
            "errors": self.errors,
            "duration_seconds": round(self.duration_seconds, 1),
        }


def _ensure_base_certifications(db):
    """
    Garantit la presence des certifications de base.
    En production elles sont seedees au demarrage (main.py), mais le loader
    doit etre autonome (tests, premier import avant un redeploiement, etc.).
    """
    from app.db.models import Certification
    base = [
        ("FT", "Fairtrade", "FLOCERT"),
        ("RA", "Rainforest Alliance", "Rainforest Alliance"),
        ("EUDR", "EU Deforestation Regulation", "Union Europeenne"),
        ("ARS_1000", "ARS 1000 - Cacao durable", "Conseil Cafe-Cacao"),
        ("BIO", "Agriculture Biologique", "Ecocert"),
    ]
    existing = {c.code for c in db.query(Certification).all()}
    for code, nom, org in base:
        if code not in existing:
            db.add(Certification(code=code, nom_complet=nom,
                                 organisme=org, actif=True))
    db.flush()


def load_registry(parse_result, db, cooperative_id, fichier_source=None, user_id=None):
    """
    Insere en base le resultat d'un parsing de registre.

    Args:
        parse_result : RegistryParseResult issu de parse_registry()
        db            : session SQLAlchemy
        cooperative_id: id de la cooperative cible
        fichier_source: nom du fichier importe (tracabilite)
        user_id       : id de l'utilisateur a l'origine de l'import (tracabilite)

    Returns:
        ImportReport
    """
    import time
    import uuid as _uuid
    from app.db.models import (
        Producer, Plantation, Campagne, Certification,
        PlantationCertification, FormationSession, FormationParticipant,
        ImportBatch,
    )

    t0 = time.time()
    report = ImportReport()

    if parse_result.errors:
        report.errors.extend(parse_result.errors)
        return report

    # --- Lot d'import : permet d'annuler cet import en masse plus tard --------
    batch_uuid = _uuid.uuid4().hex
    report.batch_uuid = batch_uuid
    import_batch = ImportBatch(
        batch_uuid=batch_uuid,
        cooperative_id=cooperative_id,
        user_id=user_id,
        fichier_source=fichier_source,
        status="active",
    )
    db.add(import_batch)
    db.flush()

    # --- Vague 1 : Campagne -------------------------------------------------
    campagne = None
    libelle = parse_result.detected_campaign
    if libelle:
        campagne = db.query(Campagne).filter(
            Campagne.cooperative_id == cooperative_id,
            Campagne.libelle == libelle,
        ).first()
        if not campagne:
            campagne = Campagne(
                cooperative_id=cooperative_id,
                libelle=libelle,
                fichier_source=fichier_source,
                est_courante=False,
            )
            db.add(campagne)
            db.flush()
        report.campaign = libelle

    # --- Pre-chargement des certifications ----------------------------------
    _ensure_base_certifications(db)
    cert_by_code = {c.code: c for c in db.query(Certification).all()}

    # --- Vague 2 : Producteurs (UPSERT par code_yeyasso) --------------------
    # Index des producteurs existants de la cooperative
    existing_producers = {
        p.code_yeyasso: p
        for p in db.query(Producer).filter(
            Producer.cooperative_id == cooperative_id,
            Producer.code_yeyasso.isnot(None),
        ).all()
    }

    producer_by_code = dict(existing_producers)  # sera complete au fur et a mesure

    for pp in parse_result.producers:
        existing = existing_producers.get(pp.code_yeyasso)
        if existing:
            # Mise a jour : on ne remplace que par des valeurs non nulles
            if pp.nom_complet:
                existing.nom_complet = pp.nom_complet
            if pp.sexe:
                existing.sexe = pp.sexe
            if pp.date_naissance:
                existing.date_naissance = datetime.combine(
                    pp.date_naissance, datetime.min.time())
            if pp.telephone:
                existing.telephone = pp.telephone
            if pp.code_saco:
                existing.code_saco = pp.code_saco
            if pp.recepisse:
                existing.recepisse = pp.recepisse
            if pp.section:
                existing.section = pp.section
            if pp.localite:
                existing.localite = pp.localite
            if pp.formateur_interne_nom:
                existing.formateur_interne_nom = pp.formateur_interne_nom
            if pp.piece_numero:
                existing.piece_identite_numero = pp.piece_numero
            if pp.piece_nature:
                existing.piece_identite_nature = pp.piece_nature
            if pp.latitude is not None:
                existing.latitude = pp.latitude
            if pp.longitude is not None:
                existing.longitude = pp.longitude
            report.producers_updated += 1
            producer_by_code[pp.code_yeyasso] = existing
        else:
            new_p = Producer(
                cooperative_id=cooperative_id,
                code_yeyasso=pp.code_yeyasso,
                nom_complet=pp.nom_complet,
                sexe=pp.sexe,
                date_naissance=(datetime.combine(pp.date_naissance, datetime.min.time())
                                if pp.date_naissance else None),
                telephone=pp.telephone,
                code_saco=pp.code_saco,
                recepisse=pp.recepisse,
                section=pp.section,
                localite=pp.localite,
                formateur_interne_nom=pp.formateur_interne_nom,
                piece_identite_numero=pp.piece_numero,
                piece_identite_nature=pp.piece_nature,
                latitude=pp.latitude,
                longitude=pp.longitude,
                is_active=True,
                import_batch_id=batch_uuid,
            )
            db.add(new_p)
            report.producers_created += 1
            producer_by_code[pp.code_yeyasso] = new_p

    db.flush()  # attribue les id aux nouveaux producteurs

    # --- Vague 3 : Plantations + certifications -----------------------------
    # Le code plantation est stocke dans Plantation.name (le modele n'a pas
    # de colonne code_plantation dediee). On indexe donc par name.
    existing_plantations = {
        pl.name: pl
        for pl in db.query(Plantation).filter(
            Plantation.cooperative_id == cooperative_id,
        ).all()
        if pl.name
    }

    for pp_plant in parse_result.plantations:
        code = pp_plant.code_plantation
        producer = producer_by_code.get(pp_plant.code_producteur)

        if not producer:
            # Le producteur n'est pas dans la feuille Producteurs mais apparait
            # dans la feuille Plantations. On le cree automatiquement a minima
            # (creation differee, sera enrichi a un futur import du registre
            # producteurs). Mieux vaut un producteur incomplet qu'une plantation
            # orpheline perdue.
            if not pp_plant.code_producteur:
                report.warnings.append(
                    f"Plantation {code} : aucun code producteur, plantation ignoree"
                )
                report.rows_skipped += 1
                continue
            producer = Producer(
                cooperative_id=cooperative_id,
                code_yeyasso=pp_plant.code_producteur,
                nom_complet=pp_plant.code_producteur,  # nom inconnu : on met le code
                is_active=True,
                import_batch_id=batch_uuid,
            )
            db.add(producer)
            db.flush()
            producer_by_code[pp_plant.code_producteur] = producer
            report.producers_created += 1
            report.warnings.append(
                f"Producteur {pp_plant.code_producteur} cree automatiquement "
                f"(present dans la feuille Plantations mais absent du registre Producteurs)"
            )

        plantation = existing_plantations.get(code)
        if plantation:
            if pp_plant.superficie_ha is not None:
                plantation.hectares = pp_plant.superficie_ha
            if pp_plant.latitude is not None:
                plantation.latitude = pp_plant.latitude
            if pp_plant.longitude is not None:
                plantation.longitude = pp_plant.longitude
            plantation.producer_id = producer.id
            report.plantations_updated += 1
        else:
            plantation = Plantation(
                name=code,
                owner_name=producer.nom_complet,
                country="Cote d'Ivoire",
                hectares=pp_plant.superficie_ha,
                latitude=pp_plant.latitude,
                longitude=pp_plant.longitude,
                cooperative_id=cooperative_id,
                producer_id=producer.id,
                import_batch_id=batch_uuid,
            )
            # code_plantation : colonne ajoutee au Sprint #0
            if hasattr(plantation, "code_plantation"):
                plantation.code_plantation = code
            db.add(plantation)
            report.plantations_created += 1
            existing_plantations[code] = plantation

        db.flush()  # pour avoir plantation.id

        # Liens de certification depuis le champ projet
        projet_norm = _norm_projet(pp_plant.projet)
        cert_codes = PROJET_CERTIFICATION_MAP.get(projet_norm)
        if cert_codes is None and projet_norm:
            report.warnings.append(
                f"Plantation {code} : projet '{pp_plant.projet}' non reconnu, "
                f"aucune certification liee"
            )
        elif cert_codes:
            # Liens existants pour eviter les doublons
            existing_links = {
                link.certification_id
                for link in db.query(PlantationCertification).filter(
                    PlantationCertification.plantation_id == plantation.id
                ).all()
            }
            for cc in cert_codes:
                cert = cert_by_code.get(cc)
                if cert and cert.id not in existing_links:
                    db.add(PlantationCertification(
                        plantation_id=plantation.id,
                        certification_id=cert.id,
                    ))
                    report.certifications_linked += 1

    # --- Vague 4 : Formations / sensibilisations ---------------------------
    if getattr(parse_result, "formations", None):
        session_by_theme = {}
        existing_participations = {
            (fp.formation_session_id, fp.producer_id)
            for fp in db.query(FormationParticipant)
            .join(FormationSession)
            .filter(FormationSession.cooperative_id == cooperative_id)
            .all()
        }
        for pf in parse_result.formations:
            producer = producer_by_code.get(pf.code_producteur)
            if not producer:
                report.warnings.append(
                    f"Formation ligne {pf.row_index}: producteur {pf.code_producteur} introuvable"
                )
                continue
            theme_key = " ".join(str(pf.thematique).split())
            session = session_by_theme.get(theme_key)
            if not session:
                session = db.query(FormationSession).filter(
                    FormationSession.cooperative_id == cooperative_id,
                    FormationSession.thematique == theme_key,
                    FormationSession.document_url == fichier_source,
                ).first()
                if not session:
                    session = FormationSession(
                        cooperative_id=cooperative_id,
                        thematique=theme_key,
                        lieu="Registre import",
                        formateur_nom="Registre YEYASSO",
                        document_url=fichier_source,
                    )
                    db.add(session)
                    db.flush()
                session_by_theme[theme_key] = session
            key = (session.id, producer.id)
            if key in existing_participations:
                continue
            db.add(FormationParticipant(
                formation_session_id=session.id,
                producer_id=producer.id,
                signature_present=True,
            ))
            existing_participations.add(key)
            report.formation_participations_created += 1

    # Finalise le lot d'import (compteurs + campagne) pour l'historique.
    import_batch.campaign = report.campaign
    import_batch.producers_created = report.producers_created
    import_batch.plantations_created = report.plantations_created

    db.commit()
    report.duration_seconds = time.time() - t0
    logger.info("Import termine : %s", report.as_dict())
    return report
