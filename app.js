const state = {
  mode: 'quiz',
  questions: [],
  byId: new Map(),
  quizCurrent: null,
  examQueue: [],
  examIndex: 0,
  examActive: false,
  examEndsAt: 0,
  examTimer: null,
  installPrompt: null,
  progress: loadProgress(),
};

const el = {
  quizCard: document.getElementById('quizCard'),
  examCard: document.getElementById('examCard'),
  reviewList: document.getElementById('reviewList'),
  reviewSearch: document.getElementById('reviewSearch'),
  progressBox: document.getElementById('progressBox'),
  examStart: document.getElementById('examStart'),
  examFinish: document.getElementById('examFinish'),
  examTimer: document.getElementById('examTimer'),
  quizNext: document.getElementById('quizNext'),
  toast: document.getElementById('toast'),
  installBtn: document.getElementById('installBtn'),
};

init();

async function init() {
  const res = await fetch('data/questions.json');
  state.questions = await res.json();
  state.questions.forEach((q) => state.byId.set(q.id, q));
  bindUI();
  renderQuiz(nextQuizQuestion());
  renderReview();
  renderProgress();
  registerSW();
}

function bindUI() {
  document.querySelectorAll('.bottom-nav button').forEach((btn) => {
    btn.addEventListener('click', () => switchMode(btn.dataset.mode));
  });

  el.quizNext.addEventListener('click', () => renderQuiz(nextQuizQuestion()));
  el.examStart.addEventListener('click', startExam);
  el.examFinish.addEventListener('click', finishExam);
  el.reviewSearch.addEventListener('input', renderReview);

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    state.installPrompt = e;
    el.installBtn.hidden = false;
  });

  el.installBtn.addEventListener('click', async () => {
    if (!state.installPrompt) return;
    await state.installPrompt.prompt();
    state.installPrompt = null;
    el.installBtn.hidden = true;
  });

  bindSwipe(el.quizCard, () => renderQuiz(nextQuizQuestion()));
  bindSwipe(el.examCard, () => {
    if (state.examActive) goExamNext();
  });
}

function switchMode(mode) {
  state.mode = mode;
  document.querySelectorAll('.mode').forEach((m) => m.classList.remove('active'));
  document.querySelector(`#mode-${mode}`).classList.add('active');
  document.querySelectorAll('.bottom-nav button').forEach((b) => b.classList.toggle('active', b.dataset.mode === mode));
  if (mode === 'progress') renderProgress();
}

function renderQuestionCard(container, q, opts = {}) {
  if (!q) {
    container.innerHTML = '<p class="muted">No hay preguntas disponibles.</p>';
    return;
  }

  const sec = `${q.exam} · ${q.section} T${q.teil} · #${q.number}`;
  const options = (q.options || []).map((opt, i) => {
    const label = String(opt);
    const val = parseOptKey(label, i);
    return `<button data-val="${escapeHtml(val)}">${escapeHtml(label)}</button>`;
  }).join('');

  container.innerHTML = `
    <div class="section-tag">${escapeHtml(sec)}</div>
    <div class="context">${wrapVocab(q.context || '')}</div>
    <div class="question">${escapeHtml(q.question || 'Pregunta')}</div>
    <div class="options">${options}</div>
    <div class="muted">Instrucción: ${escapeHtml(q.instruction || '')}</div>
    <div class="feedback" id="feedback" hidden></div>
  `;

  container.querySelectorAll('.vocab-hit').forEach((hit) => {
    hit.addEventListener('click', () => showToast(hit.dataset.tip));
  });

  container.querySelectorAll('.options button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const chosen = btn.dataset.val;
      const right = normalizeAnswer(q.correct);
      const ok = chosen === right;

      registerAnswer(q, ok);
      container.querySelectorAll('.options button').forEach((b) => {
        const v = b.dataset.val;
        if (v === right) b.classList.add('correct');
        if (v === chosen && !ok) b.classList.add('wrong');
        b.disabled = true;
      });

      const fb = container.querySelector('#feedback');
      fb.hidden = false;
      fb.className = `feedback ${ok ? 'ok' : 'bad'}`;
      fb.innerHTML = `
        <div><strong>${ok ? 'Correcto' : 'Incorrecto'}</strong> · Respuesta: ${escapeHtml(q.correct || '?')}</div>
        <div>${escapeHtml(q.explanation_es || 'Sin explicación disponible.')}</div>
        ${renderVocab(q.vocabulary || [])}
      `;

      if (opts.onAnswered) opts.onAnswered();
      renderProgress();
    }, { once: true });
  });
}

