# 7. EUDR & Conformité

## 7.A — EUDR (déforestation / Due Diligence)

### À quoi ça sert
Vérifier qu'une parcelle respecte le **règlement européen sur la déforestation (EUDR)** et produire
le **DDS** (Déclaration de Diligence Raisonnée) en PDF. C'est exigé par les acheteurs européens.

### Comment se calcule la conformité
Le score repose sur **6 règles** (méthodologie `eudr-1.1b`), exprimé en **pourcentage** :
1. Polygone de la parcelle **valide**,
2. **Superficie** cohérente,
3. **GPS** dans la zone cacao,
4. **Inspection récente**,
5. **Aucun blocage** de traçabilité actif,
6. **Aucune déforestation** après le 31/12/2020.

| Statut | Seuil |
|---|---|
| ✅ **Conforme** | ≥ 80 % |
| 🟠 **À vérifier** | 40 – 79 % |
| 🔴 **Non conforme** | < 40 % |

### Pas à pas
1. Menu **EUDR**.
2. Consultez le **score par parcelle** et le **résumé coopérative** (taux de conformité).
3. Pour faire **monter** le score d'une parcelle :
   - **Délimitez** la parcelle (Carte → *Tracer par GPS* de préférence) → règles 1, 2, 3.
   - Réalisez une **inspection** récente → règle 4.
   - Résolvez les **blocages** (CacaoGuard) → règle 5.
   - Renseignez/contrôlez la **déforestation** (constat terrain ou satellite GFW) → règle 6.
4. Téléchargez le **DDS PDF** pour l'acheteur.

> La **déforestation** peut être confirmée par **constat terrain** (saisie manuelle) ou
> **automatiquement** par satellite (Global Forest Watch) si les clés sont configurées.

---

## 7.B — Conformité (vue transversale)

### À quoi ça sert
Vue d'ensemble de la **conformité traçabilité** : blocages actifs, producteurs à revoir, lots impactés.

### Pas à pas
1. Menu **Conformité**.
2. Consultez les **blocages actifs**, les **producteurs à examiner** (enfants à risque non encore bloqués),
   et les **lots/livraisons impactés**.
3. Agissez : ouvrez un plan de remédiation, résolvez un blocage quand le cas est traité.

### En cas de problème
| Problème | Solution |
|---|---|
| Parcelle « à vérifier » à 0 % | Pas de polygone ni d'inspection : délimitez la parcelle et inspectez-la. |
| Le DDS PDF ne reflète pas mes changements | Régénérez-le après avoir mis à jour la parcelle. |
