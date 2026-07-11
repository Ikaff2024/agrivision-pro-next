# 13. Jumeau de parcelle & Parcelles à risque

### À quoi ça sert
Le **jumeau de parcelle** est une **photo 360°** de chaque parcelle : il **rassemble au même endroit**
tout ce que l'application sait déjà d'elle (conformité, diagnostic, récoltes, revenu, certification,
protection de l'enfant…) et en déduit une **liste d'alertes claires avec, pour chacune, l'action à mener**.

La page **Parcelles à risque** fait la même chose mais pour **toute la coopérative d'un coup** :
elle **classe les parcelles de la plus à risque à la moins à risque**, pour savoir **par où commencer**.

> En une phrase : le jumeau ne crée **aucune nouvelle donnée**, il **relie** ce que vous avez déjà saisi
> et vous dit **quoi traiter en priorité**. C'est un outil d'aide à la décision, en **lecture seule**.

### Les notions en clair
- **Descriptif, pas devin** : le jumeau décrit l'état réel à partir de vos données. Il ne fait **aucune
  prédiction hasardeuse**. Chaque alerte est **explicable** (on sait exactement pourquoi elle apparaît).
- **Sévérité** d'une alerte : **🔴 élevé** (à traiter en priorité), **🟠 moyen**, **⚪ faible**.
- **Plus vous remplissez les autres modules** (diagnostic, EUDR, récoltes, Revenu vital, certification…),
  **plus le jumeau est riche et juste**. Une parcelle « vide » remonte surtout des alertes « à compléter ».
- **Jumeau du ménage (Palier 2, prédictif *léger et explicable*)** : une première brique existe pour la
  **protection de l'enfant** — l'indicateur **« 🔮 Priorités d'enquête »** (page **Protection enfant**)
  classe les ménages par **risque précoce** de travail d'enfant, **en affichant les facteurs**. C'est une
  **aide à l'enquête** (priorise les visites), **jamais un verdict**. Voir [Protection de l'enfant](16_protection_enfant.md).

### Où le trouver
1. **Sur une parcelle** : ouvrez une plantation (menu **Plantations** → une parcelle). Tout en bas,
   la carte **« 🧭 Jumeau de la parcelle — synthèse »** affiche les **indicateurs** (puces) et les **alertes**.
2. **Pour toute la coopérative** : menu **Parcelles à risque**. Vous y voyez le **tableau de bord** et la
   **liste classée** des parcelles à traiter.

### Lire la fiche d'une parcelle
Les **puces** résument chaque dimension (vert = bon, rouge = à traiter) :

| Puce | Ce qu'elle montre |
|---|---|
| **Conformité EUDR** | Score /6 et statut (conforme / à vérifier / non conforme). |
| **Délimitation** | La parcelle a-t-elle un **polygone** tracé sur la carte (requis EUDR). |
| **Diagnostic** | Dernier diagnostic agronomique et son niveau de risque. |
| **Récoltes** | Total récolté et **rendement** (kg/ha). |
| **Déforestation** | Résultat du dernier contrôle satellite. |
| **Météo** | Conditions actuelles (température, humidité, pluie sur 30 j). |
| **Revenu vital** | Revenu net du ménage vs seuil : **Atteint** ou **Écart**. |
| **Certification** | La parcelle a-t-elle une certification **active** ou **expirée**. |
| **Protection enfant** | Producteur **bloqué** ou **plan de remédiation en cours**. |

### Utiliser la page « Parcelles à risque » (pas à pas)
1. Menu **Parcelles à risque**.
2. En haut, 4 chiffres : **parcelles** au total, **signalées**, en **risque élevé**, en **risque moyen**.
3. Filtrez avec les puces **Toutes / Risque élevé / Risque moyen / Risque faible**.
4. La liste est **classée** : les parcelles avec le plus d'alertes graves sont **en haut**.
5. Pour chaque parcelle : les **alertes** et la **recommandation**. Cliquez sur **Ouvrir la fiche →**
   pour aller traiter le problème sur la parcelle.
6. Bouton **Actualiser** pour recalculer, **Voir plus** pour charger la suite.

### Comprendre les alertes
On ne signale que des situations **actionnables** (on n'inonde pas la liste pour une simple donnée manquante).

| Alerte | Sévérité | Que faire |
|---|---|---|
| Parcelle non délimitée | 🔴 | Tracer le polygone sur la **Carte** (requis EUDR). |
| Non conforme EUDR / à vérifier | 🔴 / 🟠 | Traiter les blocages sur la page **EUDR**. |
| Déforestation détectée / contrôle à faire | 🔴 / 🟠 | Lancer/vérifier le contrôle satellite (page **EUDR**). |
| Blocage traçabilité CacaoGuard | 🔴 | Traiter via le **plan de remédiation**. |
| Plan de remédiation en cours | 🔴 | Suivre le plan de **protection de l'enfant** jusqu'à clôture. |
| Revenu vital non atteint | 🔴 | Renforcer les revenus (diversification, productivité, primes). |
| Risque agronomique élevé | 🔴 | Intervention agronomique prioritaire. |
| Certification expirée | 🟠 | Planifier le **renouvellement**. |
| Diagnostic absent / de +12 mois | 🟠 | Réaliser / refaire un **diagnostic** terrain. |
| Verger âgé / rendement faible | 🟠 | Diagnostiquer les causes ; envisager une **replantation**. |
| Aucune récolte enregistrée | ⚪ | Saisir les **récoltes** pour suivre la production. |

### Astuces
- **Coût : nul.** Le jumeau ne fait que lire vos données — pas d'appel facturé, pas de risque.
- **Routine conseillée** : ouvrez **Parcelles à risque** en début de semaine, filtrez sur **Risque élevé**,
  et traitez la liste de haut en bas. C'est votre **plan d'action**.
- Pour qu'une parcelle « se vide » de ses alertes, **complétez le module concerné** (tracer le polygone,
  faire le diagnostic, saisir le livret Revenu vital, etc.) — l'alerte disparaît au prochain **Actualiser**.

### Scénario guidé (cas concret)

> Vérifier l'état complet de la **Parcelle 1 de Koffi Yao**, puis prioriser à l'échelle de la coopérative.

1. **Menu Plantations → `Parcelle 1`** → tout en bas, carte **« 🧭 Jumeau de la parcelle — synthèse »** :
   lisez les **puces** (EUDR, délimitation, diagnostic, récoltes, déforestation, revenu vital, certification,
   protection enfant) et les **alertes** avec, pour chacune, l'action recommandée.
2. **Menu Parcelles à risque** → filtrez **Risque élevé** → traitez la liste **de haut en bas**
   (chaque ligne renvoie à la fiche pour agir).

### En cas de problème
| Problème | Solution |
|---|---|
| « Aucune parcelle à risque » | Tant mieux 🎉 — ou aucune donnée n'est encore saisie : remplissez les modules. |
| Une parcelle a beaucoup d'alertes « à compléter » | Normal pour une parcelle neuve : saisissez diagnostic, délimitation, récoltes. |
| Le menu **Parcelles à risque** est absent | Votre plan ne l'inclut peut-être pas, ou reconnectez-vous (le menu se met à jour). |
| Revenu vital « Non évalué » | Aucun **livret Revenu vital** pour ce producteur — saisissez-en un (voir fiche 8). |