function renderQuiz(q) {
  state.quizCurrent = q;
  renderQuestionCard(el.quizCard, q);
}

function nextQuizQuestion() {
  const weights = state.questions.map((q) => {
    const p = state.progress.answers[q.id] || { seen: 0, wrong: 0 };
    const wrongBias = p.wrong > 0 ? 2 : 1;
    return Math.max(1, wrongBias + Math.floor((5 - Math.min(5, p.seen)) / 2));
  });

  const total = weights.reduce((a, b) => a + b, 0);
  let r = Math.random() * total;
  for (let i = 0; i < state.questions.length; i++) {
    r -= weights[i];
    if (r <= 0) return state.questions[i];
  }
  return state.questions[0];
}

function startExam() {
  const shuffled = [...state.questions].sort(() => Math.random() - 0.5);
  state.examQueue = shuffled.slice(0, 40);
  state.examIndex = 0;
  state.examActive = true;
  state.examEndsAt = Date.now() + 60 * 60 * 1000;
  el.examFinish.disabled = false;

  if (state.examTimer) clearInterval(state.examTimer);
  state.examTimer = setInterval(updateExamTimer, 1000);
  updateExamTimer();
  renderExamCurrent();
}

function renderExamCurrent() {
  if (!state.examActive) {
    el.examCard.innerHTML = '<p class="muted">Inicia un examen para empezar.</p>';
    return;
  }
  const q = state.examQueue[state.examIndex];
  if (!q) return finishExam();
  renderQuestionCard(el.examCard, q, { onAnswered: goExamNext });
}

function goExamNext() {
  if (!state.examActive) return;
  state.examIndex += 1;
  if (state.examIndex >= state.examQueue.length) {
    finishExam();
    return;
  }
  renderExamCurrent();
}

function finishExam() {
  state.examActive = false;
  el.examFinish.disabled = true;
  if (state.examTimer) clearInterval(state.examTimer);
  updateExamTimer();
  const attempted = state.examQueue.length;
  const acc = calcAccuracy();
  el.examCard.innerHTML = `<div class="feedback ok"><strong>Examen finalizado.</strong><br>Preguntas: ${attempted}<br>Precisión global: ${acc}%</div>`;
}

