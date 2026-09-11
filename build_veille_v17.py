import json

VEILLE_DB_ID = "371e27a7-f3e3-8104-abf3-ec5d673086f3"
NOTION_CRED   = {"id": "4rbkLchn0g0a74Te", "name": "Notion account"}
TELEGRAM_CRED = {"id": "cAqYgyvMNZd6mPlk", "name": "Telegram account"}
GEMINI_CRED   = {"id": "mTD96rhOwH0wn5rL", "name": "Google Gemini API"}

# RSS directs des publishers — URLs réelles → Jina peut les scraper
RSS_FEEDS = [
    ("https://searchengineland.com/feed",                      "Search Engine Land"),
    ("https://www.adexchanger.com/feed",                       "AdExchanger"),
    ("https://www.ppchero.com/feed",                           "PPC Hero"),
    ("https://www.searchenginejournal.com/feed",               "Search Engine Journal"),
    ("https://blog.n8n.io/rss",                                "n8n Blog"),
    ("https://www.wordstream.com/blog/feed",                   "WordStream"),
]

nodes = []
x = 200

# ── Trigger ───────────────────────────────────────────────────────────────────
nodes.append({
    "id": "trigger",
    "name": "7h + 13h Lun-Ven",
    "type": "n8n-nodes-base.scheduleTrigger",
    "typeVersion": 1.2,
    "position": [x, 300],
    "parameters": {
        "rule": {"interval": [{"field": "cronExpression", "expression": "0 7,13 * * 1-5"}]}
    }
})

# ── Charger URLs Notion (alwaysOutputData → table vide ne bloque pas) ─────────
nodes.append({
    "id": "load-notion-urls",
    "name": "Charger URLs Notion",
    "type": "n8n-nodes-base.notion",
    "typeVersion": 2.2,
    "position": [x+280, 300],
    "alwaysOutputData": True,
    "parameters": {
        "resource": "databasePage",
        "operation": "getAll",
        "databaseId": {"__rl": True, "value": VEILLE_DB_ID, "mode": "id"},
        "returnAll": True,
        "options": {}
    },
    "credentials": {"notionApi": NOTION_CRED}
})

# ── Initialiser mémoire ────────────────────────────────────────────────────────
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
    "position": [x+560, 300],
    "parameters": {"jsCode": SEED_CODE}
})

# ── 6 RSS directs publishers ───────────────────────────────────────────────────
rss_names = []
for i, (feed_url, feed_name) in enumerate(RSS_FEEDS):
    name = f"RSS — {feed_name}"
    rss_names.append(name)
    nodes.append({
        "id": f"rss-{i}",
        "name": name,
        "type": "n8n-nodes-base.rssFeedRead",
        "typeVersion": 1,
        "position": [x+840, 60 + i*120],
        "parameters": {"url": feed_url}
    })

# ── Merge ─────────────────────────────────────────────────────────────────────
nodes.append({
    "id": "merge",
    "name": "Fusionner 6 flux",
    "type": "n8n-nodes-base.merge",
    "typeVersion": 3,
    "position": [x+1120, 400],
    "parameters": {"mode": "append"}
})

# ── Filtrer + Formater ─────────────────────────────────────────────────────────
# Filtre par pertinence : seuls les articles sur PPC, automation, Google Ads, n8n, IA
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

  // Filtre de pertinence : l'article doit parler d'au moins un de ces sujets
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
// Max 3 articles par run — quota Gemini free tier : 20 req/jour (3×2runs = 6/jour)
return results.sort((a, b) => (order[a.json.pertinence]??1) - (order[b.json.pertinence]??1)).slice(0, 3);
""".strip()

nodes.append({
    "id": "format",
    "name": "Filtrer + Formater",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [x+1360, 400],
    "parameters": {"jsCode": FILTER_CODE}
})

# ── Code — Jina Reader sur URL directe publisher ───────────────────────────────
# Les URLs viennent maintenant des publishers directement (pas Google News)
# → Jina peut les scraper sans restriction
FETCH_CONTENT_CODE = r"""
const item = $input.item.json;
let articleContent = item.snippet || '';

try {
  // URL directe du publisher → Jina Reader fonctionne
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
} catch(e) {
  // Fallback sur snippet RSS si Jina échoue
}

return { json: { ...item, articleContent } };
""".strip()

nodes.append({
    "id": "fetch-content",
    "name": "Jina — Lire Article",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [x+1600, 400],
    "parameters": {"jsCode": FETCH_CONTENT_CODE, "mode": "runOnceForEachItem"}
})

# ── Basic LLM Chain ────────────────────────────────────────────────────────────
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
    "name": "Résumé IA — LLM Chain",
    "type": "@n8n/n8n-nodes-langchain.chainLlm",
    "typeVersion": 1.5,
    "position": [x+1840, 400],
    "parameters": {"promptType": "define", "text": PROMPT_TEXT}
})

nodes.append({
    "id": "gemini-model",
    "name": "Google Gemini Chat Model",
    "type": "@n8n/n8n-nodes-langchain.lmChatGoogleGemini",
    "typeVersion": 1,
    "position": [x+1840, 580],
    "parameters": {
        "modelName": "gemini-2.5-flash",
        "options": {"temperature": 0.3, "maxOutputTokens": 350}
    },
    "credentials": {"googlePalmApi": GEMINI_CRED}
})

# ── Assembler — FIX : LLM Chain retourne "text" pas "output" ─────────────────
MERGE_CODE = r"""
// FIX : chainLlm retourne le résultat dans "text", pas "output"
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
    "position": [x+2080, 400],
    "parameters": {"jsCode": MERGE_CODE, "mode": "runOnceForEachItem"}
})

