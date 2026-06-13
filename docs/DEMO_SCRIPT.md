# Script de démo AgriVision Pro — « parcours en or » (~25 min)

> Pour présenter la plateforme à une **coopérative prospect** (public : direction / décideurs).
> Objectif : raconter **une histoire de bout en bout**, pas faire le tour des menus. À chaque étape :
> **ce qu'on clique**, **ce qu'on dit**, **le message de valeur**.
>
> Règle d'or : on ne « montre des fonctions », on **résout les problèmes du client** (conformité EUDR,
> travail des enfants, revenu vital, traçabilité, pilotage). On parle **bénéfice**, l'écran est la preuve.

---

## Bascule vers la coop démo « Coopérative Démo Cacao 2026 » (à faire une fois)

> ⚠️ **Prérequis avant toute démo** : le frontend doit être **publié** (Netlify). Vérifier qu'il n'y a
> plus « Yeyasso » à l'écran (ex. **Producteurs** → champ « Code interne (coopérative) ») et que le guide
> chapitre 12 ne contient plus l'espace propriétaire. Sinon : Netlify → **Deploys** → *Clear cache and deploy*.

1. **Compte de démo** : `demo3@agrivision-pro.com` / `DemoAgriVision2026!` — coop **« Coopérative Démo Cacao 2026 »** (seedée).
2. **Ancienne coop** « …Yeyasso 2026 » (`demo2@`) : depuis l'**espace propriétaire** (`owner.html`, clé propriétaire), la repasser en **suspendu/inactif** si l'option existe ; sinon, **ne pas s'y connecter**. L'essentiel : ne présenter **que** la coop « Cacao 2026 ».
3. **Logo** : Administration → charger le logo de la coop (les PDF sortent à son image).
4. **Onglets pré-ouverts** : Dashboard, Carte, une fiche Plantation, EUDR, CacaoGuard, Direction, Parcelles à risque.
5. **IA (optionnel)** : crédit Anthropic approvisionné si tu montres le Conseil IA / Veille en live (sinon, parade par capture — cf. §0).

### Le jeu de données seedé (8 parcelles à exploiter)
| Producteur | Particularité | À montrer |
|---|---|---|
| **Kouassi Yao** (Soubré) | Cas **à risque** + **blocage traçabilité** + plan de remédiation | CacaoGuard, drill-down « Enfants à risque » |
| **Konan Aka** (Méagui) | Cas **sain** (contraste) | CacaoGuard |
| **N'Guessan Adjoua** (Soubré) | **Sans délimitation** → EUDR à vérifier | EUDR, tracer le polygone |
| **Brou Amani** (Méagui) | **Déforestation** détectée | EUDR + Satellite/GFW |
| **Tanoh Affoué** (Gagnoa) | **Sans diagnostic** | Diagnostic / Parcelles à risque |
| **Kouamé Akissi** (Daloa) | **Faible rendement** | Jumeau de parcelle |
| **Diby Serge** (Soubré) | **Sans récolte** | Récoltes / Parcelles à risque |
| **Yao Koffi** (San-Pédro) | Profil complet | Parcours nominal |

Revenu vital : **1 ménage en écart + 1 atteint** · Traçabilité : **2 lots + passeports** · Certification : **8 liens FT/RA**.

### Mini-parcours conseillé (s'appuie sur le seed)
1. **Dashboard → cockpit Vue 360°** : lire les KPIs, **cliquer « Enfants à risque »** → Kouassi Yao (drill-down filtré), puis **« X conformes »** sous EUDR → liste filtrée.
2. **EUDR** : Brou Amani (déforestation) + N'Guessan Adjoua (à délimiter) → score + **DDS PDF**.
3. **CacaoGuard** : Kouassi Yao (risque → blocage → remédiation) vs Konan Aka (sain).
4. **FarmForce** : le ménage **en écart** vs **atteint**.
5. **Traçabilité** : un lot → **passeport** + **composition (Excel)**.
6. **Parcelles à risque / Jumeau** : la liste classée comme « plan d'action ».

