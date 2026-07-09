// Chatwoot Dashboard App — WhatsApp Template Sender
// Serves the picker UI (rendered as a tab inside a Chatwoot conversation) and
// proxies /api/* to the n8n wa_template_picker_api webhooks so the secret n8n
// URLs are never exposed to the browser.
//
// Supports two recipient modes:
//   • current conversation contact (default) — uses appContext
//   • "different / new number" — backend (send_wa_template) resolves-or-creates
//     the contact + conversation in inbox 9, returns conversation_id, and the UI
//     navigates the agent to that thread.
//
// Deploys to Cloudflare Workers.  Deploy:  wrangler deploy

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // CORS preflight (defensive; same-origin in practice)
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: cors() });
    }

    // GET /api/templates -> n8n list webhook
    if (url.pathname === '/api/templates') {
      const r = await fetch(env.N8N_LIST_URL, { method: 'GET' });
      return passthrough(r);
    }

    // POST /api/send -> n8n send webhook
    if (url.pathname === '/api/send' && request.method === 'POST') {
      const body = await request.text();
      const r = await fetch(env.N8N_SEND_URL, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body,
      });
      return passthrough(r);
    }

    // GET /api/agent?id=123 -> { display_name } for the logged-in agent.
    // The Chatwoot dashboard-app context only passes the agent's `name`, not the
    // "display name" (available_name). We resolve it server-side via the Chatwoot
    // Agents API so the admin token never reaches the browser.
    if (url.pathname === '/api/agent') {
      const id = url.searchParams.get('id');
      if (!id || !env.CHATWOOT_API_TOKEN) return json({ display_name: '' });
      const account = url.searchParams.get('account') || env.CHATWOOT_ACCOUNT || '2';
      const base = env.CHATWOOT_BASE || 'https://chat.studygram.me';
      try {
        const r = await fetch(`${base}/api/v1/accounts/${account}/agents`, {
          headers: { api_access_token: env.CHATWOOT_API_TOKEN },
        });
        const list = await r.json();
        const me = Array.isArray(list) ? list.find((a) => String(a.id) === String(id)) : null;
        return json({ display_name: me ? me.available_name || me.name || '' : '' });
      } catch (e) {
        return json({ display_name: '' });
      }
    }

    // Everything else -> the form
    return new Response(HTML, {
      headers: { 'content-type': 'text/html; charset=utf-8', ...cors() },
    });
  },
};

function cors() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'content-type',
  };
}
async function passthrough(r) {
  return new Response(await r.text(), {
    status: r.status,
    headers: { 'content-type': 'application/json', ...cors() },
  });
}
function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'content-type': 'application/json', ...cors() },
  });
}

