# SSRTE — Analyse des écarts (vs PDF officiels)

> **But du document.** Les Fiches SSRTE A / B / C sont implémentées sur leur **cœur métier**
> (identité, structure des données, calcul du risque travail des enfants, alertes, export PDF),
> mais elles **ne couvrent pas encore l'intégralité** des questionnaires papier.
> Ce document liste, fiche par fiche, ce qui est **capturé** et ce qui **reste à faire**, afin de
> ne rien oublier et de communiquer un état d'avancement **honnête** au client.
>
> ⚠️ **Ne pas dire au client que les Fiches SSRTE sont « terminées ».** Elles sont
> **fonctionnelles sur l'essentiel**, mais incomplètes par rapport aux formulaires officiels.

Dernière mise à jour : 2026-05-31.

> ✅ **COUVERTURE COMPLÈTE livrée (2026-05-31)** : après audit ligne par ligne des **3 PDF officiels**
> (Fiche A 25 p., F1 Ménage 50 p., Fiche C 35 p.), **tous les champs de données** des questionnaires
> sont désormais capturés de bout en bout (modèle + API + PDF + UI mobile/tablette) :
> - **Fiche A** : identification admin (A.02-A.06), GPS+heures (A.07a/b/c), origine électricité (A.12b),
>   distance eau (A.13b), noms organisations (A.18b/c/d), classes secondaires (A.21a/b),
>   tableau écoles complet (A.22-A.29 : titulaires/bénévoles, élèves H/F, cantine service+coût, latrines).
> - **Fiche B** : admin (B.02-B.07), GPS+heures (B.09a/b/c), type d'enquête, statut visite (B.10a/b),
>   statut personne (B.15), exploitation (B.16-B.23), travailleurs (B.18b/c/d), membres M01+ (B.27-B.36).
> - **Fiche C** : admin (C.01-C.07), heures (C.09b/c), comptages adultes/journaliers (C.10a/b/d),
>   enfants présents + hors ménage (C.11/C.12), bloc enfants non-membres V01-V10 (C.14-C.18).
> - **Transversal** : « Remarques + actions proposées » gérées **par section** ; **branches conditionnelles**
>   rendues par affichage dynamique côté UI (allège la saisie terrain).
>
> Décisions de design (à confirmer avec le client au feedback) : remarques **par section** plutôt que
> par question ; listes de choix alignées sur le PDF ; champs Coopérative repris du contexte utilisateur.

---

## Fiche A — Profil de la localité (PDF ~25 pages, codes A.01 → A.30)

### ✅ Capturé
- A.04 Nom de la localité · Section · A.07 Date de la visite
- Répondant + rôle
- A.08 Population totale · A.09 Type (village / campement)
- A.20a École primaire (oui/non) · A.20b Distance école la plus proche
- Comité de protection de l'enfant (oui/non) + membres · Risques identifiés
- **Accès aux services en oui/non** : A.11 route, A.12a électricité, A.13a point d'eau,
  A.14 réseau mobile, A.15 internet, A.30 structure sanitaire, A.16 travail journalier,
  A.17 intrants agricoles, A.18a organisations anti-travail des enfants,
  A.19 jardin d'enfants, A.21 secondaire, A.28a cantine, A.29a latrines
- Export PDF Fiche A

### ❌ Manquant (à implémenter)
| Code | Question | Remarque |
|---|---|---|
| A.02 | Fournisseur | champ admin |
| A.03 | Sous-préfecture | champ admin |
| A.05 / A.06 | Code + nom de l'agent de collecte | champ admin |
| A.07a | **Point GPS de la localité** | aucune capture GPS sur Fiche A |
| A.07b / A.09c | Heures de début / fin de visite | |
| A.12b | **Origine de l'électricité** (réseau national / solaire) | on n'a que oui/non |
| A.13b | **Distance du point d'eau** (0-100 m / 100-500 m / >500 m) | on n'a que oui/non |
| A.18b/c/d | **Noms des organisations** (Structure d'État / ONG / autres) | on n'a que oui/non |
| A.21a | **Nombre** de classes secondaires | on n'a qu'un booléen (P2) |
| ~~**A.22 → A.29**~~ | ~~**Tableau détaillé des écoles**~~ | ✅ **FAIT (P1, 2026-05-31)** — colonne `schools` |

**~~Détail du tableau des écoles manquant (A.22-A.29)~~ → ✅ capturé** (colonne `schools`, par école) :
nom de l'école · GPS de l'école · type d'école · construite par ·
nb de salles de classe · nb d'enseignants (total / titulaires) ·
nb d'élèves inscrits (garçons / filles) · cantine (existence / repas par
semaine / coût par ration) · latrines (existence / bloc séparé H-F).

