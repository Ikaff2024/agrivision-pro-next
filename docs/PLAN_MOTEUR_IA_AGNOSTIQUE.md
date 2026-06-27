# Plan — Moteur IA agnostique (open-source) + veille auto-hébergée

> **Objectif (2026-06-16)** : rendre la plateforme **indépendante de Claude**, maîtriser le **coût IA**, et
> pouvoir **auto-héberger un modèle open-source** (VPS Hostinger) qui alimente toute la plateforme — en
> priorité la **veille réglementaire/marché**.
>
> Statut : **PLAN** (rien d'implémenté ici). Décisions à trancher en fin de doc.

---

## 1. État des lieux (vérifié dans le code)

| Brique | Fichier | Dépendance Claude aujourd'hui |
|---|---|---|
| **Conseil IA** (agronome) | `app/ai_advisor.py` | ✅ **Déjà agnostique** : `AI_PROVIDER` + `_OPENAI_PRESETS` (deepseek/qwen/openai/**openrouter**/openweights/local), surcharge `AI_OPENAI_BASE_URL` / `_MODEL` / `_API_KEY`. Sortie normalisée + `usage` (suivi coût). |
| **Veille — prix** | `app/services/market_intel.py` | ✅ **Indépendant** : cours ICE NY via source publique gratuite (Yahoo). Ne dépend d'aucune IA. |
| **Veille — actualités + synthèse** | `app/services/market_intel.py` | ❌ **Claude + recherche web** (`ANTHROPIC_API_KEY` + web search). **C'est LE point de couplage à casser.** |
| Suivi du coût | `AiUsage` (modèle) | Déjà en place (tokens in/out par modèle). |

**Conclusion** : le Conseil IA est déjà « agnostique » — l'auto-héberger = **config seule** (pointer le
`base_url` sur le VPS). Le vrai chantier est la **veille**.

---

## 2. L'insight clé (à ne pas rater)

« Moteur agnostique » **≠** « remplacer Claude par Llama ». Pour la veille, le LLM est la partie **facile**.
Le point dur : **un modèle open-source n'a pas d'accès web.** Claude faisait *recherche web + synthèse* en un appel.
Sans lui, il faut **construire la couche de sourcing** (récupération des sources) et ne laisser au modèle que la
**synthèse** de textes qu'on lui fournit.

➡️ Le composant neuf à bâtir = **un pipeline de veille (RAG)**, pas « brancher un autre modèle ».

---

## 3. Architecture cible

```
            ┌──────────────────────── Pipeline VEILLE (nouveau) ───────────────────────┐
 Sources →  │  RSS/API/scrape ciblé  →  ingestion (dédup, nettoyage, découpage)         │
 (UE/EUDR,  │      → embeddings open-source (bge-m3 / multilingual-e5)                  │
 CCC-CI,    │      → stockage vectoriel  ===>  pgvector DANS le Postgres existant       │
 ICCO, RA,  │  Génération : récupère le contexte récent pertinent → LLM (open) →        │
 Fairtrade, │      synthèse structurée {résumé, impacts, sources citées} → cache+AiUsage│
 actus,prix)└──────────────────────────────────┬───────────────────────────────────────┘
                                                │ (OpenAI-compatible)
        ┌───────────────────── Passerelle LLM (étendre l'existant) ────────────────────┐
        │  Routage par TÂCHE + fallback :                                               │
        │   • veille / résumé / triage (volume)      → modèle OPEN (auto-héb. ou API)   │
        │   • conseil agronome à fort enjeu          → modèle FORT (gros open / Claude) │
        │  Tout en OpenAI-compatible (réutilise _OPENAI_PRESETS). Fallback en cascade.  │
        └───────────────────────────────────────────────────────────────────────────────┘
```

- **Ordonnancement** : job planifié (cron VPS **ou** Railway) — la veille tourne en **batch** (nocturne / toutes
  les 6 h), pas à la demande → la latence d'un modèle open lent est **acceptable**.
- **pgvector** : réutilise le **Postgres déjà en place** (Railway) → pas de nouvelle base. Embeddings open-source
  tournent très bien en CPU.
- **Anti-hallucination** : la synthèse **cite les sources récupérées** ; pas de source = pas d'affirmation.

---

