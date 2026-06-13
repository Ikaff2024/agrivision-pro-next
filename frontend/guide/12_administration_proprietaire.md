# 12. Administration & Espace propriétaire (plans)

## 12.A — Administration (gestion de la coopérative)

### À quoi ça sert
Gérer les **membres** de **votre** coopérative et les outils d'admin. Réservé à l'**Administrateur**.

### Ce qu'on peut faire
- **Voir les membres** (email, rôle, date d'inscription) et les compteurs (total, admins, agronomes/techniciens).
- **Ajouter un membre**.
- **Changer le rôle** d'un membre (menu déroulant).
- **Réinitialiser le mot de passe** d'un membre (bouton **MDP**) → un mot de passe temporaire est affiché à lui communiquer.
- **Attribuer les parcelles** à un technicien (bouton **Parcelles**).
- **Retirer** un membre.
- **Importer un registre** (voir fiche dédiée).

### Pas à pas (réinitialiser un mot de passe)
1. Menu **Administration**.
2. Sur la ligne du membre → bouton **MDP**.
3. Notez le **mot de passe temporaire** affiché et transmettez‑le au membre (il le changera ensuite).

> ⚠️ Gardez **au moins deux administrateurs** par coopérative : si l'unique admin est bloqué,
> personne ne peut réinitialiser son mot de passe en interne (sauf via l'email « mot de passe oublié »).

### Scénario guidé (ajouter un agent terrain)

1. **Menu Administration → Ajouter un membre** : email `agent.traore@coop.ci`, rôle **Technicien**
   (agent terrain) → un **mot de passe temporaire** s'affiche : transmettez-le à l'agent.
2. (Optionnel) bouton **Parcelles** sur sa ligne → **attribuez-lui les parcelles** qu'il suivra.
3. L'agent se connecte, change son mot de passe, et accède aux modules de son rôle.

> Rôles : **admin** (tout), **agronome**, **technicien** (terrain), **gestionnaire** (guichet
> administratif, **sans** accès aux données sensibles CacaoGuard/SSRTE), **viewer** (lecture seule).

---

## 12.B — Espace propriétaire (IKAFFANAN) & plans d'abonnement

### À quoi ça sert
Une page **séparée**, réservée à **IKAFFANAN LTD** (le propriétaire de la plateforme), pour piloter
**toutes les coopératives** et leurs **abonnements**. Elle s'ouvre avec une **clé propriétaire**
(`OWNER_API_KEY`), pas avec un compte coopérative.

### Ce qu'on y voit
- **KPIs plateforme** : coopératives (actives/suspendues/inactives), plantations, diagnostics,
  **producteurs**, **enfants suivis** (+ à risque), **blocages traçabilité**, **lots**, **volume acheté**.
- **Répartition par plan** d'abonnement.
- **Tableau des coopératives** : activité, **plan** (modifiable), statut.

### Gérer les plans d'abonnement (pas à pas)
1. Ouvrez la page **propriétaire** et saisissez la **clé propriétaire**.
2. Dans le tableau, colonne **Plan**, choisissez le palier d'une coopérative :
   **Starter**, **Conformité**, **Pro** ou **Entreprise**.
3. Le changement est immédiat ; la coopérative voit **son menu s'adapter** à sa prochaine connexion.

### Les paliers (proposition par défaut)
| Plan | Modules inclus |
|---|---|
| **Starter** | Cœur agronomique (Plantations, Producteurs, Diagnostic, Carte, Récoltes, Agroforesterie, Dashboard) |
| **Conformité** | Starter + Conformité & durabilité (EUDR, CacaoGuard, SSRTE, Protection enfant, Monitoring, Remédiation, Signalements, Formation, Direction) |
| **Pro / Exportateur** | Conformité + Commercial (Achats, Traçabilité lots, Certification) |
| **Entreprise** | Tout + Premium (Satellite avancé, FarmForce / revenu vital) |

> Par **défaut**, toute coopérative est en **Entreprise** (tout activé) tant qu'un plan inférieur
> n'est pas explicitement choisi — rien n'est restreint sans décision.

### En cas de problème
| Problème | Solution |
|---|---|
| « OWNER_API_KEY non configurée » | La clé propriétaire n'est pas définie côté serveur : à régler par l'équipe technique. |
| Un module disparu du menu d'une coop | Son **plan** ne l'inclut pas : repassez‑la en plan supérieur depuis l'espace propriétaire. |
| Clé propriétaire refusée | Vérifiez la clé saisie (sensible à la casse). |
