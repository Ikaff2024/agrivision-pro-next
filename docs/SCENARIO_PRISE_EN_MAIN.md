# Scénario de prise en main — « du planteur au lot conforme » (démo & formation)

Ce parcours guidé sert à la fois de SCRIPT DE DÉMONSTRATION (~15 min) et de SCÉNARIO DE FORMATION pratique (~45 min avec exercices). On suit une histoire de bout en bout ; à chaque étape : ce qu'on fait, ce qu'on observe, le point clé.

Prérequis :
- Un compte administrateur ou gestionnaire de la coopérative.
- Après une mise à jour de la plateforme : recharger une fois avec Ctrl+Maj+R.
- Idéalement le registre de la coopérative importé (sinon, la coopérative de démonstration).

## Étape 0 — Se repérer et rencontrer Aya
- Se connecter : on arrive sur l'écran OPÉRATIONS (page d'accueil).
- Ouvrir « Aya · Assistant IA » (pilier Piloter). Aya est votre assistante : elle explique où trouver une fonction et répond sur vos chiffres.
- Exercice : demander à Aya « Où ajouter un producteur ? » puis « Combien de parcelles non conformes EUDR ? ».
- Point clé : Aya répond à partir de VOS données et n'invente aucun chiffre.

## Étape 1 — Enregistrer les producteurs avec la bonne catégorie (obligatoire)

Chaque planteur est soit MEMBRE (la coopérative organise sa récolte), soit NON-MEMBRE (on achète sa production bord champ). Cette catégorie est désormais OBLIGATOIRE : elle conditionne toute la chaîne (récolte ou achat, seuil OHADA de 20 % d'achats).
- Producteurs → « Nouveau producteur ».
- Renseigner le nom puis la CATÉGORIE (obligatoire) : Membre ou Non-membre. Sans catégorie, la création est refusée.
- Exercice : créer 1 membre et 1 non-membre.
- Point clé : fini le « tout le monde est membre » par défaut.

## Étape 2 — Reclasser en masse (coopérative à gros volume)

Après un import, des milliers de producteurs peuvent être tous « membre ». On corrige en une fois.
- Producteurs → (option) filtrer par recherche / localité → bouton « Classer en masse ».
- Choisir la catégorie cible (ex. Non-membre) : l'aperçu indique le nombre impacté. Laisser cochée l'option « ne toucher que l'autre catégorie » pour ne pas réécrire les déjà classés, puis Appliquer.
- Réservé aux rôles administrateur / gestionnaire.
- Exercice : filtrer une localité, tout passer en non-membre, vérifier le KPI « Part achats ».

## Étape 3 — Pré-contrôle EUDR AVANT d'intégrer une parcelle

Le critère décisif pour vendre en Europe : aucune déforestation après le 31/12/2020. On le vérifie AVANT d'acheter ou d'intégrer la parcelle.
- Opérations → bouton « Pré-contrôle EUDR ».
- Saisir latitude / longitude (ou GPS) → Vérifier. Verdict : Feu vert / Achat déconseillé / Indéterminé.
- Point clé : on ne perd pas de temps à intégrer une parcelle non vendable. « Indéterminé » = contrôle satellite réel non activé (mode simulation).
- Exercice : tester un point GPS.

## Étape 4 — Créer la plantation (catégorie du propriétaire)
- Opérations → « Nouvelle plantation ».
- Renseigner nom, propriétaire, CATÉGORIE DU PROPRIÉTAIRE (obligatoire, appliquée si le propriétaire est nouveau), position GPS et superficie.
- Astuce : délimiter la parcelle (Carte) améliore la précision satellite et EUDR.

## Étape 5 — Saisir la production : le verrou récolte / achat

Règle métier : MEMBRE = récolte uniquement ; NON-MEMBRE = achat uniquement. La plateforme bloque l'erreur.
- Membre → Récoltes : choisir la parcelle grâce au CHAMP DE RECHERCHE (taper quelques lettres) puis « Saisir une récolte ».
- Non-membre → Achats : le formulaire ne propose QUE les non-membres ; enregistrer l'achat (il génère une trace de volume traçable).
- Démonstration du verrou : tenter une récolte sur une parcelle de non-membre → message de blocage ; tenter un achat à un membre → blocage. C'est voulu (intégrité + OHADA).
- Nouveauté : partout où il y a des milliers de parcelles/producteurs, un champ de recherche filtre instantanément.

## Étape 6 — Piloter : le palmarès des parcelles
- Opérations → section « Palmarès des parcelles ».
- Onglet « À redresser » : les 50 parcelles au risque le plus élevé → cibler l'appui technique.
- Onglet « Modèles » : les 50 meilleures → visites d'échange, champs-écoles, diffusion des bonnes pratiques (« faire école »).
- Point clé : on priorise l'action et on s'appuie sur les meilleurs comme modèles.

## Récapitulatif express (à retenir)
- Catégorie OBLIGATOIRE à la création ; reclassement en masse pour rattraper l'historique.
- Membre = récolte, non-membre = achat (verrou automatique).
- Pré-contrôle EUDR AVANT d'intégrer une parcelle.
- Recherche cherchable partout (parcelles, producteurs).
- Palmarès pour prioriser ; Aya pour être guidé.
