#!/usr/bin/env python3
"""Génère veille-ads-client-v18.json — Veille client Gemini + LangChain."""
import json
from pathlib import Path

VEILLE_DB_ID = "REMPLACER_PAR_ID_BASE_NOTION"
NOTION_CRED = {"id": "4rbkLchn0g0a74Te", "name": "Notion account"}
TELEGRAM_CRED = {"id": "cAqYgyvMNZd6mPlk", "name": "Telegram account"}
GEMINI_CRED = {"id": "mTD96rhOwH0wn5rL", "name": "Google Gemini API"}

RSS_FEEDS = [
    ("https://searchengineland.com/feed", "Search Engine Land"),
    ("https://www.adexchanger.com/feed", "AdExchanger"),
    ("https://www.ppchero.com/feed", "PPC Hero"),
    ("https://www.searchenginejournal.com/feed", "Search Engine Journal"),
    ("https://blog.n8n.io/rss", "n8n Blog"),
    ("https://www.wordstream.com/blog/feed", "WordStream"),
]

OUT = Path(__file__).resolve().parent / "veille-ads-client-v18.json"

nodes = []
x = 200

nodes.append({
    "id": "guide",
    "name": "Guide — Veille Client v18",
    "type": "n8n-nodes-base.stickyNote",
    "typeVersion": 1,
    "position": [x - 80, 40],
    "parameters": {
        "width": 520,
        "height": 220,
        "content": (
            "## Veille ADS Client (Gemini v18)\n"
            "1. Cron Lun-Ven 7h/13h → URLs Notion → mémoire processedUrls\n"
            "2. 6 RSS publishers → merge → filtre pertinence (max 3/run)\n"
            "3. Jina Reader → Basic LLM Chain (Gemini 2.5-flash)\n"
            "4. Notion create natif + Telegram si 🔥 Haute\n"
            "Credentials : Notion, Google Gemini API, Telegram"
        ),
    },
})

nodes.append({
    "id": "trigger",
    "name": "7h + 13h Lun-Ven",
    "type": "n8n-nodes-base.scheduleTrigger",
    "typeVersion": 1.2,
    "position": [x, 300],
    "parameters": {
        "rule": {"interval": [{"field": "cronExpression", "expression": "0 7,13 * * 1-5"}]}
    },
})

nodes.append({
    "id": "load-notion-urls",
    "name": "Charger URLs Notion",
    "type": "n8n-nodes-base.notion",
    "typeVersion": 2.2,
    "position": [x + 280, 300],
    "alwaysOutputData": True,
    "parameters": {
        "resource": "databasePage",
        "operation": "getAll",
        "databaseId": {"__rl": True, "value": VEILLE_DB_ID, "mode": "id"},
        "returnAll": True,
        "options": {},
    },
    "credentials": {"notionApi": NOTION_CRED},
})

SEED_CODE = r"""
const pages = $input.all();
const existingUrls = pages
  .map(p => { const u = p.json?.properties?.URL; return (u && u.url) ? u.url : ''; })
  .filter(u => u && u.startsWith('http'));

const wfData = $workflow.staticData;
if (wfData) {
  const current = new Set(wfData.processedUrls || []);
  existingUrls.forEach(u => current.add(u));
  wfData.processedUrls = [...current].slice(-2000);
}
return [{ json: { ready: true, urlsChargees: existingUrls.length } }];
""".strip()

nodes.append({
    "id": "seed-memory",
    "name": "Initialiser mémoire",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [x + 560, 300],
    "parameters": {"jsCode": SEED_CODE},
})

rss_names = []
for i, (feed_url, feed_name) in enumerate(RSS_FEEDS):
    name = f"RSS — {feed_name}"
    rss_names.append(name)
    nodes.append({
        "id": f"rss-{i}",
        "name": name,
        "type": "n8n-nodes-base.rssFeedRead",
        "typeVersion": 1,
        "position": [x + 840, 60 + i * 120],
        "parameters": {"url": feed_url},
    })

nodes.append({
    "id": "merge",
    "name": "Fusionner 6 flux",
    "type": "n8n-nodes-base.merge",
    "typeVersion": 3,
    "position": [x + 1120, 400],
    "parameters": {"mode": "append"},
})

