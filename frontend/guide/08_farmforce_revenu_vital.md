# 8. Revenu vital (Livret de suivi)

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
1. Menu **Revenu vital**.
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

### Scénario guidé (cas concret)

> Évaluer le ménage de **Koffi Yao N'Guessan**, campagne **2025-2026** (seuil revenu vital : 2 360 000 FCFA).

1. **Menu Revenu vital → Nouvelle évaluation** : producteur `Koffi Yao N'Guessan`, campagne `2025-2026`.
2. **Revenus** : cacao `1 800 kg × 1 500 FCFA = 2 700 000`, vivrier `200 000` → ≈ `2 900 000` FCFA.
3. **Coûts** : intrants `350 000`, main-d'œuvre `300 000` → `650 000` FCFA *(profit ≈ 2 250 000)*.
4. **Dépenses du ménage** : alimentation `700 000`, éducation `150 000`, santé `100 000` → `950 000` FCFA.
5. **Enregistrer** : l'appli calcule un **revenu net ≈ 1 300 000 FCFA** → **verdict : écart**
   (≈ 1 060 000 FCFA manquants pour atteindre le seuil).
6. Cet **écart** justifie une action d'**appui au revenu** (à relier au plan de remédiation, chapitre 6) ;
   il alimente la tuile « Revenu vital atteint » du tableau de bord.

### En cas de problème
| Problème | Solution |
|---|---|
| Verdict vide | Le seuil n'est peut-être pas défini ; contactez l'administrateur. |
| Import Excel échoue | Vérifiez que c'est bien le **modèle officiel** et qu'un producteur est indiqué. |
