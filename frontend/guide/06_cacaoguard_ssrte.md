# 6. CacaoGuard, Protection de l'enfant & Fiches SSRTE

> Ces modules forment le système de **prévention et remédiation du travail des enfants** (SSRTE),
> avec **blocage de traçabilité automatique** en cas de cas critique. C'est un argument fort
> pour les acheteurs internationaux.

## 6.A — CacaoGuard (vue d'ensemble)

### À quoi ça sert
Tableau de bord de la **protection de l'enfant** et de la **traçabilité sociale** de votre coopérative :
enfants suivis, niveaux de risque, scolarisation, visites, plans de remédiation, blocages.

### Pas à pas
1. Menu **CacaoGuard**.
2. Lisez les compteurs (enfants suivis, à risque élevé, taux de scolarisation, alertes, blocages…).
3. Tous les chiffres sont **limités à votre coopérative**.

---

## 6.B — Protection de l'enfant (registre des enfants)

### À quoi ça sert
Enregistrer les **enfants** d'un ménage producteur, leur **scolarisation**, et détecter les **risques**
(travail dangereux). Le **niveau de risque** est calculé automatiquement.

### Pas à pas
1. Menu **Protection enfant**.
2. Ajoutez un enfant rattaché à un producteur : nom, âge/année de naissance, **scolarisation**,
   **travaille sur la ferme ?**, tâches dangereuses éventuelles.
3. Le système calcule un **niveau de risque** (Aucun → Critique).
4. Un cas **Élevé/Critique** déclenche un **plan de remédiation** et, si critique, un **blocage de traçabilité**.

---

## 6.C — Fiches SSRTE (A / B / C)

### À quoi ça sert
Remplir les **3 questionnaires officiels** du dispositif SSRTE, exportables en **PDF** :
- **Fiche A** — profil de la **localité** (services, écoles, comité de protection…),
- **Fiche B** — profilage du **ménage** du producteur (membres, enfants, exploitation, travailleurs…),
- **Fiche C** — **visite de plantation** (enfants/adultes présents, tâches dangereuses…).

### Remplir une fiche (pas à pas)
1. Menu **Fiches SSRTE**.
2. Choisissez l'onglet **Fiche A**, **F1 Ménage** ou **Fiche C**.
3. Remplissez les sections. Astuces de saisie :
   - Les **tâches dangereuses** sont des **cases à cocher** (faciles au doigt sur tablette).
   - Les blocs répétables (écoles, membres du ménage, travailleurs, enfants) s'ajoutent avec
     les boutons **+ École / + Membre / + Travailleur / + Enfant**.
   - Les champs qui ne s'appliquent pas **apparaissent/disparaissent** selon vos réponses
     (ex. l'origine de l'électricité n'apparaît que si « électricité = oui »).
   - Capturez le **GPS** au doigt avec l'icône 📍.
   - Une zone **Remarques / actions** existe par grande section.
4. Cliquez **Enregistrer** la fiche.
5. Dans **Saisies récentes**, cliquez **Fiche A/B/C PDF** pour télécharger le document à la charte.

### Suspicion & blocage automatique (Fiche C)
- Si une **tâche dangereuse** est observée, la **suspicion** se coche automatiquement,
  une **alerte** est créée et un **blocage de traçabilité** peut être déclenché.

### Astuces
- Travail **hors ligne** possible sur le terrain : les fiches en attente se synchronisent au retour du réseau
  (un bandeau l'indique, avec un bouton **Synchroniser maintenant**).

### En cas de problème
| Problème | Solution |
|---|---|
| Le producteur n'apparaît pas | Il doit exister dans votre coopérative (créez-le / importez-le). |
| Le PDF ne se télécharge pas | Réessayez ; vérifiez que la fiche est bien enregistrée. |
| Chiffres SSRTE différents d'une page à l'autre | Tout est cloisonné par coopérative ; faites **Ctrl + F5**. |

---

## 6.D — Scénario guidé de prise en main (cas concret)

> 🎓 **Version pas à pas complète (formation)** : voir le chapitre [16 — Scénario Protection de l'enfant](16_protection_enfant.md).
> Ci-dessous, la version condensée.

> Un cas complet pour s'exercer, du terrain à la due diligence. **Cas fil rouge** : producteur
> **Koffi Yao N'Guessan** (Gnamangui / Méagui) ; **Awa Kouassi, 14 ans, déscolarisée**, observée à la
> machette ; son frère **Yao, 8 ans**, scolarisé. Rôle nécessaire : **admin / agronome / technicien**.

**1. Recenser l'enfant** — Menu **Protection enfant → + Enfant** : Prénom `Awa`, Nom `Kouassi`,
naissance `2011-03-12`, Féminin, **producteur parent** `Koffi Yao N'Guessan`. Laissez le bloc
« Évaluation initiale » fermé : l'enquête le renseignera.

**2. Enquête SSRTE** — Menu **Fiches SSRTE** (chaque fiche : **brouillon → clôture définitive** ; corrigez
le brouillon, ne dupliquez pas) :
- **Fiche A — localité** : Gnamangui / Méagui, école primaire 4 km, **classes secondaires 0**,
  risques identifiés : déscolarisation.
- **Fiche B — ménage** : 6 personnes / 3 enfants / 2 scolarisés ; 2 parcelles cacao, 4,5 ha, 1 800 kg/an ;
  **logement traditionnel** ; possessions ☑ moto ☑ télévision ; autorise l'entretien des travailleurs ;
  photo du chef de ménage ; membres du ménage (cochez **machette** pour Awa) ; **consentement obtenu**.
- **Fiche C — parcelle** : ☑ **suspicion de travail d'enfant** (crée une alerte automatiquement),
  tâche observée : machette, actions immédiates.

**3. Évaluer le risque** — Menu **Protection enfant → Évaluer un enfant** : sélectionnez Awa → scolarité
`déscolarisé`, distance école `3–5 km`, travail `régulier`, tâches ☑ machette ☑ pesticides, besoin de
main-d'œuvre `élevé` → **Enregistrer**. Un score **élevé / critique génère automatiquement un plan de
remédiation**.

**4. Alertes** — Menu **CacaoGuard → Vérifier alertes** : les contrôles créent les alertes ; la liste
(filtre **Ouvertes / Toutes**) affiche priorité + date. Accès direct depuis la tuile « Alertes ouvertes »
du tableau de bord.

**5. Blocage de traçabilité** — Menu **CacaoGuard → Blocage traçabilité** : bloquez **Koffi Yao**
(motif : travail d'enfant constaté). Effet : ses récoltes ne peuvent plus être affectées à un lot.

**6. Plan de remédiation** — Menu **Remédiation** : renseignez les actions (réinscription scolaire,
retrait des tâches dangereuses + suivi, appui au revenu) avec **responsable** et **échéance** ; mettez à
jour les statuts au fil du suivi.

**7. Signalement** (si le cas remonte par un canal externe) — Menu **Signalements → Nouveau** :
type `Travail enfant`, sévérité `Haute`, producteur `Koffi Yao`, source `Agent terrain`.

**8. Clôture & preuve** — clôturez les fiches SSRTE (définitif), résolvez l'alerte, **levez le blocage**
une fois la situation corrigée, puis **CacaoGuard → Rapports** pour générer le **rapport de due
diligence (PDF)**.

> Pour la suite (regrouper le cacao en lot et le remettre à l'exportateur), voir
> [chapitre 5 — Traçabilité des lots](05_achats_lots_certification.md).