function updateExamTimer() {
  if (!state.examActive) {
    el.examTimer.textContent = '60:00';
    return;
  }
  const left = Math.max(0, state.examEndsAt - Date.now());
  if (left <= 0) {
    finishExam();
    return;
  }
  const mins = Math.floor(left / 60000);
  const secs = Math.floor((left % 60000) / 1000);
  el.examTimer.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function renderReview() {
  const query = el.reviewSearch.value.trim().toLowerCase();
  const rows = state.questions.filter((q) => {
    if (!query) return true;
    return (`${q.context} ${q.question} ${q.explanation_es}`).toLowerCase().includes(query);
  }).slice(0, 200);

  el.reviewList.innerHTML = rows.map((q) => `
    <details class="review-item">
      <summary>${escapeHtml(q.exam)} · ${escapeHtml(q.section)} T${q.teil} · #${q.number}</summary>
      <p><strong>Pregunta:</strong> ${escapeHtml(q.question)}</p>
      <p class="muted"><strong>Correcta:</strong> ${escapeHtml(q.correct || '?')}</p>
      <p>${escapeHtml(q.explanation_es || '')}</p>
      ${renderVocab(q.vocabulary || [])}
    </details>
  `).join('') || '<p class="muted">Sin resultados.</p>';
}

function renderProgress() {
  const total = Object.keys(state.progress.answers).length;
  const acc = calcAccuracy();
  const streak = state.progress.streak || 0;

  const sectionStats = {};
  for (const q of state.questions) {
    const key = `${q.section} T${q.teil}`;
    const p = state.progress.answers[q.id];
    if (!p || !p.seen) continue;
    sectionStats[key] ||= { seen: 0, ok: 0 };
    sectionStats[key].seen += p.seen;
    sectionStats[key].ok += p.ok;
  }

  const bySection = Object.entries(sectionStats)
    .map(([k, v]) => `<li>${escapeHtml(k)}: ${Math.round((v.ok / Math.max(1, v.seen)) * 100)}%</li>`)
    .join('');

  el.progressBox.innerHTML = `
    <p><strong>Preguntas practicadas:</strong> ${total}</p>
    <p><strong>Precisión global:</strong> ${acc}%</p>
    <p><strong>Racha actual:</strong> ${streak}</p>
    <p><strong>Por sección:</strong></p>
    <ul>${bySection || '<li class="muted">Aún sin datos</li>'}</ul>
  `;
}

function registerAnswer(q, ok) {
  const rec = state.progress.answers[q.id] || { seen: 0, ok: 0, wrong: 0 };
  rec.seen += 1;
  if (ok) {
    rec.ok += 1;
    state.progress.streak = (state.progress.streak || 0) + 1;
  } else {
    rec.wrong += 1;
    state.progress.streak = 0;
  }
  state.progress.answers[q.id] = rec;
  saveProgress();
}

function loadProgress() {
  try {
    return JSON.parse(localStorage.getItem('telc_b1_progress') || '{"answers":{},"streak":0}');
  } catch {
    return { answers: {}, streak: 0 };
  }
}

function saveProgress() {
  localStorage.setItem('telc_b1_progress', JSON.stringify(state.progress));
}

function calcAccuracy() {
  let seen = 0;
  let ok = 0;
  Object.values(state.progress.answers).forEach((p) => {
    seen += p.seen || 0;
    ok += p.ok || 0;
  });
  return Math.round((ok / Math.max(1, seen)) * 100);
}

function parseOptKey(opt, i) {
  const m = String(opt).match(/^([A-Za-zXx])\)?/);
  if (m) return m[1].toUpperCase();
  return String.fromCharCode(65 + (i % 26));
}

function normalizeAnswer(ans) {
  return String(ans || '?').trim().charAt(0).toUpperCase();
}

function renderVocab(items) {
  if (!items.length) return '';
  return `<div class="vocab">${items.map((v) => `<span>${escapeHtml(v.de)} = ${escapeHtml(v.es)}</span>`).join('')}</div>`;
}

function wrapVocab(text) {
  if (!text) return '';
  const toks = text.split(/(\s+)/);
  return toks.map((t) => {
    const k = t.replace(/[^A-Za-zÄÖÜäöüß]/g, '').toLowerCase();
    if (!k) return escapeHtml(t);
    const hit = state.questions.find((q) => (q.vocabulary || []).some((v) => v.de.toLowerCase() === k));
    if (!hit) return escapeHtml(t);
    const vv = (hit.vocabulary || []).find((v) => v.de.toLowerCase() === k);
    if (!vv) return escapeHtml(t);
    return `<span class="vocab-hit" data-tip="${escapeHtml(`${vv.de} = ${vv.es}`)}">${escapeHtml(t)}</span>`;
  }).join('');
}

function showToast(msg) {
  el.toast.textContent = msg;
  el.toast.hidden = false;
  setTimeout(() => { el.toast.hidden = true; }, 1800);
}

function bindSwipe(node, onLeft) {
  let sx = 0;
  node.addEventListener('touchstart', (e) => { sx = e.changedTouches[0].clientX; }, { passive: true });
  node.addEventListener('touchend', (e) => {
    const dx = e.changedTouches[0].clientX - sx;
    if (dx < -70) onLeft();
  }, { passive: true });
}

function escapeHtml(s) {
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function registerSW() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
}
