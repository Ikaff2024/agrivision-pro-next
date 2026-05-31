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
  const init = user ? user.email.substring(0, 2).toUpperCase() : '??';
  const links = [
    { id: 'dashboard', href: 'index.html', icon: 'dashboard', label: 'Dashboard' },
    { id: 'direction', href: 'direction.html', icon: 'insights', label: 'Direction' },
    { id: 'plantations', href: 'plantations.html', icon: 'park', label: 'Plantations' },
    { id: 'diagnostic', href: 'diagnostic.html', icon: 'biotech', label: 'Diagnostic' },
    { id: 'map', href: 'map.html', icon: 'map', label: 'Carte' },
    { id: 'satellite', href: 'satellite.html', icon: 'satellite_alt', label: 'Satellite' },
    { id: 'agroforestry', href: 'agroforestry.html', icon: 'forest', label: 'Agroforesterie' },
    { id: 'harvests', href: 'harvests.html', icon: 'agriculture', label: 'Récoltes' },
    { id: 'purchases', href: 'achats.html', icon: 'shopping_cart', label: 'Achats' },
    { id: 'lots', href: 'lots.html', icon: 'inventory_2', label: 'Traçabilité lots' },
    { id: 'farmforce', href: 'farmforce.html', icon: 'request_quote', label: 'FarmForce' },
    { id: 'cacaoguard', href: 'cacaoguard.html', icon: 'verified_user', label: 'CacaoGuard' },
    { id: 'children', href: 'children.html', icon: 'diversity_3', label: 'Protection enfant' },
    { id: 'risk-assessment', href: 'risk_assessment.html', icon: 'fact_check', label: 'Evaluation risque' },
    { id: 'monitoring', href: 'monitoring.html', icon: 'travel_explore', label: 'Monitoring' },
    { id: 'ssrte', href: 'ssrte.html', icon: 'clinical_notes', label: 'Fiches SSRTE' },
    { id: 'remediation', href: 'remediation.html', icon: 'assignment_turned_in', label: 'Remediation' },
    { id: 'complaints', href: 'complaints.html', icon: 'report', label: 'Signalements' },
    { id: 'training', href: 'training.html', icon: 'school', label: 'Formation' },
    { id: 'compliance', href: 'compliance.html', icon: 'gpp_maybe', label: 'Conformite' },
    { id: 'certification', href: 'certification.html', icon: 'workspace_premium', label: 'Certification' },
    { id: 'eudr', href: 'eudr.html', icon: 'eco', label: 'EUDR' },
    { id: 'reports-cacaoguard', href: 'reports_cacaoguard.html', icon: 'summarize', label: 'Rapports' },
  ];
  if (user && user.role === 'admin') {
    links.push({ id: 'admin', href: 'admin.html', icon: 'admin_panel_settings', label: 'Administration' });
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
      <div class="sb-sec">Navigation</div>
      ${links.map(l => `
        <a href="${l.href}" data-mod="${l.id}" class="nav-link ${activePage === l.id ? 'active' : ''}" onclick="closeSidebar()">
          <span class="material-symbols-outlined ms">${l.icon}</span>${l.label}
        </a>`).join('')}
    </nav>
    ${userBlock}`;
}
// Masque les modules de menu hors plan de la cooperative (feature-gating).
// Non-bloquant : si l'appel echoue ou plan inconnu, on n'enleve rien.
async function applyPlanFeatures(activePage) {
  try {
    const res = await authFetch('/me/features');
    if (!res || !res.ok) return;
    const data = await res.json();
    const allowed = new Set(data.modules || []);
    if (!allowed.size) return;
    document.querySelectorAll('#sidebar a.nav-link[data-mod]').forEach(a => {
      const mod = a.getAttribute('data-mod');
      if (!allowed.has(mod)) a.style.display = 'none';
    });
    // Si la page courante n'est pas autorisee par le plan, rediriger vers l'accueil.
    if (activePage && !allowed.has(activePage) && activePage !== 'dashboard') {
      window.location.replace('index.html');
    }
  } catch (e) { /* non-bloquant */ }
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