FILTER_CODE = r"""
const items = $input.all();
const results = [];

const wfData = $workflow.staticData;
const processedSet = new Set((wfData && wfData.processedUrls) ? wfData.processedUrls : []);
const newUrls = [];

function decode(str) {
  return str.replace(/&nbsp;/g,' ').replace(/&amp;/g,'&').replace(/&lt;/g,'<')
            .replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#(\d+);/g,(_,n)=>String.fromCharCode(n))
            .replace(/\s+/g,' ').trim();
}

for (const item of items) {
  const d = item.json;
  const title = decode((d.titre || d.title || '').replace(/<[^>]+>/g, ''));
  const url   = d.lien || d.link || d.url || '';
  const pubDate = d['date de publication'] || d.pubDate || d.isoDate || '';
  const snippet = decode((d.content || d.contenu || d['extrait de contenu'] || d.summary || d.contentSnippet || '')
    .replace(/<[^>]+>/g, '').slice(0, 800));
  const source = (d.source?.name || d.feed?.title || 'Autre').replace(/ - RSS.*$/i,'').trim();

  if (!title || !url || !url.startsWith('http')) continue;
  if (processedSet.has(url) || newUrls.includes(url)) continue;

  const pub = new Date(pubDate);
  if (pubDate && !isNaN(pub.getTime()) && (Date.now() - pub.getTime()) > 604800000) continue;

  const text = (title + ' ' + snippet).toLowerCase();
  const relevant = ['google ads','adwords','ppc','paid search','paid media','meta ads','facebook ads',
    'automation','automatisation','n8n','workflow','ai ','artificial intelligence','machine learning',
    'ad spend','campaign','cpc','roas','impression','bidding','performance max','smart bidding',
    'agenc','marketing digital','programmatic'];
  if (!relevant.some(w => text.includes(w))) continue;

  const tags = [];
  if (text.includes('google ads') || text.includes('adwords') || text.includes('paid search')) tags.push('Google Ads');
  if (text.includes('meta') || text.includes('facebook ads')) tags.push('Meta Ads');
  if (text.includes('automation') || text.includes('automatisation')) tags.push('Automation');
  if (text.includes('n8n')) tags.push('n8n');
  if (text.includes(' ai ') || text.includes('artificial intelligence') || text.includes('machine learning')) tags.push('IA');
  if (text.includes('agenc') || text.includes('agence')) tags.push('Agences');
  if (tags.length === 0) tags.push('Technologie');

  const highValue = ['automation','n8n','workflow','google ads','ppc','performance max','smart bidding','roas','api'];
  const score = highValue.filter(w => text.includes(w)).length;
  const pertinence = score >= 3 ? '🔥 Haute' : score >= 1 ? '🟡 Moyenne' : '⬇️ Faible';
  const pubISO = !isNaN(pub.getTime()) ? pub.toISOString() : new Date().toISOString();

  newUrls.push(url);
  results.push({ json: { title, url, source, snippet, tags, pertinence, pubISO } });
}

if (wfData) wfData.processedUrls = [...processedSet, ...newUrls].slice(-2000);
const order = {'🔥 Haute': 0, '🟡 Moyenne': 1, '⬇️ Faible': 2};
return results.sort((a, b) => (order[a.json.pertinence]??1) - (order[b.json.pertinence]??1)).slice(0, 3);
""".strip()

nodes.append({
    "id": "format",
    "name": "Filtrer + Formater",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [x + 1360, 400],
    "parameters": {"jsCode": FILTER_CODE},
})

FETCH_CONTENT_CODE = r"""
const item = $input.item.json;
let articleContent = item.snippet || '';

try {
  const jinaResp = await fetch(`https://r.jina.ai/${item.url}`, {
    headers: {
      'Accept': 'text/plain',
      'X-Return-Format': 'text',
      'X-Timeout': '10'
    }
  });
  const text = await jinaResp.text();

  if (text && text.length > 300
      && !text.includes('SecurityCompromiseError')
      && !text.includes('AuthenticationRequiredError')
      && !text.toLowerCase().startsWith('error')) {
    articleContent = text.slice(0, 4000);
  }
} catch(e) {}

return { json: { ...item, articleContent } };
""".strip()

nodes.append({
    "id": "fetch-content",
    "name": "Jina — Lire Article",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [x + 1600, 400],
    "parameters": {"jsCode": FETCH_CONTENT_CODE, "mode": "runOnceForEachItem"},
})

PROMPT_TEXT = (
    "Tu es un expert en marketing digital, publicite payante (Google Ads, Meta Ads) et automation marketing.\n"
    "Ta mission : analyser cet article et produire une SYNTHESE ACTIONNABLE pour une agence PPC/automation.\n\n"
    "REGLES :\n"
    "- Langue : francais uniquement\n"
    "- Format : exactement 3 points cles introduits par le symbole bullet point\n"
    "- Longueur : 120 mots maximum au total\n"
    "- Angle : ce que cela signifie concrètement pour une agence (opportunité, risque, action)\n"
    "- Sois factuel et direct, zero generalite\n\n"
    "ARTICLE :\n"
    "Titre : {{ $json.title }}\n"
    "Source : {{ $json.source }}\n"
    "Contenu : {{ $json.articleContent }}"
)

nodes.append({
    "id": "llm-chain",
    "name": "Résumé IA — Basic LLM Chain",
    "type": "@n8n/n8n-nodes-langchain.chainLlm",
    "typeVersion": 1.9,
    "position": [x + 1840, 400],
    "continueOnFail": True,
    "parameters": {"promptType": "define", "text": PROMPT_TEXT},
})