# ── Build Notion Payload ───────────────────────────────────────────────────────
NOTION_PAYLOAD_CODE = f"""
const d = $input.item.json;
return {{
  json: {{
    parent: {{ database_id: '{VEILLE_DB_ID}' }},
    properties: {{
      'Titre': {{ title: [{{ text: {{ content: d.title || '' }} }}] }},
      'Source': {{ select: {{ name: d.source || 'Autre' }} }},
      'URL': {{ url: d.url || null }},
      'Résumé': {{ rich_text: [{{ text: {{ content: (d.ai_summary || d.snippet || '').slice(0, 2000) }} }}] }},
      'Tags': {{ multi_select: (d.tags || []).map(t => ({{ name: t }})) }},
      'Date': {{ date: {{ start: d.pubISO }} }},
      'Pertinence': {{ select: {{ name: d.pertinence || '⬇️ Faible' }} }}
    }},
    _telegramMsg: d.telegramMsg,
    _pertinence: d.pertinence
  }}
}};
""".strip()

nodes.append({
    "id": "notion-payload",
    "name": "Build Notion Payload",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [x+2320, 280],
    "parameters": {"jsCode": NOTION_PAYLOAD_CODE, "mode": "runOnceForEachItem"}
})

nodes.append({
    "id": "notion-http",
    "name": "Notion — Créer Page",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [x+2560, 280],
    "parameters": {
        "method": "POST",
        "url": "https://api.notion.com/v1/pages",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "notionApi",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ parent: $json.parent, properties: $json.properties }) }}",
        "options": {}
    },
    "credentials": {"notionApi": NOTION_CRED}
})

nodes.append({
    "id": "filter-hot",
    "name": "Seulement Haute pertinence",
    "type": "n8n-nodes-base.filter",
    "typeVersion": 2,
    "position": [x+2320, 560],
    "parameters": {
        "conditions": {
            "options": {"caseSensitive": False, "typeValidation": "loose"},
            "conditions": [{"id": "1", "leftValue": "={{ $json.pertinence }}", "rightValue": "Haute", "operator": {"type": "string", "operation": "contains"}}],
            "combinator": "and"
        }
    }
})

nodes.append({
    "id": "telegram",
    "name": "Telegram — Alerte",
    "type": "n8n-nodes-base.telegram",
    "typeVersion": 1.2,
    "position": [x+2560, 560],
    "parameters": {
        "chatId": "6587303725",
        "text": "={{ $json.telegramMsg }}",
        "additionalFields": {"parse_mode": "Markdown", "disable_web_page_preview": True}
    },
    "credentials": {"telegramApi": TELEGRAM_CRED}
})

# ── Connections ───────────────────────────────────────────────────────────────
conns = {
    "7h + 13h Lun-Ven":           {"main": [[{"node": "Charger URLs Notion",          "type": "main", "index": 0}]]},
    "Charger URLs Notion":         {"main": [[{"node": "Initialiser mémoire",          "type": "main", "index": 0}]]},
    "Initialiser mémoire":         {"main": [[{"node": n, "type": "main", "index": 0} for n in rss_names]]},
    "Fusionner 6 flux":            {"main": [[{"node": "Filtrer + Formater",           "type": "main", "index": 0}]]},
    "Filtrer + Formater":          {"main": [[{"node": "Jina — Lire Article",          "type": "main", "index": 0}]]},
    "Jina — Lire Article":         {"main": [[{"node": "Résumé IA — LLM Chain",        "type": "main", "index": 0}]]},
    "Résumé IA — LLM Chain":       {"main": [[{"node": "Assembler Article + Résumé IA","type": "main", "index": 0}]]},
    "Google Gemini Chat Model":    {"ai_languageModel": [[{"node": "Résumé IA — LLM Chain", "type": "ai_languageModel", "index": 0}]]},
    "Assembler Article + Résumé IA": {"main": [[
        {"node": "Build Notion Payload",       "type": "main", "index": 0},
        {"node": "Seulement Haute pertinence", "type": "main", "index": 0},
    ]]},
    "Build Notion Payload":          {"main": [[{"node": "Notion — Créer Page",    "type": "main", "index": 0}]]},
    "Seulement Haute pertinence":    {"main": [[{"node": "Telegram — Alerte",      "type": "main", "index": 0}]]},
}

for i, name in enumerate(rss_names):
    conns[name] = {"main": [[{"node": "Fusionner 6 flux", "type": "main", "index": i}]]}

wf = {
    "name": "Veille ADS — Publishers directs → Notion + Telegram",
    "nodes": nodes,
    "connections": conns,
    "settings": {"executionOrder": "v1"},
    "staticData": None
}

out = "/Users/sedera/Documents/BOS-main/Output/n8n-workflows/veille-ads-gnews-notion-telegram.json"
json.dump(wf, open(out, 'w'), ensure_ascii=False, indent=2)
print(f"v17 généré : {len(nodes)} nodes, {len(conns)} connexions")
print(f"Sources : {[f[1] for f in RSS_FEEDS]}")
