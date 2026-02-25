const DAILY_GOAL_DEFAULT = 60;
const INACTIVITY_MS = 2 * 60 * 1000;

const state = {
  mode: 'quiz',
  showTranslation: loadTranslationPref(),
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
  study: {
    active: false,
    lastInteraction: 0,
    lastTick: Date.now(),
    carryMs: 0,
    timer: null,
    goalCelebratedDate: null,
    unsavedSeconds: 0,
  },
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
  goalTracker: document.getElementById('goalTracker'),
  goalText: document.getElementById('goalText'),
  goalStatus: document.getElementById('goalStatus'),
  goalFill: document.getElementById('goalFill'),
  confettiLayer: document.getElementById('confettiLayer'),
  translationToggle: document.getElementById('translationToggle'),
};

init();

async function init() {
  const res = await fetch('data/questions.json');
  state.questions = await res.json();
  state.questions.forEach((q) => state.byId.set(q.id, q));
  bindUI();
  startStudyClock();
  renderQuiz(nextQuizQuestion());
  renderReview();
  renderProgress();
  renderGoalTracker();
  updateGoalTrackerVisibility();
  registerSW();
}

function bindUI() {
  document.querySelectorAll('.bottom-nav button').forEach((btn) => {
    btn.addEventListener('click', () => switchMode(btn.dataset.mode));
  });

  el.quizNext.addEventListener('click', () => {
    registerInteraction();
    renderQuiz(nextQuizQuestion());
  });
  el.examStart.addEventListener('click', () => {
    registerInteraction();
    startExam();
  });
  el.examFinish.addEventListener('click', () => {
    registerInteraction();
    finishExam();
  });
  el.reviewSearch.addEventListener('input', () => {
    registerInteraction();
    renderReview();
  });

  if (el.translationToggle) {
    el.translationToggle.checked = !!state.showTranslation;
    el.translationToggle.addEventListener('change', () => {
      state.showTranslation = el.translationToggle.checked;
      saveTranslationPref(state.showTranslation);
      if (state.quizCurrent) renderQuiz(state.quizCurrent);
      if (state.examActive) renderExamCurrent();
    });
  }

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    state.installPrompt = e;
    el.installBtn.hidden = false;
  });

  el.installBtn.addEventListener('click', async () => {
    if (!state.installPrompt) return;
    registerInteraction();
    await state.installPrompt.prompt();
    state.installPrompt = null;
    el.installBtn.hidden = true;
  });

  const interactionEvents = ['pointerdown', 'keydown', 'touchstart'];
  interactionEvents.forEach((evt) => {
    document.addEventListener(evt, registerInteraction, { passive: true });
  });

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      state.study.active = false;
      flushStudySave();
    }
  });
  window.addEventListener('beforeunload', flushStudySave);

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
  updateGoalTrackerVisibility();
  renderGoalTracker();
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
    const tr = state.showTranslation ? optionTranslation(q, label) : '';
    return `<button data-val="${escapeHtml(val)}">${escapeHtml(label)}${tr ? `<div class="translation-line">${escapeHtml(tr)}</div>` : ''}</button>`;
  }).join('');

  const questionEs = state.showTranslation ? (q.question_es || inferQuestionTranslation(q)) : '';

  container.innerHTML = `
    <div class="section-tag">${escapeHtml(sec)}</div>
    <div class="context">${wrapVocab(q.context || '')}</div>
    <div class="question">${escapeHtml(q.question || 'Pregunta')}${questionEs ? `<div class="translation-line">${escapeHtml(questionEs)}</div>` : ''}</div>
    <div class="options">${options}</div>
    <div class="muted">Instrucción: ${escapeHtml(q.instruction || '')}</div>
    <div class="feedback" id="feedback" hidden></div>
  `;

  container.querySelectorAll('.vocab-hit').forEach((hit) => {
    hit.addEventListener('click', () => {
      registerInteraction();
      showToast(hit.dataset.tip);
    });
  });

  container.querySelectorAll('.options button').forEach((btn) => {
    btn.addEventListener('click', () => {
      registerInteraction();
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
      renderGoalTracker();
    }, { once: true });
  });
}

function renderQuiz(q) {
  state.quizCurrent = q;
  renderQuestionCard(el.quizCard, q);
}

