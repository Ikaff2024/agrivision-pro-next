/* ============================================================
   AgriVision Pro — auth.js  v2.0
   Refresh token automatique + design system complet
   ============================================================ */

const PROD_API_BASE = 'https://handsome-wisdom-production-d83b.up.railway.app';
const LOCAL_API_BASE = 'http://127.0.0.1:8010';
const API_BASE = (
  window.CG_API_BASE ||
  (['localhost', '127.0.0.1'].includes(window.location.hostname) ? LOCAL_API_BASE : PROD_API_BASE)
);
window.API_BASE = API_BASE;

/* ── Inject shared fonts + design system ───────────────────── */
(function injectDesignSystem() {
  if (document.getElementById('avp-styles')) return;

  const fonts = document.createElement('link');
  fonts.rel = 'stylesheet';
  fonts.href = 'https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,700&family=DM+Sans:wght@400;500;600&display=swap';
  document.head.appendChild(fonts);

  const icons = document.createElement('link');
  icons.rel = 'stylesheet';
  icons.href = 'https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200';
  document.head.appendChild(icons);

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
    .sb-user{padding:14px 14px 18px;border-top:1px solid var(--sb-border);flex-shrink:0}
    .sb-user-inner{display:flex;align-items:center;gap:10px}
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
function toast(msg, type = 'success') {
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

/* ── Auth guards ─────────────────────────────────────────────── */
function requireAuth() {
  // Authentification désactivée - accès libre
  return true;
}

function logout() { localStorage.clear(); window.location.href = 'index.html'; }

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

  // ── Hamburger button (mobile) ─────────────────────────────────────────────
  if (!document.getElementById('avp-hamburger')) {
    const hamburger = document.createElement('button');
    hamburger.id = 'avp-hamburger';
    hamburger.className = 'hamburger';
    hamburger.innerHTML = '<span class="material-symbols-outlined ms">menu</span>';
    hamburger.onclick = toggleSidebar;
    document.body.appendChild(hamburger);

    // Overlay pour fermer la sidebar en cliquant à côté
    const overlay = document.createElement('div');
    overlay.id = 'avp-overlay';
    overlay.className = 'sb-overlay';
    overlay.onclick = closeSidebar;
    document.body.appendChild(overlay);
  }
  const user = getCurrentUser();
  const init = user ? user.email.substring(0, 2).toUpperCase() : '??';
  const links = [
    { id: 'dashboard', href: 'index.html', icon: 'dashboard', label: 'Dashboard' },
    { id: 'plantations', href: 'plantations.html', icon: 'park', label: 'Plantations' },
    { id: 'diagnostic', href: 'diagnostic.html', icon: 'biotech', label: 'Diagnostic' },
    { id: 'map', href: 'map.html', icon: 'map', label: 'Carte' },
    { id: 'analytics', href: 'analytics.html', icon: 'bar_chart_4_bars', label: 'Analytique' },
    { id: 'satellite', href: 'satellite.html', icon: 'satellite_alt', label: 'Satellite' },
    { id: 'agroforestry', href: 'agroforestry.html', icon: 'forest', label: 'Agroforesterie' },
    { id: 'harvests', href: 'harvests.html', icon: 'agriculture', label: 'Récoltes' },
    { id: 'farmforce', href: 'farmforce.html', icon: 'request_quote', label: 'FarmForce' },
    { id: 'cacaoguard', href: 'cacaoguard.html', icon: 'verified_user', label: 'CacaoGuard' },
    { id: 'children', href: 'children.html', icon: 'diversity_3', label: 'Protection enfant' },
    { id: 'risk-assessment', href: 'risk_assessment.html', icon: 'fact_check', label: 'Evaluation risque' },
    { id: 'monitoring', href: 'monitoring.html', icon: 'travel_explore', label: 'Monitoring' },
    { id: 'ssrte', href: 'ssrte.html', icon: 'clinical_notes', label: 'Fiches SSRTE' },
    { id: 'remediation', href: 'remediation.html', icon: 'assignment_turned_in', label: 'Remediation' },
    { id: 'training', href: 'training.html', icon: 'school', label: 'Formation' },
    { id: 'compliance', href: 'compliance.html', icon: 'gpp_maybe', label: 'Conformite' },
    { id: 'reports-cacaoguard', href: 'reports_cacaoguard.html', icon: 'summarize', label: 'Rapports' },
  ];
  // Lien admin uniquement visible pour les administrateurs
  if (user && user.role === 'admin') {
    links.push({ id: 'admin', href: 'admin.html', icon: 'admin_panel_settings', label: 'Administration' });
  }
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
      <div class="sb-sec">Navigation</div>
      ${links.map(l => `
        <a href="${l.href}" class="nav-link ${activePage === l.id ? 'active' : ''}" onclick="closeSidebar()">
          <span class="material-symbols-outlined ms">${l.icon}</span>${l.label}
        </a>`).join('')}
    </nav>
    <div class="sb-user">
      <div class="sb-user-inner">
        <div class="sb-avatar">${init}</div>
        <div class="sb-user-info">
          <div class="sb-user-email">${user ? user.email : ''}</div>
          <div class="sb-user-role">${user ? user.role : ''}</div>
        </div>
        <button class="sb-logout" onclick="logout()" title="Déconnexion">
          <span class="material-symbols-outlined" style="font-size:18px">logout</span>
        </button>
      </div>
    </div>`;
}

function initApp(page) {
  setupNetworkBanner();  // Sprint Honnetete-Offline
  if (!requireAuth()) return;
  renderSidebar(page);
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