nodes.append({
    "id": "gemini-model",
    "name": "Google Gemini Chat Model",
    "type": "@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
    "typeVersion": 1,
    "position": [x + 1840, 580],
    "parameters": {
        "modelName": "gemini-2.5-flash",
        "options": {"temperature": 0.3, "maxOutputTokens": 350},
    },
    "credentials": {"googlePalmApi": GEMINI_CRED},
})

MERGE_CODE = r"""
const aiOutput = ($input.item.json.text || $input.item.json.output || '').trim();
const orig = $('Jina — Lire Article').item.json;
const emoji = orig.pertinence?.includes('Haute') ? '🔥' : orig.pertinence?.includes('Moyenne') ? '📡' : '📰';
const telegramMsg = `${emoji} *${orig.title}*\n\n${aiOutput}\n\n🔗 ${orig.url}`;
const { articleContent, ...origClean } = orig;
return { json: { ...origClean, ai_summary: aiOutput, telegramMsg } };
""".strip()

nodes.append({
    "id": "merge-ai",
    "name": "Assembler Article + Résumé IA",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [x + 2080, 400],
    "parameters": {"jsCode": MERGE_CODE, "mode": "runOnceForEachItem"},
})

nodes.append({
    "id": "notion-create",
    "name": "Notion — Créer Page",
    "type": "n8n-nodes-base.notion",
    "typeVersion": 2.2,
    "position": [x + 2320, 280],
    "parameters": {
        "resource": "databasePage",
        "operation": "create",
        "databaseId": {"__rl": True, "value": VEILLE_DB_ID, "mode": "id"},
        "title": "={{ $json.title }}",
        "propertiesUi": {
            "propertyValues": [
                {"key": "Source|select", "selectValue": "={{ $json.source }}"},
                {"key": "URL|url", "urlValue": "={{ $json.url }}"},
                {"key": "Résumé|rich_text", "textContent": "={{ $json.ai_summary }}"},
                {"key": "Pertinence|select", "selectValue": "={{ $json.pertinence }}"},
                {"key": "Date|date", "date": "={{ $json.pubISO }}"},
            ]
        },
        "options": {},
    },
    "credentials": {"notionApi": NOTION_CRED},
})

nodes.append({
    "id": "filter-hot",
    "name": "Seulement Haute pertinence",
    "type": "n8n-nodes-base.filter",
    "typeVersion": 2,
    "position": [x + 2320, 560],
    "parameters": {
        "conditions": {
            "options": {"caseSensitive": False, "typeValidation": "loose"},
            "conditions": [{
                "id": "1",
                "leftValue": "={{ $json.pertinence }}",
                "rightValue": "Haute",
                "operator": {"type": "string", "operation": "contains"},
            }],
            "combinator": "and",
        }
    },
})

nodes.append({
    "id": "telegram",
    "name": "Telegram — Alerte",
    "type": "n8n-nodes-base.telegram",
    "typeVersion": 1.2,
    "position": [x + 2560, 560],
    "continueOnFail": True,
    "parameters": {
        "chatId": "6587303725",
        "text": "={{ $json.telegramMsg }}",
        "additionalFields": {"parse_mode": "Markdown", "disable_web_page_preview": True},
    },
    "credentials": {"telegramApi": TELEGRAM_CRED},
})

conns = {
    "7h + 13h Lun-Ven": {"main": [[{"node": "Charger URLs Notion", "type": "main", "index": 0}]]},
    "Charger URLs Notion": {"main": [[{"node": "Initialiser mémoire", "type": "main", "index": 0}]]},
    "Initialiser mémoire": {"main": [[{"node": n, "type": "main", "index": 0} for n in rss_names]]},
    "Fusionner 6 flux": {"main": [[{"node": "Filtrer + Formater", "type": "main", "index": 0}]]},
    "Filtrer + Formater": {"main": [[{"node": "Jina — Lire Article", "type": "main", "index": 0}]]},
    "Jina — Lire Article": {"main": [[{"node": "Résumé IA — Basic LLM Chain", "type": "main", "index": 0}]]},
    "Résumé IA — Basic LLM Chain": {"main": [[{"node": "Assembler Article + Résumé IA", "type": "main", "index": 0}]]},
    "Google Gemini Chat Model": {
        "ai_languageModel": [[{"node": "Résumé IA — Basic LLM Chain", "type": "ai_languageModel", "index": 0}]]
    },
    "Assembler Article + Résumé IA": {"main": [[
        {"node": "Notion — Créer Page", "type": "main", "index": 0},
        {"node": "Seulement Haute pertinence", "type": "main", "index": 0},
    ]]},
    "Seulement Haute pertinence": {"main": [[{"node": "Telegram — Alerte", "type": "main", "index": 0}]]},
}

for i, name in enumerate(rss_names):
    conns[name] = {"main": [[{"node": "Fusionner 6 flux", "type": "main", "index": i}]]}

wf = {
    "name": "Veille ADS — Client (Gemini + LangChain) v18",
    "nodes": nodes,
    "connections": conns,
    "settings": {"executionOrder": "v1"},
    "staticData": None,
}

OUT.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Généré : {OUT}")
print(f"Nodes : {len(nodes)}")
