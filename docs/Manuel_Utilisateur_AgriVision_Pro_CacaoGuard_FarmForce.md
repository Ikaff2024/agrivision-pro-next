# Manuel utilisateur AgriVision Pro

Modules AgriVision, CacaoGuard et FarmForce

Version : guide local de prise en main - mai 2026  
Public : administrateurs, superviseurs, agents terrain et techniciens de cooperative cacao  
Environnement : projet local de validation, sans impact sur la version en production

## 1. Vue generale

AgriVision Pro est une plateforme de gestion de cooperative cacao. Elle centralise les producteurs, les plantations, les diagnostics agronomiques, les recoltes, la tracabilite et les modules terrain.

Deux modules complementaires sont integres :

- **FarmForce** : compte d'exploitation producteur base sur le formulaire PDF client.
- **CacaoGuard** : prevention, detection, remediation et preuve contre le travail des enfants.

## 2. Premier demarrage

1. Ouvrir l'adresse locale de l'application.
2. Se connecter avec le compte fourni.
3. Verifier le menu lateral : Plantations, Diagnostic, Recoltes, FarmForce, puis CacaoGuard.
4. Si l'API ne repond pas, verifier que le backend local est demarre sur le port de test prevu.

## 3. Module FarmForce

FarmForce numerise le cahier papier du client : identification producteur, menage, parcelles, ventes, couts, travail familial, main-d'oeuvre embauchee et resultat annuel.

### Saisir un formulaire

1. Ouvrir **FarmForce** dans le menu.
2. Selectionner le producteur.
3. Renseigner la campagne, par exemple `2025-2026`.
4. Ajouter les membres du menage.
5. Ajouter les parcelles.
6. Saisir les rentrees : mois, produit, quantite, prix unitaire.
7. Saisir les couts : intrants, outils, transport, emballages, services.
8. Saisir le travail familial.
9. Saisir la main-d'oeuvre embauchee.
10. Verifier les indicateurs calcules puis cliquer sur **Enregistrer**.

### Indicateurs calcules

- **Rentrees CFA** : somme des ventes saisies.
- **Couts CFA** : couts agricoles + main-d'oeuvre embauchee.
- **Profit CFA** : rentrees moins couts.
- **Journees familiales** : total des journees de travail familial.
- **Retour par jour** : profit divise par les journees familiales.

## 4. Module CacaoGuard

CacaoGuard aide la cooperative a prevenir, detecter, remedier et demontrer l'absence de travail des enfants.

### Fiche enfant

1. Ouvrir **Protection enfant**.
2. Choisir le producteur parent.
3. Saisir l'identite, l'age, le statut scolaire et le statut travail.
4. Renseigner les taches observees ou declarees.
5. Enregistrer. Le risque est calcule automatiquement.

### Evaluation des risques

1. Ouvrir **Evaluation risque**.
2. Selectionner le producteur.
3. Renseigner les facteurs : enfants en age scolaire, distance a l'ecole, taches, main-d'oeuvre, revenu.
4. Enregistrer l'evaluation.

### Monitoring terrain

1. Ouvrir **Monitoring**.
2. Selectionner le producteur et le type de visite.
3. Completer la checklist.
4. Ajouter localisation, consentement, photos et signature si disponibles.
5. Enregistrer. Hors ligne, la saisie est synchronisee plus tard.

### Remediation

1. Ouvrir **Remediation**.
2. Creer ou consulter le plan lie au cas.
3. Ajouter les actions : inscription scolaire, kit scolaire, soutien economique, sensibilisation, suivi.
4. Mettre a jour le statut jusqu'a resolution.

### Formation

1. Ouvrir **Formation**.
2. Planifier la session : theme, date, lieu, formateur.
3. Ajouter les participants et resultats de quiz.
4. Utiliser l'historique comme preuve de prevention.

### Conformite et rapports

- La page **Conformite** liste les producteurs a examiner et les blocages actifs.
- Un lot peut etre bloque si un cas grave reste non resolu.
- Le rapport CacaoGuard PDF rassemble indicateurs, preuves, visites, plans, formations, blocages et journaux d'acces.

## 5. Travail hors ligne

- Ne pas fermer brutalement le navigateur apres une saisie hors ligne.
- Verifier l'indicateur de synchronisation avant de quitter le terrain.
- Revenir sur la page une fois connecte pour confirmer que la file est vide.

## 6. Confidentialite

- Les donnees enfants sont sensibles.
- Les photos doivent etre prises avec consentement.
- Les rapports externes doivent limiter les informations nominatives inutiles.
- Les journaux d'acces permettent de verifier les consultations sensibles.

## 7. Checklist avant audit

- Producteurs actifs rattaches a une localite ou section.
- Enfants suivis avec statut scolaire et statut travail.
- Visites critiques avec lieu, consentement et preuves.
- Plans de remediation avec prochaine action.
- Blocages tracabilite justifies.
- Rapport CacaoGuard PDF genere correctement.
- Formulaires FarmForce saisis pour la campagne cible.
- Donnees sensibles controlees avant partage.

## 8. Depannage rapide

| Probleme | Cause probable | Action conseillee |
|---|---|---|
| Page non chargee | Serveur local arrete | Relancer les serveurs locaux |
| API inaccessible | Backend indisponible | Verifier le port local de test |
| Producteur absent | Registre non importe ou producteur inactif | Verifier l'import producteurs |
| Saisie hors ligne invisible | Synchronisation en attente | Reconnecter puis attendre la synchronisation |
| PDF non genere | Dependances PDF ou erreur rapport | Reessayer puis signaler au support technique |

