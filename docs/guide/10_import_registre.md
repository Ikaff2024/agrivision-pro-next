# 10. Import d'un registre Excel

### À quoi ça sert
Créer **en masse** des producteurs et des plantations à partir d'un **fichier Excel** (registre coopérative),
au lieu de tout saisir à la main. Indispensable quand vous avez des milliers de producteurs.

### Qui peut l'utiliser
**Administrateur** uniquement.

### Pas à pas
1. Menu **Administration** → bouton **Importer un registre** (ou menu d'import si présent).
2. **Sélectionnez** votre fichier `.xlsx`.
3. Un **aperçu** s'affiche : nombre de producteurs, de plantations, et les **éventuelles erreurs/avertissements**.
4. Si l'aperçu est correct, **confirmez l'import**. Les producteurs et parcelles sont créés dans **votre** coopérative.

### Formats acceptés
L'import est **souple** :
- Registre avec une feuille **« Producteurs »** + une feuille **« Plantations »** (et **Formations** en option).
- Registre **centré plantations** (une seule feuille) : les producteurs sont **déduits automatiquement**
  des codes présents. ⚠️ S'il n'y a pas de colonne de **noms**, les producteurs prennent leur **code**
  comme nom provisoire (à compléter ensuite). Un avertissement transparent le signale.

### Ce que l'import récupère
- **Producteurs** (code, nom si présent, localité, section…),
- **Plantations** (code, superficie, GPS, certification comme FT‑RA…),
- **Formations/livraisons** si les feuilles existent.

### Astuces
- L'import de **milliers** de lignes peut prendre une **trentaine de secondes** : patientez.
- Vérifiez **toujours l'aperçu** (nombres et erreurs) avant de confirmer.
- La **campagne** (ex. 2025‑2026) est détectée depuis le nom du fichier.

### En cas de problème
| Problème | Solution |
|---|---|
| « Aucune feuille producteurs ni plantations » | Le fichier n'a pas la structure attendue : vérifiez les en‑têtes (CODE PRODUCTEURS, CODE PLANTATION…). |
| Producteurs nommés par leur code | Le fichier ne contenait pas les noms : normal, complétez‑les après. |
| L'import semble bloqué | Patientez (gros fichiers) ; ne fermez pas l'onglet. |
| Page d'import « apparaît puis disparaît » | Mettez à jour l'app (**Ctrl + F5**) : ce comportement a été corrigé. |
