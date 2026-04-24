/**
 * AgriVision Pro — Conseil Agronome IA
 * Charge séparément pour éviter les conflits de cache SW.
 */
async function loadAIAdvice() {
  var btn = document.getElementById('ai-btn');
  var spinner = document.getElementById('ai-spinner');
  var btnTxt = document.getElementById('ai-btn-txt');
  var result = document.getElementById('ai-result');
  if (!btn || !result) { console.error('AI elements not found'); return; }

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
