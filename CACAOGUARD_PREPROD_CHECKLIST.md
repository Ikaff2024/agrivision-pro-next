# CacaoGuard - Checklist pre-production

Objectif : valider le module CacaoGuard comme module AgriVision Pro avant toute bascule vers la production existante.

## Perimetre protege

- Ne pas modifier les ports, domaines, secrets, repo GitHub ou workflows de la version actuellement en production sans decision explicite.
- Tester d'abord sur branche et base de pre-production.
- Conserver un export base de donnees avant migration.

## Validation technique locale

```bash
pytest tests/test_auth.py tests/test_plantations.py tests/test_cacaoguard.py -q
python -m py_compile main.py app/api/cacaoguard_ops_routes.py app/api/social_routes.py app/db/models_social.py
```

Resultat attendu au 26/05/2026 :

```text
31 passed, 2 warnings
```

## Migrations

Alembic importe maintenant `app.db.models_social`.

Commande pre-prod :

```bash
alembic upgrade head
```

Rollback de la derniere migration :

```bash
alembic downgrade 0001_baseline
```

Note Railway : le projet garde aussi `Base.metadata.create_all()` au demarrage, ce qui cree les nouvelles tables absentes. Alembic reste le chemin de reference pour la pre-prod controlee.

## Variables d'environnement

- `DATABASE_URL` : base PostgreSQL pre-prod, jamais la prod directe.
- `SECRET_KEY` : cle distincte de la prod.
- `ALLOWED_ORIGINS` : domaine frontend pre-prod + domaines locaux utiles.
- `ACCESS_TOKEN_EXPIRE_MINUTES` : valeur conforme securite coop.

## Smoke tests API CacaoGuard

```bash
curl http://127.0.0.1:8010/cacaoguard/summary
curl http://127.0.0.1:8010/compliance/report
curl http://127.0.0.1:8010/ai/inconsistencies
curl http://127.0.0.1:8010/privacy/access-logs
```

Verifier :

- Dashboard retourne producteurs/enfants/alertes.
- Rapport contient `privacy_access_logs`, `ai_inconsistencies`, `ai_critical_inconsistencies`.
- PDF `/compliance/report.pdf` retourne `application/pdf`.
- Technicien ne peut pas lire rapports sensibles, plans de remediation, logs confidentialite.

## Tests terrain navigateur

Valider hors-ligne / retour reseau sur :

- `monitoring.html`
- `risk_assessment.html`
- `training.html`
- `remediation.html`

Scenario attendu :

1. Charger la page en ligne.
2. Couper le reseau.
3. Creer une saisie.
4. Verifier le compteur `1 en attente`.
5. Retablir le reseau.
6. Cliquer `Synchroniser`.
7. Verifier compteur revenu a `0`.

## Donnees sensibles

- Verifier que les techniciens voient les donnees enfants masquees.
- Verifier que chaque consultation enfant ou rapport ajoute une entree `/privacy/access-logs`.
- Verifier que les signatures monitoring contiennent `payload_hash`, `device_id`, `signed_at`, `consent_given`.

## Conformite sociale

- Creer un enfant risque critique.
- Confirmer creation automatique :
  - alerte,
  - plan de remediation,
  - blocage tracabilite.
- Generer le rapport due diligence.
- Lancer `/ai/inconsistencies?create_alerts=true` sur un cas incoherent et verifier l'alerte `audit_failure`.

## Rollback fonctionnel

Avant bascule :

1. Exporter la base pre-prod.
2. Conserver le frontend AgriVision Pro prod actuel.
3. Ne pas pointer le domaine prod vers le nouveau frontend tant que la coop pilote n'a pas valide.
4. En cas de rollback :
   - remettre l'ancien frontend,
   - redemarrer l'API precedente,
   - ne pas supprimer les tables CacaoGuard sans export.

## Definition du pret pilote

- Tests automatises verts.
- 1 parcours producteur/enfant complet valide par utilisateur metier.
- 1 visite offline synchronisee.
- 1 rapport PDF accepte par superviseur.
- 1 blocage tracabilite resolu.
- 1 revue confidentialite validee.
