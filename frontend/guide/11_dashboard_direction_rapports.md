# 11. Dashboard, Direction & Rapports

## 11.A — Dashboard (tableau de bord d'accueil)

### À quoi ça sert
La page d'**accueil** après connexion : vue **opérationnelle** de votre coopérative.

### Ce qu'on y voit
- **Cockpit « Vue 360° »** (Admin/Agronome) : indicateurs **cliquables** — Producteurs actifs, Conformité
  EUDR, Enfants à risque, Revenu vital atteint, Volume campagne, **Volume non tracé** (récoltes pas encore
  affectées à un lot — cliquer ouvre **Lots** pour les rattacher), Volume certifié, Alertes ouvertes. Cliquer
  une métrique **ouvre la page concernée pré-filtrée** sur ce sous-ensemble (ex. « X conformes » → liste EUDR
  filtrée sur les parcelles conformes).
- **Compteurs agronomiques** : nombre de plantations, répartition du **risque agronomique** (faible/moyen/élevé).
- **Parcelles à surveiller** : les parcelles aux **scores agronomiques les plus faibles** (à traiter en priorité).
- **Analyse agronomique** (graphiques) : répartition des risques, distribution des scores, scores par région.

> Le mot **« risque »** ici = **agronomique** (santé des parcelles, issu des diagnostics).

> 📐 **Le tableau de bord s'adapte à votre plan** : les indicateurs de modules non inclus dans votre
> abonnement sont **masqués** (et la grille se réorganise automatiquement) — vous ne voyez que ce qui
> vous concerne.

---

## 11.B — Direction (vue stratégique)

### À quoi ça sert
Une vue **consolidée pour la direction** : conformité et durabilité en un coup d'œil. Réservée aux
rôles **Administrateur** et **Agronome**.

> 🤖 Bouton **« Synthèse IA »** : génère un **résumé exécutif** (situation, risques prioritaires,
> 2 recommandations chiffrées) à partir de vos KPI, via le moteur IA configuré.

### Ce qu'on y voit
- **Périmètre** : producteurs actifs, plantations, superficie.
- **Conformité EUDR** : taux de conformité, statuts, score moyen.
- **Protection de l'enfant** : enfants suivis, à risque, taux de scolarisation, blocages.
- **Revenu vital** : taux de ménages au seuil, revenu net moyen.
- **Volumes & certification** : volume total, volume certifié, taux certifié.
- **Alertes** ouvertes.

### Pas à pas
1. Menu **Direction**.
2. Lisez les **cartes KPI** et les jauges. Cliquez **Actualiser** pour rafraîchir.

---

## 11.C — Rapports

### À quoi ça sert
Accéder aux **rapports CacaoGuard** et documents de **due diligence** (synthèse de conformité,
export PDF), cloisonnés à votre coopérative.

### Pas à pas
1. Menu **Rapports**.
2. Consultez la synthèse et **téléchargez** le rapport (PDF) si proposé.

### En cas de problème
| Problème | Solution |
|---|---|
| « Direction » affiche 403 / inaccessible | Réservé Admin/Agronome ; connectez‑vous avec le bon rôle. |
| Chiffres à 0 | Aucune donnée saisie encore dans le module concerné (normal au démarrage). |
| Les chiffres semblent globaux | Tout est **cloisonné par coopérative** ; faites **Ctrl + F5**. |

---

## 11.D — Scénario guidé (piloter en 3 minutes)

> Routine de direction, du global au cas précis.

1. **Dashboard** : lisez le **cockpit Vue 360°**. Repérez une métrique à traiter (ex. **Enfants à risque** = 3).
2. **Drill-down** : cliquez la métrique → vous arrivez sur la **liste filtrée** correspondante (ex. enfants à
   risque élevé/critique), pas sur toutes les données.
3. **Conformité EUDR** : cliquez « X non conf. » → la liste EUDR ne montre que les parcelles à corriger.
4. **Direction** (Admin/Agronome) : vérifiez les jauges consolidées (EUDR, revenu vital, volumes).
5. **Rapports** : téléchargez le **rapport de due diligence (PDF)** pour l'acheteur.
