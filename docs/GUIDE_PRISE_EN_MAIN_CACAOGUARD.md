# Guide de prise en main — CacaoGuard (protection de l'enfant & due diligence)

> Scénario de formation pas-à-pas, suivant **un seul cas** du terrain jusqu'à la due diligence.
> Les champs correspondent à l'application réelle. Dernière mise à jour : 2026-06-13.
> **Rôle requis** : admin, agronome ou technicien (un *viewer* / *gestionnaire* n'a pas accès aux données enfants).

## Le cas (fil rouge)

Producteur **Koffi Yao N'Guessan** (code YEYASSO `CI-YEY-00428`), localité **Gnamangui**, section **Méagui**.
Lors d'une enquête terrain, l'agent constate qu'**Awa Kouassi (14 ans, déscolarisée)** travaille régulièrement
à la machette sur la parcelle. Son frère **Yao (8 ans)** est scolarisé. On va recenser, enquêter, évaluer,
alerter, bloquer la traçabilité, remédier, puis clôturer.

---

## Étape 0 — Le hub CacaoGuard (point de départ)

**Menu : CacaoGuard.** KPIs (producteurs, enfants, *enfants à risque*, alertes ouvertes, visites, plans de
remédiation, blocages, SSRTE, FarmForce) + distribution du risque + liste d'alertes. C'est le tableau de
pilotage : on y revient à la fin pour vérifier que le cas est traité.

## Étape 1 — Recenser les enfants du ménage

**Menu : Protection enfant → « + Enfant ».** Crée d'abord l'**identité** (le reste vient de l'enquête).

**Enfant 1 — le cas à risque :**
- **Prénom\*** : `Awa` — **Nom\*** : `Kouassi`
- **Date de naissance\*** : `2011-03-12` (≈14 ans) — **Genre\*** : `Féminin`
- **Acte de naissance** : *laisser vide* (absence d'acte = facteur de vulnérabilité)
- **Producteur parent\*** : `Koffi Yao N'Guessan`
- Bloc **« Évaluation initiale (facultatif) »** : **laisser fermé** — scolarisation/travail seront relevés
  par l'enquête (Fiche B) puis l'évaluation (Étape 3).

**Enfant 2 — le « bon cas » (contraste) :** `Yao` `Kouassi`, naissance `2017-09-01`, `Masculin`, parent `Koffi Yao N'Guessan`.

## Étape 2 — Enquête terrain SSRTE

**Menu : SSRTE.** Trois fiches. ⚠️ Chaque fiche se crée en **brouillon** puis se **clôture en définitif**.
Pour corriger, **modifie le brouillon** — ne recrée pas une fiche (sinon doublons + audit faussé).

### 2a — Fiche A · Communauté
- **Localité** `Gnamangui` · **Section** `Méagui` · **Date** `2026-06-10`
- **Répondant** `Brou Konan` · **Rôle** `Chef du village`
- **Fournisseur (A.02)** `YEYASSO` · **Sous-préfecture (A.03)** `Méagui`
- **Code/Nom agent collecte (A.05/06)** `AG-014` / `Traoré Mariam`
- **GPS localité + heures (A.07)** : bouton 📍
- **Distance école primaire (A.20b)** `4` km · **Classes secondaires (A.21a)** `0` (pas de secondaire = facteur)
- **Population** `1200` · **Type de localité** `Village`
- **Accès services / électricité / point d'eau** : coche selon le terrain
- **Comité protection enfant** `Brou Konan (président), Aya Koffi (secrétaire)`
- **Risques identifiés** `Déscolarisation, travaux dangereux, éloignement école secondaire`
- **Enregistrer (brouillon)**.

### 2b — Fiche B · Profilage du ménage (Koffi Yao)
- **Producteur** `Koffi Yao N'Guessan` · **Date (B.09)** `2026-06-10` · **Agent (B.06)** `Traoré Mariam`
- **Codes (B.05/B.07)**, **Fournisseur (B.02)** `YEYASSO`, **Sous-préfecture (B.03)** `Méagui`, **Localité (B.04)** `Gnamangui`
- **GPS plantation** 📍 + **heures**
- **Producteur disponible (B.10a)** `Oui` · **Statut de la personne visitée (B.15)** `Propriétaire`
- **Taille ménage** `6` · **Enfants** `3` · **Âge scolaire** `3` · **Scolarisés** `2` (1 non scolarisé = signal)
- **Exploitation** : Parcelles cacao `2` · Superficie `4.5` ha · Production `1800` kg/an · Travailleurs ext. (B.18b) `0`
- **Situation économique du ménage** :
  - **Type de logement (B.25)** `Traditionnel`
  - **Possessions (B.26)** : ☑ Moto ☑ Télévision
  - **Autorise l'entretien des travailleurs (B.18e)** `Oui`
  - **Photo du chef de ménage (B.29)** `koffi_yao_2026.jpg` (référence)
- **Membres du ménage** : Koffi (chef), épouse, **Awa** (5-17 → coche la tâche dangereuse **Machette**), Yao…
- **Vulnérabilités** `Revenu faible, 1 enfant déscolarisé` · **Déclarations travail enfant** `Awa: machette`
- ☑ **Consentement obtenu** · **Signature** · **Enregistrer F1 (brouillon)**.

### 2c — Fiche C · Visite de parcelle
- **Date / Agent / GPS** · **Section** `Méagui` · **Localité** `Gnamangui`
- **Adultes / Enfants présents** `1` · **Autorise l'entretien** `Oui`
- ☑ **Suspicion de travail d'enfant** *(déclenche une alerte automatique)*
- **Tâches dangereuses observées** : Machette · **Actions immédiates** `Retrait de la tâche, sensibilisation du parent`
- ☑ **Consentement preuves** · **Enregistrer (brouillon)**.

## Étape 3 — Évaluer le risque de l'enfant → plan auto

**Menu : Protection enfant → « Évaluer un enfant ».**
- **Producteur parent** `Koffi Yao N'Guessan` → **Enfant à évaluer** `Awa Kouassi`
- **Statut scolaire** `Déscolarisé` · **Distance école** `3 à 5 km` · **Fréquence travail** `Régulier`
- **Tâches dangereuses** ☑ Machette ☑ Pesticides · **Besoin en main d'œuvre** `Élevé`
- **Notes agent terrain** `Observée machette en main, déscolarisée depuis 2025, parent demandeur d'appui`
- Le **score** se calcule en direct → **Enregistrer.**

➡️ **Effet automatique** : un score élevé/critique **génère automatiquement un plan de remédiation** pour Awa.

## Étape 4 — Alertes

**Menu : CacaoGuard → « Vérifier alertes »** : lance les contrôles (retards, escalades, suspicions SSRTE) et crée
les alertes. La **liste « Alertes ouvertes »** (filtre Ouvertes/Toutes) montre l'alerte avec priorité + date.
💡 Depuis le **tableau de bord**, la tuile **« Alertes ouvertes »** ouvre directement cette liste filtrée.

## Étape 5 — Blocage de traçabilité (levier de diligence)

**Menu : CacaoGuard → « Blocage traçabilité ».** Bloque le producteur **Koffi Yao**, motif
`Travail d'enfant constaté (Awa, machette) — remédiation en cours`.

➡️ **Effet** : tant que le blocage est **actif**, **impossible d'affecter les récoltes de ce producteur à un lot**
(refus automatique). C'est ce qui empêche le cacao « à risque » d'entrer dans la chaîne tracée.

## Étape 6 — Plan de remédiation

**Menu : Remédiation** (ou via la fiche d'Awa). Renseigne les **actions** du plan auto-généré :
- `Réinscription scolaire d'Awa` — échéance `2026-09-15`, responsable `Coordinateur social`
- `Retrait des tâches dangereuses + suivi mensuel` — échéance `2026-07-15`
- `Appui revenu au ménage (FarmForce)` — échéance `2026-08-31`

Mets à jour le **statut** des actions (en cours → fait).

## Étape 7 — Signalement (mécanisme de doléance)

**Menu : Signalements → « Nouveau signalement »** :
- **Type\*** `Travail enfant` · **Sévérité\*** `Haute`
- **Description\*** `Enfant de 14 ans déscolarisée observée à la machette sur la parcelle de Koffi Yao, Gnamangui`
- **Producteur concerné** `Koffi Yao N'Guessan` · **Source** `Agent terrain`
- **Enregistrer.**

## Étape 8 — Suivi, clôture, preuve

1. Actions faites → **clôture les fiches SSRTE en définitif** + **résous l'alerte**.
2. **Lève le blocage de traçabilité** une fois la situation corrigée → le producteur peut de nouveau livrer.
3. **CacaoGuard → « Rapports »** : génère le **rapport de due diligence** (PDF) — preuve pour l'exportateur/EUDR.
4. **Tableau de bord** : la tuile **« Enfants à risque »** ramène à la liste filtrée (élevé+critique) ;
   **« Alertes ouvertes »** doit retomber.

---

## Points clés
- **Identité d'abord, enquête ensuite** : l'enfant est créé léger ; Fiche B + évaluation enrichissent.
- **Brouillon → définitif** sur les fiches SSRTE : corrige le brouillon, ne duplique pas.
- **L'évaluation pilote tout** : un score élevé crée le plan ; la suspicion SSRTE et le blocage pilotent la traçabilité.
- **Données enfants = sensibles** : consentement + cloisonnement coopérative + journal d'audit.
