/* ============================================================
   AgriVision Pro — auth.js  v2.0
   Refresh token automatique + design system complet
   ============================================================ */

const PROD_API_BASE = window.AGRIVISION_API_BASE || 'https://agrivision-api-production.up.railway.app';
const LOCAL_API_BASE = 'http://127.0.0.1:8010';
const API_BASE = (
  window.CG_API_BASE ||
  (['localhost', '127.0.0.1'].includes(window.location.hostname) ? LOCAL_API_BASE : PROD_API_BASE)
);
window.API_BASE = API_BASE;

/* ── Inject shared fonts + design system ───────────────────── */
(function injectDesignSystem() {
  if (document.getElementById('avp-styles')) return;
  const head = document.head;
  const addLink = (attrs) => {
    const l = document.createElement('link');
    Object.entries(attrs).forEach(([k, v]) => { l[k] = v; });
    head.appendChild(l);
    return l;
  };

  // Preconnect aux serveurs Google Fonts → les polices arrivent plus vite (moins de "flash").
  if (!head.querySelector('link[rel="preconnect"][href*="fonts.gstatic"]')) {
    addLink({ rel: 'preconnect', href: 'https://fonts.googleapis.com' });
    addLink({ rel: 'preconnect', href: 'https://fonts.gstatic.com', crossOrigin: 'anonymous' });
  }
  // Polices de texte — sautées si déjà déclarées en statique dans le <head> de la page.
  if (!head.querySelector('link[href*="fonts.googleapis.com/css2"][href*="Fraunces"]')) {
    addLink({ rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,700&family=DM+Sans:wght@400;500;600&display=swap' });
  }
  // Icônes (Material Symbols) en display=block → plus de nom d'icône qui clignote en texte.
  if (!head.querySelector('link[href*="Material+Symbols+Outlined"]')) {
    addLink({ rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=block' });
  }

  // Anti-flash des ligatures d'icônes : tant que la police Material Symbols n'est
  // pas chargée (et sa classe appliquée), le navigateur afficherait le TEXTE de
  // la ligature ("person_add", "dashboard"…). On masque les icônes jusqu'à ce que
  // la police soit prête, puis on révèle. Filet de sécurité : révélation forcée
  // après 3 s pour ne jamais rester masqué (police bloquée / hors ligne).
  const markFontsReady = () => document.documentElement.classList.add('avp-fonts-ready');
  try {
    if (document.fonts && document.fonts.load) {
      Promise.race([
        document.fonts.load('24px "Material Symbols Outlined"').then(() => document.fonts.ready),
        new Promise((r) => setTimeout(r, 3000)),
      ]).then(markFontsReady).catch(markFontsReady);
    } else {
      markFontsReady();
    }
  } catch (e) {
    markFontsReady();
  }

  // Anti-flash du SHELL : la page reste invisible (opacity 0, appliquée avant le
  // 1er rendu via #avp-styles) jusqu'à ce que le DOM soit construit (sidebar
  // comprise) ET les polices prêtes — puis on révèle d'un bloc, comme le montage
  // d'un framework, au lieu du "pas net puis stabilise". Filet de sécurité :
  // révélation forcée sous 1,2 s (jamais de page blanche si un chargement traîne).
  (function revealAppShell() {
    let done = false;
    const reveal = () => {
      if (done) return;
      done = true;
      document.documentElement.classList.add('avp-ready');
    };
    setTimeout(reveal, 1200); // garde-fou absolu
    const whenDom = (cb) => (document.readyState === 'loading'
      ? document.addEventListener('DOMContentLoaded', cb, { once: true })
      : cb());
    const fontsReady = (document.fonts && document.fonts.ready)
      ? document.fonts.ready : Promise.resolve();
    whenDom(() => {
      Promise.race([fontsReady, new Promise((r) => setTimeout(r, 800))])
        .then(() => requestAnimationFrame(reveal))
        .catch(reveal);
    });
  })();

  const style = document.createElement('style');
  style.id = 'avp-styles';
  style.textContent = `
    :root{
      --sb:#0c2018;--sb-hover:rgba(82,183,136,.1);--sb-active:rgba(82,183,136,.16);
      --sb-text:rgba(255,255,255,.55);--sb-text-on:rgba(255,255,255,.85);--sb-text-active:#fff;
      --sb-accent:#52b788;--sb-border:rgba(255,255,255,.07);
      --bg:#f8f4ee;--surface:#fff;--surface-warm:#fdf9f5;
      --border:#e6ddd0;--border-l:#f0ead8;
      --text:#1a2218;--muted:#6a7d64;--faint:#a0b09a;
      --primary:#1a4231;--primary-dark:#0c2018;--accent:#52b788;
      --low:#1a6b3a;--low-bg:#eafaf1;--low-b:#a8d8bb;
      --med:#9a6200;--med-bg:#fef8ec;--med-b:#f0c97a;
      --high:#922b21;--high-bg:#fdedec;--high-b:#f1948a;
      --r:10px;--rl:16px;
      --sh:0 1px 3px rgba(0,0,0,.04),0 4px 12px rgba(26,42,24,.07);
      --sh-md:0 6px 28px rgba(26,42,24,.13);
    }
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    html,body{font-size:16px}
    /* Anti-flash icones : masque les ligatures Material Symbols jusqu'au chargement
       de la police d'icones (voir markFontsReady dans auth.js). visibility (et non
       display) => aucun decalage de mise en page pendant le chargement. */
    .material-symbols-outlined{visibility:hidden}
    html.avp-fonts-ready .material-symbols-outlined{visibility:visible}
    /* ── Anti-flash du shell (voir revealAppShell dans auth.js) ──────────────
       Pendant le chargement (avant "avp-ready"), on montre un SKELETON shimmer
       (barres sans texte ni icones -> insensible aux polices, jamais de "pas
       net") : sidebar en placeholder + contenu masque. Une fois le DOM construit
       ET les polices pretes, la vraie UI apparait en fondu. Filet : <= 1,2 s. */
    @keyframes avp-pulse{0%,100%{opacity:.45}50%{opacity:.85}}
    /* Contenu principal : masque puis fondu */
    html:not(.avp-ready) .avp-main{opacity:0}
    html.avp-ready .avp-main{opacity:1;transition:opacity .22s ease}
    /* Sidebar : on masque les vrais elements et on affiche des barres shimmer */
    html:not(.avp-ready) #sidebar > *{opacity:0}
    html.avp-ready #sidebar > *{opacity:1;transition:opacity .22s ease}
    html:not(.avp-ready) #sidebar::after{
      content:'';position:absolute;left:16px;right:16px;top:70px;height:320px;
      border-radius:8px;
      background:repeating-linear-gradient(to bottom,
        rgba(255,255,255,.08) 0,rgba(255,255,255,.08) 13px,
        transparent 13px,transparent 40px);
      animation:avp-pulse 1.2s ease-in-out infinite;
    }
    @media (prefers-reduced-motion: reduce){
      html.avp-ready .avp-main,html.avp-ready #sidebar > *{transition:none}
      html:not(.avp-ready) #sidebar::after{animation:none}
    }
    body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
    a{text-decoration:none;color:inherit}
    button{font-family:'DM Sans',sans-serif}
    input,select,textarea{font-family:'DM Sans',sans-serif}
    .avp-layout{display:flex;min-height:100vh}
    #sidebar{width:240px;background:var(--sb);display:flex;flex-direction:column;flex-shrink:0;position:sticky;top:0;height:100vh;overflow-y:auto}
    .avp-main{flex:1;min-width:0;display:flex;flex-direction:column;overflow-y:auto;height:100vh}
    .avp-content{flex:1;padding:28px 32px}
    .sb-logo{padding:22px 16px 18px;border-bottom:1px solid var(--sb-border);flex-shrink:0}
    .sb-logo-row{display:flex;align-items:center;gap:10px}
    .sb-logo-icon{width:38px;height:38px;background:rgba(82,183,136,.15);border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
    .sb-logo-icon svg{width:20px;height:20px}
    .sb-logo-name{font-family:'Fraunces',serif;font-size:17px;font-weight:700;color:#fff;letter-spacing:-.3px;line-height:1.15}
    .sb-logo-sub{font-size:10.5px;color:var(--sb-text);margin-top:2px}
    .sb-nav{flex:1;padding:12px 10px}
    .sb-sec{font-size:9.5px;font-weight:600;color:rgba(255,255,255,.25);text-transform:uppercase;letter-spacing:.1em;padding:10px 10px 4px;margin-top:4px}
    .nav-link{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:8px;color:var(--sb-text);font-size:13.5px;font-weight:500;transition:.15s;margin-bottom:2px;cursor:pointer}
    .nav-link:hover{background:var(--sb-hover);color:var(--sb-text-on)}
    .nav-link.active{background:var(--sb-active);color:var(--sb-text-active)}
    .nav-link .ms{font-size:19px;flex-shrink:0}
    .nav-link.active .ms{color:var(--sb-accent)}
    .nav-link.locked{opacity:.45}
    .nav-link.locked::after{content:'🔒';margin-left:auto;font-size:11px;opacity:.85}
    .sb-user{padding:14px 14px 18px;border-top:1px solid var(--sb-border);flex-shrink:0}
    .sb-user-inner{display:flex;align-items:center;gap:10px}
    .sb-auth-actions{display:grid;gap:8px}
    .sb-auth-link{display:flex;align-items:center;justify-content:center;gap:8px;padding:9px 10px;border-radius:8px;font-size:13px;font-weight:600;transition:.15s}
    .sb-auth-link.primary{background:rgba(82,183,136,.18);color:#fff;border:1px solid rgba(82,183,136,.35)}
    .sb-auth-link.primary:hover{background:rgba(82,183,136,.26)}
    .sb-auth-link.secondary{color:var(--sb-text-on);border:1px solid var(--sb-border)}
    .sb-auth-link.secondary:hover{background:var(--sb-hover);color:#fff}
    .sb-avatar{width:34px;height:34px;border-radius:50%;background:rgba(82,183,136,.2);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600;color:var(--sb-accent);flex-shrink:0;text-transform:uppercase;letter-spacing:.05em}
    .sb-user-info{flex:1;min-width:0}
    .sb-user-email{font-size:12px;font-weight:500;color:rgba(255,255,255,.85);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .sb-user-role{font-size:10.5px;color:var(--sb-text);text-transform:capitalize;margin-top:1px}
    .sb-logout{background:none;border:none;cursor:pointer;color:var(--sb-text);padding:5px;border-radius:6px;transition:.15s;display:flex;align-items:center}
    .sb-logout:hover{color:#f87171;background:rgba(248,113,113,.1)}
    .avp-header{padding:22px 32px 18px;background:var(--surface);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-shrink:0;gap:16px}
    .page-title{font-family:'Fraunces',serif;font-size:22px;font-weight:700;letter-spacing:-.3px}
    .page-sub{font-size:13px;color:var(--muted);margin-top:2px}
    .card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:20px;box-shadow:var(--sh)}
    .stats-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(175px,1fr));gap:16px;margin-bottom:28px}
    .stat-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:20px;box-shadow:var(--sh);position:relative;overflow:hidden}
    .stat-val{font-family:'Fraunces',serif;font-size:36px;font-weight:700;line-height:1}
    .stat-lbl{font-size:11.5px;color:var(--muted);font-weight:500;margin-top:6px;text-transform:uppercase;letter-spacing:.05em}
    .badge{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:99px;font-size:11.5px;font-weight:600;border:1px solid;white-space:nowrap}
    .badge::before{content:'';width:6px;height:6px;border-radius:50%;flex-shrink:0}
    .badge-low{background:var(--low-bg);color:var(--low);border-color:var(--low-b)}.badge-low::before{background:var(--low)}
    .badge-med{background:var(--med-bg);color:var(--med);border-color:var(--med-b)}.badge-med::before{background:var(--med)}
    .badge-high{background:var(--high-bg);color:var(--high);border-color:var(--high-b)}.badge-high::before{background:var(--high)}
    .btn{display:inline-flex;align-items:center;gap:6px;padding:9px 18px;border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;transition:.15s;border:none;font-family:'DM Sans',sans-serif;line-height:1}
    .btn-primary{background:var(--primary);color:#fff}.btn-primary:hover{background:var(--primary-dark)}
    .btn-outline{background:transparent;color:var(--text);border:1px solid var(--border)}.btn-outline:hover{background:var(--bg)}
    .btn-ghost{background:transparent;color:var(--muted);border:none}.btn-ghost:hover{color:var(--text);background:var(--bg)}
    .btn-sm{padding:6px 12px;font-size:12.5px}
    .btn-icon{width:34px;height:34px;padding:0;justify-content:center}
    .btn:disabled{opacity:.5;cursor:not-allowed}
    .table-wrap{overflow:auto;border-radius:var(--r);border:1px solid var(--border);box-shadow:var(--sh)}
    table{width:100%;border-collapse:collapse;background:var(--surface)}
    thead{background:var(--surface-warm)}
    th{padding:11px 16px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);border-bottom:1px solid var(--border);white-space:nowrap}
    td{padding:13px 16px;font-size:13.5px;border-bottom:1px solid var(--border-l)}
    tr:last-child td{border-bottom:none}
    tbody tr{transition:.1s}
    tbody tr:hover{background:#fdf9f3}
    .form-group{margin-bottom:16px}
    .form-label{display:block;font-size:13px;font-weight:500;color:var(--muted);margin-bottom:6px}
    .form-input{width:100%;padding:10px 14px;border:1.5px solid var(--border);border-radius:8px;font-size:14px;color:var(--text);background:var(--surface);transition:.15s;outline:none}
    .form-input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(82,183,136,.14)}
    .form-row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
    .modal-overlay{position:fixed;inset:0;background:rgba(12,32,24,.55);display:flex;align-items:center;justify-content:center;z-index:900;padding:20px;display:none}
    .modal-overlay.active{display:flex}
    .modal{background:var(--surface);border-radius:var(--rl);padding:28px;width:100%;max-width:520px;box-shadow:var(--sh-md);animation:modalIn .2s ease}
    @keyframes modalIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
    .modal-title{font-family:'Fraunces',serif;font-size:20px;font-weight:700;margin-bottom:20px}
    .modal-footer{display:flex;justify-content:flex-end;gap:10px;margin-top:22px;padding-top:16px;border-top:1px solid var(--border)}
    .score-bar-wrap{background:var(--border-l);border-radius:99px;height:7px;overflow:hidden}
    .score-bar{height:100%;border-radius:99px;transition:.4s}
    .spinner{width:18px;height:18px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;display:inline-block}
    @keyframes spin{to{transform:rotate(360deg)}}
    #avp-toast{position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none}
    .toast{padding:12px 18px;border-radius:10px;font-size:13.5px;font-weight:500;box-shadow:var(--sh-md);animation:toastIn .25s ease;pointer-events:auto;max-width:340px}
    .toast-success{background:#1a4231;color:#fff}
    .toast-error{background:#922b21;color:#fff}
    .toast-info{background:#1e4a6e;color:#fff}
    @keyframes toastIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
    .upload-zone{border:2px dashed var(--border);border-radius:var(--r);padding:40px 20px;text-align:center;cursor:pointer;transition:.2s;background:var(--surface-warm)}
    .upload-zone:hover,.upload-zone.over{border-color:var(--accent);background:#f0faf5}
    .flex{display:flex}.items-center{align-items:center}.justify-between{justify-content:space-between}
    .gap-2{gap:8px}.gap-3{gap:12px}.gap-4{gap:16px}
    .mt-1{margin-top:4px}.mt-2{margin-top:8px}.mt-3{margin-top:12px}.mt-4{margin-top:16px}
    .mb-3{margin-bottom:12px}.mb-4{margin-bottom:16px}
    .font-display{font-family:'Fraunces',serif}
    .text-muted{color:var(--muted)}.text-sm{font-size:13px}.text-xs{font-size:11.5px}
    .fw-600{font-weight:600}.fw-500{font-weight:500}
    .empty-state{text-align:center;padding:60px 20px;color:var(--muted)}
    .empty-icon{font-size:48px;opacity:.2;margin-bottom:12px}
    .section-title{font-family:'Fraunces',serif;font-size:17px;font-weight:700;margin-bottom:16px}
    .divider{height:1px;background:var(--border);margin:20px 0}
    .truncate{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px}

    .sb-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:998}
    .sb-overlay.open{display:block}
    .hamburger{display:none;position:fixed;top:14px;left:14px;z-index:1001;
      width:40px;height:40px;border-radius:10px;border:none;cursor:pointer;
      background:var(--sb);color:#fff;align-items:center;justify-content:center;
      box-shadow:0 2px 8px rgba(0,0,0,.25)}
    .hamburger .ms{font-size:22px;color:#fff}

    @media(max-width:768px){
      .hamburger{display:flex!important}
      #sidebar{
        position:fixed!important;top:0!important;left:0!important;
        height:100vh!important;z-index:999!important;width:260px!important;
        transform:translateX(-100%)!important;
        transition:transform .25s ease!important;
        flex-shrink:0!important}
      #sidebar.open{transform:translateX(0)!important}
      .avp-layout{display:block!important}
      .avp-main{
        width:100%!important;max-width:100vw!important;
        height:100vh!important;overflow-y:auto!important;
        margin-left:0!important}
      .avp-header{
        padding:14px 16px 12px 64px!important;
        flex-wrap:wrap!important;gap:10px!important}
      .page-title{font-size:18px!important}
      .avp-content{padding:14px 12px!important}
      .table-wrap{overflow-x:auto!important;-webkit-overflow-scrolling:touch}
      table{min-width:480px!important}
      .content-grid,.analytics-grid,.diag-layout,.detail-grid,
      .grid-2,.form-row,.form-row2,.form-row3{
        display:grid!important;grid-template-columns:1fr!important}
      .stats-row,.kpi-row{
        display:grid!important;grid-template-columns:1fr 1fr!important}
      .quick-actions{
        display:grid!important;grid-template-columns:1fr 1fr!important}
      .result-panel{position:static!important;top:auto!important}
      .map-layout{flex-direction:column!important}
      .map-panel{
        width:100%!important;max-height:260px!important;
        border-right:none!important;
        border-bottom:1px solid var(--border)!important}
      #map{height:300px!important;width:100%!important}
      .map-container{min-height:300px!important}
      .btn{padding:8px 12px!important;font-size:12.5px!important}
      input[type=range]{height:6px!important}
      .stat-cards{grid-template-columns:1fr!important}
      .hide-mobile{display:none!important}
      #avp-toast{left:8px!important;right:8px!important;bottom:8px!important}
      .toast{max-width:100%!important}
      /* ── Agroforesterie ── */
      .agro-layout{display:grid!important;grid-template-columns:1fr!important}
      .metrics-grid{grid-template-columns:1fr 1fr!important}
      .agro-metrics{grid-template-columns:1fr 1fr!important}
      .carbon-banner{flex-direction:column!important;gap:12px!important;padding:16px!important}
      .carbon-val{font-size:26px!important}
      .carbon-detail{gap:12px!important}
      /* ── Diagnostic ── */
      .result-panel{position:static!important}
      .range-val{font-size:14px!important}
    }
  `;
  document.head.appendChild(style);

  const toastEl = document.createElement('div');
  toastEl.id = 'avp-toast';
  // body peut être null si le script est dans <head> — attendre le DOM
  if (document.body) {
    document.body.appendChild(toastEl);
  } else {
    document.addEventListener('DOMContentLoaded', () => document.body.appendChild(toastEl));
  }
})();

/* ── Toast ──────────────────────────────────────────────────── */
function toast(msg, type) {
  // Auto-détection du type quand non précisé : un message d'erreur s'affiche en rouge.
  if (!type) {
    type = /impossible|erreur|invalide|requis|obligatoire|refus|incorrect|échec|echec|trop court|introuvable|manquant|non autoris|interdit|échou/i.test(String(msg))
      ? 'error' : 'success';
  }
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  const c = document.getElementById('avp-toast');
  if (c) c.appendChild(el);
  setTimeout(() => { el.style.transition = 'opacity .4s'; el.style.opacity = '0'; }, 2800);
  setTimeout(() => el.remove(), 3300);
}

/* ── Token storage ──────────────────────────────────────────── */
function getToken() { return localStorage.getItem('avp_token'); }
function getRefreshToken() { return localStorage.getItem('avp_refresh_token'); }

function saveTokens(access, refresh) {
  localStorage.setItem('avp_token', access);
  if (refresh) localStorage.setItem('avp_refresh_token', refresh);
}

function getCurrentUser() {
  const token = getToken();
  if (!token) return null;
  try {
    const p = JSON.parse(atob(token.split('.')[1]));
    return { email: p.sub || '', role: p.role || '', coop_id: p.coop_id || null, exp: p.exp || 0 };
  } catch { return null; }
}

function isTokenExpired(token) {
  try {
    const p = JSON.parse(atob(token.split('.')[1]));
    // Considérer expiré 5 minutes avant l'expiration réelle
    return Date.now() / 1000 > (p.exp - 300);
  } catch { return true; }
}

/* ── Refresh token automatique ──────────────────────────────── */
async function refreshAccessToken() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken })
    });
    if (!res.ok) return false;
    const data = await res.json();
    saveTokens(data.access_token, null); // conserver l'ancien refresh
    return true;
  } catch { return false; }
}

