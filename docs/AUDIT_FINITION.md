# Audit « crédibilité & finition » — AgriVision Pro

> But : repérer ce qui peut faire « amateur » à l'usage et proposer un plan de polissage
> **priorisé**, pour inspirer confiance comme un logiciel établi (Odoo, SAGE…).
> Date : 2026-06-01. Périmètre : frontend (`frontend/`) + quelques points ops.

## Méthode
Scan du code + revue des écrans. Constats **mesurés** (comptages réels), pas d'impressions.

---

## Constats (avec preuves)

### 🔴 P1 — Incohérence des notifications (le plus visible)
- Il existe déjà un **système maison `toast()`** (joli bandeau non bloquant) dans `auth.js`,
  **utilisé par 21 pages**. ✅
- MAIS plusieurs pages **récentes** utilisent des **`alert()` bruts** (fenêtre système moche) :
  `ssrte.html` (17), `lots.html` (9), `certification.html` (7), `achats.html` (4),
  `farmforce.html` (4), `plantation_detail.html` (5), `owner.html` (1) — ~**47 `alert()`**.
- **Effet** : selon la page, les messages changent de style → sensation d'incohérence.
- **Correctif** : remplacer `alert('x')` par `toast('x')` (et `toast('x','error')` pour les erreurs).

### 🔴 P1 — Messages d'erreur génériques / peu utiles
- Beaucoup de « **impossible.** » (15×), « **Erreur.** », « **Erreur serveur** » sans contexte ni action.
- **Effet** : l'utilisateur ne sait pas quoi faire.
- **Correctif** : messages clairs + action (« Enregistrement impossible : vérifiez votre connexion. »).

### 🟠 P2 — Dialogues navigateur `confirm()` / `prompt()`
- Présents dans 7 pages (`achats`, `admin`, `agroforestry`, `assignment`, `certification`,
  `compliance`, `map`). Ex. `prompt('Résultat ?')` pour clôturer un audit.
- **Effet** : fenêtres système hors charte, peu pro, impossibles à styliser.
- **Correctif** : petite **modale maison** réutilisable (confirmation + saisie simple).

### 🟠 P2 — `console.log` / `console.error` oubliés
- ~**24 occurrences** dans ~10 pages (`diagnostic` 5, `plantation_detail` 5, `index` 3…).
- **Effet** : pas visible par l'utilisateur, mais « bruit » en console (peu pro en démo / revue technique).
- **Correctif** : retirer ou conditionner à un mode debug.

### 🟡 P3 — Finitions diverses
- **Duplication** : chaque page redéfinit `API_BASE` (pas grave, mais à centraliser dans `config.js`).
- **États de chargement / vides** : harmoniser (« Chargement… » et « Aucune donnée » au même style partout).
- **Badge de version** affiché seulement sur `map.html` → uniformiser ou retirer en prod.
- **Accessibilité légère** : `alt` sur images, focus visible, contrastes — passe rapide.

---

## Points « crédibilité » hors frontend (ops / organisation)
Ce qui rassure le plus un acheteur/auditeur sérieux :
1. **Sauvegardes automatiques PostgreSQL** (Railway) + test de restauration documenté. ⚠️ à confirmer.
2. **Domaine propre + HTTPS** en prod (`agri-vision-pro.com`) — éviter l'URL Netlify pour la prod.
3. **Rotation des secrets** (mot de passe PostgreSQL, clés) — déjà noté dans la reprise. ⚠️
4. **Page de statut / monitoring** (uptime) + **journal d'audit** (✅ déjà présent côté CacaoGuard).
5. **Politique de support** (canal, délais) et **mentions légales / RGPD** (données producteurs/enfants = sensibles).

---

## Plan d'action priorisé

| Prio | Action | Effort | Risque | Impact perçu |
|---|---|---|---|---|
| ✅ **P1** | ~~Remplacer tous les `alert()` par `toast()`~~ **FAIT** (46 conversions, type auto) | Moyen | Faible | ⭐⭐⭐ |
| ✅ **P1** | ~~Réécrire les messages d'erreur génériques en messages clairs + action~~ **FAIT** (12 pages) | Moyen | Faible | ⭐⭐⭐ |
| ✅ **P2** | ~~Modale maison pour `confirm()` / `prompt()`~~ **FAIT** (`avpConfirm`/`avpPrompt`, 11 conversions) | Moyen+ | Faible | ⭐⭐ |
| ✅ **P2** | ~~Nettoyer les `console.*`~~ **FAIT** (11 retirés) | Faible | Nul | ⭐ (revue technique) |
| 🟡 **P3** | `lang="fr"` ✅ sur toutes les pages · états vides/chargement OK. Reste : centraliser `API_BASE` (différé, invisible utilisateur, risque inutile maintenant) | Faible | Faible | ⭐ |
| **OPS** | Sauvegardes DB + domaine/HTTPS prod + rotation secrets + page statut | Variable | — | ⭐⭐⭐ (confiance) |

### Recommandation de séquence
1. **Quick wins immédiats** (sûrs, fort impact visuel) : `alert()` → `toast()` + nettoyage `console.*`.
2. Ensuite : messages d'erreur clairs, puis modale `confirm/prompt`.
3. En parallèle (toi/ops) : sauvegardes, domaine/HTTPS prod, rotation secrets.