> Le **script détaillé** (ce qu'on dit, le message de valeur) suit ci-dessous (§1 et suivants).

---

## 0. Préparation (la veille — 15 min)

**À vérifier AVANT la démo (critique) :**
- [ ] Connexion OK sur **app-agrivision-pro.com** avec le compte démo : **demo3@agrivision-pro.com** / `DemoAgriVision2026!` (admin de « Coopérative Démo Cacao 2026 »).
- [ ] **Logo de la coopérative** chargé (Administration → Logo) → les PDF sortent à leur image. ⭐ effet « waouh ».
- [ ] Un **producteur + une parcelle géolocalisée** prêts, avec : un **diagnostic**, une **délimitation (polygone)**, une **récolte**, idéalement un **contrôle déforestation**.
- [ ] **Crédit Anthropic** approvisionné si tu veux montrer le **Conseil Agronome IA** et la **Veille marché** en live (sinon, voir la parade ci-dessous).
- [ ] Onglets pré-ouverts : Carte, une fiche Plantation, EUDR, Direction, Parcelles à risque.
- [ ] Connexion internet testée ; PDF récents téléchargés en secours (si le wifi lâche).

> **Parade si l'IA n'est pas dispo (crédit) :** la quasi-totalité de la démo fonctionne **sans IA**
> (parcelles, EUDR, satellite réel, lots, fiches, PDF, pilotage). Pour le **Conseil IA** et la **Veille**,
> montre une **capture** déjà générée et dis : « cette brique s'appuie sur l'IA, activable en un clic ».

### Jeu de données de démo — le (re)créer

Le script `seed_demo.py` peuple une coopérative de démo complète : 8 parcelles en états variés (conforme,
à délimiter, déforestation, rendement faible, sans diagnostic, sans récolte), diagnostics, récoltes 2 campagnes,
agroforesterie, contrôles déforestation, achats, **lots + passeports**, CacaoGuard/SSRTE, certification, et le **revenu vital**.

```bash
# Coop démo neuve (le nom de coop doit être unique côté serveur)
AVP_DEMO_EMAIL=demo3@agrivision-pro.com \
AVP_DEMO_COOP="Coopérative Démo Cacao 2026" \
python seed_demo.py
```

> - Après le seed : se connecter à ce compte et **téléverser le logo** (Administration → Logo) — tous les PDF sortent alors à l'image de la coop. ⭐
> - Le seed est **idempotent** sur les parcelles (relançable sans doublon). Pour repartir d'une coop **vierge**, prendre un **nouveau** `AVP_DEMO_EMAIL` **et** un **nouveau** `AVP_DEMO_COOP` (un nom de coop déjà pris est refusé à l'inscription).

---

## 1. Accroche — partir de LEURS douleurs (5 min, **sans écran**)

**Ne montrez rien d'abord. Posez des questions** — le but est qu'ils disent eux-mêmes « oui, c'est compliqué » :
- Combien de temps pour **retrouver les infos d'une parcelle** (GPS, superficie, historique) ?
- Comment préparez-vous les **audits Rainforest / Fairtrade** aujourd'hui ?
- Comment **prouvez-vous qu'un lot vient de plantations conformes** quand un acheteur le demande ?
- Combien de temps pour **produire un rapport demandé par un acheteur** ?
- Êtes-vous **prêts pour l'EUDR** (zéro déforestation prouvée + géolocalisation des parcelles) ?

Puis, en une phrase de bascule :
> « AgriVision Pro relie le producteur, sa parcelle, ses récoltes et le lot vendu, **avec la preuve de
> conformité générée automatiquement**. Je ne vais pas vous montrer un logiciel — je vais vous montrer
> ce que votre coopérative **devient** : plus organisée, crédible face aux acheteurs, prête pour l'EUDR. »