/* ── Refresh proactif du jeton ───────────────────────────────────
   Le jeton d'acces dure 2h. Sans renouvellement, l'utilisateur est ejecte
   ("Could not validate credentials") en pleine saisie (ex: cloturer une
   visite monitoring). auth.js etant charge sur toutes les pages, ce timer
   maintient avp_token frais dans localStorage : tous les wrappers (authFetch
   ET les cgFetch des modules CacaoGuard) qui lisent getToken() recoivent un
   jeton valide, sans modification page par page.
   isTokenExpired() integre une marge de 5 min, donc on rafraichit AVANT
   l'expiration reelle. */
let _avpRefreshInFlight = null;
async function ensureFreshToken() {
  const token = getToken();
  if (!token || !isTokenExpired(token)) return;       // encore valide
  if (!getRefreshToken()) return;                      // pas de refresh dispo
  if (_avpRefreshInFlight) return _avpRefreshInFlight; // evite les appels concurrents
  _avpRefreshInFlight = refreshAccessToken().finally(() => { _avpRefreshInFlight = null; });
  return _avpRefreshInFlight;
}

function startTokenAutoRefresh() {
  ensureFreshToken();                       // verification immediate au chargement
  setInterval(ensureFreshToken, 60 * 1000); // puis toutes les 60 s
  // Renouvelle aussi quand l'onglet redevient actif (apres une mise en veille).
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') ensureFreshToken();
  });
}

