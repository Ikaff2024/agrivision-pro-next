# Script de démo AgriVision Pro — « parcours en or » (~25 min)

> Pour présenter la plateforme à une **coopérative prospect** (public : direction / décideurs).
> Objectif : raconter **une histoire de bout en bout**, pas faire le tour des menus. À chaque étape :
> **ce qu'on clique**, **ce qu'on dit**, **le message de valeur**.
>
> Règle d'or : on ne « montre des fonctions », on **résout les problèmes du client** (conformité EUDR,
> travail des enfants, revenu vital, traçabilité, pilotage). On parle **bénéfice**, l'écran est la preuve.

---

## 0. Préparation (la veille — 15 min)

**À vérifier AVANT la démo (critique) :**
- [ ] Connexion OK sur **app-agrivision-pro.com** avec le compte démo : **demo2@agrivision-pro.com** / `DemoAgriVision2026!` (admin de « Coopérative Démo Yeyasso 2026 »).
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
AVP_DEMO_EMAIL=demo2@agrivision-pro.com \
AVP_DEMO_COOP="Coopérative Démo Yeyasso 2026" \
python seed_demo.py
```

> - Après le seed : se connecter à ce compte et **téléverser le logo** (Administration → Logo) — tous les PDF sortent alors à l'image de la coop. ⭐
> - Le seed est **idempotent** sur les parcelles (relançable sans doublon). Pour repartir d'une coop **vierge**, prendre un **nouveau** `AVP_DEMO_EMAIL` **et** un **nouveau** `AVP_DEMO_COOP` (un nom de coop déjà pris est refusé à l'inscription).

---

## 1. Accroche — le problème (2 min, **slide ou parole, sans écran**)

> « Aujourd'hui, vendre du cacao en Europe impose 3 choses, sous peine de **perdre l'accès au marché** :
> prouver **zéro déforestation (EUDR)**, prouver l'**absence de travail des enfants**, et démontrer un
> **revenu décent** aux producteurs. La plupart des coops gèrent ça sur papier et Excel — **infaisable à l'échelle**.
> AgriVision Pro, c'est **une seule plateforme** qui relie le producteur, sa parcelle, ses récoltes et le lot
> vendu, **avec la preuve de conformité générée automatiquement**. Laissez-moi vous montrer. »

**Valeur :** on plante l'enjeu = **accès marché + prime durabilité**, pas « un logiciel agricole ».

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

**Action :** **Achats** (un bon d'achat) → **Traçabilité lots** (un lot) → **passeport du lot (PDF)**.
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

---

## Annexe — réponses aux objections fréquentes

| Objection | Réponse courte |
|---|---|
| « C'est cher ? » | Modulaire : on démarre petit (Starter) et on monte avec la valeur. Le coût d'un **lot refusé à l'export** dépasse l'abonnement. |
| « Nos données sensibles (enfants, producteurs) ? » | Cloisonnées par coopérative, accès par rôle, journal d'audit, sauvegardes chiffrées hors-site. |
| « Nos agents terrain ont peu de réseau » | Saisie mobile, fonctionne en mode dégradé ; la synchro se fait dès le réseau revenu. |
| « On a déjà un registre Excel » | Import en quelques minutes — on **réutilise** votre existant, on ne repart pas de zéro. |
| « Et si AgriVision tombe ? » | Sauvegardes automatiques chiffrées **hors plateforme** + procédure de restauration documentée. |

> Durée cible : **20-25 min** de démo + 10-15 min de questions. Adapter l'ordre selon ce qui fait réagir le client
> (souvent : commencer par l'EUDR/DDS si l'acheteur met la pression sur la conformité).