function nextQuizQuestion() {
  const masteredPool = [];
  const regularPool = [];

  state.questions.forEach((q) => {
    const p = ensureAnswerRecord(state.progress.answers[q.id]);
    if (p.mastered && p.reviewCount === 0) masteredPool.push({ q, p });
    else regularPool.push({ q, p });
  });

  const useMastered = masteredPool.length > 0 && (regularPool.length === 0 || Math.random() < 0.1);
  const pool = useMastered ? masteredPool : regularPool;

  const weights = pool.map(({ p }) => {
    let base = 1;
    if (p.reviewCount > 0) base = 2;
    const freshness = Math.max(0, 3 - Math.min(3, p.seen)) * 0.4;
    return base + freshness;
  });

  const total = weights.reduce((a, b) => a + b, 0);
  let r = Math.random() * total;
  for (let i = 0; i < pool.length; i++) {
    r -= weights[i];
    if (r <= 0) return pool[i].q;
  }
  return pool[0]?.q || state.questions[0];
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
  const sectionKeys = [
    'Leseverstehen T1',
    'Leseverstehen T2',
    'Leseverstehen T3',
    'Sprachbausteine T1',
    'Sprachbausteine T2',
  ];
  const sectionStats = {};
  sectionKeys.forEach((k) => { sectionStats[k] = { seen: 0, ok: 0 }; });

  let practicedQuestions = 0;
  let mastered = 0;
  let learning = 0;
  let isNew = 0;

  for (const q of state.questions) {
    const key = `${q.section} T${q.teil}`;
    const rec = ensureAnswerRecord(state.progress.answers[q.id]);
    if (sectionStats[key] && rec.seen > 0) {
      sectionStats[key].seen += rec.seen;
      sectionStats[key].ok += rec.ok;
    }
    if (rec.seen > 0) practicedQuestions += 1;
    if (rec.mastered) mastered += 1;
    else if (rec.seen === 0) isNew += 1;
    else learning += 1;
  }

  const totalQuestions = state.questions.length || 640;
  const acc = calcAccuracy();
  const todayKey = getDateKey();
  const streakCurrent = getDisplayedStreak();
  const streakLongest = state.progress.streak.longest || 0;
  const warning = getStreakWarning();
  const totalStudyMin = Math.round(getTotalStudySeconds() / 60);
  const masteredPct = Math.round((mastered / Math.max(1, totalQuestions)) * 100);

  const sectionRows = sectionKeys.map((k) => {
    const s = sectionStats[k];
    const pct = s.seen > 0 ? Math.round((s.ok / s.seen) * 100) : 0;
    return `<li><span>${escapeHtml(k)}</span><strong>${s.seen > 0 ? `${pct}%` : 'Sin datos'}</strong></li>`;
  }).join('');

  const weekly = getLastNDates(7).map((day) => {
    const minutes = Math.round((state.progress.dailySeconds[day] || 0) / 60);
    return { day, minutes };
  });
  const maxMinute = Math.max(1, ...weekly.map((d) => d.minutes));
  const weeklyBars = weekly.map(({ day, minutes }) => {
    const h = Math.round((minutes / maxMinute) * 100);
    const label = day.slice(5);
    return `
      <div class="bar-col">
        <div class="bar"><span style="--h:${h}%"></span></div>
        <div class="bar-value">${minutes}m</div>
        <div class="bar-label">${escapeHtml(label)}</div>
      </div>
    `;
  }).join('');

  const forecast = buildForecast({ mastered, totalQuestions, accuracy: acc, todayKey });

  el.progressBox.innerHTML = `
    <p><strong>🔥 Racha actual:</strong> ${streakCurrent} días</p>
    <p><strong>🏆 Récord de racha:</strong> ${streakLongest} días</p>
    ${warning ? '<div class="warn-box">Ayer estudiaste, pero hoy todavía no. Tu racha está en riesgo.</div>' : ''}
    <p><strong>Preguntas practicadas:</strong> ${practicedQuestions}/${totalQuestions}</p>
    <p><strong>Precisión global:</strong> ${acc}%</p>
    <p><strong>Tiempo total estudiado:</strong> ${totalStudyMin} min</p>

    <p><strong>Precisión por sección:</strong></p>
    <ul class="section-list">${sectionRows}</ul>

    <p><strong>Niveles de dominio:</strong></p>
    <ul class="mastery-legend">
      <li>🔴 Nuevas: ${isNew}</li>
      <li>🟡 En aprendizaje: ${learning}</li>
      <li>🟢 Dominadas (3+ seguidas): ${mastered}</li>
    </ul>
    <p><strong>Preguntas dominadas:</strong> ${mastered}/${totalQuestions}</p>
    <div class="simple-progress"><span style="width:${masteredPct}%"></span></div>

    <p><strong>Últimos 7 días (minutos):</strong></p>
    <div class="weekly-chart">${weeklyBars}</div>

    <div class="forecast">
      <strong>📅 ${forecast.dateLine}</strong>
      <div>${forecast.confidence}</div>
      <div>${forecast.paceMessage}</div>
      ${forecast.milestones}
    </div>
  `;
}

