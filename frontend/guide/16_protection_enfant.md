# 16. Scénario — Prise en main de la Protection de l'enfant

> Un **parcours guidé de bout en bout**, du **terrain** jusqu'à la **preuve de due diligence**,
> pour prévenir et remédier au **travail des enfants** (dispositif SSRTE). Sert de **fil conducteur
> de formation** (avec exercices). Comptez ~40 min avec les exercices.

## À quoi ça sert
- Savoir **enchaîner** les bons gestes face à un cas : recenser → enquêter → évaluer → alerter → bloquer → remédier → prouver.
- **Former** un agent terrain / gestionnaire à la chaîne complète de protection de l'enfant.
- Comprendre le **blocage de traçabilité automatique** (l'argument fort vis-à-vis des acheteurs).

## Prérequis
- Un compte **administrateur**, **agronome** ou **technicien**.
- Le **producteur parent** doit exister dans la coopérative (voir [Import d'un registre](10_import_registre.md) ou créez-le).
- Sur le terrain : le travail **hors ligne** est possible, la synchronisation se fait au retour du réseau.

> **Cas fil rouge** : producteur **Koffi Yao N'Guessan** (Gnamangui / Méagui).
> **Awa Kouassi, 14 ans, déscolarisée**, observée à la machette ; son frère **Yao, 8 ans**, scolarisé.

---

## Étape 1 — Recenser l'enfant
1. Menu **Protection enfant → + Enfant**.
2. Renseignez : prénom `Awa`, nom `Kouassi`, naissance `2011-03-12`, sexe `Féminin`, **producteur parent** `Koffi Yao N'Guessan`.
3. Laissez le bloc « Évaluation initiale » fermé : l'enquête le renseignera.

> **Point clé** : chaque enfant est **rattaché à un producteur** — c'est ce lien qui permettra le blocage de traçabilité.

## Étape 2 — Enquête SSRTE (fiches A / B / C)
Menu **Fiches SSRTE**. Chaque fiche suit le cycle **brouillon → clôture définitive** : corrigez le brouillon, **ne dupliquez pas**.
- **Fiche A — localité** : Gnamangui / Méagui, école primaire à 4 km, **classes secondaires : 0**, risque identifié : déscolarisation.
- **Fiche B — ménage** : 6 personnes / 3 enfants / 2 scolarisés ; 2 parcelles cacao, 4,5 ha, 1 800 kg/an ; logement traditionnel ; **consentement obtenu** ; pour Awa, cochez **machette**.
- **Fiche C — parcelle** : cochez ☑ **suspicion de travail d'enfant** (crée une **alerte** automatiquement), tâche observée : machette, actions immédiates.

> **Astuce** : les tâches dangereuses sont des **cases à cocher** (faciles au doigt) ; capturez le **GPS** avec l'icône 📍. Détails : [CacaoGuard & SSRTE](06_cacaoguard_ssrte.md).

## Étape 3 — Évaluer le risque
1. Menu **Protection enfant → Évaluer un enfant**, sélectionnez **Awa**.
2. Scolarité `déscolarisé`, distance école `3–5 km`, travail `régulier`, tâches ☑ machette ☑ pesticides, besoin de main-d'œuvre `élevé` → **Enregistrer**.
3. Un score **Élevé / Critique** **génère automatiquement un plan de remédiation**.

> **Exercice** : refaites l'évaluation avec « scolarisé » + « pas de travail » et observez la chute du niveau de risque.

## Étape 4 — Vérifier les alertes
1. Menu **CacaoGuard → Vérifier alertes** : les contrôles créent les alertes.
2. Filtrez **Ouvertes / Toutes** ; la liste affiche **priorité + date**. Accès direct depuis la tuile **Alertes ouvertes** du tableau de bord.

## Étape 5 — Blocage de traçabilité
1. Menu **CacaoGuard → Blocage traçabilité**.
2. Bloquez **Koffi Yao N'Guessan** (motif : travail d'enfant constaté).
3. **Effet** : ses récoltes **ne peuvent plus être affectées à un lot** — son volume reste **hors lot tant que le cas n'est pas traité**.

> **Point clé** : c'est le cœur du dispositif. Le blocage **empêche** le cacao concerné de partir à l'export tant que la situation n'est pas corrigée.

## Étape 6 — Plan de remédiation
1. Menu **Remédiation**.
2. Renseignez les actions : **réinscription scolaire**, retrait des tâches dangereuses + suivi, appui au revenu — avec **responsable** et **échéance**.
3. Mettez à jour les **statuts** au fil du suivi.

## Étape 7 — Signalement *(si le cas remonte par un canal externe)*
- Menu **Signalements → Nouveau** : type `Travail enfant`, sévérité `Haute`, producteur `Koffi Yao`, source `Agent terrain`.

## Étape 8 — Clôture & preuve
1. **Clôturez** les fiches SSRTE (définitif).
2. **Résolvez** l'alerte une fois la cause traitée.
3. **Levez le blocage** quand la situation est corrigée (le volume redevient affectable à un lot).
4. Menu **CacaoGuard → Rapports** : générez le **rapport de due diligence (PDF)** — votre preuve pour l'acheteur.

> Pour la suite (regrouper le cacao en lot et le remettre à l'exportateur), voir [Traçabilité des lots](05_achats_lots_certification.md).

---

## Récapitulatif express *(à retenir)*
- **Recenser → enquêter (SSRTE) → évaluer → alerter → bloquer → remédier → prouver.**
- Un enfant est **rattaché à un producteur** ; un cas grave **bloque la traçabilité** de ce producteur.
- Le blocage **retire son volume des lots** jusqu'à correction — puis on **lève** le blocage.
- La preuve finale : le **rapport de due diligence PDF**.

## En cas de problème
- **Le producteur n'apparaît pas** → il doit exister dans la coopérative (créez-le / importez-le).
- **L'évaluation ne crée pas de plan** → le score doit être **Élevé/Critique** ; vérifiez les réponses (travail, tâches).
- **Le volume d'un producteur reste hors lot** → il est peut-être **sous blocage** : traitez le cas via la **Remédiation**, puis levez le blocage.
- **Chiffres différents d'une page à l'autre** → tout est cloisonné par coopérative ; faites **Ctrl+Maj+R**.
