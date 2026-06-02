# 8. FarmForce — Revenu vital (Livret de suivi)

### À quoi ça sert
Évaluer le **revenu** d'un ménage producteur et le comparer au **seuil de revenu vital**
(Living Income). C'est un indicateur clé de **durabilité** et un argument pour les acheteurs.

### Les notions en clair
- **Revenu** = ventes (cacao, café, vivrier, élevage…).
- **Coûts** = intrants, main-d'œuvre, etc.
- **Profit** = Revenu − Coûts.
- **Dépenses du ménage** = alimentation, éducation, santé, autres.
- **Revenu net disponible** = Profit − Dépenses du ménage.
- **Verdict revenu vital** : le revenu net est comparé au **seuil** (paramétrable). Résultat :
  **« atteint »** ou **« écart »** (avec le montant manquant).

### Saisir / consulter une évaluation (pas à pas)
1. Menu **FarmForce**.
2. Pour une **nouvelle** évaluation : choisissez le producteur, la **campagne**, puis renseignez
   les **revenus**, **coûts**, **main-d'œuvre familiale**, **dépenses du ménage**…
3. Enregistrez. L'application calcule **profit**, **revenu net** et le **verdict revenu vital**.
4. Téléchargez le **PDF du Livret** si besoin.

### Importer depuis l'outil Excel
- Vous pouvez **importer** une évaluation depuis le fichier Excel officiel (digital data capturing tool) :
  utilisez l'option d'import et indiquez le producteur concerné.

### Lire le récapitulatif
- Le résumé montre le **nombre d'évaluations**, le **profit total**, le **rendement moyen par jour de travail familial**.
- Le **Dashboard direction** affiche le **taux de ménages au seuil vital** et le **revenu net moyen**.

### Astuces
- Le **seuil de revenu vital** est un réglage serveur (`LIVING_INCOME_BENCHMARK_CFA`, défaut 2 360 000 FCFA).
  Il peut être ajusté par l'administrateur sans toucher aux données déjà saisies.

### En cas de problème
| Problème | Solution |
|---|---|
| Verdict vide | Le seuil n'est peut-être pas défini ; contactez l'administrateur. |
| Import Excel échoue | Vérifiez que c'est bien le **modèle officiel** et qu'un producteur est indiqué. |