function buildForecast({ mastered, totalQuestions, accuracy, todayKey }) {
  const studyDays = Object.entries(state.progress.dailySeconds).filter(([, secs]) => secs > 0).length;
  if (studyDays < 3) {
    return {
      dateLine: 'Fecha estimada: Necesito más datos',
      confidence: 'Necesito más datos — sigue practicando unos días.',
      paceMessage: '',
      milestones: '',
    };
  }

  const velocity = getRollingMasteryVelocity(7, 0);
  if (velocity <= 0) {
    return {
      dateLine: 'Fecha estimada: Necesito más datos',
      confidence: 'Aún no hay progreso de dominio suficiente para estimar fecha.',
      paceMessage: '',
      milestones: '',
    };
  }

  const remaining = Math.max(0, totalQuestions - mastered);
  const estimateDays = estimateDaysToReady({ remaining, velocity, accuracy });
  const estimatedDate = addDays(todayKey, Math.ceil(estimateDays));

  let paceMessage = 'Mantén este ritmo para seguir adelantando la fecha.';
  const prevVelocity = getRollingMasteryVelocity(7, 7);
  if (prevVelocity > 0) {
    const prevDays = estimateDaysToReady({ remaining, velocity: prevVelocity, accuracy });
    const prevDate = addDays(todayKey, Math.ceil(prevDays));
    if (velocity < prevVelocity * 0.9) {
      paceMessage = `Tu ritmo bajó esta semana — a este paso, la fecha se mueve a ${formatDateEs(estimatedDate)}.`;
    } else if (velocity > prevVelocity * 1.1) {
      paceMessage = `¡Vas más rápido! Fecha adelantada a ${formatDateEs(estimatedDate)} (antes: ${formatDateEs(prevDate)}).`;
    }
  }

  const milestones = [25, 50, 75, 100].map((pct) => {
    const target = Math.ceil((pct / 100) * totalQuestions);
    if (mastered >= target) return `<li>${pct}%: Cumplido</li>`;
    const days = estimateDaysToReady({ remaining: target - mastered, velocity, accuracy });
    return `<li>${pct}%: ${formatDateEs(addDays(todayKey, Math.ceil(days)))}</li>`;
  }).join('');

  return {
    dateLine: `Fecha estimada: ${formatDateEs(estimatedDate)}`,
    confidence: `Al ritmo actual, estarás listo en ~${Math.ceil(estimateDays)} días.`,
    paceMessage,
    milestones: `<ul class="milestones">${milestones}</ul>`,
  };
}

function estimateDaysToReady({ remaining, velocity, accuracy }) {
  let days = remaining / Math.max(0.01, velocity);
  if (accuracy < 60) days *= 1.5;
  days *= 1.2;
  return days;
}

function renderGoalTracker() {
  const goal = state.progress.dailyGoalMinutes || DAILY_GOAL_DEFAULT;
  const today = getDateKey();
  const secs = state.progress.dailySeconds[today] || 0;
  const mins = Math.floor(secs / 60);
  const pct = Math.min(100, Math.round((mins / goal) * 100));
  const warning = getStreakWarning();

  el.goalText.textContent = `${mins}/${goal} min`;
  el.goalFill.style.width = `${pct}%`;
  if (mins >= goal) {
    el.goalStatus.textContent = 'Objetivo cumplido hoy';
  } else if (warning) {
    el.goalStatus.textContent = 'Ayer estudiaste. Hoy aún no.';
  } else {
    el.goalStatus.textContent = 'Objetivo diario';
  }
}

