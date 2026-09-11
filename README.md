# Veille ADS — Client (Gemini + LangChain v18)

**Fichier généré :** `veille-ads-client-v18.json`  
**Script de build :** `build_veille_v18.py`  
**Nom n8n :** Veille ADS — Client (Gemini + LangChain) v18

## Vue d'ensemble

Workflow de veille **orienté livraison client** : articles filtrés et limités, résumé IA via **Google Gemini 2.5-flash** (Basic LLM Chain), enregistrement **Notion natif** (create), alerte Telegram uniquement pour la pertinence 🔥 Haute.

| Critère | Client v18 | Perso v3 |
|--------|------------|----------|
| LLM | Gemini 2.5-flash (cloud) | Ollama qwen2.5:14b **ou** Gemini |
| Chaînes LangChain | 1 (résumé) | 2 (résumé + post LinkedIn) |
| Limite articles / run | **Max 3** | Aucune limite |
| Pertinence faible | Conservée (Notion) | **Exclue** du pipeline |
| Mémoire Notion | `processedUrls` seulement | `processedUrls` + `needsUpdate` (upsert) |
| Notion | Nœud **create** natif | HTTP PATCH + POST (upsert) |
| Cron | `0 7,13 * * 1-5` (Lun–Ven) | `0 7,13 * * *` (tous les jours) |
| Quota / coût | ~6 appels LLM/jour max | Ollama illimité ou quota Gemini perso |

## Import dans n8n

1. **Workflows → Import from file** → choisir `veille-ads-client-v18.json`.
2. Ouvrir chaque nœud marqué avec credentials et associer :
   - **Notion account** — accès lecture DB + création de pages.
   - **Google Gemini API** — clé API Gemini (nœud sous-modèle LangChain).
   - **Telegram account** — bot Telegram ; `chatId` déjà `6587303725`.
3. Vérifier l’ID base Notion : `371e27a7-f3e3-8104-abf3-ec5d673086f3` (propriétés : Titre, Source, URL, Résumé, Tags, Date, Pertinence).
4. Activer le workflow ; tester une exécution manuelle.

## Credentials

| Credential | Nœuds concernés |
|------------|-----------------|
| Notion account | Charger URLs Notion, Notion — Créer Page |
| Google Gemini API | Google Gemini Chat Model |
| Telegram account | Telegram — Alerte |

## Cron

Expression : **`0 7,13 * * 1-5`** — exécution à **7h00** et **13h00**, **lundi à vendredi** (fuseau = celui de l’instance n8n).

## Pattern LangChain (chainLlm + modèle)

- **`Résumé IA — Basic LLM Chain`** (`@n8n/n8n-nodes-langchain.chainLlm`, v1.9) : reçoit les items après Jina ; le prompt utilise `{{ $json.title }}`, `{{ $json.source }}`, `{{ $json.articleContent }}`.
- **`Google Gemini Chat Model`** (`lmChatGoogleGemini`) : **sous-nœud** relié par la connexion **`ai_languageModel`** (pas le flux `main`). Un modèle peut alimenter une ou plusieurs chains ; ici une seule chain.
- Sortie chain : champ **`text`** (parfois `output`) → l’**Assembler** normalise en `ai_summary`.
- **`continueOnFail: true`** sur la chain et Telegram : une erreur LLM ou d’envoi n’arrête pas tout le run.

---

## Documentation nœud par nœud

### Guide — Veille Client v18
| | |
|--|--|
| **TYPE** | `stickyNote` |
| **RÔLE** | Documentation visuelle dans le canvas |
| **INPUT** | — |
| **OUTPUT** | — |
| **POURQUOI** | Rappel du flux et des credentials sans ouvrir le README |

### 7h + 13h Lun-Ven
| | |
|--|--|
| **TYPE** | `scheduleTrigger` |
| **RÔLE** | Démarre le workflow sur cron |
| **INPUT** | Horloge n8n |
| **OUTPUT** | 1 item vide de déclenchement |
| **POURQUOI** | Cadence bureau : 2×/jour en semaine, alignée quota Gemini (max 3 articles × 2 runs) |

### Charger URLs Notion
| | |
|--|--|
| **TYPE** | `notion` — databasePage / getAll |
| **RÔLE** | Lit toutes les pages de la base veille |
| **INPUT** | Trigger |
| **OUTPUT** | 1 item par page Notion (properties) |
| **POURQUOI** | Alimenter la mémoire anti-doublon via les URLs déjà stockées ; `alwaysOutputData` évite un blocage si la base est vide |

