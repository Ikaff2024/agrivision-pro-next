# 15. Scénario de prise en main — « du planteur au lot conforme »

> Un **parcours guidé de bout en bout** pour découvrir l'essentiel en une seule séance.
> Il sert à la fois de **fil conducteur de formation** (avec exercices) et de **démonstration**.
> Comptez ~15 min pour survoler, ~45 min avec les exercices.

## À quoi ça sert
- Découvrir la plateforme comme une **histoire** : du producteur jusqu'au lot vendable, pas menu par menu.
- **Former** un nouvel utilisateur (agronome, technicien, gestionnaire) avec des gestes concrets.
- Retenir les **règles clés** : catégorie obligatoire, verrou récolte/achat, pré-contrôle EUDR.

## Prérequis
- Un compte **administrateur** ou **gestionnaire** de la coopérative.
- Après une mise à jour de la plateforme : rechargez **une fois** avec **Ctrl+Maj+R**.
- Idéalement, votre **registre importé** (voir [Import d'un registre](10_import_registre.md)), sinon la coopérative de démonstration.

---

## Étape 0 — Se repérer et rencontrer Aya
1. Connectez-vous : vous arrivez sur l'écran **Opérations** (page d'accueil).
2. Ouvrez **Piloter ▸ Aya · Assistant IA**. **Aya** est votre assistante : elle explique où trouver une fonction et répond sur vos chiffres.
3. **Exercice** : demandez à Aya « **Où ajouter un producteur ?** » puis « **Combien de parcelles sont non conformes EUDR ?** ».

> **Point clé** : Aya répond à partir de **vos** données et n'invente aucun chiffre. Détails : [Aya · Assistant IA](14_assistant_ia.md).

## Étape 1 — Enregistrer les producteurs avec la bonne catégorie *(obligatoire)*
Chaque planteur est soit **Membre** (la coopérative organise sa **récolte**), soit **Non-membre** (on **achète** sa production bord champ). Cette catégorie est **obligatoire** : elle conditionne toute la chaîne (récolte ou achat, seuil OHADA de 20 % d'achats).
1. **Producteurs ▸ Nouveau producteur**.
2. Renseignez le nom puis la **Catégorie** (obligatoire) : **Membre** ou **Non-membre**. Sans catégorie, la création est **refusée**.
3. **Exercice** : créez **1 membre** et **1 non-membre**.

> **Point clé** : fini le « tout le monde est membre » par défaut.

## Étape 2 — Reclasser en masse *(coopérative à gros volume)*
Après un import, des milliers de producteurs peuvent être tous « membre ». On corrige **en une fois**.
1. **Producteurs** → (au besoin) filtrez par **recherche** ou **localité** → bouton **Classer en masse**.
2. Choisissez la **catégorie cible** (ex. Non-membre) : l'**aperçu** indique le nombre impacté. Laissez cochée l'option « **ne toucher que l'autre catégorie** » pour ne pas réécrire les déjà classés, puis **Appliquer**.
3. Réservé aux rôles **administrateur / gestionnaire**.

> **Exercice** : filtrez une localité, passez-la en non-membre, vérifiez le KPI **Part achats**.

## Étape 3 — Pré-contrôle EUDR **avant** d'intégrer une parcelle
Le critère décisif pour vendre en Europe : **aucune déforestation après le 31/12/2020**. On le vérifie **avant** d'acheter ou d'intégrer la parcelle.
1. **Opérations** → bouton **Pré-contrôle EUDR**.
2. Saisissez **latitude / longitude** (ou **GPS**) → **Vérifier**. Verdict : **Feu vert** / **Achat déconseillé** / **Indéterminé**.

> **Point clé** : on ne perd pas de temps à intégrer une parcelle non vendable. « Indéterminé » = contrôle satellite réel non activé (mode simulation). Voir [EUDR & Conformité](07_eudr_conformite.md).

## Étape 4 — Créer la plantation *(catégorie du propriétaire)*
1. **Opérations ▸ Nouvelle plantation**.
2. Renseignez nom, propriétaire, **Catégorie du propriétaire** (obligatoire, appliquée si le propriétaire est **nouveau**), position **GPS** et superficie.

> **Astuce** : délimiter la parcelle sur la **Carte** améliore la précision satellite et EUDR — voir [Diagnostic, Carte & Satellite](03_diagnostic_carte_satellite.md).

## Étape 5 — Saisir la production : le **verrou récolte / achat**
Règle métier : **Membre = récolte uniquement** ; **Non-membre = achat uniquement**. La plateforme **bloque** l'erreur.
- **Membre → Récoltes** : choisissez la parcelle grâce au **champ de recherche** (tapez quelques lettres) puis **Saisir une récolte**.
- **Non-membre → Achats** : le formulaire ne propose **que** les non-membres ; enregistrez l'achat (il génère une trace de volume traçable).
- **Démonstration du verrou** : tentez une récolte sur une parcelle de non-membre → **message de blocage** ; tentez un achat à un membre → **blocage**. C'est voulu (intégrité + OHADA).

> **Nouveauté** : partout où il y a des milliers de parcelles/producteurs, un **champ de recherche** filtre instantanément. Détails : [Achats, Lots & Certification](05_achats_lots_certification.md).

## Étape 6 — Piloter : le **palmarès des parcelles**
1. **Opérations** → section **Palmarès des parcelles**.
2. Onglet **⚠️ À redresser** : les 50 parcelles au risque le plus **élevé** → cibler l'appui technique.
3. Onglet **🏆 Modèles** : les 50 **meilleures** → visites d'échange, champs-écoles, diffusion des bonnes pratiques (« faire école »).

> **Point clé** : on **priorise** l'action et on s'appuie sur les meilleurs comme **modèles**.

---

## Récapitulatif express *(à retenir)*
- **Catégorie obligatoire** à la création ; **reclassement en masse** pour rattraper l'historique.
- **Membre = récolte, non-membre = achat** (verrou automatique).
- **Pré-contrôle EUDR** avant d'intégrer une parcelle.
- **Recherche cherchable** partout (parcelles, producteurs).
- **Palmarès** pour prioriser ; **Aya** pour être guidé.

## En cas de problème
- **Le champ de recherche n'apparaît pas** → rechargez avec **Ctrl+Maj+R** (nouvelle version).
- **Un achat est refusé** → le producteur est **Membre** : saisissez une récolte, ou reclassez-le en non-membre.
- **Une récolte est refusée** → la parcelle appartient à un **Non-membre** : passez par **Achats**.
- **Bouton « Classer en masse » absent** → réservé aux rôles **administrateur / gestionnaire**.
