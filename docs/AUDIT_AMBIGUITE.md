# Audit d'ambiguïté des sorties — module par module

> **But** : repérer les affichages qui pourraient être **mal lus** par un utilisateur ou un visiteur
> (comme le « Feu vert » de la déforestation à Bingerville) et les clarifier de façon proactive.
> Phase pilote : les retours terrain compléteront cette liste. **Date** : juillet 2026.
>
> Légende priorité : 🔴 à corriger · 🟠 à trancher (choix produit) · 🟢 déjà clair (RAS).

---

## Vue d'ensemble
Bonne nouvelle : l'app est **déjà très majoritairement légendée**. Les scores de risque portent la mention
« ↑ élevé = moins bon », le carbone est marqué « estimation », l'EUDR en simulation refuse le mot « conforme »
et bloque le DDS, le revenu vital est chiffré (atteint/écart + montant). Peu de vrais pièges subsistent.

---

## Corrigé dans cette passe
- 🔴→🟢 **Pré-contrôle EUDR / position urbaine** *(satellite)* : un « Feu vert » sur une zone sans forêt
  (Bingerville) était trompeur. Désormais, si aucune déforestation **mais** couvert végétal très faible
  (urbain/sol nu/eau), le verdict devient **« Zone à vérifier — ne ressemble pas à une parcelle »**. *(Déployé, vérifié.)*
- 🔴→🟢 **Satellite avancé, mode simulation** : affichait « ✓ Aucune perte » (vert) sans contrôle réel.
  Corrigé en **« ❔ Non vérifié »** quand la clé GFW est absente.

---

## Tranché & implémenté (décision propriétaire) ✅

### A. Le mot « Conforme EUDR » à partir de 4/5 — *fait*
- **Décision** : garder « Conforme » mais **toujours afficher le score**. Le badge montre désormais
  **« Conforme · 4/5 »** (liste EUDR + fiche parcelle), avec une **mini-légende** du seuil
  (Conforme = 4–5/5 · À vérifier = 2–3/5 · Non conforme = 0–1/5) et une info-bulle.

### B. « ✓ Conforme » sur la fiche producteur (volet social) — *fait*
- **Décision** : remplacé par **« Aucun blocage actif »** (neutre) + rappel *« un ménage sans blocage peut
  rester à surveiller »*, avec le **niveau de risque** affiché quand il n'est pas nul.

### C. Déforestation « Aucune (RAS) » dans le Jumeau — *fait*
- **Où** : `plantation_detail.html` — puce « Déforestation » de la carte Jumeau.
- **Fait** : info-bulle (ⓘ) ajoutée — « Concerne uniquement une perte de forêt après le 31/12/2020 ;
  “Aucune” ne juge pas les autres critères EUDR. »

---

## Déjà clair (contrôlé) 🟢
- **Tableau de bord / Direction** : « Score = risque (↑ élevé = moins bon) », « Santé globale = 100 − risque »,
  palmarès « risque le plus élevé d'abord ». ✔
- **Agroforesterie** : carbone « (estimation) », score carbone « Plus élevé = mieux ». ✔
- **EUDR (simulation)** : bannière « GFW non configuré → verdict “à vérifier”, jamais “conforme” ; DDS bloqué ». ✔
- **Diagnostic photo** : si modèle indisponible → « ⏳ Modèle indisponible » (pas de faux résultat). ✔
- **Revenu vital** : « ✓ atteint / ⚠ écart » + % + montant ; seuil éditable expliqué. ✔
- **Lots / Conformité** : « déforestation NON vérifiée — contrôle requis avant export ». ✔
- **Protection enfant** : niveaux faible/moyen/élevé, « déjà suivi », disclaimer « aide à l'enquête ». ✔

---

## À vérifier au fil des retours pilote (backlog)
- Formulations « Faible / Moyen / Élevé » : toujours accompagner d'un sens (bon vs mauvais selon le contexte).
- Sources satellite « simulation » vs réelle : rendre le badge de source visible partout où un chiffre satellite s'affiche.
- Unités et périodes (kg/ha « par campagne », CFA/an) : garder explicites.