/* ── Auth guards ─────────────────────────────────────────────── */
// Pages publiques (accessibles sans authentification).
const PUBLIC_PAGES = ['login.html', 'register.html', 'reset_password.html', 'owner.html'];

function _currentPage() {
  const path = (window.location.pathname || '').split('/').pop();
  return path || 'index.html';
}

function requireAuth() {
  // Sur une page applicative, exiger un jeton valide : sinon rediriger vers la
  // connexion (evite l'affichage d'un tableau de bord vide apres deconnexion).
  if (PUBLIC_PAGES.includes(_currentPage())) return true;
  const token = getToken();
  // Jeton present et encore exploitable (ou rafraichissable) => OK.
  if (token && (!isTokenExpired(token) || getRefreshToken())) return true;
  window.location.replace('login.html');
  return false;
}

function logout() { localStorage.clear(); window.location.replace('login.html'); }

/* ── Modale maison (remplace confirm()/prompt() natifs) ─────────────────────
   avpConfirm(message, opts) -> Promise<bool>
   avpPrompt(message, opts)  -> Promise<string|null>   (opts: defaultValue, placeholder, multiline, okText, danger)
   Style inline (indépendant du CSS de la page). Échap = annuler, Entrée = valider. */
function _avpModal({ message, input = false, defaultValue = '', placeholder = '', multiline = false, okText = 'Confirmer', cancelText = 'Annuler', danger = false }) {
  return new Promise((resolve) => {
    const ov = document.createElement('div');
    ov.style.cssText = 'position:fixed;inset:0;background:rgba(12,32,24,.55);display:flex;align-items:center;justify-content:center;z-index:10001;padding:20px';
    const field = input
      ? (multiline
          ? `<textarea id="_avp-mf" rows="3" style="width:100%;padding:10px 12px;border:1.5px solid #e5e7eb;border-radius:8px;font:14px/1.4 system-ui,sans-serif;margin-top:12px" placeholder="${placeholder}"></textarea>`
          : `<input id="_avp-mf" style="width:100%;padding:10px 12px;border:1.5px solid #e5e7eb;border-radius:8px;font:14px system-ui,sans-serif;margin-top:12px" placeholder="${placeholder}">`)
      : '';
    ov.innerHTML = `
      <div style="background:#fff;border-radius:12px;padding:22px 24px;width:100%;max-width:420px;box-shadow:0 10px 40px rgba(0,0,0,.25);font-family:system-ui,sans-serif">
        <div style="font-size:14.5px;line-height:1.5;color:#1a2218;white-space:pre-line">${message}</div>
        ${field}
        <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:18px">
          <button id="_avp-cancel" style="padding:9px 16px;border:1px solid #e5e7eb;background:#fff;border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;font-family:inherit">${cancelText}</button>
          <button id="_avp-ok" style="padding:9px 16px;border:none;background:${danger ? '#922b21' : '#1a4231'};color:#fff;border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;font-family:inherit">${okText}</button>
        </div>
      </div>`;
    document.body.appendChild(ov);
    const f = ov.querySelector('#_avp-mf');
    if (f) setTimeout(() => f.focus(), 50);
    const done = (val) => { ov.remove(); document.removeEventListener('keydown', onKey); resolve(val); };
    const onOk = () => done(input ? (f ? f.value : '') : true);
    const onCancel = () => done(input ? null : false);
    ov.querySelector('#_avp-ok').onclick = onOk;
    ov.querySelector('#_avp-cancel').onclick = onCancel;
    ov.addEventListener('click', (e) => { if (e.target === ov) onCancel(); });
    function onKey(e) {
      if (e.key === 'Escape') onCancel();
      else if (e.key === 'Enter' && (!multiline || e.ctrlKey)) onOk();
    }
    document.addEventListener('keydown', onKey);
    if (f && defaultValue) f.value = defaultValue;
  });
}
function avpConfirm(message, opts = {}) { return _avpModal({ message, input: false, ...opts }); }
function avpPrompt(message, opts = {}) { return _avpModal({ message, input: true, ...opts }); }

/* ── Géo-horodatage anti-fraude : helpers partagés (capture texte + badge) ─── */
function avpParseLatLng(s) {
  if (!s) return null;
  const parts = String(s).split(',');
  if (parts.length < 2) return null;
  const lat = parseFloat(parts[0]), lng = parseFloat(parts[1]);
  if (isNaN(lat) || isNaN(lng)) return null;
  return { lat, lng };
}
function avpGeoBadge(geo) {
  if (!geo || !geo.geo_status) return '';
  const map = {
    verified:     ['#1a6b3a', '✓ GPS vérifié'],
    far:          ['#922b21', '⚠ Hors zone' + (geo.distance_m != null ? ' (' + Math.round(geo.distance_m) + ' m)' : '')],
    no_fix:       ['#9a6200', '⚠ Sans GPS'],
    overridden:   ['#9a6200', '⚠ Sans GPS (motivé)'],
    no_reference: ['#6a7d64', '📍 GPS (réf. inconnue)'],
  };
  const m = map[geo.geo_status] || ['#6a7d64', geo.geo_status];
  return `<span style="font-size:11px;font-weight:700;color:${m[0]}">${m[1]}</span>`;
}