### Initialiser mémoire
| | |
|--|--|
| **TYPE** | `code` |
| **RÔLE** | Fusionne les URLs Notion dans `$workflow.staticData.processedUrls` |
| **INPUT** | Pages Notion |
| **OUTPUT** | `{ ready, urlsChargees }` puis fan-out vers les RSS |
| **POURQUOI** | Mémoire simple client : pas d’upsert, seulement « déjà vu » |

### RSS — (6 flux)
| | |
|--|--|
| **TYPE** | `rssFeedRead` |
| **RÔLE** | Pull des flux publishers (SEL, AdExchanger, PPC Hero, SEJ, n8n Blog, WordStream) |
| **INPUT** | Seed (parallèle ×6) |
| **OUTPUT** | Items RSS bruts |
| **POURQUOI** | URLs directes publisher → Jina fiable (pas Google News) |

### Fusionner 6 flux
| | |
|--|--|
| **TYPE** | `merge` — mode append |
| **RÔLE** | Concatène les 6 entrées RSS |
| **INPUT** | 6 branches RSS (index 0–5) |
| **OUTPUT** | Flux unique d’articles |
| **POURQUOI** | Un seul nœud filtre pour toute la veille |

### Filtrer + Formater
| | |
|--|--|
| **TYPE** | `code` |
| **RÔLE** | Déduplication, fraîcheur 7j, mots-clés PPC/automation, score pertinence, **max 3** articles triés |
| **INPUT** | Items RSS mergés + staticData |
| **OUTPUT** | `{ title, url, source, snippet, tags, pertinence, pubISO }` |
| **POURQUOI** | Qualité + quota API : priorité 🔥 puis 🟡, cap à 3 |

### Jina — Lire Article
| | |
|--|--|
| **TYPE** | `code` (runOnceForEachItem) |
| **RÔLE** | `fetch` vers `https://r.jina.ai/{url}` → `articleContent` |
| **INPUT** | Article filtré |
| **OUTPUT** | Item enrichi (fallback snippet) |
| **POURQUOI** | Contenu complet pour un résumé utile |

### Résumé IA — Basic LLM Chain
| | |
|--|--|
| **TYPE** | `chainLlm` v1.9 |
| **RÔLE** | Prompt structuré → synthèse FR 3 bullets |
| **INPUT** | Item Jina (flux main) + modèle Gemini (ai_languageModel) |
| **OUTPUT** | `{ text, ... }` |
| **POURQUOI** | LangChain natif n8n, pas d’HTTP Gemini manuel ; `continueOnFail` |

### Google Gemini Chat Model
| | |
|--|--|
| **TYPE** | `lmChatGoogleGemini` |
| **RÔLE** | Modèle `gemini-2.5-flash`, temp 0.3 |
| **INPUT** | Connexion ai_languageModel depuis la chain |
| **OUTPUT** | (interne LangChain) |
| **POURQUOI** | Qualité client + latence acceptable |

### Assembler Article + Résumé IA
| | |
|--|--|
| **TYPE** | `code` |
| **RÔLE** | Parse `text`/`output`, recolle métadonnées Jina, `ai_summary`, `telegramMsg` |
| **INPUT** | Sortie chain |
| **OUTPUT** | Item prêt Notion + Telegram |
| **POURQUOI** | La chain ne porte pas toutes les colonnes métier |

### Notion — Créer Page
| | |
|--|--|
| **TYPE** | `notion` — databasePage / create |
| **RÔLE** | Crée une ligne dans la base veille |
| **INPUT** | Item assemblé |
| **OUTPUT** | Page Notion créée |
| **POURQUOI** | Intégration native (mapping propertiesUi) vs HTTP — flux client = create only |

### Seulement Haute pertinence
| | |
|--|--|
| **TYPE** | `filter` |
| **RÔLE** | `pertinence` contient « Haute » |
| **INPUT** | Branche parallèle depuis Assembler |
| **OUTPUT** | Sous-ensemble 🔥 |
| **POURQUOI** | Telegram = signal fort uniquement |

### Telegram — Alerte
| | |
|--|--|
| **TYPE** | `telegram` |
| **RÔLE** | Envoie `telegramMsg` Markdown à `6587303725` |
| **INPUT** | Articles haute pertinence |
| **OUTPUT** | Message envoyé |
| **POURQUOI** | Notification mobile ; `continueOnFail` si bot indisponible |

---

## Regénérer le JSON

```bash
python3 build_veille_v18.py
```

**Nombre de nœuds :** 19 (dont 1 sticky + 6 RSS).
