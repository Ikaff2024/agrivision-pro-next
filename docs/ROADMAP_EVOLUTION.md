# AgriVision Pro — Feuille de route d'évolution (analyse CTO)

> Réponse à `docs/PROPOSITION D'AMELIORATION.txt`. Analyse des 5 modules proposés
> pour passer d'un « logiciel agricole » à une **plateforme intégrée de conformité,
> traçabilité et durabilité** pour coopératives cacao.
>
> Dernière mise à jour : **2026-05-31**.

---

## Décision immédiate (livrée cette session, en autonomie)

✅ **Module #5 — Tableau de bord direction** : livré de bout en bout (endpoint
`GET /dashboard/direction` + page `direction.html`).

**Pourquoi celui-ci en premier, seul et sans validation préalable :**
- **Lecture seule** : aucune écriture, aucune migration → risque quasi nul.
- **Aucune dépendance externe** (contrairement au satellite avancé).
- **Valorise immédiatement** tout ce qui est déjà construit (EUDR, SSRTE, FarmForce,
  volumes, certification) en une vue exécutive unique.
- **Réutilise le cloisonnement multi-tenant** corrigé en début de session.

Indicateurs consolidés : périmètre (producteurs/plantations/ha), conformité EUDR
(taux + statuts + score moyen), protection de l'enfant (enfants suivis, risque élevé,
scolarisation, blocages traçabilité, suspicions), revenu vital (taux d'atteinte du
seuil, revenu net moyen), volumes & taux certifié, alertes ouvertes.

---

## Analyse des 5 modules proposés

| # | Module | Valeur | Effort | Risque | Dépendance externe |
|---|---|---|---|---|---|
| 1 | Traçabilité cacao (lots, QR, mouvements, entrepôts) | ⭐⭐⭐⭐⭐ | Élevé | Moyen (schéma) | Non |
| 2 | Achats producteurs (bons, pesées, **paiements**) | ⭐⭐⭐⭐⭐ | Élevé | **Élevé** ($) | Non |
| 3 | Certification (RA, FT, Cocoa Horizons…) | ⭐⭐⭐⭐ | Moyen | Moyen | Non |
| 4 | Satellite avancé (NDVI/NDMI/alertes) | ⭐⭐⭐⭐ | Moyen | Faible | **Oui (GEE/Sentinel)** |
| 5 | **Tableau de bord direction** | ⭐⭐⭐⭐ | Faible | **Faible** | Non | ✅ FAIT |

### Séquencement recommandé (après validation client)

1. **Traçabilité des lots** (#1) — cœur de la valeur exportateur. Base : `Lot`
   (code, campagne, certification, poids, statut), `LotMovement` (entrée magasin,
   fusion, sortie export), `Warehouse`, lien `Harvest → Lot`. QR code = simple
   payload encodant le code lot (génération côté front, pas de dépendance lourde).
   Le **blocage traçabilité CacaoGuard existant** doit empêcher l'affectation à un lot.
2. **Achats producteurs** (#2) — `PurchaseRecord` (bord champ : producteur, poids,
   prix/kg, prime, reçu) → alimente automatiquement `Harvest` + volume du lot.
   ⚠️ Volet **paiements** : à cadrer prudemment (traçabilité financière, droits,
   audit). À faire en module séparé après le foncier achat/pesée.
3. **Certification** (#3) — étendre le modèle `Certification`/`PlantationCertification`
   déjà présent : audits, non-conformités, plans d'action, échéances, alertes.
4. **Satellite avancé** (#4) — **bloqué** tant que les accès Google Earth Engine /
   Sentinel Hub (clés + quotas) ne sont pas fournis. Préparer l'abstraction de
   service (interface `SatelliteProvider`) pour brancher le fournisseur le jour J.

---

## Principes d'architecture à respecter pour la suite

- **Multi-tenant strict** : tout nouvel agrégat scopé par `cooperative_id`
  (cf. correctif CacaoGuard de cette session).
- **Migrations idempotentes** au démarrage (`ALTER TABLE … IF NOT EXISTS`), jamais
  de migration destructive automatique.
- **PDF** : WeasyPrint + fallback natif (pas de dépendance Cairo en CI/Windows).
- **Tests verts avant tout push** ; push **uniquement** sur `origin`
  (`codex/cacaoguard-fusion`), jamais sur la prod sans feu vert explicite.
- **Aucune action destructive ni manipulation d'argent** sans validation explicite.