## 4. Hébergement — la vraie décision (réalité Hostinger)

⚠️ **Les VPS Hostinger standard n'ont pas de GPU.** Conséquences :

| Option | Ce que ça donne | Pour quoi |
|---|---|---|
| **Self-host modèle 7–14B quantifié** (Ollama / llama.cpp GGUF, CPU) sur le VPS | Fonctionne, mais **lent** (qqs tokens/s) et **RAM-lourd** (~8–16 Go pour un 7–14B Q4) | ✅ **Veille (batch, tolérant latence)** · ❌ **PAS** le Conseil IA interactif |
| **API open-weights hébergée** (Together, Groq, DeepInfra, Scaleway, OpenRouter, Mistral) | OpenAI-compatible, **10–50× moins cher que Claude**, **zéro ops GPU** | ✅ Tout, surtout l'interactif |
| **Hybride (RECO)** | VPS Hostinger = **pipeline veille léger** (sources + pgvector + scheduler, CPU-friendly) ; **génération** via petit modèle local (batch) **ou** API open hébergée (interactif). Claude en **fallback qualité**. | ✅ Meilleur rapport coût / ops / qualité |

> **Reco** : commencer par une **API open-weights hébergée** (dé-risque, rapide à brancher via la config
> existante), héberger le **pipeline veille** sur le VPS, et **n'auto-héberger le modèle qu'ensuite** si le coût
> token le justifie. Auto-héberger un LLM = tu possèdes uptime, MAJ, sécurité, scaling (charge réelle pour un
> fondateur solo) ; l'API hébergée donne **90 % du gain coût pour 10 % de l'ops**.

---

## 5. Qualité & routage par tâche