**Premier (et seul) écran d'intro : le Dashboard cockpit** — la **vue 360°** (producteurs, conformité EUDR,
protection enfant, revenu vital, volumes, certification, alertes), chaque chiffre **cliquable**. 10 secondes, puis on plonge dans l'histoire.

**Valeur :** on vend la **résolution de leurs problèmes** (accès marché + prime durabilité), pas « un logiciel de plus ».

---

## 2. La carte & le périmètre (3 min)

**Action :** ouvrir **Carte** → montrer les parcelles géolocalisées ; cliquer une parcelle.
**Discours :** « Chaque parcelle est cartographiée et reliée à son producteur. Voilà votre coopérative, vue du ciel. »
**Valeur :** **donnée structurée et spatiale** = la base de toute conformité.

---

## 3. La fiche parcelle & le jumeau (4 min)

**Action :** ouvrir une **Plantation** → faire défiler jusqu'au bloc **« 🧭 Jumeau de la parcelle »**.
**Discours :** « En un coup d'œil : conformité EUDR, diagnostic, récoltes, climat 30 jours, revenu, certification,
protection de l'enfant — et des **alertes avec l'action à mener**. »
**Valeur :** **vue 360° + priorisation** : on sait quoi traiter, sans fouiller.
*(Bonus : cliquer « Générer le rapport PDF » → la couverture sort **au logo de la coop**.)* ⭐

---

## 4. Conformité EUDR + satellite réel (5 min — **le cœur**)

**Action :** menu **EUDR** sur la parcelle → montrer le **score /6**, le **statut**, puis lancer/montrer le
**contrôle déforestation** (satellite réel) → **télécharger le DDS PDF**.
**Discours :** « Le contrôle déforestation utilise de **vraies images satellite** (Copernicus) et **Global Forest
Watch**. Et voici le **Due Diligence Statement** — le document exact que vos acheteurs (Cargill, Barry Callebaut,
Nestlé…) exigent — généré en un clic, **à votre en-tête**. »
**Valeur :** **la preuve réglementaire, automatisée**. C'est l'argument d'achat n°1.

---

## 5. Protection de l'enfant — CacaoGuard / SSRTE (4 min)

**Action :** menu **CacaoGuard** / **Évaluation risque** → montrer une évaluation, une **fiche SSRTE**, un **plan de
remédiation**, et le **blocage de traçabilité** d'un producteur à risque.
**Discours :** « Le devoir de vigilance « travail des enfants » est suivi du repérage à la remédiation. Un producteur
non conforme peut être **bloqué dans la traçabilité** — vous ne vendez que du cacao propre. »
**Valeur :** **conformité sociale démontrable** + protection de la réputation de la coop.

---

## 6. Revenu vital — FarmForce (3 min)

**Action :** menu **FarmForce** → une évaluation → montrer le **verdict « revenu vital atteint / écart »**.
**Discours :** « On calcule le revenu net du ménage et on le compare au **seuil de revenu vital**. C'est l'indicateur
que réclament les standards (Fairtrade, Rainforest) et un **argument prime** auprès des acheteurs. »
**Valeur :** **durabilité chiffrée**, pas déclarative.

---

## 7. Traçabilité commerciale — achats → lot → passeport (3 min)

