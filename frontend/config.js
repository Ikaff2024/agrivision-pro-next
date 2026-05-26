(function () {
  const LOCAL_API_BASE = 'http://127.0.0.1:8010';
  const STAGING_API_BASE = 'https://agrivision-api-production.up.railway.app';
  const host = window.location.hostname;
  const isLocal = ['localhost', '127.0.0.1'].includes(host);
  const explicitApi = window.AGRIVISION_API_BASE || window.CG_API_BASE;

  window.AGRIVISION_API_BASE = explicitApi || (isLocal ? LOCAL_API_BASE : STAGING_API_BASE);
  window.CG_API_BASE = window.AGRIVISION_API_BASE;
})();