function updateGoalTrackerVisibility() {
  const visible = state.mode === 'quiz' || state.mode === 'exam';
  el.goalTracker.hidden = !visible;
}

function registerAnswer(q, ok) {
  const rec = ensureAnswerRecord(state.progress.answers[q.id]);
  rec.seen += 1;
  const today = getDateKey();

  if (ok) {
    rec.ok += 1;
    rec.correctStreak += 1;
    if (rec.reviewCount > 0) rec.reviewCount -= 1;
    if (!rec.mastered && rec.correctStreak >= 3) {
      rec.mastered = true;
      rec.masteredAt = today;
      state.progress.masteredByDate[today] = (state.progress.masteredByDate[today] || 0) + 1;
    }
  } else {
    rec.wrong += 1;
    rec.correctStreak = 0;
    rec.reviewCount += 1;
  }

  state.progress.answers[q.id] = rec;
  saveProgress();
}

function startStudyClock() {
  if (state.study.timer) clearInterval(state.study.timer);
  state.study.lastTick = Date.now();
  state.study.timer = setInterval(() => {
    const now = Date.now();
    const delta = now - state.study.lastTick;
    state.study.lastTick = now;

    if (!isTrackableMode()) {
      state.study.active = false;
      return;
    }

    if (state.study.active && now - state.study.lastInteraction <= INACTIVITY_MS) {
      addStudyTime(delta);
    } else if (state.study.active) {
      state.study.active = false;
      flushStudySave();
    }

    renderGoalTracker();
    if (state.mode === 'progress' && now % 5000 < 1000) renderProgress();
  }, 1000);
}

function registerInteraction() {
  if (!isTrackableMode()) return;
  state.study.lastInteraction = Date.now();
  state.study.active = true;
}

function addStudyTime(deltaMs) {
  state.study.carryMs += deltaMs;
  let addedSeconds = 0;
  while (state.study.carryMs >= 1000) {
    state.study.carryMs -= 1000;
    addedSeconds += 1;
  }
  if (!addedSeconds) return;

  const day = getDateKey();
  state.progress.dailySeconds[day] = (state.progress.dailySeconds[day] || 0) + addedSeconds;
  state.study.unsavedSeconds += addedSeconds;
  maybeUnlockGoal(day);

  if (state.study.unsavedSeconds >= 10) flushStudySave();
}

function maybeUnlockGoal(day) {
  const goalSeconds = (state.progress.dailyGoalMinutes || DAILY_GOAL_DEFAULT) * 60;
  const todaySeconds = state.progress.dailySeconds[day] || 0;
  if (todaySeconds < goalSeconds) return;
  if (state.progress.streak.lastGoalDate === day) return;

  if (isYesterday(state.progress.streak.lastGoalDate, day)) {
    state.progress.streak.current += 1;
  } else {
    state.progress.streak.current = 1;
  }
  state.progress.streak.longest = Math.max(state.progress.streak.longest, state.progress.streak.current);
  state.progress.streak.lastGoalDate = day;
  saveProgress();

  if (state.study.goalCelebratedDate !== day) {
    state.study.goalCelebratedDate = day;
    triggerConfetti();
    showToast('Objetivo diario cumplido. ¡Excelente!');
  }
}

function flushStudySave() {
  if (!state.study.unsavedSeconds) return;
  state.study.unsavedSeconds = 0;
  saveProgress();
}

function isTrackableMode() {
  return state.mode === 'quiz' || state.mode === 'exam' || state.mode === 'review';
}

function getDisplayedStreak() {
  const current = state.progress.streak.current || 0;
  const lastGoalDate = state.progress.streak.lastGoalDate;
  if (!lastGoalDate) return 0;
  const today = getDateKey();
  if (lastGoalDate === today) return current;
  if (isYesterday(lastGoalDate, today)) return current;
  return 0;
}

function getStreakWarning() {
  const today = getDateKey();
  const yesterday = addDays(today, -1);
  const ySecs = state.progress.dailySeconds[yesterday] || 0;
  const tSecs = state.progress.dailySeconds[today] || 0;
  return ySecs > 0 && tSecs === 0;
}

function getTotalStudySeconds() {
  return Object.values(state.progress.dailySeconds).reduce((sum, secs) => sum + secs, 0);
}