/* ── Changer mon mot de passe (self-service, tous roles) ───────── */
function ensureChangePasswordModal() {
  if (document.getElementById('avp-cp-overlay')) return;
  const ov = document.createElement('div');
  ov.id = 'avp-cp-overlay';
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(12,32,24,.55);display:none;align-items:center;justify-content:center;z-index:10000;padding:20px';
  ov.innerHTML = `
    <div style="background:#fff;border-radius:12px;padding:22px 24px;width:100%;max-width:380px;box-shadow:0 10px 40px rgba(0,0,0,.25);font-family:system-ui,sans-serif">
      <div style="font-size:17px;font-weight:800;color:#14532d;margin-bottom:14px">Changer mon mot de passe</div>
      <label style="font-size:12px;font-weight:600;color:#374151">Mot de passe actuel</label>
      <input type="password" id="avp-cp-current" style="width:100%;padding:9px 11px;margin:4px 0 12px;border:1px solid #e5e7eb;border-radius:8px;font-size:14px">
      <label style="font-size:12px;font-weight:600;color:#374151">Nouveau mot de passe <span style="color:#6b7280;font-weight:400">(min. 6 caractères)</span></label>
      <input type="password" id="avp-cp-new" style="width:100%;padding:9px 11px;margin:4px 0 12px;border:1px solid #e5e7eb;border-radius:8px;font-size:14px">
      <label style="font-size:12px;font-weight:600;color:#374151">Confirmer le nouveau</label>
      <input type="password" id="avp-cp-confirm" style="width:100%;padding:9px 11px;margin:4px 0 6px;border:1px solid #e5e7eb;border-radius:8px;font-size:14px">
      <div id="avp-cp-err" style="display:none;color:#b91c1c;font-size:12.5px;margin:6px 0"></div>
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px">
        <button onclick="closeChangePassword()" style="padding:8px 14px;border:1px solid #e5e7eb;border-radius:8px;background:#fff;cursor:pointer;font-size:13px">Annuler</button>
        <button id="avp-cp-ok" onclick="submitChangePassword()" style="padding:8px 16px;border:none;border-radius:8px;background:#15803d;color:#fff;cursor:pointer;font-weight:700;font-size:13px">Enregistrer</button>
      </div>
    </div>`;
  ov.addEventListener('click', e => { if (e.target === ov) closeChangePassword(); });
  document.body.appendChild(ov);
}

function openChangePassword() {
  if (typeof closeSidebar === 'function') closeSidebar();
  ensureChangePasswordModal();
  ['avp-cp-current','avp-cp-new','avp-cp-confirm'].forEach(id => { const el=document.getElementById(id); if (el) el.value=''; });
  document.getElementById('avp-cp-err').style.display = 'none';
  document.getElementById('avp-cp-overlay').style.display = 'flex';
}

function closeChangePassword() {
  const ov = document.getElementById('avp-cp-overlay');
  if (ov) ov.style.display = 'none';
}

async function submitChangePassword() {
  const err = document.getElementById('avp-cp-err');
  err.style.display = 'none';
  const cur = document.getElementById('avp-cp-current').value;
  const nw = document.getElementById('avp-cp-new').value;
  const cf = document.getElementById('avp-cp-confirm').value;
  if (!cur || !nw) { err.textContent = 'Tous les champs sont requis.'; err.style.display='block'; return; }
  if (nw.length < 6) { err.textContent = 'Le nouveau mot de passe doit faire au moins 6 caractères.'; err.style.display='block'; return; }
  if (nw !== cf) { err.textContent = 'La confirmation ne correspond pas.'; err.style.display='block'; return; }
  const btn = document.getElementById('avp-cp-ok');
  btn.disabled = true; btn.textContent = 'Enregistrement...';
  try {
    const res = await authFetch('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password: cur, new_password: nw })
    });
    if (res && res.status === 401) throw new Error('Mot de passe actuel incorrect.');
    if (!res || !res.ok) {
      const e = await res?.json().catch(()=>({}));
      throw new Error(e.detail || 'Erreur lors du changement.');
    }
    closeChangePassword();
    if (typeof toast === 'function') toast('Mot de passe modifié avec succès.');
    else alert('Mot de passe modifié avec succès.');
  } catch (e) {
    err.textContent = e.message; err.style.display = 'block';
  } finally {
    btn.disabled = false; btn.textContent = 'Enregistrer';
  }
}

/* ── API wrapper avec refresh automatique ───────────────────── */
async function authFetch(endpoint, options = {}) {
  const token = getToken();
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  // Authentification désactivée - pas de token requis
  try {
    const res = await fetch(API_BASE + endpoint, {
      ...options,
      headers: {
        ...(!isFormData ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { 'Authorization': 'Bearer ' + token } : {}),
        ...(options.headers || {})
      }
    });
    return res;
  } catch (e) {
    console.warn('[authFetch] request failed', endpoint, API_BASE, e);
    if (!navigator.onLine) {
      toast('Hors ligne — Reconnectez-vous pour accéder à vos données.', 'error');
    } else {
      toast('Serveur inaccessible. Réessayez dans un instant.', 'error');
    }
  }
}


/* ── Téléchargement authentifié (PDF/ZIP) ─────────────────────────────
   Récupère le fichier via authFetch (donc AVEC le jeton) puis déclenche un
   VRAI téléchargement (<a download>), au lieu d'ouvrir une visionneuse dans
   un onglet — ce qui, sur certains appareils, obligeait à « enregistrer via
   Google Drive ». Renvoie true si OK, false sinon (toast d'erreur affiché). */
async function downloadAuthedFile(path, fallbackName) {
  let r;
  try {
    r = await authFetch(path);
  } catch (e) {
    toast('Téléchargement impossible : ' + ((e && e.message) || 'réseau'), 'error');
    return false;
  }
  if (!r || !r.ok) {
    let detail = '';
    try { detail = (await r.json()).detail || ''; } catch (_) {}
    toast('Téléchargement impossible' + (detail ? ' : ' + detail : ` (${r ? r.status : 'réseau'})`), 'error');
    return false;
  }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  // Nom de fichier : priorité au filename* (UTF-8 → accents fiables), sinon filename="…"
  const cd = r.headers.get('content-disposition') || '';
  let name = fallbackName || 'document';
  let m = cd.match(/filename\*=UTF-8''([^;]+)/i);
  if (m) { try { name = decodeURIComponent(m[1]); } catch (_) {} }
  else { m = cd.match(/filename="?([^";]+)"?/i); if (m) name = m[1]; }
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  return true;
}


/* ── Export CSV (Excel) — helper partagé ──────────────────────────────
   Exporte un tableau d'objets déjà chargés (donc déjà cloisonnés par coop)
   en CSV ouvrable par Excel. BOM UTF-8 → les accents s'affichent correctement.
   `columns` = [{key, label}] (ordre + en-têtes). Si omis, déduit des clés du
   1er objet. Renvoie false (et toast) si aucune donnée. */
