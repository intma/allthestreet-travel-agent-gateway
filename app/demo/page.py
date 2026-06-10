"""
Demo page renderer (B-1 step 2) — Gemini-web-chat styled showcase.

One job: make it feel like the agentic moment is happening *inside Gemini*.
Familiar chat layout (user bubble right, Gemini answer left with a sparkle
avatar, Gemini blue->purple gradient accent, rounded pill composer). Our
signature is folded in as a "Gemini가 AllTheStreet MCP 사용 중" tool chip that
expands into the real tool-call log. Then place cards with prices + kkday
buttons + a /p link.
"""

from __future__ import annotations

from app.config import settings

_EXAMPLES = [
    "부산 해운대 가볼 곳과 예약 가능한 티켓 알려줘",
    "성수동 카페 추천해줘",
    "서울에서 아이와 가기 좋은 곳은?",
    "부산에서 야경 좋은 곳",
]


def render_demo_page() -> str:
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    chips = "".join(
        f'<button class="example" data-q="{q}">{q}</button>' for q in _EXAMPLES
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AllTheStreet \u00d7 Gemini</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Google+Sans+Text:wght@400;500;700&family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #ffffff; --bg-soft: #f0f4f9; --ink: #1f1f1f; --muted: #5f6368;
    --line: #e3e3e3; --user-bubble: #d3e3fd; --chip: #f0f4f9;
    --g1: #4285f4; --g2: #9b72cb; --g3: #d96570; --warm: #c2410c;
    --sans: "Google Sans Text", "Noto Sans KR", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #1b1c1d; --bg-soft: #282a2c; --ink: #e3e3e3; --muted: #c4c7c5;
      --line: #444746; --user-bubble: #2f3133; --chip: #282a2c; }}
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ height: 100%; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: var(--sans);
    line-height: 1.6; -webkit-font-smoothing: antialiased; }}
  .app {{ max-width: 820px; margin: 0 auto; min-height: 100%; display: flex;
    flex-direction: column; padding: 0 16px; }}
  .top {{ display: flex; align-items: center; gap: 10px; padding: 18px 4px 8px; }}
  .top .logo {{ font-size: 20px; font-weight: 700;
    background: linear-gradient(90deg, var(--g1), var(--g2) 60%, var(--g3));
    -webkit-background-clip: text; background-clip: text; color: transparent; }}
  .top .tag {{ font-size: 12px; color: var(--muted); border: 1px solid var(--line);
    padding: 3px 9px; border-radius: 999px; }}
  .top .langs {{ margin-left: auto; display: flex; gap: 4px; background: var(--bg-soft);
    border: 1px solid var(--line); border-radius: 999px; padding: 3px; }}
  .top .langs button {{ border: 0; background: transparent; color: var(--muted);
    font-family: var(--sans); font-size: 12.5px; padding: 5px 11px; border-radius: 999px;
    cursor: pointer; }}
  .top .langs button.on {{ background: var(--bg); color: var(--ink); font-weight: 700;
    box-shadow: 0 1px 3px rgba(0,0,0,.12); }}
  .thread {{ flex: 1; padding: 16px 4px 140px; }}
  .greet {{ padding: 40px 4px 8px; }}
  .greet h1 {{ font-size: 32px; line-height: 1.25; margin: 0 0 6px; font-weight: 500;
    background: linear-gradient(90deg, var(--g1), var(--g2) 55%, var(--g3));
    -webkit-background-clip: text; background-clip: text; color: transparent;
    display: inline-block; }}
  .greet p {{ color: var(--muted); font-size: 15px; margin: 0; }}
  .examples {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 22px; }}
  .example {{ text-align: left; background: var(--bg-soft); border: 0; color: var(--ink);
    font-family: var(--sans); font-size: 14px; padding: 14px 16px; border-radius: 14px;
    cursor: pointer; max-width: 250px; }}
  .example:hover {{ background: var(--chip); outline: 1px solid var(--line); }}
  .row {{ display: flex; margin: 18px 0; gap: 12px; }}
  .row.user {{ justify-content: flex-end; }}
  .bubble {{ background: var(--user-bubble); padding: 12px 16px; border-radius: 18px;
    max-width: 78%; font-size: 15px; }}
  .avatar {{ width: 28px; height: 28px; flex: 0 0 28px; border-radius: 50%;
    background: conic-gradient(from 180deg, var(--g1), var(--g2), var(--g3), var(--g1));
    display: grid; place-items: center; }}
  .ai {{ flex: 1; min-width: 0; }}
  .toolchip {{ display: inline-flex; align-items: center; gap: 8px; cursor: pointer;
    background: var(--bg-soft); border: 1px solid var(--line); border-radius: 999px;
    padding: 7px 14px; font-size: 13px; color: var(--muted); user-select: none; }}
  .toolchip .spark {{ width: 14px; height: 14px; }}
  .toolchip .caret {{ transition: transform .2s; }}
  .toolchip.open .caret {{ transform: rotate(180deg); }}
  .toollog {{ margin: 10px 0 4px; border-left: 2px solid var(--g2); padding: 4px 0 4px 14px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px;
    color: var(--muted); display: none; }}
  .toollog.show {{ display: block; }}
  .toollog .l {{ padding: 2px 0; }}
  .toollog .t {{ color: var(--g1); }}
  .toollog .a {{ color: var(--g2); }}
  .toollog .c {{ color: var(--warm); }}
  .md {{ font-size: 15.5px; margin-top: 10px; }}
  .md h3 {{ font-size: 17px; margin: 18px 0 6px; font-weight: 700; }}
  .md a {{ color: var(--g1); }}
  .md p {{ margin: 8px 0; }}
  .md ul {{ padding-left: 20px; }}
  .thinking {{ display: inline-flex; align-items: center; gap: 10px; color: var(--muted); font-size: 14px; }}
  .thinking .stage {{ background: linear-gradient(90deg, var(--muted) 25%, var(--ink) 50%, var(--muted) 75%);
    background-size: 200% 100%; -webkit-background-clip: text; background-clip: text;
    color: transparent; animation: shimmer 1.6s linear infinite; }}
  @keyframes shimmer {{ 0% {{ background-position: 200% 0; }} 100% {{ background-position: -200% 0; }} }}
  .cards {{ margin-top: 16px; display: grid; gap: 12px;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }}
  .card {{ background: var(--bg-soft); border: 1px solid var(--line); border-radius: 16px;
    overflow: hidden; display: flex; flex-direction: column; }}
  .card .thumb {{ display: block; aspect-ratio: 16/9; background-size: cover;
    background-position: center; position: relative; }}
  .card .thumb .play {{ position: absolute; inset: 0; margin: auto; width: 46px; height: 46px;
    border-radius: 50%; background: rgba(0,0,0,.55); }}
  .card .thumb .play::after {{ content: ""; position: absolute; top: 50%; left: 54%;
    transform: translate(-50%,-50%); border-style: solid; border-width: 9px 0 9px 15px;
    border-color: transparent transparent transparent #fff; }}
  .card .thumb:hover .play {{ background: rgba(0,0,0,.7); }}
  .card-body {{ padding: 15px; display: flex; flex-direction: column; flex: 1; }}
  .card h4 {{ font-size: 15px; margin: 0 0 4px; }}
  .card .addr {{ color: var(--muted); font-size: 12.5px; margin: 0 0 10px; }}
  .price {{ font-size: 13.5px; margin: 3px 0; }}
  .price .was {{ color: var(--muted); text-decoration: line-through; margin-right: 6px; }}
  .price .now {{ color: var(--warm); font-weight: 700; }}
  .acts {{ margin-top: auto; padding-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; }}
  .btn {{ font-size: 13px; padding: 8px 14px; border-radius: 999px; text-decoration: none;
    border: 1px solid var(--line); color: var(--ink); }}
  .btn.detail {{ border-color: var(--g1); color: var(--g1); }}
  .btn.buy {{ background: var(--warm); color: #fff; border-color: var(--warm); font-weight: 700; }}
  .err {{ color: #c5221f; background: #fce8e6; border-radius: 12px; padding: 12px 16px;
    font-size: 14px; margin-top: 10px; }}
  @media (prefers-color-scheme: dark) {{ .err {{ background: #3c1b1a; color: #f2b8b5; }} }}
  .composer {{ position: fixed; left: 0; right: 0; bottom: 0; }}
  .composer-inner {{ max-width: 820px; margin: 0 auto; padding: 12px 16px 20px;
    background: linear-gradient(to top, var(--bg) 70%, transparent); }}
  .box {{ display: flex; align-items: center; gap: 8px; background: var(--bg-soft);
    border: 1px solid var(--line); border-radius: 999px; padding: 8px 8px 8px 20px; }}
  .box input {{ flex: 1; background: transparent; border: 0; outline: none; color: var(--ink);
    font-family: var(--sans); font-size: 15px; }}
  .box button {{ width: 40px; height: 40px; border-radius: 50%; border: 0; cursor: pointer;
    background: linear-gradient(135deg, var(--g1), var(--g2)); color: #fff; display: grid;
    place-items: center; }}
  .box button:disabled {{ opacity: .45; cursor: default; }}
  .foot {{ text-align: center; color: var(--muted); font-size: 11px; margin-top: 8px; }}
  .foot a {{ color: var(--muted); }}
</style>
</head>
<body>
<div class="app">
  <div class="top">
    <span class="logo">AllTheStreet</span>
    <span class="tag">\u00d7 Gemini \u00b7 MCP Live</span>
    <div class="langs" id="langs">
      <button data-lang="auto" class="on">\uc790\ub3d9</button>
      <button data-lang="ko">\ud55c\uad6d\uc5b4</button>
      <button data-lang="en">EN</button>
      <button data-lang="ja">\u65e5\u672c\u8a9e</button>
    </div>
  </div>
  <div class="thread" id="thread">
    <div class="greet" id="greet">
      <h1>\uc548\ub155\ud558\uc138\uc694</h1>
      <p>\uc5ec\ud589\uc9c0\u00b7\ub9db\uc9d1\u00b7\ud2f0\ucf13\uc744 \ubb3c\uc5b4\ubcf4\uc138\uc694. Gemini\uac00 AllTheStreet \ub370\uc774\ud130\ub97c \uc9c1\uc811 \ucc3e\uc544 \ub2f5\ud569\ub2c8\ub2e4.</p>
      <div class="examples">{chips}</div>
    </div>
  </div>
  <div class="composer">
    <div class="composer-inner">
      <div class="box">
        <input id="q" type="text" placeholder="\uc5ec\uae30\uc5d0 \uc9c8\ubb38\uc744 \uc785\ub825\ud558\uc138\uc694" autocomplete="off"/>
        <button id="go" title="\ubcf4\ub0b4\uae30">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M4 12h14M12 5l7 7-7 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
      </div>
      <div class="foot">model: {settings.GEMINI_MODEL} \u00b7 <a href="{base}/docs">API</a> \u00b7 \ub2f5\ubcc0\uc740 AllTheStreet MCP \ub370\uc774\ud130 \uae30\ubc18</div>
    </div>
  </div>
</div>
<script>
const base = {base!r};
let currentLang = "auto";

// UI labels per language (used for buttons/stage text in the result).
const L = {{
  ko: {{ detail: "상세 보기", buy: "예약·구매", toolUse: "Gemini가 AllTheStreet MCP 사용 · 도구",
    stages: ["질문 분석 중", "AllTheStreet MCP에서 장소 검색 중", "예약 가능한 상품 확인 중", "답변 작성 중"],
    err: "답변을 가져오지 못했습니다: " }},
  en: {{ detail: "View details", buy: "Book now", toolUse: "Gemini queried AllTheStreet MCP · tools",
    stages: ["Analyzing your question", "Searching places via AllTheStreet MCP", "Checking bookable tickets", "Writing the answer"],
    err: "Could not get an answer: " }},
  ja: {{ detail: "詳細を見る", buy: "予約・購入", toolUse: "GeminiがAllTheStreet MCPを使用 · ツール",
    stages: ["質問を分析中", "AllTheStreet MCPで場所を検索中", "予約可能なチケットを確認中", "回答を作成中"],
    err: "回答を取得できませんでした: " }},
}};
function labels(lang) {{ return L[lang] || L.ko; }}
const $ = (id) => document.getElementById(id);
let stageTimer = null;
const SPARK = '<svg class="spark" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z"/></svg>';
const AVATAR = '<div class="avatar"><svg width="16" height="16" viewBox="0 0 24 24" fill="#fff"><path d="M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z"/></svg></div>';
function escapeHtml(s) {{
  return (s||"").replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}
function renderMarkdown(md) {{
  const lines = (md||"").split(/\\r?\\n/);
  let html = "", inList = false;
  const inline = (t) => escapeHtml(t)
    .replace(/\\*\\*(.+?)\\*\\*/g, "<b>$1</b>")
    .replace(/\\[(.+?)\\]\\((https?:\\/\\/[^\\s)]+)\\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  for (let raw of lines) {{
    const line = raw.trim();
    if (!line) {{ if (inList) {{ html += "</ul>"; inList = false; }} continue; }}
    let m;
    if ((m = line.match(/^#{{1,4}}\\s+(.*)/))) {{
      if (inList) {{ html += "</ul>"; inList = false; }} html += "<h3>" + inline(m[1]) + "</h3>";
    }} else if ((m = line.match(/^[\\*\\-]\\s+(.*)/))) {{
      if (!inList) {{ html += "<ul>"; inList = true; }} html += "<li>" + inline(m[1]) + "</li>";
    }} else {{
      if (inList) {{ html += "</ul>"; inList = false; }} html += "<p>" + inline(line) + "</p>";
    }}
  }}
  if (inList) html += "</ul>";
  return html;
}}
function addUserRow(q) {{
  const row = document.createElement("div");
  row.className = "row user";
  row.innerHTML = '<div class="bubble">' + escapeHtml(q) + '</div>';
  $("thread").appendChild(row);
}}
function addAiRow() {{
  const stg = labels(currentLang === "auto" ? "ko" : currentLang).stages;
  const row = document.createElement("div");
  row.className = "row ai-row";
  row.innerHTML = AVATAR + '<div class="ai"><div class="thinking"><span class="stage" id="stage">' + stg[0] + '</span></div></div>';
  $("thread").appendChild(row);
  window.scrollTo(0, document.body.scrollHeight);
  let i = 0;
  stageTimer = setInterval(() => {{ i = (i + 1) % stg.length; const el = $("stage"); if (el) el.textContent = stg[i]; }}, 1100);
  return row;
}}
function toolLogHtml(calls, lang) {{
  if (!calls.length) return "";
  const lab = labels(lang);
  const lines = calls.map(c => {{
    const args = Object.entries(c.args||{{}}).map(([k,v]) =>
      '<span class="a">' + escapeHtml(k) + "=" + escapeHtml(String(v)) + "</span>").join(" ");
    return '<div class="l">\u203a <span class="t">' + escapeHtml(c.name) + "</span> " + args
      + ' <span class="c">\u2192 ' + c.count + "</span></div>";
  }}).join("");
  const id = "tl" + Math.random().toString(36).slice(2, 7);
  return '<div class="toolchip" onclick="this.classList.toggle(\\'open\\');'
    + 'document.getElementById(\\'' + id + '\\').classList.toggle(\\'show\\')">'
    + SPARK + '<span>' + lab.toolUse + ' ' + calls.length + '</span>'
    + '<svg class="caret" width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></div>'
    + '<div class="toollog" id="' + id + '">' + lines + '</div>';
}}
function cardsHtml(spots, lang) {{
  const lab = labels(lang);
  const withContent = (spots||[]).filter(s => s.name);
  if (!withContent.length) return "";
  const cards = withContent.map(s => {{
    // video thumbnail (clicks through to the /p page where the video lives on top)
    let thumbHtml = "";
    const vid = (s.videos||[])[0];
    if (vid && vid.thumbnail) {{
      thumbHtml = '<a class="thumb" href="' + s.page_url + '" target="_blank" rel="noopener" '
        + 'style="background-image:url(\\'' + vid.thumbnail + '\\')" title="'
        + escapeHtml(vid.title||"") + '"><span class="play"></span></a>';
    }}
    let priceHtml = "", buyLink = "";
    for (const p of (s.products||[])) {{
      if (p.out_link && !buyLink) buyLink = p.out_link;
      for (const o of (p.options||[])) {{
        if (o.out_link && !buyLink) buyLink = o.out_link;
        if (o.normal || o.discount) {{
          const was = (o.discount && o.normal && o.discount !== o.normal)
            ? '<span class="was">' + Number(o.normal).toLocaleString() + '\uc6d0</span>' : "";
          const now = '<span class="now">' + Number(o.discount || o.normal).toLocaleString() + '\uc6d0</span>';
          priceHtml += '<div class="price">' + escapeHtml(o.name||"") + " " + was + now + "</div>";
        }}
      }}
    }}
    const detail = '<a class="btn detail" href="' + s.page_url + '" target="_blank" rel="noopener">' + lab.detail + '</a>';
    const buy = buyLink ? '<a class="btn buy" href="' + buyLink + '" target="_blank" rel="noopener">' + lab.buy + '</a>' : "";
    return '<div class="card">' + thumbHtml + '<div class="card-body"><h4>' + escapeHtml(s.name) + '</h4><p class="addr">'
      + escapeHtml(s.address||"") + '</p>' + priceHtml + '<div class="acts">' + detail + buy + '</div></div></div>';
  }}).join("");
  return '<div class="cards">' + cards + '</div>';
}}
async function ask(q) {{
  if (!q) return;
  const greet = $("greet"); if (greet) greet.remove();
  $("q").value = "";
  addUserRow(q);
  const aiRow = addAiRow();
  $("go").disabled = true;
  try {{
    const res = await fetch(base + "/demo/ask", {{
      method: "POST", headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ question: q, lang: currentLang }}),
    }});
    const data = await res.json();
    if (stageTimer) {{ clearInterval(stageTimer); stageTimer = null; }}
    if (!res.ok) throw new Error(data.error || ("\uc624\ub958 " + res.status));
    const rlang = data.lang || (currentLang === "auto" ? "ko" : currentLang);
    aiRow.querySelector(".ai").innerHTML =
      toolLogHtml(data.tool_calls || [], rlang) +
      '<div class="md">' + renderMarkdown(data.answer || "") + '</div>' +
      cardsHtml(data.spots || [], rlang);
  }} catch (e) {{
    if (stageTimer) {{ clearInterval(stageTimer); stageTimer = null; }}
    const lab = labels(currentLang === "auto" ? "ko" : currentLang);
    aiRow.querySelector(".ai").innerHTML = '<div class="err">' + lab.err + escapeHtml(e.message) + '</div>';
  }} finally {{
    $("go").disabled = false;
    window.scrollTo(0, document.body.scrollHeight);
  }}
}}
$("go").addEventListener("click", () => ask($("q").value.trim()));
$("q").addEventListener("keydown", (e) => {{ if (e.key === "Enter") ask($("q").value.trim()); }});
document.querySelectorAll(".example").forEach(c => c.addEventListener("click", () => ask(c.dataset.q)));
document.querySelectorAll("#langs button").forEach(b => b.addEventListener("click", () => {{
  currentLang = b.dataset.lang;
  document.querySelectorAll("#langs button").forEach(x => x.classList.toggle("on", x === b));
}}));
</script>
</body>
</html>"""