function getRollingMasteryVelocity(days, offsetDays) {
  const dates = getLastNDates(days + offsetDays).slice(0, days);
  const total = dates.reduce((sum, day) => sum + (state.progress.masteredByDate[day] || 0), 0);
  return total / days;
}

function getLastNDates(n) {
  const days = [];
  const today = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    days.push(getDateKey(d));
  }
  return days;
}

function getDateKey(date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function addDays(dateKey, amount) {
  const [y, m, d] = dateKey.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  date.setDate(date.getDate() + amount);
  return getDateKey(date);
}

function isYesterday(candidateDate, referenceDate) {
  if (!candidateDate) return false;
  return candidateDate === addDays(referenceDate, -1);
}

function formatDateEs(dateKey) {
  const [y, m, d] = dateKey.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString('es-ES', { year: 'numeric', month: 'long', day: 'numeric' });
}

function ensureAnswerRecord(rec = {}) {
  return {
    seen: rec.seen || 0,
    ok: rec.ok || 0,
    wrong: rec.wrong || 0,
    correctStreak: rec.correctStreak || 0,
    reviewCount: rec.reviewCount || 0,
    mastered: !!rec.mastered,
    masteredAt: rec.masteredAt || null,
  };
}

function loadProgress() {
  const fallback = {
    answers: {},
    streak: { current: 0, longest: 0, lastGoalDate: null },
    dailyGoalMinutes: DAILY_GOAL_DEFAULT,
    dailySeconds: {},
    masteredByDate: {},
  };
  try {
    const raw = JSON.parse(localStorage.getItem('telc_b1_progress') || '{}');
    const streak = typeof raw.streak === 'number'
      ? { current: raw.streak, longest: raw.streak, lastGoalDate: null }
      : { ...fallback.streak, ...(raw.streak || {}) };
    const answers = {};
    Object.entries(raw.answers || {}).forEach(([id, rec]) => {
      answers[id] = ensureAnswerRecord(rec);
    });
    return {
      ...fallback,
      ...raw,
      streak,
      answers,
      dailyGoalMinutes: raw.dailyGoalMinutes || DAILY_GOAL_DEFAULT,
      dailySeconds: raw.dailySeconds || {},
      masteredByDate: raw.masteredByDate || {},
    };
  } catch {
    return fallback;
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

function triggerConfetti() {
  const colors = ['#5ce1e6', '#ffd166', '#06d6a0', '#ff6b6b', '#7aa2ff'];
  for (let i = 0; i < 28; i++) {
    const piece = document.createElement('span');
    piece.className = 'confetti-piece';
    piece.style.left = `${Math.random() * 100}%`;
    piece.style.background = colors[Math.floor(Math.random() * colors.length)];
    piece.style.animationDelay = `${Math.random() * 0.4}s`;
    piece.style.transform = `translateY(-20px) rotate(${Math.random() * 360}deg)`;
    el.confettiLayer.appendChild(piece);
    setTimeout(() => piece.remove(), 2800);
  }
}

function bindSwipe(node, onLeft) {
  let sx = 0;
  node.addEventListener('touchstart', (e) => {
    sx = e.changedTouches[0].clientX;
    registerInteraction();
  }, { passive: true });
  node.addEventListener('touchend', (e) => {
    const dx = e.changedTouches[0].clientX - sx;
    if (dx < -70) onLeft();
  }, { passive: true });
}

function optionTranslation(q, label) {
  const clean = String(label).replace(/^[A-Za-zXx]\)?\s*/, '').toLowerCase();
  const hits = (q.vocabulary || []).filter((v) => clean.includes(String(v.de || '').toLowerCase()));
  if (hits.length) return hits.slice(0, 3).map((v) => `${v.de} = ${v.es}`).join(' · ');
  return '';
}

function inferQuestionTranslation(q) {
  if (q.question_es) return q.question_es;
  if (!q.explanation_es) return '';
  const first = q.explanation_es.split(/[.!?]\s/)[0] || '';
  return first.length > 8 ? first : '';
}

function loadTranslationPref() {
  return localStorage.getItem('telc_b1_show_translation') === '1';
}

function saveTranslationPref(value) {
  localStorage.setItem('telc_b1_show_translation', value ? '1' : '0');
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
