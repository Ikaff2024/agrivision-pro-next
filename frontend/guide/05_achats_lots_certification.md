# 5. Achats, Traçabilité des lots & Certification

## 5.A — Achats producteurs

### À quoi ça sert
Enregistrer les **achats bord champ** : pesée, bon d'achat, prix, montant — et suivre le **paiement**
(comptable). Chaque achat peut **générer une récolte traçable** rattachée à une parcelle.

> ⚠️ **Important** : le module gère le **suivi** (payé / en attente). Il **n'exécute aucun virement** —
> c'est de la comptabilité, pas un moyen de paiement.

### Enregistrer un achat (pas à pas)
1. Menu **Achats**.
2. Choisissez le **Producteur** (la liste s'affiche ; s'il y a un blocage CacaoGuard, un avertissement 🚫 apparaît).
3. Choisissez la **Plantation** (recommandé : génère une récolte traçable).
4. Renseignez la **pesée** :
   - **Poids brut** et **Tare (sacs)** → le **Poids net** se calcule tout seul (ou saisissez le net directement),
   - **Nb de sacs**, **Prix au kg** → le **Montant total** se calcule automatiquement.
5. **Qualité**, **n° de bon d'achat**, **acheteur**, **statut de paiement** (En attente / Payé).
6. Cliquez **Enregistrer l'achat**.

### Marquer un achat comme payé
- Dans la liste, bouton **Marquer payé** (réservé admin/agronome) → c'est un suivi comptable.

### Astuces
- Reliez toujours une **plantation** : l'achat alimente alors automatiquement les volumes et les lots.
- Le **récapitulatif** affiche kg achetés, montant total, payé vs en attente.

---

## 5.B — Traçabilité des lots

### À quoi ça sert
Regrouper des récoltes en **lots** physiques, suivre leurs **mouvements** (entrée magasin, scellage,
expédition), les **fusionner**, et éditer un **passeport de traçabilité** (PDF) pour l'acheteur/auditeur.

### Créer un lot (pas à pas)
1. Menu **Traçabilité lots**.
2. (Optionnel) Créez d'abord un **entrepôt** (panneau de gauche : nom + lieu → **+ Entrepôt**).
3. **Nouveau lot** : campagne, entrepôt, puis **choisissez une plantation** → cochez les **récoltes libres** à inclure.
4. **Créer le lot** : un **code** unique est généré (ex. `LOT-2026-00001`), le **poids** et le **nb de sacs** se calculent.

> 🔒 **Sécurité CacaoGuard** : si une récolte appartient à un producteur **bloqué** (cas travail des enfants),
> l'application **refuse** de l'ajouter au lot (message d'erreur). C'est voulu : la traçabilité physique
> hérite de la conformité sociale.

### Suivre le cycle de vie d'un lot
- Ouvrez un lot → boutons : **Entrée magasin** (choisir l'entrepôt), **Sceller**, **Expédier**.
- Chaque action est **journalisée** (historique des mouvements).

### Fusionner des lots
- Sélectionnez plusieurs lots sources → ils sont combinés en un **nouveau lot** ; les sources passent en « fusionné ».

### Éditer le passeport (PDF)
- Ouvrez un lot → bouton **Passeport** → un **PDF à la charte** s'ouvre : composition (producteurs/parcelles),
  conformité EUDR, blocages éventuels, historique des mouvements.

---

## 5.C — Certification

### À quoi ça sert
Gérer les **audits** de certification (Rainforest Alliance, Fairtrade, Cocoa Horizons…),
les **non-conformités** et leurs **actions correctives** avec **échéances**.

### Créer un audit (pas à pas)
1. Menu **Certification**.
2. Panneau **Nouvel audit** : standard, type (interne / externe / surveillance), date, organisme, périmètre → **Créer l'audit**.
3. L'audit est **« planifié »**. Plus tard, ouvrez-le et **Clôturez-le** avec un résultat
   (Réussi / Conditionnel / Échec) et un score %.

### Enregistrer une non-conformité (NC)
1. Panneau **Nouvelle non-conformité** : reliez-la à un audit (facultatif), choisissez la **sévérité**
   (Mineure / Majeure / Critique), décrivez le problème, l'**action corrective**, le **responsable** et l'**échéance**.
2. **Enregistrer**. Une NC dont l'échéance est dépassée s'affiche **« en retard »**.

### Résoudre une NC
- Dans la liste, bouton **Résoudre** → la NC passe « résolue » (date de résolution enregistrée).

### Les KPIs en haut
- Audits, NC ouvertes, **NC en retard**, audits planifiés : un coup d'œil pour piloter.

### En cas de problème
| Problème | Solution |
|---|---|
| Producteur « bloqué » au moment d'un lot | Cas CacaoGuard à résoudre d'abord (voir fiche CacaoGuard). |
| Le passeport sort « page web » | Vous avez une vieille version : **Ctrl + F5** (le passeport est un vrai PDF serveur). |
| Liste des standards vide | Le référentiel (FT, RA…) est initialisé côté serveur ; contactez l'admin si absent. |
