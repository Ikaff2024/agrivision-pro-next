# Sauvegarde & reprise après incident (Disaster Recovery)

> But : **aucune coopérative ne doit perdre ses données** si Railway (ou la base) a un souci,
> et pouvoir **repartir vite**. Ce document est le mode d'emploi (mise en place + restauration).
>
> ⚠️ Sauvegarde ≠ disponibilité. Une sauvegarde protège contre la **perte de données**.
> Elle n'empêche pas une **coupure** temporaire pendant une panne Railway (voir § Disponibilité).

## Objectifs (RPO / RTO)
- **RPO** (perte de données maximale acceptable) : **≤ 6 h** (sauvegarde hors-site toutes les 6 h).
- **RTO** (temps de remise en service) : **~15–60 min** (restauration d'un dump dans une base neuve + repointage).

## Défense en profondeur — 3 niveaux

### Niveau 1 — Sauvegardes natives Railway (à activer dans la console)
Première ligne de défense, la plus simple à restaurer (même plateforme).
1. Railway → projet → service **base `agrivision-db`** → onglet **Backups**.
2. Activer les **sauvegardes automatiques** (quotidiennes) si le plan le permet.
3. Tester une **restauration** depuis l'interface au moins une fois (voir checklist).

> Limite : si le **compte/region Railway** est indisponible, ces sauvegardes le sont aussi.
> → d'où le niveau 2, **hors Railway**.

### Niveau 2 — Sauvegarde hors-site automatique chiffrée (GitHub Actions) ✅ fournie
Workflow **`.github/workflows/backup.yml`** : toutes les 6 h, fait un `pg_dump`, le **chiffre**
(AES-256) et le stocke comme **artefact GitHub** (hors Railway). Survit à une panne Railway.

**Mise en place (5 min, une seule fois) :**
1. Récupère la **chaîne de connexion PUBLIQUE** de la base : Railway → `agrivision-db` →
   Variables → **`DATABASE_PUBLIC_URL`** (forme `postgresql://user:pass@…proxy.rlwy.net:PORT/railway`).
   *(L'URL interne `…railway.internal` ne marche pas depuis GitHub — il faut la publique.)*
2. Choisis une **phrase secrète** longue et unique (gestionnaire de mots de passe). C'est la **clé**
   de déchiffrement des sauvegardes : **sans elle, les sauvegardes sont irrécupérables**. Garde-la
   en lieu sûr, **séparément** de GitHub.
3. GitHub → repo **agrivision-pro-next** → **Settings → Secrets and variables → Actions** →
   *New repository secret*, crée :
   - **`BACKUP_DATABASE_URL`** = l'URL publique de l'étape 1.
   - **`BACKUP_PASSPHRASE`** = la phrase secrète de l'étape 2.
4. (Important) Les workflows planifiés (`schedule`) ne tournent que sur la **branche par défaut**
   du repo. Assure-toi que `codex/cacaoguard-fusion` est la **branche par défaut**
   (Settings → Branches), **ou** déclenche la sauvegarde manuellement (étape 5).
5. Vérifie : onglet **Actions** → « Sauvegarde DB (hors-site) » → **Run workflow**. Au bout d'une
   minute, un **artefact** `avp-db-backup-AAAAMMJJ-HHMMSS` apparaît (fichier `.dump.enc`).

> Sécurité/RGPD : les dumps contiennent des **données sensibles** (producteurs, enfants). Ils sont
> **chiffrés** avant tout stockage → un artefact seul est inexploitable sans la phrase secrète.
> Pour une séparation plus forte, voir § Stockage externe (Backblaze B2 / S3).

### Niveau 3 — Sauvegarde manuelle avant une opération sensible
Avant une **mise en prod**, une migration, un import massif… prends un instantané :
```bash
# WSL / Linux / Git-Bash, Docker requis. (openssl côté hôte)
BACKUP_PASSPHRASE='votre-phrase' \
DATABASE_URL='postgresql://…proxy.rlwy.net:PORT/railway' \
./ops/backup_db.sh ./backups
# → ./backups/avp-AAAAMMJJ-HHMMSS.dump.enc
```

## Restauration (en cas d'incident)
On restaure un dump chiffré dans une **base de destination** (une nouvelle base Railway, ou ailleurs).

```bash
# 1. Crée une nouvelle base PostgreSQL (Railway → New → Database → PostgreSQL),
#    récupère sa chaîne PUBLIQUE = TARGET_DATABASE_URL.
# 2. Restaure :
BACKUP_PASSPHRASE='votre-phrase' \
TARGET_DATABASE_URL='postgresql://…(NOUVELLE base)…' \
./ops/restore_db.sh ./backups/avp-AAAAMMJJ-HHMMSS.dump.enc
# 3. Repointe l'API : service agrivision-api → Variable DATABASE_URL = URL INTERNE de la nouvelle base.
#    Railway redéploie ; vérifier /health → {"database":"postgresql","persistent":true}.
```
> `restore_db.sh` applique `--clean --if-exists` : il **remplace** les objets existants dans la base
> cible. Restaure de préférence dans une base **neuve** pour éviter d'écraser des données vivantes.

## Disponibilité — « ne pas s'arrêter »
Les sauvegardes garantissent qu'on **ne perd pas les données**. Pendant une panne Railway, l'app peut
être **momentanément indisponible**. Pour réduire ce temps :
- **Court terme (en place)** : restauration rapide (RTO ~15–60 min) vers une base neuve + repointage.
  Les **prix de la veille** et l'app restent toutefois dépendants du backend Railway.
- **Moyen terme (option)** : **base de secours (read replica / standby)** chez un autre hébergeur,
  promue en cas de panne. C'est un **projet d'infra dédié** (coût + complexité) — à décider plus tard.
- **Monitoring** : une **page de statut**/sonde uptime (UptimeRobot gratuit sur `/health`) prévient
  dès qu'il y a un souci. (Voir backlog OPS.)

## Stockage externe (option, recommandé à terme)
Les artefacts GitHub conviennent au démarrage. Pour une vraie séparation hors-GitHub, pousser le
`.dump.enc` vers un **bucket privé** (Backblaze B2 ~quelques €/mois, ou S3) : ajouter une étape
`rclone copy` dans `backup.yml` avec les secrets du bucket. Les dumps restent **chiffrés**.

## Checklist « test de restauration » (à faire 1×/trimestre)
- [ ] Télécharger le dernier artefact `.dump.enc`.
- [ ] Créer une base PostgreSQL **jetable**.
- [ ] `restore_db.sh` dans cette base.
- [ ] Vérifier le nombre de coopératives / producteurs / plantations (cohérent avec la prod).
- [ ] Supprimer la base jetable. Noter la date du test ici :

| Date du test | Par | Résultat |
|---|---|---|
| _(à remplir)_ | | |

## Récapitulatif des secrets (jamais dans le code)
| Secret (GitHub Actions) | Valeur | Où le trouver |
|---|---|---|
| `BACKUP_DATABASE_URL` | URL **publique** de la base | Railway → `agrivision-db` → `DATABASE_PUBLIC_URL` |
| `BACKUP_PASSPHRASE` | phrase secrète de chiffrement | la vôtre, stockée hors-ligne |
