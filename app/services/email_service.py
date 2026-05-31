"""
Service d'envoi d'emails (SMTP) avec fallback sans configuration.

Utilise par le flux "mot de passe oublie". Si aucun serveur SMTP n'est
configure (variable SMTP_HOST absente), l'email n'est pas envoye : le lien
est journalise (utile en dev / diagnostic) et la fonction renvoie False.
Le endpoint appelant renvoie volontairement le meme message generique dans
tous les cas, afin de ne pas reveler si un email existe (anti-enumeration).
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger("agrivision.email")


def smtp_is_configured() -> bool:
    return bool(os.getenv("SMTP_HOST"))


def app_base_url() -> str:
    """URL de base du frontend pour construire les liens (sans slash final)."""
    return os.getenv("APP_BASE_URL", "https://agrivision-pro-next.netlify.app").rstrip("/")


def send_email(to_email: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    """
    Envoie un email via SMTP. Renvoie True si envoye, False si SMTP non
    configure ou en cas d'erreur (l'erreur est journalisee, pas levee).
    """
    if not smtp_is_configured():
        logger.warning(
            "SMTP non configure : email '%s' a %s NON envoye. Corps:\n%s",
            subject, to_email, body_text,
        )
        return False

    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM", user or "no-reply@agri-vision-pro.com")
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"}
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body_text)
    if body_html:
        message.add_alternative(body_html, subtype="html")

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as server:
                if user and password:
                    server.login(user, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                if use_tls:
                    server.starttls(context=ssl.create_default_context())
                if user and password:
                    server.login(user, password)
                server.send_message(message)
        logger.info("Email '%s' envoye a %s.", subject, to_email)
        return True
    except Exception as exc:  # noqa: BLE001 - on ne casse jamais le flux applicatif
        logger.error("Echec d'envoi email a %s : %s", to_email, exc)
        return False


def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    """Envoie l'email de reinitialisation de mot de passe."""
    subject = "AgriVision Pro — Reinitialisation de votre mot de passe"
    text = (
        "Bonjour,\n\n"
        "Vous avez demande la reinitialisation de votre mot de passe AgriVision Pro.\n"
        f"Cliquez sur le lien suivant (valable 1 heure) pour definir un nouveau mot de passe :\n\n"
        f"{reset_link}\n\n"
        "Si vous n'etes pas a l'origine de cette demande, ignorez ce message : "
        "votre mot de passe reste inchange.\n\n"
        "— AgriVision Pro"
    )
    html = (
        f"<p>Bonjour,</p>"
        f"<p>Vous avez demande la reinitialisation de votre mot de passe <strong>AgriVision Pro</strong>.</p>"
        f"<p><a href=\"{reset_link}\" style=\"background:#1a4231;color:#fff;padding:10px 18px;"
        f"border-radius:8px;text-decoration:none;display:inline-block\">Reinitialiser mon mot de passe</a></p>"
        f"<p style=\"color:#6a7d64;font-size:13px\">Lien valable 1 heure. "
        f"Si vous n'etes pas a l'origine de cette demande, ignorez ce message.</p>"
        f"<p style=\"color:#6a7d64;font-size:12px\">Lien direct : {reset_link}</p>"
    )
    return send_email(to_email, subject, text, html)
