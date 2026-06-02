# 2. Plantations & Producteurs

## 2.A — Plantations

### À quoi ça sert
Gérer la liste de vos **parcelles de cacao** : nom, propriétaire, région, superficie, GPS.
C'est la base de tout : diagnostics, récoltes, satellite, EUDR s'appuient sur la plantation.

### Qui peut l'utiliser
Création/modification : **Admin** (et selon réglages, agronome). Consultation : tous.

### Créer une plantation (pas à pas)
1. Menu **Plantations** → bouton **+ Nouvelle plantation** (ou **Ajouter**).
2. Remplissez :
   - **Nom** (ex. « Parcelle Soubré »)
   - **Propriétaire** (nom du producteur) — s'il n'existe pas, il est **créé automatiquement**.
   - **Pays**, **Région**
   - **Latitude / Longitude** : tapez-les, ou cliquez **Utiliser ma position GPS** si vous êtes sur la parcelle.
   - **Superficie (hectares)** — important : sert au calcul satellite et à la délimitation rapide.
3. Cliquez **Créer**.

### Modifier une plantation
- Dans la liste, ouvrez la plantation → bouton **Modifier** → changez les champs → **Enregistrer**.

### Astuces
- Renseignez **toujours la superficie et le GPS** : ça débloque la carte, le satellite et l'EUDR.
- Le **propriétaire** saisi crée/relie un **producteur** : pas besoin de le créer deux fois.

---

## 2.B — Producteurs (annuaire)

### À quoi ça sert
Voir **tous les producteurs** de votre coopérative au même endroit : code, nom, localité,
section, téléphone — avec un accès direct à leur **fiche détaillée** (profil).

### Pas à pas
1. Menu **Producteurs**.
2. La liste s'affiche avec le **nombre total**, le nombre de **localités**.
3. **Rechercher** : tapez un nom, un code ou un téléphone dans la barre de recherche — la liste se filtre toute seule.
4. Cliquez sur **Profil →** au bout d'une ligne pour ouvrir la fiche complète du producteur
   (parcelles, enfants suivis, évaluations, statut de traçabilité…).

### D'où viennent les producteurs ?
- De la **création de plantations** (le propriétaire devient producteur), ou
- De l'**import d'un registre Excel** (voir fiche *Import d'un registre*).

### Astuces
- Si un producteur s'affiche avec un **code** comme nom (ex. `PROD0001`), c'est qu'il a été
  importé d'un registre **sans colonne de noms** : vous pourrez compléter son nom plus tard.

### En cas de problème
| Problème | Solution |
|---|---|
| La liste est vide | Aucun producteur encore : créez une plantation ou importez un registre. |
| Je ne trouve pas un producteur | Utilisez la recherche (nom **ou** code **ou** téléphone). |
| Je ne vois pas le menu « Producteurs » | Faites **Ctrl + F5** ; sinon, voir votre plan d'abonnement. |
