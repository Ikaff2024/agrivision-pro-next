/**
 * AgriVision Pro — Conseil Agronome IA
 * Charge séparément pour éviter les conflits de cache SW.
 */
// AI advice offline UX fix : detection offline + UI dediee
async function loadAIAdvice() {
  var btn = document.getElementById('ai-btn');
  var spinner = document.getElementById('ai-spinner');
  var btnTxt = document.getElementById('ai-btn-txt');
  var result = document.getElementById('ai-result');
  if (!btn || !result) { console.error('AI elements not found'); return; }

  // AI advice offline UX fix : court-circuit si hors ligne
  // Le Conseil IA appelle Claude API en temps reel et ne peut pas
  // etre mis en queue (la valeur est dans le contexte instantane).
  if (!navigator.onLine) {
    _avpShowAIOfflineState();
    return;
  }

  btn.disabled = true;
  if (spinner) spinner.style.display = 'block';
  if (btnTxt) btnTxt.textContent = 'Analyse en cours...';
  result.style.display = 'none';
  result.innerHTML = '';

  try {
    var r = await authFetch('/plantations/' + pid + '/ai-advice', { method: 'POST' });
    if (!r || !r.ok) throw new Error('Erreur serveur ' + (r ? r.status : ''));
    var d = await r.json();

    if (d.error) {
      result.innerHTML = '<div class="ai-error">' + esc(d.error) + '</div>';
      result.style.cssText = 'display:block!important';
      return;
    }

    var html = '';
    if (d.resume) {
      html += '<div class="ai-resume">' + esc(d.resume) + '</div>';
    }
    if (d.points_forts && d.points_forts.length) {
      html += '<div class="ai-section-title">✅ Points forts</div><div class="ai-tags">';
      d.points_forts.forEach(function(p) {
        html += '<span class="ai-tag">' + esc(p) + '</span>';
      });
      html += '</div>';
    }
    if (d.risques_prioritaires && d.risques_prioritaires.length) {
      html += '<div class="ai-section-title">⚠️ Risques prioritaires</div><div class="ai-tags">';
      d.risques_prioritaires.forEach(function(rr) {
        html += '<span class="ai-tag risk">' + esc(rr) + '</span>';
      });
      html += '</div>';
    }
    if (d.actions && d.actions.length) {
      html += '<div class="ai-section-title">🎯 Actions recommandées</div><div class="ai-actions">';
      d.actions.forEach(function(a) {
        var dot = a.priorite === 'urgent' ? 'urgent' : (a.priorite === 'important' ? 'important' : 'conseil');
        html += '<div class="ai-action">';
        html += '<div class="ai-action-dot ' + dot + '"></div>';
        html += '<div class="ai-action-body">';
        html += '<div class="ai-action-title">' + esc(a.titre) + '</div>';
        html += '<div class="ai-action-detail">' + esc(a.detail) + '</div>';
        if (a.impact) html += '<div class="ai-action-impact">→ ' + esc(a.impact) + '</div>';
        html += '</div></div>';
      });
      html += '</div>';
    }
    if (d.perspective_eudr) {
      html += '<div class="ai-section-title">🌿 Conformité EUDR</div>';
      html += '<div class="ai-eudr">' + esc(d.perspective_eudr) + '</div>';
    }
    if (d.score_potentiel) {
      html += '<div class="ai-score-row">';
      html += '<span class="ai-score-label">Score potentiel estimé</span>';
      html += '<span class="ai-score-val">' + d.score_potentiel + '/100</span>';
      html += '</div>';
    }

    result.innerHTML = html;
    result.style.cssText = 'display:block!important;margin-top:14px';

  } catch(e) {
    console.error('AI advice error:', e);
    result.innerHTML = '<div class="ai-error">Analyse indisponible : ' + esc(e.message) + '</div>';
    result.style.cssText = 'display:block!important';
  } finally {
    if (btn) btn.disabled = false;
    if (spinner) spinner.style.display = 'none';
    if (btnTxt) btnTxt.textContent = "Relancer l'analyse";
  }
}


// AI advice offline UX fix : helper d'affichage etat offline
function _avpShowAIOfflineState() {
  var btn = document.getElementById('ai-btn');
  var btnTxt = document.getElementById('ai-btn-txt');
  var spinner = document.getElementById('ai-spinner');
  var result = document.getElementById('ai-result');
  if (!result) return;

  // UI dediee offline : message clair + bouton desactive
  result.innerHTML = '<div class="ai-error" style="background:#fef3c7;color:#78350f;border:1px solid #d97706;padding:14px 16px;border-radius:8px;line-height:1.55;font-size:13.5px">' +
    '<div style="font-weight:600;margin-bottom:6px">📡 Conseil IA indisponible hors ligne</div>' +
    'Le Conseil Agronome IA nécessite une connexion Internet pour analyser cette plantation. ' +
    'Reconnectez-vous puis cliquez sur "Relancer l\'analyse" pour obtenir vos recommandations.' +
    '</div>';
  result.style.cssText = 'display:block!important;margin-top:14px';

  // Bouton : visuellement et fonctionnellement desactive
  if (btn) {
    btn.disabled = true;
    btn.style.opacity = '0.6';
    btn.style.cursor = 'not-allowed';
  }
  if (btnTxt) btnTxt.textContent = "Reconnectez-vous d'abord";
  if (spinner) spinner.style.display = 'none';
}

// AI advice offline UX fix : helper de retour en ligne (reactive le bouton)
function _avpShowAIOnlineReady() {
  var btn = document.getElementById('ai-btn');
  var btnTxt = document.getElementById('ai-btn-txt');
  if (!btn) return;
  // Reactiver le bouton seulement s'il etait desactive a cause de l'offline
  // (on ne reactive PAS pendant qu'une analyse est en cours)
  if (btnTxt && btnTxt.textContent === "Reconnectez-vous d'abord") {
    btn.disabled = false;
    btn.style.opacity = '';
    btn.style.cursor = '';
    btnTxt.textContent = "Relancer l'analyse";
    // Effacer le message d'erreur offline (l'utilisateur peut maintenant cliquer)
    var result = document.getElementById('ai-result');
    if (result) {
      result.style.display = 'none';
      result.innerHTML = '';
    }
  }
}

// AI advice offline UX fix : init au chargement de la page
// Si la page demarre offline, on affiche immediatement l'etat correct
(function _avpInitAIAdviceOfflineUX() {
  function _init() {
    // Attendre que les elements DOM soient prets ET que le module ai-advice
    // soit reellement utilise (bouton ai-btn present dans la page)
    var btn = document.getElementById('ai-btn');
    if (!btn) return;
    if (!navigator.onLine) {
      _avpShowAIOfflineState();
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }
  // Reagir aux changements de connectivite
  window.addEventListener('online', _avpShowAIOnlineReady);
  window.addEventListener('offline', function() {
    var btn = document.getElementById('ai-btn');
    if (btn && !btn.disabled) {
      // Si l'utilisateur perd le reseau pendant que le bouton est actif,
      // on l'avertit (mais on n'interrompt pas une analyse en cours).
      var btnTxt = document.getElementById('ai-btn-txt');
      if (btnTxt && btnTxt.textContent === "Relancer l'analyse") {
        _avpShowAIOfflineState();
      }
    }
  });
})();