function avpExportCsv(rows, filename, columns) {
  if (!Array.isArray(rows) || rows.length === 0) {
    if (typeof toast === 'function') toast('Aucune donnée à exporter.', 'error');
    return false;
  }
  const cols = (columns && columns.length)
    ? columns
    : Object.keys(rows[0]).map(k => ({ key: k, label: k }));
  const esc = (v) => {
    if (v === null || v === undefined) return '';
    let s = String(v);
    if (Array.isArray(v)) s = v.join(' | ');
    else if (typeof v === 'object') { try { s = JSON.stringify(v); } catch (_) { s = ''; } }
    // Échappement CSV : guillemets doublés, et encadrement si caractère spécial.
    if (/[",;\n\r]/.test(s)) s = '"' + s.replace(/"/g, '""') + '"';
    return s;
  };
  const header = cols.map(c => esc(c.label)).join(';');   // ';' = séparateur Excel FR
  const lines = rows.map(r => cols.map(c => esc(typeof c.value === 'function' ? c.value(r) : r[c.key])).join(';'));
  const csv = '﻿' + [header, ...lines].join('\r\n');   // BOM UTF-8
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = (filename || 'export') + (String(filename || '').endsWith('.csv') ? '' : '.csv');
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  if (typeof toast === 'function') toast(`${rows.length} ligne(s) exportée(s).`);
  return true;
}


/* ── Sprint Honnetete-Offline : Bandeau reseau persistant ────────────── */

// Bandeau reseau v2 - bottom : repositionne en bas avec version mobile compacte
// Fix UX mobile (09/05/2026) : la version v1 cachait le menu burger sur petits ecrans.
function avpUpdateNetworkBanner() {
  const existing = document.getElementById('avp-offline-banner');
  if (!navigator.onLine) {
    if (!existing) {
      // Detection mobile via viewport (640px = breakpoint Tailwind sm)
      const isMobile = window.innerWidth < 640;
      const fullText = '📡 Vous êtes hors ligne — certaines fonctionnalités ne sont pas disponibles. ' +
        'Reconnectez-vous pour utiliser AgriVision Pro.';
      const shortText = '📡 Hors ligne — fonctionnalités limitées';

      const banner = document.createElement('div');
      banner.id = 'avp-offline-banner';
      banner.innerHTML = isMobile ? shortText : fullText;
      banner.setAttribute('role', 'status');
      banner.setAttribute('aria-live', 'polite');
      banner.style.cssText = [
        'position:fixed',
        'bottom:0',
        'left:0',
        'right:0',
        'z-index:9999',
        'padding:' + (isMobile ? '10px 14px' : '12px 16px'),
        'background:#fef3c7',
        'color:#78350f',
        'border-top:2px solid #d97706',
        'font-size:' + (isMobile ? '13px' : '13.5px'),
        'text-align:center',
        'font-weight:500',
        'line-height:1.35',
        'box-shadow:0 -2px 8px rgba(0,0,0,0.08)',
        'transform:translateY(100%)',
        'transition:transform 0.25s ease-out',
        'pointer-events:none'  // ne bloque pas les clics
      ].join(';');
      document.body.appendChild(banner);

      // Animation slide-up subtile
      requestAnimationFrame(() => {
        banner.style.transform = 'translateY(0)';
      });

      // Re-evaluer le texte si l'utilisateur tourne le telephone (orientation change)
      window.addEventListener('resize', avpAdjustBannerText, { passive: true });
    }
  } else if (existing) {
    // Animation slide-down avant suppression
    existing.style.transform = 'translateY(100%)';
    setTimeout(() => existing.remove(), 250);
    window.removeEventListener('resize', avpAdjustBannerText);
  }
}

// Helper : ajuste le texte du bandeau si la taille d'ecran change (rotation)
function avpAdjustBannerText() {
  const banner = document.getElementById('avp-offline-banner');
  if (!banner) return;
  const isMobile = window.innerWidth < 640;
  banner.innerHTML = isMobile
    ? '📡 Hors ligne — fonctionnalités limitées'
    : '📡 Vous êtes hors ligne — certaines fonctionnalités ne sont pas disponibles. Reconnectez-vous pour utiliser AgriVision Pro.';
  banner.style.padding = isMobile ? '10px 14px' : '12px 16px';
  banner.style.fontSize = isMobile ? '13px' : '13.5px';
}

function setupNetworkBanner() {
  // Etat initial au chargement
  avpUpdateNetworkBanner();
  // Reagir aux changements de connectivite
  window.addEventListener('online', avpUpdateNetworkBanner);
  window.addEventListener('offline', avpUpdateNetworkBanner);
}

/* ── Sidebar ─────────────────────────────────────────────────── */

function toggleSidebar() {
  const sb = document.getElementById('sidebar');
  const ov = document.getElementById('avp-overlay');
  const hb = document.getElementById('avp-hamburger');
  const open = sb && sb.classList.toggle('open');
  if (ov) ov.classList.toggle('open', open);
  if (hb) hb.querySelector('.ms').textContent = open ? 'close' : 'menu';
}

function closeSidebar() {
  const sb = document.getElementById('sidebar');
  const ov = document.getElementById('avp-overlay');
  const hb = document.getElementById('avp-hamburger');
  if (sb) sb.classList.remove('open');
  if (ov) ov.classList.remove('open');
  if (hb) hb.querySelector('.ms').textContent = 'menu';
}

function renderSidebar(activePage) {
  const el = document.getElementById('sidebar');
  if (!el) return;

  if (!document.getElementById('avp-hamburger')) {
    const hamburger = document.createElement('button');
    hamburger.id = 'avp-hamburger';
    hamburger.className = 'hamburger';
    hamburger.innerHTML = '<span class="material-symbols-outlined ms">menu</span>';
    hamburger.onclick = toggleSidebar;
    document.body.appendChild(hamburger);

    const overlay = document.createElement('div');
    overlay.id = 'avp-overlay';
    overlay.className = 'sb-overlay';
    overlay.onclick = closeSidebar;
    document.body.appendChild(overlay);
  }

  const user = getCurrentUser();
  const _cachedMods = getCachedModules();  // gating immédiat (anti-flash) depuis le cache
  const init = user ? user.email.substring(0, 2).toUpperCase() : '??';
  // Menu regroupé par les 4 piliers (+ socle). L'ordre du tableau = l'ordre d'affichage ;
  // un en-tête de section est rendu à chaque changement de `group`. Les id/href/icon/label
  // sont inchangés → le feature-gating (data-mod), l'état actif et navClick ne bougent pas.
  const links = [
    // 📊 Piloter — décider et prouver (Dashboard en tête = page d'accueil)
    { id: 'dashboard', href: 'index.html', icon: 'dashboard', label: 'Opérations', group: '📊 Piloter' },
    { id: 'direction', href: 'direction.html', icon: 'insights', label: 'Direction', group: '📊 Piloter' },
    { id: 'assistant', href: 'assistant.html', icon: 'forum', label: 'Aya · Assistant IA', group: '📊 Piloter' },
    { id: 'reports-cacaoguard', href: 'reports_cacaoguard.html', icon: 'summarize', label: 'Rapports', group: '📊 Piloter' },
    { id: 'veille', href: 'veille.html', icon: 'trending_up', label: 'Veille Marché', group: '📊 Piloter' },
    // 🌱 Produire — exploitations & performance
    { id: 'plantations', href: 'plantations.html', icon: 'park', label: 'Plantations', group: '🌱 Produire' },
    { id: 'producers', href: 'producers.html', icon: 'groups', label: 'Producteurs', group: '🌱 Produire' },
    { id: 'diagnostic', href: 'diagnostic.html', icon: 'biotech', label: 'Diagnostic', group: '🌱 Produire' },
    { id: 'map', href: 'map.html', icon: 'map', label: 'Carte', group: '🌱 Produire' },
    { id: 'satellite', href: 'satellite.html', icon: 'satellite_alt', label: 'Satellite', group: '🌱 Produire' },
    { id: 'agroforestry', href: 'agroforestry.html', icon: 'forest', label: 'Agroforesterie', group: '🌱 Produire' },
    { id: 'harvests', href: 'harvests.html', icon: 'agriculture', label: 'Récoltes', group: '🌱 Produire' },
    { id: 'twin-risk', href: 'twin_risk.html', icon: 'crisis_alert', label: 'Parcelles à risque', group: '🌱 Produire' },
    // 📦 Tracer — du champ à l'acheteur
    { id: 'purchases', href: 'achats.html', icon: 'shopping_cart', label: 'Achats', group: '📦 Tracer' },
    { id: 'lots', href: 'lots.html', icon: 'inventory_2', label: 'Traçabilité lots', group: '📦 Tracer' },
    { id: 'certification', href: 'certification.html', icon: 'workspace_premium', label: 'Certification', group: '📦 Tracer' },
    // 🌍 Protéger — conformité & durabilité
    { id: 'cacaoguard', href: 'cacaoguard.html', icon: 'verified_user', label: 'CacaoGuard', group: '🌍 Protéger' },
    { id: 'children', href: 'children.html', icon: 'diversity_3', label: 'Protection enfant', group: '🌍 Protéger' },
    { id: 'ssrte', href: 'ssrte.html', icon: 'clinical_notes', label: 'Fiches SSRTE', group: '🌍 Protéger' },
    { id: 'eudr', href: 'eudr.html', icon: 'eco', label: 'EUDR', group: '🌍 Protéger' },
    { id: 'compliance', href: 'compliance.html', icon: 'gpp_maybe', label: 'Conformite', group: '🌍 Protéger' },
    { id: 'farmforce', href: 'farmforce.html', icon: 'request_quote', label: 'Revenu vital', group: '🌍 Protéger' },
    { id: 'monitoring', href: 'monitoring.html', icon: 'travel_explore', label: 'Monitoring', group: '🌍 Protéger' },
    { id: 'remediation', href: 'remediation.html', icon: 'assignment_turned_in', label: 'Remediation', group: '🌍 Protéger' },
    { id: 'complaints', href: 'complaints.html', icon: 'report', label: 'Signalements', group: '🌍 Protéger' },
    { id: 'training', href: 'training.html', icon: 'school', label: 'Formation', group: '🌍 Protéger' },
    // ⚙️ Configuration & aide
    { id: 'guide', href: 'guide.html', icon: 'menu_book', label: 'Aide / Guide', group: '⚙️ Configuration' },
  ];
  if (user && user.role === 'admin') {
    links.push({ id: 'admin', href: 'admin.html', icon: 'admin_panel_settings', label: 'Administration', group: '⚙️ Configuration' });
  }

  const userBlock = user ? `
    <div class="sb-user">
      <div class="sb-user-inner">
        <div class="sb-avatar">${init}</div>
        <div class="sb-user-info">
          <div class="sb-user-email">${user.email}</div>
          <div class="sb-user-role">${user.role}</div>
        </div>
        <button class="sb-logout" onclick="openChangePassword()" title="Changer mon mot de passe" style="margin-right:4px">
          <span class="material-symbols-outlined" style="font-size:18px">key</span>
        </button>
        <button class="sb-logout" onclick="logout()" title="Deconnexion">
          <span class="material-symbols-outlined" style="font-size:18px">logout</span>
        </button>
      </div>
    </div>` : `
    <div class="sb-user">
      <div class="sb-auth-actions">
        <a class="sb-auth-link primary" href="login.html" onclick="closeSidebar()">
          <span class="material-symbols-outlined ms">login</span>Connexion admin
        </a>
        <a class="sb-auth-link secondary" href="register.html" onclick="closeSidebar()">
          <span class="material-symbols-outlined ms">person_add</span>Creer un compte
        </a>
      </div>
    </div>`;

  el.innerHTML = `
    <div class="sb-logo">
      <div class="sb-logo-row">
        <div class="sb-logo-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="#52b788" stroke-width="1.8" stroke-linecap="round">
            <path d="M12 2C8 2 4 6 4 11c0 3.5 1.8 6.5 4.5 8.2V22h7v-2.8C18.2 17.5 20 14.5 20 11c0-5-4-9-8-9z"/>
            <path d="M12 2v20"/><path d="M8 8c2 1 4 2 4 5"/><path d="M16 8c-2 1-4 2-4 5"/>
          </svg>
        </div>
        <div>
          <div class="sb-logo-name">AgriVision Pro</div>
          <div class="sb-logo-sub">Plateforme cacao</div>
        </div>
      </div>
    </div>
    <nav class="sb-nav">
      ${(() => {
        let _grp = null;
        return links.map(l => {
          const _locked = _cachedMods && !_cachedMods.has(l.id) ? ' locked' : '';
          let _hdr = '';
          if (l.group && l.group !== _grp) { _hdr = `<div class="sb-sec">${l.group}</div>`; _grp = l.group; }
          return _hdr + `
        <a href="${l.href}" data-mod="${l.id}" class="nav-link ${activePage === l.id ? 'active' : ''}${_locked}" onclick="return navClick(event, this)">
          <span class="material-symbols-outlined ms">${l.icon}</span>${l.label}
        </a>`;
        }).join('');
      })()}
    </nav>
    ${userBlock}`;
}
// Masque les modules de menu hors plan de la cooperative (feature-gating).
// Non-bloquant : si l'appel echoue ou plan inconnu, on n'enleve rien.
// Cache local des modules autorisés → le menu est gaté DÈS le rendu (plus de flash
// des modules Entreprise à chaque navigation). Rafraîchi en arrière-plan par /me/features.
function getCachedModules() {
  try {
    const r = localStorage.getItem('avp_features');
    return r ? new Set(JSON.parse(r)) : null;
  } catch (e) { return null; }
}

// Clic sur un module : si grisé (hors plan), on bloque la navigation et on explique.
function navClick(e, el) {
  if (el && el.classList.contains('locked')) {
    e.preventDefault();
    if (typeof toast === 'function') {
      toast("Module non inclus dans votre plan. Contactez l'administrateur pour l'activer.", 'error');
    }
    return false;
  }
  closeSidebar();
}

async function applyPlanFeatures(activePage) {
  // Garde-fou SYNCHRONE (anti-flash) : si le cache du plan exclut déjà la page courante,
  // on redirige AVANT tout appel réseau → plus de flash ~1s avant le redirect async.
  // (Ne concerne que les vrais modules de menu ; les pages hors-menu n'ont pas de data-mod.)
  const _cachedSync = getCachedModules();
  const _navSync = activePage
    ? document.querySelector(`#sidebar a.nav-link[data-mod="${(window.CSS && CSS.escape) ? CSS.escape(activePage) : activePage}"]`)
    : null;
  if (_cachedSync && _navSync && activePage !== 'dashboard' && !_cachedSync.has(activePage)) {
    window.location.replace('index.html');
    return;
  }
  // Masque immédiatement (anti-flash) les métriques hors plan, via le cache.
  if (_cachedSync) avpGateMetricsByPlan(_cachedSync);
  try {
    const res = await authFetch('/me/features');
    if (!res || !res.ok) return;
    const data = await res.json();
    const allowed = new Set(data.modules || []);
    if (!allowed.size) return;
    try { localStorage.setItem('avp_features', JSON.stringify([...allowed])); } catch (e) { /* quota */ }
    document.querySelectorAll('#sidebar a.nav-link[data-mod]').forEach(a => {
      const mod = a.getAttribute('data-mod');
      a.classList.toggle('locked', !allowed.has(mod));  // grise les modules hors plan (au lieu de masquer)
      a.style.display = '';  // corrige un eventuel ancien cache qui masquait
    });
    // Rediriger UNIQUEMENT si la page courante est un vrai module de menu bloque
    // par le plan. Les pages hors-menu (import, assignment, producer-profile,
    // plantation_detail...) ne sont jamais des modules gates => pas de redirection.
    const navLink = activePage
      ? document.querySelector(`#sidebar a.nav-link[data-mod="${(window.CSS && CSS.escape) ? CSS.escape(activePage) : activePage}"]`)
      : null;
    if (navLink && !allowed.has(activePage) && activePage !== 'dashboard') {
      window.location.replace('index.html');
    }
    // Masque les métriques/sections hors plan (tableau de bord, direction…) pour
    // ne pas montrer à l'utilisateur des chiffres de modules qu'il n'a pas.
    avpGateMetricsByPlan(allowed);
  } catch (e) { /* non-bloquant */ }
}

/* ── Masquage des métriques hors plan ─────────────────────────────────
   Tout élément portant data-plan-module="mod1 mod2" est masqué si AUCUN de ses
   modules n'est inclus dans le plan de la coopérative. Évite d'afficher des KPI
   (EUDR, Revenu vital…) que l'utilisateur ne comprend pas car hors de son offre. */
function avpGateMetricsByPlan(allowed) {
  if (!allowed || !allowed.size) return;
  document.querySelectorAll('[data-plan-module]').forEach(el => {
    const mods = (el.getAttribute('data-plan-module') || '').split(/\s+/).filter(Boolean);
    const ok = mods.length === 0 || mods.some(m => allowed.has(m));
    el.style.display = ok ? '' : 'none';
  });
}

function initApp(page) {
  setupNetworkBanner();  // Sprint Honnetete-Offline
  if (!requireAuth()) return;
  renderSidebar(page);
  applyPlanFeatures(page);    // feature-gating du menu selon le plan de la coop
  setupNotificationWidget();  // Sprint P1 - notifications in-app
  startTokenAutoRefresh();    // renouvellement proactif du jeton (anti-deconnexion)
}

/* ── Notifications in-app (Sprint P1) ────────────────────────── */
function setupNotificationWidget() {
  // Inject CSS une seule fois
  if (!document.getElementById('avp-notif-styles')) {
    const css = document.createElement('style');
    css.id = 'avp-notif-styles';
    css.textContent = `
      .avp-notif-bell{position:fixed;bottom:24px;right:24px;width:48px;height:48px;border-radius:50%;
        background:var(--primary);color:#fff;border:none;cursor:pointer;display:flex;align-items:center;
        justify-content:center;box-shadow:0 4px 12px rgba(0,0,0,.18);z-index:8500;transition:.15s}
      .avp-notif-bell:hover{background:var(--primary-dark);transform:scale(1.05)}
      .avp-notif-bell .ms{color:#fff;font-size:22px}
      .avp-notif-badge{position:absolute;top:-4px;right:-4px;min-width:20px;height:20px;padding:0 5px;
        background:#dc2626;color:#fff;border-radius:99px;font-size:11px;font-weight:700;display:flex;
        align-items:center;justify-content:center;border:2px solid var(--surface);box-sizing:content-box}
      .avp-notif-badge.hidden{display:none}
      .avp-notif-panel{position:fixed;bottom:84px;right:24px;width:380px;max-width:calc(100vw - 32px);
        max-height:calc(100vh - 140px);background:var(--surface);border:1px solid var(--border);
        border-radius:var(--rl);box-shadow:0 12px 32px rgba(0,0,0,.18);z-index:8499;display:none;
        flex-direction:column;overflow:hidden}
      .avp-notif-panel.open{display:flex}
      .avp-notif-head{padding:14px 16px;border-bottom:1px solid var(--border);display:flex;
        align-items:center;justify-content:space-between;background:var(--surface-warm)}
      .avp-notif-title{font-family:'Fraunces',serif;font-size:15px;font-weight:700}
      .avp-notif-actions{display:flex;gap:8px}
      .avp-notif-mark-all{background:none;border:none;color:var(--primary);font-size:11.5px;
        font-weight:600;cursor:pointer;padding:4px 8px;border-radius:6px;text-transform:uppercase;letter-spacing:.04em}
      .avp-notif-mark-all:hover{background:rgba(82,183,136,.1)}
      .avp-notif-list{flex:1;overflow-y:auto;padding:6px}
      .avp-notif-item{padding:12px;border-radius:8px;cursor:pointer;border-left:3px solid transparent;
        margin-bottom:4px;transition:.1s}
      .avp-notif-item:hover{background:var(--surface-warm)}
      .avp-notif-item.unread{border-left-color:var(--accent);background:rgba(82,183,136,.06)}
      .avp-notif-item-title{font-weight:600;font-size:13px;margin-bottom:3px;color:var(--text)}
      .avp-notif-item-msg{font-size:12px;color:var(--muted);line-height:1.4}
      .avp-notif-item-meta{display:flex;justify-content:space-between;margin-top:6px;font-size:11px;color:var(--faint)}
      .avp-notif-prio-urgent{color:#dc2626;font-weight:700}
      .avp-notif-prio-high{color:#9a6200;font-weight:600}
      .avp-notif-empty{padding:32px 16px;text-align:center;color:var(--muted);font-size:13px}
      @media(max-width:480px){.avp-notif-panel{left:8px;right:8px;width:auto;bottom:78px}
        .avp-notif-bell{bottom:16px;right:16px}}
    `;
    document.head.appendChild(css);
  }

  // Inject bell + panel une seule fois
  if (!document.getElementById('avp-notif-bell')) {
    const bell = document.createElement('button');
    bell.id = 'avp-notif-bell';
    bell.className = 'avp-notif-bell';
    bell.title = 'Notifications';
    bell.innerHTML = `
      <span class="material-symbols-outlined ms">notifications</span>
      <span class="avp-notif-badge hidden" id="avp-notif-badge">0</span>`;
    bell.onclick = toggleNotifPanel;

    const panel = document.createElement('div');
    panel.id = 'avp-notif-panel';
    panel.className = 'avp-notif-panel';
    panel.innerHTML = `
      <div class="avp-notif-head">
        <span class="avp-notif-title">Notifications</span>
        <div class="avp-notif-actions">
          <button class="avp-notif-mark-all" onclick="markAllNotifsRead()">Tout marquer lu</button>
        </div>
      </div>
      <div class="avp-notif-list" id="avp-notif-list">
        <div class="avp-notif-empty">Chargement...</div>
      </div>`;

    const attach = () => {
      document.body.appendChild(bell);
      document.body.appendChild(panel);
    };
    if (document.body) attach();
    else document.addEventListener('DOMContentLoaded', attach);
  }

  // Polling unread count
  refreshNotifBadge();
  if (window.__avpNotifPollId) clearInterval(window.__avpNotifPollId);
  window.__avpNotifPollId = setInterval(refreshNotifBadge, 60000);
}

async function refreshNotifBadge() {
  try {
    const res = await authFetch('/notifications/unread-count');
    if (!res || !res.ok) return;
    const data = await res.json();
    const badge = document.getElementById('avp-notif-badge');
    if (!badge) return;
    const n = data.unread_count || 0;
    badge.textContent = n > 99 ? '99+' : String(n);
    badge.classList.toggle('hidden', n === 0);
  } catch (_) { /* silent */ }
}

async function toggleNotifPanel() {
  const panel = document.getElementById('avp-notif-panel');
  if (!panel) return;
  const opening = !panel.classList.contains('open');
  panel.classList.toggle('open');
  if (opening) await loadNotifList();
}

async function loadNotifList() {
  const list = document.getElementById('avp-notif-list');
  if (!list) return;
  list.innerHTML = '<div class="avp-notif-empty">Chargement...</div>';
  try {
    const res = await authFetch('/notifications?limit=30');
    if (!res || !res.ok) {
      list.innerHTML = '<div class="avp-notif-empty">Connexion requise pour voir les notifications.</div>';
      return;
    }
    const data = await res.json();
    if (!data.items || data.items.length === 0) {
      list.innerHTML = '<div class="avp-notif-empty">Aucune notification pour le moment.</div>';
      return;
    }
    list.innerHTML = data.items.map(n => {
      const unread = !n.read_at;
      const prioCls = n.priority === 'urgent' ? 'avp-notif-prio-urgent'
        : n.priority === 'high' ? 'avp-notif-prio-high' : '';
      const time = n.created_at ? new Date(n.created_at).toLocaleString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
      return `
        <div class="avp-notif-item ${unread ? 'unread' : ''}" onclick="onClickNotif(${n.id})">
          <div class="avp-notif-item-title">${escapeHtml(n.title || '(sans titre)')}</div>
          <div class="avp-notif-item-msg">${escapeHtml((n.message || '').slice(0, 200))}</div>
          <div class="avp-notif-item-meta">
            <span class="${prioCls}">${n.priority || ''}</span>
            <span>${time}</span>
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    list.innerHTML = '<div class="avp-notif-empty">Erreur de chargement.</div>';
  }
}

async function onClickNotif(id) {
  try {
    await authFetch(`/notifications/${id}/read`, { method: 'POST' });
    refreshNotifBadge();
    loadNotifList();
  } catch (_) { /* silent */ }
}

async function markAllNotifsRead() {
  try {
    await authFetch('/notifications/mark-all-read', { method: 'POST' });
    refreshNotifBadge();
    loadNotifList();
    if (typeof toast === 'function') toast('Notifications marquées comme lues.');
  } catch (_) { /* silent */ }
}

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, m =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
}

/* ── Helpers ─────────────────────────────────────────────────── */
function riskBadge(level) {
  const cls = { LOW: 'badge-low', MEDIUM: 'badge-med', HIGH: 'badge-high' };
  const lbl = { LOW: 'Faible', MEDIUM: 'Moyen', HIGH: 'Élevé' };
  return `<span class="badge ${cls[level] || 'badge-med'}">${lbl[level] || level}</span>`;
}
function scoreColor(s) { return s >= 70 ? '#922b21' : s >= 35 ? '#9a6200' : '#1a6b3a'; }
function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' });
}

/* ── AVPCombo : liste déroulante AVEC recherche ───────────────────────────────
   Remplace un <select> quand la liste est énorme (coops à des milliers de
   parcelles/producteurs) : champ de recherche + filtrage instantané (insensible
   aux accents), clavier (↑ ↓ Entrée Échap), plafond d'affichage pour rester fluide.
   API : const h = AVPCombo.attach(hostEl|id, {items:[{value,label,sub}], value,
         placeholder, onChange(value,item)});  puis h.setItems(...) / h.setValue(...)
         / h.getValue(). */
const AVPCombo = (function () {
  let _stylesDone = false;
  function ensureStyles() {
    if (_stylesDone) return; _stylesDone = true;
    const css = `
.avp-combo{position:relative;display:block}
.avp-combo-input{width:100%;box-sizing:border-box;padding:11px 58px 11px 14px;border:1px solid var(--border);border-radius:var(--r);background:var(--surface);color:var(--text);font-family:'DM Sans',sans-serif;font-size:14px;outline:none;transition:border-color .15s,box-shadow .15s}
.avp-combo-input::placeholder{color:var(--muted)}
.avp-combo-input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(45,140,90,.12)}
.avp-combo-caret{position:absolute;right:10px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:20px;pointer-events:none}
.avp-combo-clear{position:absolute;right:33px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:18px;cursor:pointer;display:none}
.avp-combo.has-val .avp-combo-clear{display:inline-flex}
.avp-combo-panel{position:absolute;z-index:80;left:0;right:0;top:calc(100% + 4px);background:var(--surface);border:1px solid var(--border);border-radius:var(--r);box-shadow:0 8px 24px rgba(0,0,0,.14);max-height:320px;overflow-y:auto;display:none}
.avp-combo.open .avp-combo-panel{display:block}
.avp-combo-opt{padding:9px 14px;cursor:pointer;display:flex;flex-direction:column;gap:1px;border-bottom:1px solid var(--border-l)}
.avp-combo-opt:last-child{border-bottom:none}
.avp-combo-opt.active,.avp-combo-opt:hover{background:var(--surface-warm,rgba(45,140,90,.08))}
.avp-combo-opt.sel{background:rgba(45,140,90,.14)}
.avp-combo-opt-l{font-size:13.5px;font-weight:500;color:var(--text)}
.avp-combo-opt-s{font-size:12px;color:var(--muted)}
.avp-combo-more,.avp-combo-empty{padding:11px 14px;font-size:12.5px;color:var(--muted);text-align:center}`;
    const s = document.createElement('style'); s.id = 'avp-combo-styles'; s.textContent = css;
    document.head.appendChild(s);
  }
  function norm(s) { return String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); }
  const CAP = 80;
  function attach(host, opts) {
    ensureStyles();
    host = (typeof host === 'string') ? document.getElementById(host) : host;
    if (!host) return null;
    opts = opts || {};
    let items = opts.items || [];
    let value = (opts.value != null && opts.value !== '') ? String(opts.value) : '';
    let filtered = items, open = false, active = -1;
    host.classList.add('avp-combo');
    host.innerHTML =
      '<input type="text" class="avp-combo-input" autocomplete="off" spellcheck="false" placeholder="' +
        escapeHtml(opts.placeholder || 'Rechercher…') + '">' +
      '<span class="avp-combo-clear material-symbols-outlined" title="Effacer">close</span>' +
      '<span class="avp-combo-caret material-symbols-outlined">expand_more</span>' +
      '<div class="avp-combo-panel"></div>';
    const input = host.querySelector('.avp-combo-input');
    const panel = host.querySelector('.avp-combo-panel');
    const clear = host.querySelector('.avp-combo-clear');
    function itemFor(v) { return items.find(i => String(i.value) === String(v)) || null; }
    function labelFor(v) { const it = itemFor(v); return it ? it.label : ''; }
    function syncField() { input.value = labelFor(value); host.classList.toggle('has-val', !!value); }
    function render() {
      const q = norm(input.value);
      filtered = !q ? items : items.filter(i => norm(i.label).includes(q) || norm(i.sub).includes(q));
      const shown = filtered.slice(0, CAP);
      panel.innerHTML = shown.length
        ? shown.map((i, idx) =>
            '<div class="avp-combo-opt' + (idx === active ? ' active' : '') +
              (String(i.value) === value ? ' sel' : '') + '" data-v="' + escapeHtml(String(i.value)) + '">' +
              '<span class="avp-combo-opt-l">' + escapeHtml(i.label) + '</span>' +
              (i.sub ? '<span class="avp-combo-opt-s">' + escapeHtml(i.sub) + '</span>' : '') +
            '</div>').join('') +
            (filtered.length > CAP ? '<div class="avp-combo-more">… ' + (filtered.length - CAP) +
              ' autre(s) — affinez la recherche</div>' : '')
        : '<div class="avp-combo-empty">Aucun résultat</div>';
    }
    function openPanel() { open = true; host.classList.add('open'); input.value = ''; active = -1; render(); }
    function closePanel() { open = false; host.classList.remove('open'); syncField(); }
    function choose(v) {
      value = (v != null && v !== '') ? String(v) : '';
      closePanel();
      if (opts.onChange) opts.onChange(value, itemFor(value));
    }
    function scrollActive() { const el = panel.querySelector('.avp-combo-opt.active'); if (el) el.scrollIntoView({ block: 'nearest' }); }
    input.addEventListener('focus', openPanel);
    input.addEventListener('input', () => { if (!open) { open = true; host.classList.add('open'); } active = 0; render(); });
    input.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') { e.preventDefault(); if (!open) openPanel(); active = Math.min(active + 1, Math.min(filtered.length, CAP) - 1); render(); scrollActive(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(active - 1, 0); render(); scrollActive(); }
      else if (e.key === 'Enter') { e.preventDefault(); const it = filtered[active]; if (it) choose(it.value); }
      else if (e.key === 'Escape') { closePanel(); input.blur(); }
    });
    panel.addEventListener('mousedown', e => { const opt = e.target.closest('.avp-combo-opt'); if (opt) { e.preventDefault(); choose(opt.getAttribute('data-v')); } });
    clear.addEventListener('mousedown', e => { e.preventDefault(); choose(''); });
    document.addEventListener('mousedown', e => { if (open && !host.contains(e.target)) closePanel(); });
    syncField();
    return {
      setItems(newItems) { items = newItems || []; if (open) render(); else syncField(); },
      setValue(v) { value = (v != null && v !== '') ? String(v) : ''; syncField(); },
      getValue() { return value; },
      focus() { input.focus(); },
    };
  }

  /* enhance(select) : « habille » un <select> existant d'une recherche SANS toucher
     au code de la page. Le <select> natif reste la source de vérité (.value,
     onchange) ; on le masque, on affiche le combo par-dessus, et on resynchronise
     automatiquement quand les options sont peuplées (souvent en async) ou changent.
     Un simple attribut data-searchable sur le <select> suffit (auto-enhance). */
  function _readSelect(select) {
    let placeholder = 'Rechercher…';
    const items = [];
    Array.from(select.options).forEach(o => {
      if (o.value === '') { if (o.textContent.trim()) placeholder = o.textContent.trim(); return; }
      items.push({ value: o.value, label: o.textContent.trim(), sub: o.getAttribute('data-sub') || '' });
    });
    return { items, placeholder };
  }
  function enhance(select) {
    ensureStyles();
    select = (typeof select === 'string') ? document.getElementById(select) : select;
    if (!select || select.tagName !== 'SELECT' || select.multiple) return null;
    if (select._avpCombo) { select._avpCombo.refresh(); return select._avpCombo; }
    const host = document.createElement('div');
    if (select.style.minWidth) host.style.minWidth = select.style.minWidth;
    if (select.style.flex) host.style.flex = select.style.flex;
    select.style.display = 'none';
    select.setAttribute('aria-hidden', 'true');
    select.parentNode.insertBefore(host, select.nextSibling);
    const first = _readSelect(select);
    let syncing = false;
    const handle = attach(host, {
      items: first.items, placeholder: first.placeholder, value: select.value,
      onChange: (v) => {
        if (select.value === v) return;
        syncing = true;
        select.value = v;
        select.dispatchEvent(new Event('change', { bubbles: true }));
        syncing = false;
      },
    });
    handle.refresh = () => {
      if (syncing) return;
      const r = _readSelect(select);
      handle.setItems(r.items);
      handle.setValue(select.value);
    };
    // Re-sync quand les options sont (re)peuplées : populate = mutation childList.
    try { new MutationObserver(() => handle.refresh()).observe(select, { childList: true }); } catch (e) {}
    // Re-sync quand la page change la valeur par code et émet un 'change' (le guard
    // `syncing` ignore l'événement que nous venons nous-mêmes de déclencher).
    select.addEventListener('change', () => handle.refresh());
    select._avpCombo = handle;
    return handle;
  }
  function autoEnhance(root) {
    (root || document).querySelectorAll('select[data-searchable]').forEach(s => { try { enhance(s); } catch (e) {} });
  }
  if (typeof document !== 'undefined') {
    if (document.readyState !== 'loading') autoEnhance();
    else document.addEventListener('DOMContentLoaded', () => autoEnhance());
  }

  return { attach, enhance, autoEnhance };
})();

/* ── Aya · Interprétation IA par module (bouton réutilisable) ─────────────────
   Usage : <button onclick="avpInterpretModule('agroforestry', this)">…</button>
   Le résultat s'affiche dans un panneau inséré juste après le bouton. Le backend
   met en cache (coût maîtrisé) ; la 2ᵉ ouverture est quasi instantanée. */
function _avpMiniMarkdown(md) {
  const esc = s => String(s).replace(/[&<>]/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[m]));
  const lines = String(md || '').split('\n');
  let html = '', inList = false;
  const closeList = () => { if (inList) { html += '</ul>'; inList = false; } };
  for (let raw of lines) {
    let l = raw.trim();
    if (!l) { closeList(); continue; }
    l = esc(l).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`(.+?)`/g, '<code>$1</code>');
    if (/^#{1,6}\s+/.test(l)) { closeList(); html += '<div style="font-weight:700;margin:8px 0 2px">' + l.replace(/^#{1,6}\s+/, '') + '</div>'; }
    else if (/^[-*]\s+/.test(l)) { if (!inList) { html += '<ul style="margin:4px 0;padding-left:18px">'; inList = true; } html += '<li>' + l.replace(/^[-*]\s+/, '') + '</li>'; }
    else if (/^\d+[.)]\s+/.test(l)) { closeList(); html += '<div>' + l + '</div>'; }
    else { closeList(); html += '<div>' + l + '</div>'; }
  }
  closeList();
  return html;
}

function _avpAiPanel(btn) {
  // Monte le panneau en tête de la zone de contenu (pleine largeur, bien placé),
  // sinon juste après le bouton en dernier recours.
  const host = (btn && btn.closest && btn.closest('.avp-main')?.querySelector('.avp-content')) || null;
  let panel = document.getElementById('avp-ai-panel');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'avp-ai-panel';
    panel.className = 'avp-ai-panel';
    panel.style.cssText = 'margin:0 0 18px;padding:14px 16px;border:1px solid var(--border);border-left:3px solid #2D8C5A;border-radius:10px;background:var(--surface);font-size:13px;line-height:1.55;display:none';
    if (host) host.insertBefore(panel, host.firstChild);
    else btn.parentNode.insertBefore(panel, btn.nextSibling);
  }
  return panel;
}

async function avpInterpretModule(module, btn) {
  const panel = _avpAiPanel(btn);
  panel.style.display = 'block';
  panel.innerHTML = '<span style="color:var(--muted)">✨ Aya analyse les données…</span>';
  const prev = btn.disabled; btn.disabled = true;
  try {
    const r = await authFetch('/ai/interpret', { method: 'POST', body: JSON.stringify({ module }) });
    const d = await r.json().catch(() => ({}));
    if (!r || !r.ok) throw new Error(d.detail || 'Interprétation indisponible.');
    panel.innerHTML = '<div style="font-weight:700;color:#1a6b3a;margin-bottom:6px">✨ Lecture d\'Aya' +
      (d.cached ? ' <span style="font-weight:400;font-size:11px;color:var(--muted)">(en cache)</span>' : '') + '</div>' +
      _avpMiniMarkdown(d.text);
  } catch (e) {
    panel.innerHTML = '<span style="color:#922b21">' + (e.message || 'Erreur') + '</span>';
  } finally { btn.disabled = prev; }
}

async function avpTrainingSuggestions(btn) {
  const panel = _avpAiPanel(btn);
  panel.style.display = 'block';
  panel.innerHTML = '<span style="color:var(--muted)">✨ Aya prépare un plan de formation…</span>';
  const prev = btn.disabled; btn.disabled = true;
  try {
    const r = await authFetch('/ai/training-suggestions');
    const d = await r.json().catch(() => ({}));
    if (!r || !r.ok) throw new Error(d.detail || 'Suggestions indisponibles.');
    panel.innerHTML = '<div style="font-weight:700;color:#1a6b3a;margin-bottom:6px">🎓 Plan de formation proposé par Aya' +
      (d.cached ? ' <span style="font-weight:400;font-size:11px;color:var(--muted)">(en cache)</span>' : '') + '</div>' +
      _avpMiniMarkdown(d.text);
  } catch (e) {
    panel.innerHTML = '<span style="color:#922b21">' + (e.message || 'Erreur') + '</span>';
  } finally { btn.disabled = prev; }
}

/* ── Service worker : enregistrement centralisé (offline garanti partout) ──────
   auth.js étant chargé sur les 39 pages, on garantit l'installation du SW quelle
   que soit la page d'entrée (avant, seules 4 pages l'enregistraient). Idempotent :
   sans effet si le SW est déjà enregistré par une page. Enregistré au 'load' pour
   ne pas concurrencer les ressources critiques du 1er rendu. */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => { /* silencieux */ });
  });
}

