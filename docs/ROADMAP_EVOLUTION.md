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

1. **Traçabilité des lots** (#1) — ✅ **livré (2026-05-31)**. Modèles `Warehouse`, `Lot`
   (code auto `LOT-AAAA-NNNNN`, statut open/sealed/shipped/merged/blocked, poids/sacs dérivés),
   `LotMovement` (journal : creation/warehouse_in/seal/export_out/merge_in/split_out/adjustment),
   lien `Harvest.lot_id`. Endpoints `/warehouses`, `/lots` (CRUD + filtres), `/lots/{id}/affect-harvests`,
   `/lots/{id}/movements`, `/lots/merge`, `/lots/{id}/passport`. **Intégration CacaoGuard** : refus 409
   d'affecter une récolte dont le producteur a un blocage de traçabilité ACTIF. UI `lots.html`
   (liste, création, détail+passeport+mouvements+statuts, entrepôts). Cloisonné coopérative. 7 tests.
   **Reste possible** : QR code imprimable du passeport (génération image), split de lot, lien achats.
2. **Achats producteurs** (#2) — ✅ **livré (2026-05-31, hors exécution financière)**.
   `PurchaseRecord` (producteur, plantation, bon d'achat, pesée brut/tare/net, prix/kg,
   montant, qualité, campagne). Génère automatiquement une `Harvest` traçable (→ volumes → lots).
   Endpoints `/purchases` (GET/POST + filtres), `/purchases/summary`, `/purchases/{id}`,
   `/purchases/{id}/mark-paid`. Suivi de paiement **comptable uniquement** (statut pending/paid),
   signale les producteurs sous blocage CacaoGuard. UI `achats.html`. Cloisonné coop. 7 tests.
   ⚠️ **Reste à cadrer avec le client** : l'**exécution financière** réelle (virements / mobile
   money / intégration bancaire) n'est PAS implémentée — décision produit + conformité requise.
3. **Certification** (#3) — étendre le modèle `Certification`/`PlantationCertification`
   déjà présent : audits, non-conformités, plans d'action, échéances, alertes.
4. **Satellite avancé** (#4) — ✅ **abstraction livrée (2026-05-31)**. `app/satellite/provider.py`
   expose `get_indices` (NDVI+NDMI), `get_timeseries` (séries mensuelles) et
   `get_deforestation_signal`, avec **fallback simulation déterministe** (fonctionne
   sans clé) et **bascule automatique** sur Copernicus dès que `SENTINEL_CLIENT_ID/SECRET`
   sont définis (l'intégration CDSE NDVI ponctuelle existait déjà). Endpoints
   `/satellite/indices|timeseries|deforestation|status` + `/satellite/plantations/{id}/advanced`
   (cloisonné coop). UI : carte « Analyse avancée » dans `satellite.html` (NDMI, sparklines
   NDVI/NDMI, statut déforestation). On a délibérément **écarté Google Earth Engine** (licence
   commerciale payante) au profit de Copernicus Data Space + GFW (gratuits).
   ✅ **Terminé et vérifié en live (2026-05-31)** : NDVI, NDMI et séries mensuelles réels via
   Copernicus (`SENTINEL_CLIENT_ID/SECRET`) ; **alertes de déforestation réelles** via Global
   Forest Watch (`GFW_API_KEY`, dataset `gfw_integrated_alerts`, post-2020 = seuil EUDR).
   ⚠️ Piège résolu : la GFW Data API exige l'en-tête `x-api-key` **en minuscules** (urllib le
   capitalise → 403) ; les appels GFW passent donc par `http.client`. Coût total : **0 €**.

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