---

## Fiche B — Profilage du ménage (PDF ~50 pages)

### ✅ Capturé
- Identité producteur, date, agent, consentement, signature
- Compteurs ménage / enfants / âge scolaire / scolarisés (auto-calculés)
- **Tableau des membres** : nom, lien, sexe, année de naissance, extrait de naissance,
  occupation, scolarisation, niveau scolaire, présence
- **Tâches dangereuses par enfant 5-17** (15 tâches, cases à cocher) → score de risque
- Vulnérabilités, contraintes scolaires · Export PDF Fiche B

### ❌ Manquant (à implémenter)
- **Statut de la visite** (producteur disponible / absent / refus / décédé / non-résident)
  et les **branches conditionnelles** associées
- ~~**Informations exploitation** : B.16 nb parcelles cacao, B.17 superficie cacao,
  B.19 production annuelle cacao, B.20-B.23 idem café~~ → ✅ **FAIT (P1, 2026-05-31)** — colonne `farm_info`
- **Travailleurs non-journaliers** (B.18d) : nom, statut (permanent/saisonnier/métayer), téléphone
- **Situation économique** : B.25 type de logement, B.26 possessions du ménage
  (moto, véhicule, réfrigérateur, cuisinière, télévision…)
- Photo d'identité du chef de ménage (B.29)

---

## Fiche C — Visite de plantation (PDF ~35 pages)

### ✅ Capturé
- Visite (date, GPS, agent, plantation, producteur), checklist
- **Tableau structuré des enfants présents** : nom, âge, du ménage (oui/non),
  tâches dangereuses (15, cases à cocher)
- Suspicion auto + **alerte + blocage traçabilité** · actions immédiates · photos · signatures
- Export PDF Fiche C

### ❌ Manquant (à implémenter)
- ~~**Adultes présents** dans la plantation (C.10a) + **travailleurs non-journaliers**
  (C.10c : nom, statut, téléphone)~~ → ✅ **FAIT (P1, 2026-05-31)** — `adults_observed`, `workers_present`
- **Heures de début / fin** de visite (C.09b / C.09c)
- Distinction détaillée **enfants membres / non-membres du ménage** (V01-V10, code SSRTE C.20)
- Déclenchement explicite de la **Fiche D** (remédiation) quand une tâche dangereuse est observée
  (aujourd'hui : alerte + blocage créés, mais pas de « Fiche D » formelle)

---

## Proposition de priorisation

- ~~**P1 — vrais blocs manquants**~~ ✅ **LIVRÉ (2026-05-31)** :
  - Fiche A : ~~tableau détaillé des écoles (A.22-A.29)~~ ✅
  - Fiche B : ~~informations exploitation (parcelles / superficie / production cacao & café)~~ ✅
  - Fiche C : ~~adultes + travailleurs présents~~ ✅
- ~~**P2 — détails par indicateur** : origine électricité, distance point d'eau, noms des
  organisations, nombre de classes secondaires ; GPS + heures de visite (A, B, C)~~ ✅ **FAIT (2026-05-31)**.
- ~~**P3 — champs administratifs** : fournisseur, sous-préfecture, codes/noms agent de collecte~~ ✅ **FAIT (2026-05-31)**.

> Chaque bloc est indépendant et peut être ajouté de façon incrémentale, sans casser l'existant
> (le modèle de données stocke déjà des sections en JSON, ce qui facilite l'ajout de champs).