const HTML = /* html */ `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Send WhatsApp Template</title>
<style>
  /* ---- Theme tokens (defaults = light) ---- */
  :root {
    --bg: #ffffff; --panel: #f4f6fb; --panel-2: #eef1f7;
    --text: #1f2d3d; --muted: #8794a5; --border: #e6e9f0; --border-2: #c7cfdb;
    --input-bg: #ffffff; --accent: #1f93ff; --accent-soft: #9cc7f0;
    --ok-bg: #e7f7ee; --ok: #1b7a43; --err-bg: #fbe9ec; --err: #b3243b;
    --toggle-bg: #d7dce6; --shadow: 0 1px 2px rgba(16,24,40,.06);
  }
  :root[data-theme="dark"] {
    --bg: #16181e; --panel: #1e2129; --panel-2: #262a33;
    --text: #e6e8ee; --muted: #9aa1ad; --border: #2c303a; --border-2: #3a3f4b;
    --input-bg: #20242d; --accent: #1f93ff; --accent-soft: #2f6ea3;
    --ok-bg: #15241b; --ok: #5fd08a; --err-bg: #2a171b; --err: #ff8d9c;
    --toggle-bg: #3a3f4b; --shadow: 0 1px 2px rgba(0,0,0,.4);
  }
  :root { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; }
  body { margin: 0; padding: 12px; color: var(--text); background: var(--bg); font-size: 14px; }
  h1 { font-size: 14px; margin: 0 0 10px; }
  .ctx { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; font-size: 12.5px; line-height: 1.5; box-shadow: var(--shadow); }
  .ctx b { color: var(--text); }
  .warn { color: var(--err); }
  .row { display: flex; align-items: center; gap: 8px; margin: 8px 0 4px; font-size: 12.5px; font-weight: 600; cursor: pointer; user-select: none; }
  /* toggle switch */
  .switch { position: relative; width: 34px; height: 18px; flex: 0 0 auto; }
  .switch input { display: none; }
  .slider { position: absolute; inset: 0; background: var(--toggle-bg); border-radius: 18px; transition: .2s; }
  .slider:before { content: ""; position: absolute; width: 14px; height: 14px; left: 2px; top: 2px; background: #fff; border-radius: 50%; transition: .2s; box-shadow: 0 1px 2px rgba(0,0,0,.3); }
  .switch input:checked + .slider { background: var(--accent); }
  .switch input:checked + .slider:before { transform: translateX(16px); }
  #newFields { overflow: hidden; }
  #newFields.hidden { display: none; }
  label.fld { display: block; font-weight: 600; margin: 10px 0 4px; font-size: 12.5px; }
  select, input, textarea { width: 100%; box-sizing: border-box; padding: 8px; border: 1px solid var(--border-2); border-radius: 6px; font: inherit; background: var(--input-bg); color: var(--text); }
  select:focus, input:focus, textarea:focus { outline: 2px solid var(--accent-soft); outline-offset: 0; border-color: var(--accent); }
  textarea { min-height: 90px; resize: vertical; }
  .count { font-size: 11px; color: var(--muted); text-align: right; margin-top: 2px; }
  .count.over { color: var(--err); font-weight: 600; }
  button { margin-top: 16px; width: 100%; padding: 10px; border: 0; border-radius: 6px; background: var(--accent); color: #fff; font-weight: 600; font-size: 14px; cursor: pointer; }
  button:disabled { background: var(--accent-soft); cursor: not-allowed; }
  button.secondary { background: var(--panel-2); color: var(--text); border: 1px solid var(--border-2); margin-top: 8px; }
  .msg { margin-top: 12px; padding: 9px 11px; border-radius: 6px; font-size: 12.5px; display: none; box-shadow: var(--shadow); }
  .msg.ok { background: var(--ok-bg); color: var(--ok); display: block; }
  .msg.err { background: var(--err-bg); color: var(--err); display: block; white-space: pre-wrap; }
  .hint { font-size: 11px; color: var(--muted); margin-top: 2px; font-weight: 400; }
  /* live template preview */
  .preview { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; font-size: 13px; line-height: 1.55; word-break: break-word; box-shadow: var(--shadow); }
  .preview .ph { border-radius: 3px; padding: 0 3px; }
  .preview .ph.filled { background: var(--ok-bg); color: var(--ok); }
  .preview .ph.empty { background: var(--err-bg); color: var(--err); font-style: italic; }
</style>
</head>
<body>
  <h1>Send WhatsApp Template</h1>

  <div class="ctx" id="ctx">Loading conversation context…</div>

  <label class="row">
    <span class="switch"><input type="checkbox" id="newContact"><span class="slider"></span></span>
    Send to a different / new number
  </label>
  <div id="newFields" class="hidden">
    <label class="fld">Name <span class="hint">(used for the contact + template {{recipient_name}})</span></label>
    <input id="newName" type="text" placeholder="Recipient name" autocomplete="off">
    <label class="fld">Phone <span class="hint">(with country code, e.g. +965…)</span></label>
    <input id="newPhone" type="tel" placeholder="+965xxxxxxxx" autocomplete="off">
  </div>

  <label class="fld">Template</label>
  <select id="tpl"><option value="">Loading templates…</option></select>

  <div id="params"></div>

  <div id="previewWrap" style="display:none">
    <label class="fld">Live preview <span class="hint">(fixed template text + your input; <span style="color:var(--err)">red</span> = not yet filled — don't retype these parts in your message)</span></label>
    <div class="preview" id="preview"></div>
  </div>

  <button id="send" disabled>Send template</button>
  <button id="openConv" class="secondary" style="display:none">Open conversation →</button>
  <div class="msg" id="msg"></div>

<script>
var CTX = { conversation_id: '', phone: '', name: '', agent: '', agentId: '' };
var TEMPLATES = [];
var NEW_MODE = false;
var SENDER_TOUCHED = false;            // set once the agent manually edits sender_name
var AGENT_RESOLVED = false;            // true once the display name is resolved via the API
var SENDER_FALLBACK = 'Kareem (Customer Support)';
var CW_ACCOUNT = 2;
var CHATWOOT_BASE = 'https://chat.studygram.me';
var LAST_CONV_ID = null;

function firstName(n){ return String(n||'').trim().split(/\\s+/)[0] || ''; }
function el(id){ return document.getElementById(id); }
function escapeHtml(s){ return String(s).replace(/[&<>]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; }); }
// WhatsApp template body params reject newlines, tabs, 4+ consecutive spaces.
function badWhitespace(s){ return /[\\n\\t]/.test(s) || /\\s{4,}/.test(s); }

// ---------- Theme: match Chatwoot dark/light ----------
function applyTheme(mode){
  document.documentElement.setAttribute('data-theme', mode === 'dark' ? 'dark' : 'light');
}
function osDark(){ try { return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches; } catch(e){ return false; } }
var __cwThemeSeen = false;
applyTheme(osDark() ? 'dark' : 'light'); // immediate best-guess; appContext overrides if available
try {
  var mq = window.matchMedia('(prefers-color-scheme: dark)');
  var mqHandler = function(e){ if (!__cwThemeSeen) applyTheme(e.matches ? 'dark' : 'light'); };
  if (mq.addEventListener) mq.addEventListener('change', mqHandler);
  else if (mq.addListener) mq.addListener(mqHandler);
} catch(e){}

// ---------- Chatwoot context ----------
window.addEventListener('message', function(e){
  var d = e.data;
  try { if (typeof d === 'string') d = JSON.parse(d); } catch(_){ return; }
  if (!d || d.event !== 'appContext') return;
  var data = d.data || {};
  // Chatwoot recent versions pass a theme string; honor it over the OS guess.
  if (data.theme) { __cwThemeSeen = true; applyTheme(data.theme); }
  else if (typeof data.darkMode !== 'undefined') { __cwThemeSeen = true; applyTheme(data.darkMode ? 'dark' : 'light'); }
  var conv = data.conversation || {};
  var contact = data.contact || (conv.meta && conv.meta.sender) || {};
  CTX.conversation_id = conv.id || conv.display_id || '';
  CTX.phone = contact.phone_number || '';
  CTX.name = contact.name || '';
  // logged-in agent -> sender_name. The dashboard-app context usually only carries
  // the agent name (e.g. "Mohamad Yassine"), NOT the display name. Use what's here as
  // an instant best-guess, then resolve the real display name via /api/agent below.
  var agent = data.currentAgent || data.agent || {};
  CTX.agentId = agent.id || CTX.agentId || '';
  CTX.agent = agent.display_name || agent.available_name || agent.name || CTX.agent || '';
  // account id from context if present (else default 2)
  if (data.account && data.account.id) CW_ACCOUNT = data.account.id;
  renderCtx();
  prefill();
  resolveAgentName();
});

// Resolve the agent's Chatwoot "display name" (available_name) via the Worker,
// which calls the Chatwoot Agents API server-side. Runs once.
function resolveAgentName(){
  if (AGENT_RESOLVED || !CTX.agentId) return;
  fetch('/api/agent?id=' + encodeURIComponent(CTX.agentId) + '&account=' + encodeURIComponent(CW_ACCOUNT))
    .then(function(r){ return r.json(); })
    .then(function(j){
      if (j && j.display_name) { AGENT_RESOLVED = true; CTX.agent = j.display_name; syncSenderName(); }
    })
    .catch(function(){});
}
function requestCtx(){ try { window.parent.postMessage('chatwoot-dashboard-app:fetch-info','*'); } catch(_){} }

function renderCtx(){
  var box = el('ctx');
  if (NEW_MODE) {
    var n = el('newName').value.trim(), p = el('newPhone').value.trim();
    box.innerHTML = '<b>New contact</b><br>'
      + (n ? 'Name: ' + n + '<br>' : '<span class="hint">Name (optional)</span><br>')
      + (p ? 'Phone: ' + p : '<span class="warn">Enter a phone number below.</span>');
  } else {
    box.innerHTML = CTX.phone
      ? '<b>To:</b> ' + (CTX.name||'(no name)') + ' &lt;' + CTX.phone + '&gt;<br><b>Conversation:</b> #' + CTX.conversation_id
      : '<span class="warn">No contact context yet. Open this from inside a conversation, or toggle “new number”.</span>';
  }
  validate();
}

function setNewMode(on){
  NEW_MODE = on;
  el('newFields').classList.toggle('hidden', !on);
  // prefill recipient_name param from the right source when switching
  syncRecipientName();
  renderCtx();
}

function syncRecipientName(){
  var rn = el('p_recipient_name');
  if (!rn) return;
  var want = NEW_MODE ? firstName(el('newName').value) : firstName(CTX.name);
  if (want) rn.value = want;
  renderPreview();
}

// sender_name auto-maps to the logged-in agent's display name; respect manual edits.
function syncSenderName(){
  var sn = el('p_sender_name');
  if (!sn || SENDER_TOUCHED) return;
  sn.value = CTX.agent || SENDER_FALLBACK;
  renderPreview();
}

// Live preview: render body_preview with the typed param values substituted in,
// unfilled placeholders highlighted, so the agent doesn't re-type the fixed text.
function renderPreview(){
  var t = currentTpl();
  var wrap = el('previewWrap'), box = el('preview');
  if (!t || !t.body_preview) { wrap.style.display = 'none'; box.innerHTML = ''; return; }
  wrap.style.display = 'block';
  var p = collectParams();
  // body_preview stores newlines as literal "\\n"; normalize to real line breaks.
  var text = String(t.body_preview).replace(/\\\\r\\\\n|\\\\n|\\\\r/g, '\\n');
  var html = escapeHtml(text);
  (t.variables||[]).forEach(function(v){
    var val = String(p[v.name] || '').trim();
    var rep = val
      ? '<span class="ph filled">' + escapeHtml(val) + '</span>'
      : '<span class="ph empty">' + escapeHtml(v.name) + '</span>';
    html = html.split('{{' + v.name + '}}').join(rep);
  });
  box.innerHTML = html.replace(/\\n/g, '<br>');
}

// ---------- templates ----------
fetch('/api/templates').then(function(r){ return r.json(); }).then(function(j){
  TEMPLATES = (j && j.templates) || [];
  var sel = el('tpl');
  sel.innerHTML = '<option value="">— choose a template —</option>';
  TEMPLATES.forEach(function(t, i){
    var o = document.createElement('option'); o.value = String(i); o.textContent = t.label; sel.appendChild(o);
  });
}).catch(function(){ el('tpl').innerHTML = '<option value="">Failed to load templates</option>'; });

el('tpl').addEventListener('change', function(){ renderParams(); });

function currentTpl(){ var v = el('tpl').value; return v === '' ? null : TEMPLATES[Number(v)]; }

function renderParams(){
  var t = currentTpl(); var box = el('params'); box.innerHTML = '';
  if (!t) { validate(); return; }
  (t.variables||[]).forEach(function(v){
    var wrap = document.createElement('div');
    var lab = document.createElement('label'); lab.className = 'fld';
    lab.textContent = v.name + ' ';
    var hint = document.createElement('span'); hint.className='hint'; hint.textContent='(' + (v.component||'body') + ')';
    lab.appendChild(hint);
    wrap.appendChild(lab);
    var isLong = v.name === 'message_content';
    var inp = document.createElement(isLong ? 'textarea' : 'input');
    inp.id = 'p_' + v.name; inp.dataset.var = v.name;
    if (v.name === 'sender_name') {
      inp.value = CTX.agent || SENDER_FALLBACK;
      inp.addEventListener('input', function(){ SENDER_TOUCHED = true; });
    }
    if (v.name === 'recipient_name') inp.value = firstName(NEW_MODE ? el('newName').value : CTX.name);
    inp.addEventListener('input', validate);
    wrap.appendChild(inp);
    if (isLong) {
      var c = document.createElement('div'); c.className='count'; c.id='count'; wrap.appendChild(c);
    }
    box.appendChild(wrap);
  });
  validate();
}

function prefill(){
  syncRecipientName();
  syncSenderName();
}

function collectParams(){
  var t = currentTpl(); if (!t) return {};
  var p = {};
  (t.variables||[]).forEach(function(v){ var i = el('p_'+v.name); p[v.name] = i ? i.value : ''; });
  return p;
}

function newPhoneDigits(){ return String(el('newPhone').value||'').replace(/[^0-9]/g,''); }

function validate(){
  var t = currentTpl();
  var ok = !!t && (NEW_MODE ? newPhoneDigits().length >= 7 : !!CTX.phone);
  var problems = [];
  if (t) {
    var p = collectParams();
    (t.variables||[]).forEach(function(v){
      var val = p[v.name] || '';
      if (!val.trim()) { ok = false; }
      if (badWhitespace(val)) { ok = false; problems.push(v.name + ': remove line breaks / tabs'); }
    });
    var mc = el('p_message_content'), cnt = el('count');
    if (mc && cnt) {
      var len = mc.value.length;
      cnt.textContent = len + ' chars';
      cnt.className = 'count' + (len > 900 ? ' over' : '');
    }
  }
  el('send').disabled = !ok;
  if (problems.length) showMsg('err', problems.join('\\n')); else if (!el('msg').classList.contains('ok')) hideMsg();
  renderPreview();
}

function showMsg(kind, text){ var m = el('msg'); m.className = 'msg ' + kind; m.textContent = text; }
function hideMsg(){ var m = el('msg'); m.className = 'msg'; m.textContent=''; }

// ---------- navigation to the (newly created / existing) thread ----------
function convUrl(id){ return CHATWOOT_BASE + '/app/accounts/' + CW_ACCOUNT + '/conversations/' + id; }
// Try to navigate the Chatwoot parent in-tab (works if the iframe allows top-navigation).
function navTop(url){ try { window.top.location.replace(url); return true; } catch(e){ return false; } }
function openConv(id){
  var url = convUrl(id);
  if (!navTop(url)) { try { window.open(url, '_blank'); } catch(e){} }
}

el('send').addEventListener('click', function(){
  var t = currentTpl(); if (!t) return;
  el('send').disabled = true; showMsg('ok','Sending…');
  var body = {
    conversation_id: NEW_MODE ? '' : CTX.conversation_id,
    recipient_phone: NEW_MODE ? el('newPhone').value.trim() : CTX.phone,
    recipient_name: NEW_MODE ? (el('newName').value.trim()) : (CTX.name || ''),
    sender_name: (el('p_sender_name')||{}).value || '',
    template_name: t.template_name,
    language: t.language,
    params: collectParams()
  };
  fetch('/api/send', {
    method: 'POST', headers: {'content-type':'application/json'},
    body: JSON.stringify(body)
  }).then(function(r){ return r.json(); }).then(function(res){
    if (res && res.success) {
      var id = res.conversation_id || (NEW_MODE ? null : CTX.conversation_id) || null;
      LAST_CONV_ID = id;
      showMsg('ok','Template sent ✓ (wamid ' + String(res.wamid||'').slice(-8) + ')' + (id ? ' · conversation #' + id : ''));
      var mc = el('p_message_content'); if (mc) mc.value='';
      // For new contacts: land the agent on the created/existing thread.
      if (NEW_MODE && id) {
        el('openConv').style.display = 'block';
        el('openConv').onclick = function(){ openConv(id); };
        // Auto-navigate in-tab if the iframe allows it; else the button above is the one-click path.
        navTop(convUrl(id));
      }
      validate();
    } else {
      showMsg('err','Send failed: ' + ((res && res.error) || 'unknown error'));
      el('send').disabled = false;
    }
  }).catch(function(e){ showMsg('err','Network error: ' + e); el('send').disabled = false; });
});

// ---------- wiring ----------
el('newContact').addEventListener('change', function(){ setNewMode(this.checked); });
el('newName').addEventListener('input', function(){ if (NEW_MODE) { syncRecipientName(); renderCtx(); } });
el('newPhone').addEventListener('input', function(){ if (NEW_MODE) { renderCtx(); } });

requestCtx();
// Robustness: re-request context if the first post raced Chatwoot's listener (fixes the
// "stuck on Loading…" until reload symptom). Tab/panel *missing* entirely is a Chatwoot
// SPA mount issue only a full reload fixes.
var __tries = 0;
var __poll = setInterval(function(){
  if (CTX.phone || __tries++ > 12) { clearInterval(__poll); return; }
  requestCtx();
}, 1000);
document.addEventListener('visibilitychange', function(){ if (document.visibilityState === 'visible' && !CTX.phone) requestCtx(); });
</script>
</body>
</html>`;