**Action :** **Achats** (un bon d'achat) → **Traçabilité lots** (un lot) → **passeport du lot (PDF)** → bouton
**Composition (Excel)** : le fichier *exactement au format demandé par l'exportateur* (Farmer_ID / Farm_ID /
poids net / certification), généré en un clic au lieu d'être ressaisi à la main.
*(Bonus conformité : tenter **Expédier** un lot contenant une parcelle non conforme → refus motivé ;
seule une **dérogation admin tracée** peut débloquer — preuve que la plateforme verrouille l'export.)*
**Discours :** « De l'achat au producteur jusqu'au lot exporté, tout est tracé. Le **passeport de lot** prouve la
composition, la conformité EUDR et l'absence de blocage — **à votre en-tête**. »
**Valeur :** **traçabilité physique bout-en-bout** = exigée à l'export.

---

## 8. Pilotage direction (3 min)

**Action :** menu **Direction** → métriques consolidées (EUDR, enfants, revenu vital, volumes). **Cliquer une métrique**
→ on arrive sur le module détaillé. Puis **Parcelles à risque** (liste priorisée) et **Veille Marché** (prix + actus).
**Discours :** « Pour la direction : tout l'état de la coop sur un écran, **chaque chiffre est cliquable** vers le détail.
Et « Parcelles à risque » vous donne votre **plan d'action de la semaine**. »
**Valeur :** **outil de décision**, pas seulement de saisie.

---

## 9. Clôture (2 min)

**Points à marteler :**
- **Une plateforme, pas 5 outils** : producteur → parcelle → récolte → lot, + conformité + durabilité.
- **Cloisonnement strict** : chaque coopérative ne voit **que ses données** (multi-tenant sécurisé).
- **Vos documents, votre image** : tous les PDF sortent au **logo de la coop**.
- **Modulaire** : on active ce dont vous avez besoin (plans Starter → Entreprise).

**Appel à l'action :** « On vous ouvre un espace **avec vos vraies données** (import de votre registre en quelques
minutes) pour un essai encadré ? »

**Question de clôture (révèle la valeur perçue) :** ne demandez **pas** « alors, qu'en pensez-vous ? » mais
> « Si vous aviez cet outil dès aujourd'hui, **quel est le premier problème que vous régleriez** ? »

La réponse vous dit exactement ce qui les fait acheter — et oriente l'essai pilote.

---

## Annexe — réponses aux objections fréquentes

| Objection | Réponse courte |
|---|---|
| « C'est cher ? » | Modulaire : on démarre petit (Starter) et on monte avec la valeur. Le coût d'un **lot refusé à l'export** dépasse l'abonnement. |
| « Nos données sensibles (enfants, producteurs) ? » | Cloisonnées par coopérative, accès par rôle, journal d'audit, sauvegardes chiffrées hors-site. |
| « Nos agents terrain ont peu de réseau » | Saisie mobile, fonctionne en mode dégradé ; la synchro se fait dès le réseau revenu. |
| « On a déjà un registre Excel » | Import en quelques minutes — on **réutilise** votre existant, on ne repart pas de zéro. |
| « Et si AgriVision tombe ? » | Sauvegardes automatiques chiffrées **hors plateforme** + procédure de restauration documentée. |

> Durée cible : **25-30 min** de démo + 10-15 min de questions. Adapter l'ordre selon ce qui fait réagir le client
> (souvent : commencer par l'EUDR/DDS si l'acheteur met la pression sur la conformité).

---

## Annexe — à éviter absolument

- ❌ Faire le tour de **tous les menus** (démo « catalogue de fonctions »).
- ❌ Démonstration **technique** / passer du temps dans les **paramètres**.
- ❌ **Données fictives évidentes** → utiliser **leurs vraies données** (import du registre) ou la coop démo soignée.
- ❌ Présenter AgriVision comme « **un logiciel de plus** » au lieu d'un **résultat** (conformité, accès marché, prime).
- ❌ Montrer en live une brique **non financée** (Conseil IA / Veille sans crédit) → utiliser la parade (capture).

---

## Annexe — stratégie « coopérative pilote »

Vous avez **2 coops intéressées** : faites de la **première une pilote**.
- Accompagnement rapproché + **période pilote 2–3 mois**, leurs retours intégrés au produit.
- À la sortie, récoltez : **témoignage**, **captures d'écran réelles**, **indicateurs avant/après**, **lettre de recommandation**.
- La 2ᵉ coop devient alors **beaucoup plus facile à convaincre** (preuve sociale + cas réel local).

> **Idéal démo** : importer **leur** registre avant la rencontre (quelques minutes) → la démo tourne sur **leurs**
> parcelles et producteurs. À défaut, la coop démo « Coopérative Démo Cacao 2026 » (cf. §0) est prête et soignée.
