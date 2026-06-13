# 3. Diagnostic, Carte & délimitation, Satellite

## 3.A — Diagnostic agronomique

### À quoi ça sert
Évaluer la **santé d'une parcelle** à partir de critères (maladies, âge, pluviométrie, ombrage)
et obtenir un **score** + un **niveau de risque** (Faible / Moyen / Élevé).

### Pas à pas
1. Menu **Diagnostic**.
2. Choisissez la **plantation**.
3. Renseignez les champs proposés (humidité, pluviométrie, température, âge, ombrage…).
4. Lancez l'analyse → vous obtenez un **score sur 100** et un **niveau de risque**.
5. Le diagnostic est **enregistré** et apparaît dans l'historique (et sur le Dashboard).

> Le « **risque** » du diagnostic est **agronomique** (santé des arbres) — à ne pas confondre
> avec le risque « travail des enfants » (CacaoGuard) ni la conformité EUDR.

---

## 3.B — Carte & délimitation des parcelles

### À quoi ça sert
Voir vos parcelles sur une **carte** et **tracer leurs contours** (polygone), indispensable pour l'EUDR.

### Choisir et afficher
1. Menu **Carte**.
2. Filtrez par niveau de risque si besoin, ou cliquez une plantation dans la liste de gauche.

### Délimiter une parcelle — 3 méthodes (de la plus simple à la plus précise)
1. Cliquez **Délimiter une parcelle**, choisissez la plantation, puis :

**① Générer (surface) ⭐ — le plus simple (1 clic)**
- Cliquez **Générer (surface)**. L'application dessine **automatiquement un carré** de la taille
  de la superficie déclarée, centré sur le point GPS de la parcelle.
- **Glissez les coins** pour ajuster si besoin, puis **Enregistrer**.
- Idéal quand vous connaissez la superficie et que vous êtes au bureau.

**② Dessiner à la main**
- Cliquez **Dessiner à la main**, puis **cliquez sur la carte** pour poser chaque coin.
  Double-cliquez pour terminer. Min. 3 points. Puis **Enregistrer**.

**③ Tracer par GPS (terrain) — le plus exact**
- Cliquez **Tracer par GPS**, puis **marchez autour de la parcelle** avec votre téléphone :
  l'application capture les points. Après ~10 points, **Enregistrer**.
- C'est la méthode de référence pour une délimitation **conforme EUDR**.

### Astuces
- Le panneau affiche la **superficie calculée** et la compare à la superficie déclarée (en %).
- Un écart vert = cohérent ; un écart rouge = à vérifier.

---

## 3.C — Satellite (NDVI / NDMI / déforestation)

### À quoi ça sert
Mesurer **à distance** la santé de la végétation (NDVI), l'humidité du couvert (NDMI),
voir l'**évolution sur 12 mois**, et les **alertes de déforestation** — sans aller sur place.

### Analyser une plantation (coordonnées automatiques)
1. Menu **Satellite**.
2. Dans **Analyse par plantation**, choisissez la plantation : **ses coordonnées se remplissent toutes seules**.
3. Cliquez **Analyser**.
4. Lisez le résultat : **NDVI** (jauge), statut (Saine / Modérée / Stressée / Indéterminée),
   et la carte **Analyse avancée** (NDMI, courbes NDVI/NDMI, statut déforestation).

### Analyser un point GPS quelconque
- Section **Analyse par coordonnées** : tapez Latitude/Longitude (ou **Utiliser ma position GPS**) → **Analyser**.

### Comment lire les indices
| Indice | Ce qu'il dit |
|---|---|
| **NDVI** élevé (> 0,7) | Végétation dense et saine. |
| **NDVI** bas (≤ 0,35) | « Indéterminée » : sol nu / eau / hors parcelle → vérifiez les coordonnées. |
| **NDMI** | Teneur en eau (humide / sec). |
| **Déforestation** | Alertes post-2020 (seuil EUDR). « Aucune perte » = bon signe. |

> La **source** est affichée : « Sentinel‑2 (Copernicus) » = données réelles ; « simulation » = clés satellite
> non configurées (données de démonstration). C'est honnête et volontaire.

### ⚠️ Point d'interprétation important (déforestation vs NDVI)
- Les **alertes de déforestation** sont calculées sur le **polygone exact de la parcelle** si elle est
  **délimitée** (le plus juste pour l'EUDR) ; sinon sur une **zone d'environ 1 km** autour du point.
  Le texte sous l'indicateur précise le périmètre utilisé. 👉 **Délimitez vos parcelles** pour un compte fiable.
- « Perte détectée » = **signal à vérifier**, pas une condamnation.
- **Un bon NDVI ne veut PAS dire « conforme EUDR »** : une forêt défrichée après 2020 puis plantée en
  cacao donne un couvert dense (NDVI élevé) **tout en étant** une déforestation. C'est exactement le cas
  que l'EUDR cible.
- **Que faire si « Perte détectée » ?** 1) délimitez la parcelle au plus juste (tracé GPS terrain),
  2) faites un **constat terrain** dans le module **EUDR**, 3) traitez la non‑conformité si confirmée.
- Un panneau **« Comment lire ces résultats ? »** est disponible directement sous l'analyse avancée.

### En cas de problème
| Problème | Solution |
|---|---|
| « simulation » au lieu de Sentinel‑2 | Les clés Copernicus ne sont pas configurées sur le serveur (réglage administrateur). |
| Coordonnées vides après sélection | La plantation n'a pas de GPS : renseignez‑le dans **Plantations**. |
| NDVI « Indéterminée » | Le point tombe sur du sol nu/eau : vérifiez le GPS de la parcelle. |

---

## 3.D — Scénario guidé (cas concret)

> Sur la **Parcelle 1 de Koffi Yao** : poser un diagnostic, tracer le polygone, vérifier le satellite.

1. **Diagnostic** — Menu **Diagnostic** → plantation `Parcelle 1` → renseignez humidité, pluviométrie,
   température, âge du verger, ombrage → **Analyser** → score /100 + niveau de risque (enregistré).
2. **Délimiter** — Menu **Carte → Délimiter une parcelle** → `Parcelle 1` :
   - au bureau : **Générer (surface)** (carré de 4,5 ha à ajuster aux coins), ou
   - sur le terrain : **Tracer par GPS** (faire le tour) → **Enregistrer**. *(Requis pour l'EUDR.)*
3. **Satellite** — Menu **Satellite → Analyse par plantation** → `Parcelle 1` (coordonnées auto) →
   **Analyser** → lisez NDVI / NDMI + statut déforestation.

> ➡️ Étape suivante : agroforesterie et récoltes (chapitre 4).