- Un modèle open 7–14B est **en dessous de Claude** pour l'analyse réglementaire FR nuancée — mais **« assez bon »**
  pour **résumer des sources fournies** (le RAG réduit la charge du modèle : il synthétise, il n'invente pas).
- **Routage** : `open` pour veille / résumé / triage de signalements / extraction (volume) ; **modèle fort**
  (gros open type Llama-70B/Qwen-72B hébergé, ou Claude) pour le **conseil agronome à fort enjeu**.
- Le routage et le fallback **étendent l'abstraction existante** — pas de réécriture.

---

## 6. Plan de migration incrémental (non-cassant)

- **Phase 0 — Agnostique « config seule »** *(petit)* : ajouter un preset `local` / `openrouter` à
  `_OPENAI_PRESETS` ; valider le **Conseil IA** sur un modèle open via `AI_OPENAI_BASE_URL`. Aucune régression
  (défaut reste `anthropic`).
- **Phase 1 — Pipeline sources (le gros morceau, LLM-agnostique)** : flux RSS/API curés + ingestion + `pgvector`.
  Sources cacao/EUDR à suivre : UE (EUDR / Journal officiel), **Conseil du Café-Cacao (CI)**, ICCO, Rainforest
  Alliance, Fairtrade, presse spécialisée, prix ICE.
- **Phase 2 — Endpoint modèle open (OpenAI-compatible)** : démarrer sur **API hébergée** ; option self-host
  Hostinger (Ollama `/v1`) ensuite.
- **Phase 3 — Brancher la veille** : `market_intel` consomme **RAG + modèle open** au lieu de la recherche web
  Claude. Le **prix reste indépendant**. Claude conservé en **fallback**.
- **Phase 4 — Éval & arbitrage** : mesurer la **qualité FR** (jeu de cas réglementaires), décider self-host vs
  hébergé, activer le **routage par tâche** + le suivi de coût comparatif (cf. `AiUsage`).

---

## 7. Risques & garde-fous

- **Qualité FR** d'un petit modèle → mitigée par le RAG (sources fournies) + fallback modèle fort.
- **Fiabilité/fraîcheur des sources** → citer systématiquement, dater, dédupliquer.
- **Latence CPU** (self-host) → cantonner au **batch** (veille), jamais l'interactif.
- **Ops VPS** (sécurité, MAJ, sauvegardes du modèle) → charge réelle ; préférer l'API hébergée tant que le volume
  ne justifie pas le self-host.
- **Conserver la dégradation gracieuse existante** (`market_intel` ne renvoie jamais 500 / ne fabrique pas de faux
  prix) et le **cache partagé** (coût borné).

---

## 8. Décisions qu'il me faut de toi

1. **Hébergement** : API open-weights hébergée / self-host VPS Hostinger / **hybride (ma reco)** ?
2. **Tier Hostinger** visé (vCPU / RAM) — détermine si un 7–14B local est jouable en batch.
3. **Niveau de qualité veille** acceptable (un 7–14B + RAG suffit-il, ou on garde un modèle fort en synthèse ?).
4. **Sources prioritaires** à suivre en premier (EUDR/UE + Conseil Café-Cacao CI me semblent le socle).

> Une fois (1) et (2) tranchés, **Phase 0 + Phase 1** sont livrables vite et **sans risque** (config + nouveau
> pipeline isolé), branche dédiée comme d'habitude.

---

## 9. Décisions arrêtées (2026-06-16, mandat « carte blanche »)

- **VPS : Hostinger KVM 8** (8 vCPU / 32 Go RAM / 240 Go NVMe). Justification : héberger un modèle open
  **14B–32B** *en plus* du pipeline veille + pgvector + marge passage à l'échelle ; KVM 4 (16 Go) briderait le
  modèle et serait vite à l'étroit. ⚠️ **Achat par le propriétaire** (l'assistant n'achète pas / ne crée pas de compte).
- **Modèle self-hébergé (veille batch) : `Qwen2.5-14B-Instruct`** (GGUF Q4_K_M via Ollama) — top-tier pour sa
  taille, excellent **français**, tourne en batch sur CPU 32 Go (~9 Go RAM). Option qualité+ : `Qwen2.5-32B` (plus lent).
- **Qualité max (interactif / synthèse) via API hébergée open : `Llama-3.3-70B` ou `Qwen2.5-72B`**
  (Together / DeepInfra / Scaleway — OpenAI-compatible) : « le meilleur open du marché » sans GPU à gérer.
- **Embeddings : `multilingual-e5` / `bge-m3`** (CPU) — **Phase 2** (la v1 fait *recency + mots-clés*, sans pgvector).
- **Claude** : conservé en **fallback** uniquement (n'est plus le défaut une fois l'open branché).

## 10. Mise en service VPS (turnkey — à exécuter par le propriétaire)

> L'assistant **ne provisionne pas** le VPS et **ne saisit aucune clé**. Étapes à faire par toi une fois le **KVM 8** acheté :

1. **Ollama** : `curl -fsSL https://ollama.com/install.sh | sh`
2. **Modèle** : `ollama pull qwen2.5:14b-instruct` (≈ 9 Go) — *(option qualité : `qwen2.5:32b-instruct`)*.
3. **Sécuriser l'accès** : Ollama sert `http://127.0.0.1:11434/v1`. **Ne pas l'exposer en clair** — mettre un
   **reverse-proxy TLS** (Caddy/Nginx) avec une **clé d'accès**, ou restreindre par **firewall** à l'IP de Railway.
4. **Variables Railway** (Settings → Variables) :
   - `AI_PROVIDER=openweights` *(ou `local`)* · `AI_OPENAI_BASE_URL=https://<vps>/v1`
   - `AI_OPENAI_MODEL=qwen2.5:14b-instruct` · `AI_OPENAI_API_KEY=<clé du reverse-proxy>`
   - `VEILLE_ENABLED=1`
5. **Veille planifiée** : cron (VPS ou Railway) toutes les 6 h → `POST /veille/ingest` puis `POST /veille/digest`
   (endpoints admin). Le **prix** du cacao reste indépendant (déjà en place).

> Variante **sans VPS** (démarrage rapide) : `AI_PROVIDER=openweights` + `AI_OPENAI_BASE_URL` d'un fournisseur
> hébergé (Together/DeepInfra) + leur clé → on a l'open-source en prod **sans rien auto-héberger**, le temps de
> valider la qualité. Le VPS devient pertinent quand le volume justifie le coût fixe.

---

## Liens
- Abstraction LLM existante : `app/ai_advisor.py` (`AI_PROVIDER`, `_OPENAI_PRESETS`).
- Veille actuelle : `app/services/market_intel.py` (prix indépendant ✅ / actus = Claude web search ❌).
- Suivi du coût IA : modèle `AiUsage` (cf. mémoire « coût API IA par coop »).
