/* СБОРКА: логика мастера создания сайта (vanilla JS, без зависимостей) */
'use strict';

const $ = (s, r = document) => r.querySelector(s);

/* ---------------------------------------------------------------- state -- */
const LS_KEY = 'sborka_state_v1';
const state = {
  step: -1, // -1 = welcome
  kind: 'landing', // landing | taplink | vcard
  answers: { name: '', about: '', products: '', advantages: '', extras: '' },
  theme: { mode: 'light', accent: 'purple' },
  email: '',
  agree1: false, agree2: false,
  chips: null,          // {products:[], advantages:[], extras:[]}
  chipsLoading: false,
  visited: 0,
  job: null,
  code: '',
  editorJob: null,
  editorVersion: 0,
  editorBusy: false,
};
let CFG = { llm: false, accents: [] };

function saveState() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      kind: state.kind, answers: state.answers, theme: state.theme, email: state.email,
      agree1: state.agree1, agree2: state.agree2, chips: state.chips,
    }));
  } catch (e) { /* private mode — ок */ }
}
function restoreState() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return;
    const d = JSON.parse(raw);
    if (d.kind) state.kind = d.kind;
    Object.assign(state.answers, d.answers || {});
    Object.assign(state.theme, d.theme || {});
    state.email = d.email || '';
    state.agree1 = !!d.agree1; state.agree2 = !!d.agree2;
    state.chips = d.chips || null;
  } catch (e) { /* ignore */ }
}

/* ---------------------------------------------------------------- icons -- */
const I = {
  next: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" width="18" height="18"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M4 12.5l5 5L20 7"/></svg>',
  spinner: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" width="14" height="14"><path d="M21 12a9 9 0 1 1-5-8"/></svg>',
  help: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="15" height="15"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.6 2.24c-.7.33-1.1.9-1.1 1.66v.6"/><circle cx="12" cy="17" r=".4" fill="currentColor"/></svg>',
  briefcase: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><rect x="3" y="7" width="18" height="13" rx="2.5"/><path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7"/><path d="M3 12h18"/></svg>',
  box: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><path d="M12 2l8 4.5v9L12 20l-8-4.5v-9L12 2z"/><path d="M4 6.5l8 4.5 8-4.5M12 11v9"/></svg>',
  award: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><circle cx="12" cy="9" r="5"/><path d="M8.5 13.5L7 21l5-2.5L17 21l-1.5-7.5"/></svg>',
  palette: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><circle cx="12" cy="12" r="9"/><circle cx="8.5" cy="10" r="1" fill="currentColor"/><circle cx="12" cy="7.5" r="1" fill="currentColor"/><circle cx="15.5" cy="10" r="1" fill="currentColor"/><path d="M12 21a9 9 0 0 0 6.5-2.8c.8-.9.2-2.2-1-2.2H12a3 3 0 0 1 0-6h5.4c1.2 0 2-1.2 1.4-2.3"/></svg>',
  chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z"/></svg>',
  spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z"/><path d="M18.5 15.5l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7.7-2z"/></svg>',
};

/* ---------------------------------------------------------------- steps -- */
const STEP_DEFS = [
  {
    id: 'about', label: 'О бизнесе', title: 'Расскажите о своём бизнесе', icon: 'briefcase',
    sub: 'Как называется компания, чем занимаетесь и для кого. Двух-трёх предложений хватит — ИИ разберётся в деталях.',
    help: {
      title: 'Как описать бизнес',
      text: 'Просто объясните, чем занимаетесь и для кого — как рассказали бы знакомому.',
      good: ['Чем занимаетесь и в каком городе', 'Кто ваши клиенты', 'Сколько лет на рынке'],
      bad: ['Общих красивых фраз вроде «высокое качество» и «индивидуальный подход»', 'Длинной истории компании'],
      example: '«Ремонтируем квартиры в Казани с 2015 года. Бригада из 6 мастеров, работаем по договору. Делаем косметический и капитальный ремонт, кухни и санузлы под ключ. Клиенты — владельцы квартир в новостройках и вторичке, фиксируем сроки в смете.»',
    },
  },
  {
    id: 'products', label: 'Продукт', title: 'Что вы продаёте', icon: 'box',
    sub: 'Основные услуги или товары — каждую позицию с новой строки. Цена точная, диапазоном или «по запросу» — как удобно.',
    required: true,
    help: {
      title: 'Как перечислить услуги',
      text: 'Каждую услугу или товар — с новой строки. Пишите так, как их называете клиентам.',
      good: ['3–8 основных позиций', 'Цену рядом с позицией, если хотите', 'Формулировки из вашей практики'],
      bad: ['Списка из 30 позиций — возьмите главные', 'Аббревиатур без расшифровки'],
      example: '«Диагностика двигателя — от 1500 ₽\nЗамена масла и фильтров — 2500 ₽\nРемонт ходовой — по запросу»',
    },
  },
  {
    id: 'advantages', label: 'Отличия', title: 'Чем вы отличаетесь от конкурентов', icon: 'award',
    sub: 'То, ради чего клиенты выбирают именно вас. ИИ вынесет это в главные заголовки. Можно пропустить, но именно это убеждает посетителей.',
    help: {
      title: 'Как описать отличия',
      text: 'Факты и цифры работают лучше прилагательных: гарантия, сроки, опыт, условия.',
      good: ['Гарантия и её срок', 'Скорость ответа или выезда', 'Опыт, сертификаты, количество клиентов'],
      bad: ['«Лучшие на рынке» без фактов', 'Полного копирования текстов конкурентов'],
      example: '«Гарантия 3 года, выезд в день обращения, перезваниваем за 5 минут»',
    },
  },
  {
    id: 'theme', label: 'Тема', title: 'Тема оформления сайта', icon: 'palette',
    sub: 'В каком стиле показать сайт посетителям. Не переживайте: тему и цвета можно поменять в любой момент после создания.',
  },
  {
    id: 'extras', label: 'Пожелания', title: 'Хотите рассказать что-то ещё?', icon: 'chat',
    sub: 'Всё, что мы могли упустить: вопросы от клиентов, пожелания по оформлению, личная история, спецпредложения, сертификаты, ограничения. Спокойно пропускайте, если нечего добавить.',
    help: {
      title: 'Что сюда писать',
      text: 'Любой контекст, который поможет ИИ сделать сайт точнее.',
      good: ['Спецпредложения и акции', 'Особенности работы (часы, районы, выезд)', 'Пожелания по стилю или структуре'],
      bad: ['Перечня услуг заново — он уже есть на шаге 2', 'Личных данных клиентов'],
      example: '«Скидка 10% на первое обслуживание. Работаем с 9 до 21 без выходных, выезжаем по области. Хотим тёмный акцент и блок с фото работ.»',
    },
  },
  {
    id: 'review', label: 'Проверка', title: 'Почти готово', icon: 'spark',
    sub: 'Мы учли ваши ответы — дальше ИИ соберёт сайт. Хотите что-то поправить — нажмите «Назад» или кнопку у пункта.',
  },
];

/* ----------------------------------------------------------------- init -- */
document.addEventListener('DOMContentLoaded', () => {
  restoreState();
  bindButtons();
  fetchConfig();
  showScreen('welcome');
});

async function fetchConfig() {
  try {
    const r = await fetch('/api/config');
    CFG = await r.json();
  } catch (e) { CFG = { llm: false, accents: [] }; }
  const note = $('#mode-note');
  if (note) {
    note.textContent = CFG.llm
      ? `Режим LLM: сайт генерирует модель ${CFG.model} через RouterAI.`
      : 'Демо-режим: сайт собирает встроенный генератор. Добавьте ключ RouterAI (ROUTERAI_API_KEY) — и генерировать будет LLM.';
  }
  if (!CFG.accents || !CFG.accents.length) {
    CFG.accents = [
      { id: 'purple', label: 'Фиолетовый', hex: '#7c3aed' }, { id: 'blue', label: 'Синий', hex: '#2563eb' },
      { id: 'emerald', label: 'Изумруд', hex: '#059669' }, { id: 'orange', label: 'Оранжевый', hex: '#ea580c' },
      { id: 'rose', label: 'Малиновый', hex: '#e11d48' }, { id: 'teal', label: 'Бирюзовый', hex: '#0d9488' }];
  }
  // сбрасываем кэш акцентов импорта, чтобы после загрузки конфига отрисовались правильные
  const ir = document.getElementById('import-accent-row');
  if (ir) delete ir.dataset.done;
}

function bindButtons() {
  $('#btn-start').addEventListener('click', () => startKind('landing'));
  const tl = $('#btn-taplink'); if (tl) tl.addEventListener('click', () => startKind('taplink'));
  const vc = $('#btn-vcard'); if (vc) vc.addEventListener('click', () => startKind('vcard'));
  $('#btn-import-start').addEventListener('click', () => openImport());
  $('#btn-import').addEventListener('click', startImport);
  $('#btn-import-back').addEventListener('click', () => showScreen('welcome'));
  $('#btn-import-demo').addEventListener('click', () => {
    $('#import-url').value = 'https://example.com';
    $('#import-url').dispatchEvent(new Event('input'));
  });
  $('#import-url').addEventListener('input', validateImport);
  $('#import-url').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); startImport(); } });
  $('#btn-back').addEventListener('click', () => goStep(Math.max(0, state.step - 1)));
  $('#btn-next').addEventListener('click', nextStep);
  $('#modal-close').addEventListener('click', closeModal);
  $('#modal-ok').addEventListener('click', closeModal);
  $('#modal').addEventListener('click', (e) => { if (e.target === $('#modal')) closeModal(); });
  // publish choice
  const stay = $('#btn-publish-stay');
  if (stay) stay.addEventListener('click', () => {
    const h = $('#publish-hint');
    h.textContent = 'Готово: сайт остаётся на СБОРКА. Ссылка — ' + (state.editorJob ? (location.origin + '/api/site/' + state.editorJob) : 'появится после генерации') + ' — можете открыть редактор.';
    h.style.display = 'block';
  });
  const wpBtn = $('#btn-publish-wp');
  if (wpBtn) wpBtn.addEventListener('click', () => openPublishModal());
  $('#publish-close').addEventListener('click', closePublishModal);
  $('#publish-ok').addEventListener('click', closePublishModal);
  $('#publish-modal').addEventListener('click', (e) => { if (e.target === $('#publish-modal')) closePublishModal(); });
  $('#btn-wp-send').addEventListener('click', sendToWp);
  const expZip = $('#btn-export-zip');
  if (expZip) expZip.addEventListener('click', () => {
    // href уже выставлен, просто закроем через секунду
    setTimeout(() => closePublishModal(), 400);
  });
  const edPub = $('#ed-publish');
  if (edPub) edPub.addEventListener('click', () => openPublishModal());
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeModal(); closePublishModal(); } });

  /* code screen */
  $('#code-input').addEventListener('input', (e) => {
    e.target.value = e.target.value.replace(/\D/g, '').slice(0, 6);
    $('#btn-create').disabled = e.target.value.length !== 6;
  });
  $('#btn-create').addEventListener('click', startGeneration);
  $('#btn-resend').addEventListener('click', () => startResend(false));
  $('#btn-change-email').addEventListener('click', () => { showScreen('wizard'); goStep(5); });

  /* result */
  $('#btn-editor').addEventListener('click', () => openEditor(state.editorJob));
  $('#btn-restart').addEventListener('click', resetAll);

  /* editor */
  $('#ed-back').addEventListener('click', () => showScreen('result'));
  $('#ed-refresh').addEventListener('click', () => refreshEditor());
  $('#ed-undo').addEventListener('click', editorUndo);
  $('#ed-device').addEventListener('click', toggleDevice);
  $('#ed-send').addEventListener('click', sendChat);
  $('#ed-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });
}

/* ------------------------------------------------------------ screens ---- */
function showScreen(name) {
  ['welcome', 'wizard', 'code', 'generating', 'result', 'editor', 'import'].forEach((n) => {
    $('#screen-' + n).classList.toggle('hidden', n !== name);
  });
}

function goHome() {
  showScreen('welcome');
  state.step = -1;
  return false;
}
function startKind(kind) {
  state.kind = kind || 'landing';
  state.visited = 0;
  state.step = 0;
  saveState();
  state.chips = null;
  goStep(0);
}

/* ------------------------------------------------------------ stepper ---- */
function renderStepper() {
  const c = $('#stepper');
  c.innerHTML = '';
  STEP_DEFS.forEach((d, i) => {
    const st = document.createElement('div');
    const done = i < state.step, current = i === state.step;
    st.className = 'st' + (done ? ' done' : '') + (current ? ' current' : '') + (i <= state.visited && !current ? ' clickable' : '');
    st.innerHTML = `<span class="dot">${done ? I.check : i + 1}</span><span class="lbl">${d.label}</span>`;
    if (i <= state.visited && !current) st.addEventListener('click', () => goStep(i));
    c.appendChild(st);
  });
}

/* --------------------------------------------------------------- steps --- */
function goStep(i) {
  state.step = i;
  state.visited = Math.max(state.visited, i);
  showScreen('wizard');
  renderStepper();
  renderStep();
  const back = $('#btn-back');
  back.classList.toggle('hidden', i === 0);
  const next = $('#btn-next');
  next.innerHTML = (i === STEP_DEFS.length - 1 ? 'Получить код ' : 'Далее ') + I.next;
  validateStep();
}

function renderStep() {
  const def = STEP_DEFS[state.step];
  const body = $('#step-body');
  body.innerHTML = '';

  // динамические заголовки для taplink/vcard
  let title = def.title, sub = def.sub;
  if (state.kind === 'taplink') {
    if (def.id === 'about') { title = 'Кто вы'; sub = 'Как вас называть и чем занимаетесь — это шапка вашей мультиссылки.'; }
    if (def.id === 'products') { title = 'Ваши ссылки'; sub = 'Каждая ссылка — с новой строки. Формат: Название — https://... (можно и без ссылки, мы подставим).'; }
    if (def.id === 'advantages') { title = 'Соцсети и мессенджеры'; sub = 'Перечислите соцсети или мессенджеры — они появятся кнопками. Можно пропустить.'; }
    if (def.id === 'extras') { title = 'Текст и пожелания'; sub = 'Короткий текст под ссылками — призыв или пояснение.'; }
  }
  if (state.kind === 'vcard') {
    if (def.id === 'about') { title = 'Ваша визитка'; sub = 'Имя, должность и компания — это лицо вашей QR-визитки.'; }
    if (def.id === 'products') { title = 'Чем занимаетесь'; sub = 'Коротко — для блока о вас. Можно и ссылку на сайт.'; }
    if (def.id === 'advantages') { title = 'Контакты и соцсети'; sub = 'Телефон, email, соцсети — покажите как с вами связаться.'; }
    if (def.id === 'extras') { title = 'Дополнительно'; sub = 'Адрес, часы, пожелания по стилю.'; }
  }

  const head = document.createElement('div');
  head.className = 'step-head';
  head.innerHTML = `
    <div class="step-icon">${I[def.icon]}</div>
    <h2>${title}</h2>
    ${def.help ? `<button class="help-link">${I.help} Что написать?</button>` : ''}`;
  body.appendChild(head);
  if (def.help) head.querySelector('.help-link').addEventListener('click', () => openModal(def.help));
  if (sub) {
    const p = document.createElement('p');
    p.className = 'step-sub';
    p.textContent = sub;
    body.appendChild(p);
  }
  // бейдж типа
  if (state.kind !== 'landing') {
    const badge = document.createElement('div');
    badge.style.cssText = 'display:inline-block;margin-bottom:10px;font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;padding:5px 10px;border-radius:999px;background:var(--accent-soft);color:var(--accent)';
    badge.textContent = state.kind === 'taplink' ? 'Taplink — мультиссылка' : 'QR-визитка — myqrcards';
    body.appendChild(badge);
  }

  const a = state.answers;
  if (def.id === 'about') {
    const nameLabel = state.kind === 'landing' ? 'Название компании' : 'Ваше имя / бренд';
    const namePh = state.kind === 'landing' ? 'Например, кофейня «Brewhaus»' : 'Например, Иван Петров или Студия «Свет»';
    const aboutLabel = state.kind === 'landing' ? 'О бизнеса' : 'О себе / проекте';
    const aboutPh = state.kind === 'landing' ? 'Например: кофейня в центре Москвы. Работаем с 2019 года, своя обжарка, завтраки и кофе с собой.' : (state.kind === 'taplink' ? 'Например: Фотограф в Казани, снимаю свадьбы и портреты. Напишите — отвечаю быстро.' : 'Например: Иван Петров — дизайнер в Студии Свет, делаю сайты и брендинг.');
    body.appendChild(field(nameLabel, 'name', 'text', namePh, true));
    body.appendChild(field(aboutLabel, 'about', 'textarea', aboutPh, true, 4));
    autoFocus();
  }

  if (def.id === 'products' || def.id === 'advantages' || def.id === 'extras') {
    const key = def.id === 'products' ? 'products' : def.id === 'advantages' ? 'advantages' : 'extras';
    let label = def.id === 'products' ? 'Услуги или товары' : def.id === 'advantages' ? 'Ваши преимущества' : 'Дополнительно';
    let ph = def.id === 'products' ? 'Перечислите услуги или товары — каждый с новой строки' : '';
    if (state.kind === 'taplink') {
      if (key === 'products') { label = 'Ссылки (каждая с новой строки)'; ph = 'Портфолио — https://example.com\nЗапись — https://t.me/example\nМагазин — https://shop.example.com'; }
      if (key === 'advantages') { label = 'Соцсети / мессенджеры'; ph = 'Instagram — https://instagram.com/...\nTelegram — https://t.me/...'; }
      if (key === 'extras') { label = 'Текст под ссылками'; ph = 'Напишите — отвечаю в течение часа 👆'; }
    }
    if (state.kind === 'vcard') {
      if (key === 'products') { label = 'О себе / услуги'; ph = 'Дизайн сайтов и брендинг для малого бизнеса'; }
      if (key === 'advantages') { label = 'Телефон / email / соцсети'; ph = '+7 900 123-45-67\nhello@example.ru\nhttps://t.me/example'; }
    }
    body.appendChild(field(label, key, 'textarea', ph, def.required, def.id === 'products' ? 6 : 4));
    // chips only for landing
    if (state.kind === 'landing') renderChips(body, key);
    autoFocus();
  }

  if (def.id === 'theme') renderTheme(body);

  if (def.id === 'review') renderReview(body);
}

function field(label, key, tag, placeholder, required, rows) {
  const w = document.createElement('div');
  w.className = 'field';
  w.innerHTML = `
    <label>${label} ${required ? '<span class="req">*</span>' : '<span style="color:#9aa2b8;font-weight:500">(необязательно)</span>'}</label>
    ${tag === 'textarea'
      ? `<textarea rows="${rows || 4}" data-key="${key}" placeholder="${placeholder || ''}"></textarea>`
      : `<input type="text" data-key="${key}" placeholder="${placeholder || ''}">`}
    <div class="err">Заполните поле — хотя бы пара слов</div>`;
  const el = w.querySelector('input,textarea');
  el.value = state.answers[key] || '';
  el.addEventListener('input', () => {
    state.answers[key] = el.value;
    saveState(); validateStep();
  });
  return w;
}

function autoFocus() {
  setTimeout(() => {
    const f = $('#step-body input, #step-body textarea');
    if (f && window.innerWidth > 720) f.focus();
  }, 60);
}

function renderChips(container, key) {
  const wrap = document.createElement('div');
  const list = state.chips && state.chips[key];
  if (!list) {
    wrap.className = 'chips loading';
    wrap.innerHTML = '<span class="chip-skel"></span><span class="chip-skel" style="width:120px"></span><span class="chip-skel" style="width:180px"></span>';
    container.appendChild(wrap);
    ensureChips().then(() => { if (document.body.contains(wrap)) renderChipsRefresh(container, key, wrap); });
    return;
  }
  renderChipsList(wrap, list, key);
  container.appendChild(wrap);
}
function renderChipsRefresh(container, key, oldWrap) {
  const wrap = document.createElement('div');
  renderChipsList(wrap, state.chips[key] || [], key);
  container.replaceChild(wrap, oldWrap);
}
function renderChipsList(wrap, list, key) {
  wrap.className = 'chips';
  const lbl = document.createElement('div');
  lbl.className = 'chips-label';
  lbl.innerHTML = 'Нажмите — <b>добавим</b>, а вы поправьте под себя:';
  wrap.appendChild(lbl);
  const row = document.createElement('div');
  row.className = 'chips';
  (list || []).slice(0, 9).forEach((text) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip';
    b.textContent = text;
    const used = () => state.answers[key].toLowerCase().includes(text.toLowerCase());
    b.classList.toggle('used', used());
    b.addEventListener('click', () => {
      const ta = $(`#step-body textarea[data-key="${key}"]`);
      if (!ta) return;
      if (used()) return;
      ta.value = (ta.value.trim() ? ta.value.replace(/\s*$/, '\n') : '') + text;
      state.answers[key] = ta.value;
      b.classList.add('used');
      saveState(); validateStep();
      ta.focus();
    });
    row.appendChild(b);
  });
  wrap.appendChild(row);
}

async function ensureChips() {
  if (state.chips || state.chipsLoading) return;
  state.chipsLoading = true;
  try {
    const r = await fetch('/api/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: state.answers.name, about: state.answers.about }),
    });
    const data = await r.json();
    state.chips = data.chips;
  } catch (e) {
    state.chips = { products: [], advantages: [], extras: [] };
  }
  state.chipsLoading = false;
  saveState();
}

function renderTheme(container) {
  const w = document.createElement('div');
  w.innerHTML = `
    <div class="theme-grid">
      <button type="button" class="theme-card" data-mode="light">
        <div class="theme-prev light"><div class="bar"></div><div class="bar s2"></div><div class="bar s3"></div><div class="btn"></div></div>
        <div class="theme-name">Светлая</div>
      </button>
      <button type="button" class="theme-card" data-mode="dark">
        <div class="theme-prev dark"><div class="bar"></div><div class="bar s2"></div><div class="bar s3"></div><div class="btn"></div></div>
        <div class="theme-name">Тёмная</div>
      </button>
    </div>
    <div class="accent-row"><span class="lbl">Акцентный цвет</span></div>`;
  const modeBtns = w.querySelectorAll('.theme-card');
  modeBtns.forEach((b) => {
    b.classList.toggle('sel', b.dataset.mode === state.theme.mode);
    b.addEventListener('click', () => {
      state.theme.mode = b.dataset.mode;
      modeBtns.forEach((x) => x.classList.toggle('sel', x === b));
      saveState();
    });
  });
  const row = w.querySelector('.accent-row');
  (CFG.accents || []).forEach((acc) => {
    const s = document.createElement('button');
    s.type = 'button';
    s.className = 'swatch' + (acc.id === state.theme.accent ? ' sel' : '');
    s.style.background = acc.hex;
    s.title = acc.label;
    s.addEventListener('click', () => {
      state.theme.accent = acc.id;
      row.querySelectorAll('.swatch').forEach((x) => x.classList.remove('sel'));
      s.classList.add('sel');
      saveState();
    });
    row.appendChild(s);
  });
  container.appendChild(w);
}

function renderReview(container) {
  const rows = [
    ['О бизнесе', state.answers.name + (state.answers.name && state.answers.about ? '. ' : '') + state.answers.about, 0],
    ['Продукт', state.answers.products, 1],
    ['Отличия', state.answers.advantages || '—', 2],
    ['Тема', (state.theme.mode === 'dark' ? 'Тёмная' : 'Светлая') + ', акцент: ' + accentLabel(state.theme.accent), 3],
    ['Пожелания', state.answers.extras || '—', 4],
  ];
  const w = document.createElement('div');
  const sum = document.createElement('div');
  sum.className = 'summary';
  rows.forEach(([k, v, stepIdx]) => {
    const r = document.createElement('div');
    r.className = 'sum-row';
    r.innerHTML = `<span class="k">${k}</span><span class="v">${escapeHtml(truncate(v, 260))}</span>
      <button class="edit" type="button">изменить</button>`;
    r.querySelector('.edit').addEventListener('click', () => goStep(stepIdx));
    sum.appendChild(r);
  });
  w.appendChild(sum);

  const emailField = document.createElement('div');
  emailField.className = 'field';
  emailField.innerHTML = `
    <label>Куда сохранить доступ?</label>
    <input type="email" data-key="email" placeholder="you@example.com">
    <div class="err">Похоже, в адресе почты ошибка</div>`;
  const em = emailField.querySelector('input');
  em.value = state.email || '';
  em.addEventListener('input', () => { state.email = em.value; saveState(); validateStep(); });
  w.appendChild(emailField);

  const note = document.createElement('p');
  note.className = 'sub';
  note.style.cssText = 'font-size:13.5px;margin:-8px 0 18px';
  note.textContent = 'На эту почту придут ссылка на сайт, чеки и важные уведомления. Пароль не нужен — вход по коду.';
  w.appendChild(note);

  [['agree1', 'Я принимаю <a href="#" onclick="return false">оферту</a> и <a href="#" onclick="return false">политику конфиденциальности</a>', true],
   ['agree2', 'Я согласен получать информацию о новых функциях, акциях и обучающих материалах (можно отписаться в любое время)', false],
  ].forEach(([key, html, req]) => {
    const l = document.createElement('label');
    l.className = 'check-line';
    l.innerHTML = `<input type="checkbox" data-check="${key}"> <span>${html}${req ? ' <b style="color:#e11d48">*</b>' : ''}</span>`;
    const cb = l.querySelector('input');
    cb.checked = state[key];
    cb.addEventListener('change', () => { state[key] = cb.checked; saveState(); validateStep(); });
    w.appendChild(l);
  });

  container.appendChild(w);
}

function accentLabel(id) {
  const a = (CFG.accents || []).find((x) => x.id === id);
  return a ? a.label.toLowerCase() : id;
}

/* ------------------------------------------------------------ validate --- */
function validateStep() {
  const def = STEP_DEFS[state.step];
  const next = $('#btn-next');
  let ok = true;
  if (def.id === 'about') {
    ok = state.answers.name.trim().length >= 1 && state.answers.about.trim().length >= 10;
    markField('name', state.answers.name.trim().length >= 1);
    markField('about', state.answers.about.trim().length >= 10);
  } else if (def.id === 'products') {
    ok = state.answers.products.trim().length >= 3;
    markField('products', ok);
  } else if (def.id === 'review') {
    const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(state.email.trim());
    ok = emailOk && state.agree1;
    markField('email', emailOk || !state.email);
  }
  next.disabled = !ok;
  return ok;
}
function markField(key, valid) {
  const el = $(`#step-body [data-key="${key}"]`);
  if (el) el.closest('.field').classList.toggle('invalid', !valid);
}

function nextStep() {
  if (!validateStep()) return;
  if (state.step === 4) { goStep(5); return; }
  if (state.step === 5) { openCodeScreen(); return; }
  goStep(state.step + 1);
}

/* --------------------------------------------------------------- modal --- */
function openModal(help) {
  $('#modal-title').textContent = help.title;
  $('#modal-text').textContent = help.text;
  $('#modal-good').innerHTML = help.good.map((x) => `<li>${x}</li>`).join('');
  $('#modal-bad').innerHTML = help.bad.map((x) => `<li>${x}</li>`).join('');
  $('#modal-example').textContent = help.example;
  $('#modal').classList.remove('hidden');
}
function closeModal() { $('#modal').classList.add('hidden'); }

/* ----------------------------------------------------------- code step --- */
function openCodeScreen() {
  const inp = $('#code-input');
  inp.value = '';
  $('#btn-create').disabled = true;
  showScreen('code');
  setTimeout(() => inp.focus(), 80);
  if (CFG.auth) {
    // боевой режим: код отправляет сервер через SMTP
    state.code = '';
    document.querySelector('#screen-code .hint').style.display = 'none';
    $('#code-email-text').innerHTML = `Отправляем 6-значный код на <b>${escapeHtml(state.email)}</b>…`;
    requestServerCode();
    startResend(true);
    return;
  }
  // демо-режим: код генерируется локально и показывается на экране
  state.code = String(Math.floor(100000 + Math.random() * 900000));
  document.querySelector('#screen-code .hint').style.display = '';
  $('#code-email-text').innerHTML = `Мы «отправили» 6-значный код на <b>${escapeHtml(state.email)}</b>. После подтверждения сразу начнём создавать сайт.`;
  $('#demo-code').textContent = state.code;
  startResend(true);
}

async function requestServerCode() {
  try {
    const r = await fetch('/api/auth/code', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: state.email }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
    $('#code-email-text').innerHTML = `Мы отправили 6-значный код на <b>${escapeHtml(state.email)}</b>. После подтверждения сразу начнём создавать сайт.`;
  } catch (e) {
    $('#code-email-text').innerHTML = `Не удалось отправить код на <b>${escapeHtml(state.email)}</b>: ${escapeHtml(e.message)}. Попробуйте «Отправить ещё раз».`;
  }
}
let resendTimer = null;
function startResend(init) {
  let sec = 44;
  const btn = $('#btn-resend'), txt = $('#resend-text');
  clearInterval(resendTimer);
  btn.disabled = true;
  const tick = () => {
    txt.textContent = sec > 0 ? `Отправить ещё раз (${sec})` : 'Отправить ещё раз';
    if (sec <= 0) { btn.disabled = false; clearInterval(resendTimer); }
    sec--;
  };
  tick(); resendTimer = setInterval(tick, 1000);
  if (init) {
    if (!CFG.auth) $('#demo-code').textContent = state.code;
  } else if (CFG.auth) {
    requestServerCode();
  } else {
    // демо: «отправить ещё раз» = новый код
    state.code = String(Math.floor(100000 + Math.random() * 900000));
    $('#demo-code').textContent = state.code;
  }
}

/* ------------------------------------------------------------ import ---- */
function openImport() {
  showScreen('import');
  $('#import-status').classList.add('hidden');
  validateImport();
  renderImportAccents();
  setTimeout(() => $('#import-url').focus(), 80);
}
function renderImportAccents() {
  const row = $('#import-accent-row');
  if (!row || row.dataset.done) return;
  row.innerHTML = '<span class="lbl">Акцент</span>';
  (CFG.accents || []).forEach((acc) => {
    const s = document.createElement('button');
    s.type = 'button';
    s.className = 'swatch' + (acc.id === state.theme.accent ? ' sel' : '');
    s.style.background = acc.hex;
    s.title = acc.label;
    s.addEventListener('click', () => {
      state.theme.accent = acc.id;
      row.querySelectorAll('.swatch').forEach((x) => x.classList.remove('sel'));
      s.classList.add('sel');
      saveState();
    });
    row.appendChild(s);
  });
  row.dataset.done = '1';
}
function validateImport() {
  const v = $('#import-url').value.trim();
  const ok = /^https?:\/\/.+\..+/.test(v) || /^[^\/\s]+\.[^\/\s]+/.test(v);
  const field = $('#import-field');
  field.classList.toggle('invalid', !!v && !ok);
  $('#btn-import').disabled = !v || !ok;
  return ok && v;
}
async function startImport() {
  const raw = $('#import-url').value.trim();
  if (!raw) { validateImport(); return; }
  let url = raw;
  if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
  const btn = $('#btn-import');
  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = 'Загружаем…';
  const status = $('#import-status');
  status.classList.add('hidden');
  try {
    const r = await fetch('/api/import', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, theme_mode: state.theme.mode, accent: state.theme.accent }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
    beginImportPolling(d.job_id);
  } catch (e) {
    status.textContent = e.message || 'Не удалось запустить импорт';
    status.classList.remove('hidden');
    btn.disabled = false;
    btn.textContent = old;
  }
}
async function beginImportPolling(jobId) {
  showScreen('generating');
  $('#gen-error').classList.add('hidden');
  $('#gen-warning').classList.add('hidden');
  $('#gen-sub').textContent = 'Загружаем сайт по ссылке, разбираем структуру и переносим в редактор. Обычно 20–60 секунд.';
  const ul = $('#stage-list');
  const started = Date.now();
  // пока не знаем стадий — нарисуем заглушку, обновим из /api/job
  ul.innerHTML = '<li class="current"><span class="st-dot">' + I.spinner + '</span><span>Загружаем сайт<small class="st-hint">Скачиваем страницу</small></span></li>';
  $('#progress-fill').style.width = '8%';
  let lastJob = null;
  const poll = setInterval(async () => {
    let job;
    try { job = await (await fetch('/api/job/' + jobId)).json(); } catch (e) { return; }
    lastJob = job;
    const stages = job.stages || [];
    const hints = job.hints || [];
    ul.innerHTML = stages.map((s) => `<li><span class="st-dot"></span><span>${s}<small class="st-hint"></small></span></li>`).join('');
    const items = ul.querySelectorAll('li');
    items.forEach((li, i) => {
      li.classList.toggle('done', i < job.stage || job.status === 'done');
      li.classList.toggle('current', i === job.stage && job.status === 'running');
      li.querySelector('.st-dot').innerHTML = (i < job.stage || job.status === 'done') ? I.check : (i === job.stage && job.status === 'running') ? I.spinner : '';
      const hint = li.querySelector('.st-hint');
      if (hint) hint.textContent = i === job.stage ? (hints[i] || '') : '';
    });
    const p = job.status === 'done' ? 100 : Math.min(96, (job.stage / (stages.length || 5)) * 100 + 4);
    $('#progress-fill').style.width = p + '%';
    if (job.status === 'done') {
      clearInterval(poll);
      if (job.warning) { $('#gen-warning').textContent = job.warning; $('#gen-warning').classList.remove('hidden'); }
      setTimeout(() => showResult(jobId, started, lastJob), job.warning ? 1400 : 500);
    } else if (job.status === 'error') {
      clearInterval(poll);
      genError('Ошибка импорта: ' + (job.error || 'неизвестная'));
    }
  }, 700);
}

/* publish helpers */
function openPublishModal() {
  if (!state.editorJob) {
    const h = $('#publish-hint');
    if (h) { h.textContent = 'Сначала создайте или перенесите сайт.'; h.style.display = 'block'; }
    return;
  }
  $('#btn-export-zip').href = '/api/export/' + state.editorJob;
  $('#btn-export-zip').setAttribute('download', 'site-' + state.editorJob + '.zip');
  $('#wp-result').classList.add('hidden');
  $('#publish-modal').classList.remove('hidden');
}
function closePublishModal() { $('#publish-modal').classList.add('hidden'); }
async function sendToWp() {
  const wp_url = $('#wp-url').value.trim();
  const username = $('#wp-user').value.trim();
  const app_password = $('#wp-pass').value.trim();
  const status = $('#wp-status').value;
  const out = $('#wp-result');
  if (!wp_url || !username || !app_password) {
    out.textContent = 'Заполните адрес WP, логин и Application Password';
    out.classList.remove('hidden');
    return;
  }
  const btn = $('#btn-wp-send');
  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = 'Отправляем…';
  out.classList.add('hidden');
  try {
    const r = await fetch('/api/publish/wp/' + state.editorJob, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wp_url, username, app_password, status }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
    out.textContent = 'Готово! Страница создана: ' + (d.url || 'WordPress') + ' (id ' + (d.id || '?') + ')';
    out.style.background = '#e9f8ef';
    out.style.borderColor = '#bfe8cf';
    out.classList.remove('hidden');
  } catch (e) {
    out.textContent = e.message;
    out.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
}

/* ----------------------------------------------------------- generate ---- */
async function startGeneration() {
  if (CFG.auth) { await startGenerationServerAuthed(); return; }
  if ($('#code-input').value !== state.code) { $('#code-input').value = ''; $('#btn-create').disabled = true; return; }
  beginGeneration();
}

async function startGenerationServerAuthed() {
  const btn = $('#btn-create');
  btn.disabled = true;
  const oldHtml = btn.innerHTML;
  btn.textContent = 'Проверяем…';
  try {
    const r = await fetch('/api/auth/verify', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: state.email, code: $('#code-input').value.trim() }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Неверный код');
    beginGeneration();
  } catch (e) {
    $('#code-input').value = '';
    btn.innerHTML = oldHtml;
    btn.disabled = true;
    codeError(e.message);
  }
}

function codeError(msg) {
  let el = $('#code-error');
  if (!el) {
    el = document.createElement('p');
    el.id = 'code-error';
    el.className = 'warning';
    el.style.textAlign = 'center';
    $('#btn-create').before(el);
  }
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(codeError._t);
  codeError._t = setTimeout(() => el.classList.add('hidden'), 5000);
}

async function beginGeneration() {
  showScreen('generating');
  $('#gen-error').classList.add('hidden');
  $('#gen-warning').classList.add('hidden');
  $('#gen-sub').textContent = CFG.llm
    ? `Модель ${CFG.model} анализирует ответы, проектирует структуру и пишет тексты. Обычно 1–3 минуты.`
    : 'ИИ анализирует ваши ответы, проектирует структуру и пишет тексты. Демо-режим: меньше минуты.';

  const stages = ['Анализируем ваш бизнес', 'Проектируем структуру', 'Пишем тексты', 'Верстаем страницу', 'Рисуем изображения'];
  const hints = ['Определяем нишу и аудиторию', 'Подбираем секции и порядок блоков', 'Заголовки, выгоды, возражения', 'Собираем секции в страницу', 'Графика и оформление темы'];
  const ul = $('#stage-list');
  ul.innerHTML = stages.map((s) => `<li><span class="st-dot"></span><span>${s}<small class="st-hint"></small></span></li>`).join('');

  let jobId;
  try {
    const r = await fetch('/api/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: state.answers.name, about: state.answers.about,
        products: state.answers.products, advantages: state.answers.advantages,
        extras: state.answers.extras, theme_mode: state.theme.mode,
        accent: state.theme.accent, email: state.email, kind: state.kind || 'landing',
      }),
    });
    jobId = (await r.json()).job_id;
  } catch (e) {
    genError('Не удалось запустить генерацию. Проверьте, что сервер работает.');
    return;
  }

  const started = Date.now();
  const poll = setInterval(async () => {
    let job;
    try {
      job = await (await fetch('/api/job/' + jobId)).json();
    } catch (e) { return; }
    const items = ul.querySelectorAll('li');
    items.forEach((li, i) => {
      li.classList.toggle('done', i < job.stage || job.status === 'done');
      li.classList.toggle('current', i === job.stage && job.status === 'running');
      li.querySelector('.st-dot').innerHTML = (i < job.stage || job.status === 'done') ? I.check
        : (i === job.stage && job.status === 'running') ? I.spinner : '';
      const hint = li.querySelector('.st-hint');
      if (hint) hint.textContent = i === job.stage ? hints[i] : '';
    });
    const p = job.status === 'done' ? 100 : Math.min(96, (job.stage / 5) * 100 + 4);
    $('#progress-fill').style.width = p + '%';

    if (job.status === 'done') {
      clearInterval(poll);
      if (job.warning) { $('#gen-warning').textContent = job.warning; $('#gen-warning').classList.remove('hidden'); }
      setTimeout(() => showResult(jobId, started), job.warning ? 1400 : 500);
    } else if (job.status === 'error') {
      clearInterval(poll);
      genError('Ошибка генерации: ' + (job.error || 'неизвестная'));
    }
  }, 700);
}

function genError(msg) {
  const el = $('#gen-error');
  el.textContent = msg;
  el.classList.remove('hidden');
  const again = document.createElement('button');
  again.className = 'btn-grad';
  again.style.marginTop = '16px';
  again.textContent = 'Попробовать снова';
  // почта уже подтверждена в этой сессии — код повторно не спрашиваем
  again.addEventListener('click', () => { CFG.auth ? beginGeneration() : startGeneration(); });
  el.appendChild(document.createElement('br'));
  el.appendChild(again);
}

/* ------------------------------------------------------------- result ---- */
function showResult(jobId, started, job) {
  const secs = Math.max(1, Math.round((Date.now() - started) / 1000));
  const isImport = job && job.kind === 'import' && job.source_url;
  $('#result-sub').textContent = isImport
    ? `Сайт перенесён за ${secs} c. Откройте редактор — дальше правьте чатом как обычный сайт.`
    : `Сайт собран за ${secs} c. Дальше — интереснее: откройте редактор и скажите ИИ, что изменить (например, «сделай интернет-магазин»).`;
  const srcNote = $('#import-source-note');
  if (srcNote) {
    if (isImport) {
      srcNote.innerHTML = `Оригинал: <a href="${escapeHtml(job.source_url)}" target="_blank" rel="noopener">${escapeHtml(job.source_url)}</a> · <span style="color:var(--muted)">экспорт — ZIP или WordPress ниже</span>`;
      srcNote.classList.remove('hidden');
    } else {
      srcNote.classList.add('hidden');
    }
  }
  const url = '/api/site/' + jobId;
  const frame = $('#site-frame');
  frame.src = url;
  frame.addEventListener('load', () => fitFrame());
  $('#btn-open-site').href = url;
  $('#btn-download').href = url;
  $('#btn-download').setAttribute('download', 'site-' + jobId + '.html');
  state.editorJob = jobId;
  state.editorVersion = 0;
  // подготовим ссылку на ZIP для модалки публикации
  const zipBtn = document.getElementById('btn-export-zip');
  if (zipBtn) { zipBtn.href = '/api/export/' + jobId; zipBtn.setAttribute('download', 'site-' + jobId + '.zip'); }
  const hint = document.getElementById('publish-hint');
  if (hint) hint.style.display = 'none';
  showScreen('result');
  setTimeout(fitFrame, 100);
}
function fitFrame() {
  const frame = $('#site-frame');
  const box = frame.parentElement;
  if (!box.clientWidth) return;
  const scale = box.clientWidth / 1280;
  frame.style.transform = `scale(${scale})`;
  frame.style.height = Math.round(720 / scale) + 'px';
  frame.parentElement.style.height = Math.min(640, Math.round(720 * scale)) + 'px';
}
window.addEventListener('resize', fitFrame);

/* -------------------------------------------------------------- utils ---- */
function resetAll() {
  state.step = -1; state.visited = 0; state.job = null;
  state.answers = { name: '', about: '', products: '', advantages: '', extras: '' };
  state.chips = null; state.email = ''; state.agree1 = false; state.agree2 = false;
  saveState();
  showScreen('welcome');
  fetchConfig();
}
function truncate(s, n) { s = s || ''; return s.length > n ? s.slice(0, n - 1) + '…' : s; }
function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* Ctrl+Enter — следующий шаг */
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    const b = $('#btn-next');
    if (b && !$('#screen-wizard').classList.contains('hidden') && !b.disabled) b.click();
  }
});

/* ------------------------------------------------------------- editor ---- */
/* ИИ-редактор: слева живое превью, справа чат. Каждая правка — новая версия. */

const ED_SUGGESTIONS = [
  'Сделай интернет-магазин с корзиной',
  'Смени тему на тёмную',
  'Сгенерируй фото для товаров',
  'Добавь блок с ценами',
  'Сделай заголовок короче и конкретнее',
];

function openEditor(jobId) {
  if (!jobId) return;
  state.editorJob = jobId;
  showScreen('editor');
  const url = '/api/site/' + jobId;
  $('#ed-open').href = url;
  const dl = $('#ed-download');
  dl.href = url;
  dl.setAttribute('download', 'site-' + jobId + '.html');
  $('#ed-model').textContent = CFG.llm && CFG.model ? ' · ' + CFG.model : '';
  updateEdTitle();
  const box = $('#ed-msgs');
  if (!box.dataset.greeted) {
    box.dataset.greeted = '1';
    box.innerHTML = '';
    edMsg('ai', 'Привет! Я помогу изменить сайт словами: тексты, секции, тему. Могу даже превратить лендинг в интернет-магазин. Напишите, что поправить, — или нажмите подсказку ниже.');
  }
  renderEdChips();
  refreshEditor();
  setTimeout(() => $('#ed-input').focus(), 120);
}

function updateEdTitle() {
  $('#ed-title').textContent = 'Редактор сайта' +
    (state.editorVersion > 0 ? ' · v' + state.editorVersion : '');
}

function refreshEditor() {
  if (!state.editorJob) return;
  $('#ed-frame').src = '/api/site/' + state.editorJob + '?v=' + Date.now();
}

function toggleDevice() {
  const box = $('#ed-preview-box');
  const mobile = !box.classList.contains('mobile');
  box.classList.toggle('mobile', mobile);
  $('#ic-desktop').classList.toggle('hidden', mobile);
  $('#ic-mobile').classList.toggle('hidden', !mobile);
}

function edMsg(role, text) {
  const box = $('#ed-msgs');
  const d = document.createElement('div');
  d.className = 'ed-msg ' + (role === 'user' ? 'user' : 'ai');
  d.textContent = text;
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
  return d;
}

function edTyping() {
  const box = $('#ed-msgs');
  const d = document.createElement('div');
  d.className = 'ed-msg ai typing';
  d.innerHTML = '<i></i><i></i><i></i>';
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
  return d;
}

function renderEdChips() {
  const wrap = $('#ed-chips');
  wrap.innerHTML = '';
  ED_SUGGESTIONS.forEach((s) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'ed-chip';
    b.textContent = s;
    b.addEventListener('click', () => {
      if (state.editorBusy) return;
      $('#ed-input').value = s;
      sendChat();
    });
    wrap.appendChild(b);
  });
}

async function sendChat() {
  const inp = $('#ed-input');
  const msg = inp.value.trim();
  if (!msg || state.editorBusy || !state.editorJob) return;
  if (!CFG.llm) {
    edMsg('ai', 'Редактору нужен ключ RouterAI: добавьте ROUTERAI_API_KEY в .env и перезапустите сервер.');
    return;
  }
  state.editorBusy = true;
  $('#ed-send').disabled = true;
  edMsg('user', msg);
  inp.value = '';
  inp.style.height = 'auto';
  // Пробуем SSE-поток, при любой проблеме — классический POST с опросом прогресса.
  if (window.EventSource) {
    try { await sendChatSSE(msg); return; }
    catch (e) { /* молча откатываемся на POST */ }
    finally {
      if (state.editorBusy) { state.editorBusy = false; $('#ed-send').disabled = false; }
    }
  }
  await sendChatLegacy(msg);
}

function chatProgressLabel(pr, s) {
  if (pr && pr.stage === 'images' && pr.total) {
    return pr.target === 'hero'
      ? `Рисую фото для первого экрана… ${s} с`
      : `Рисую фото товаров ${pr.done || 0}/${pr.total}… ${s} с`;
  }
  return s > 4 ? `Думаю… ${s} с` : '';
}

function finishChat(wait, timer, d) {
  if (timer) clearInterval(timer);
  wait.remove();
  let text = d.reply || 'Готово.';
  if (d.notes && d.notes.length) text += ' (' + d.notes.join('; ') + ')';
  if (d.applied) text += '\n\nПрименено правок: ' + d.applied + '.';
  edMsg('ai', text);
  if (d.version) { state.editorVersion = d.version; updateEdTitle(); }
  if (d.applied) refreshEditor();
  state.editorBusy = false;
  $('#ed-send').disabled = false;
  $('#ed-input').focus();
}

function sendChatSSE(msg) {
  return new Promise((resolve, reject) => {
    const wait = edTyping();
    const t0 = Date.now();
    const url = '/api/chat/stream/' + state.editorJob + '?message=' + encodeURIComponent(msg);
    const es = new EventSource(url);
    let settled = false;
    const timer = setInterval(() => {
      const s = Math.round((Date.now() - t0) / 1000);
      const label = s > 4 ? `Думаю… ${s} с` : '';
      if (label && wait.isConnected) wait.innerHTML = '<span style="font-size:13px;color:var(--muted)">' + label + '</span>';
    }, 1000);
    const cleanup = () => { clearInterval(timer); try { es.close(); } catch (e) {} };
    const finish = (fn) => { if (!settled) { settled = true; cleanup(); fn(); } };
    const hardTimeout = setTimeout(() => finish(() => { wait.remove(); reject(new Error('timeout')); }), 6 * 60 * 1000);
    es.addEventListener('progress', (e) => {
      try {
        const pr = JSON.parse(e.data);
        const s = Math.round((Date.now() - t0) / 1000);
        const label = chatProgressLabel(pr, s);
        if (label) wait.innerHTML = '<span style="font-size:13px;color:var(--muted)">' + label + '</span>';
      } catch (err) {}
    });
    es.addEventListener('done', (e) => {
      clearTimeout(hardTimeout);
      let d = {};
      try { d = JSON.parse(e.data); } catch (err) {}
      finish(() => { finishChat(wait, null, d); resolve(); });
    });
    es.addEventListener('error', (e) => {
      // серверное событие error … или обрыв соединения (e.data пусто)
      clearTimeout(hardTimeout);
      let serverErr = null;
      try { serverErr = e.data ? JSON.parse(e.data).error : null; } catch (err) {}
      if (serverErr) {
        finish(() => {
          wait.remove();
          edMsg('ai', 'Не получилось применить правку: ' + serverErr + '\nПопробуйте переформулировать запрос.');
          state.editorBusy = false;
          $('#ed-send').disabled = false;
          resolve();
        });
      } else {
        finish(() => { wait.remove(); reject(new Error('sse failed')); });
      }
    });
    es.onerror = () => {
      // HTTP-ошибка до старта потока (429/503/404): откат на POST
      clearTimeout(hardTimeout);
      finish(() => { wait.remove(); reject(new Error('sse failed')); });
    };
  });
}

async function sendChatLegacy(msg) {
  const inp = $('#ed-input');
  const wait = edTyping();
  // Пока ждём синхронный /api/chat — показываем живой прогресс: сервер пишет
  // его в память, фронт опрашивает отдельно.
  const t0 = Date.now();
  const timer = setInterval(async () => {
    const s = Math.round((Date.now() - t0) / 1000);
    let label = chatProgressLabel(null, s);
    try {
      const pr = await (await fetch('/api/chat/progress/' + state.editorJob)).json();
      label = chatProgressLabel(pr, s);
    } catch (e) { /* прогресс недоступен — показываем только таймер */ }
    if (label) wait.innerHTML = '<span style="font-size:13px;color:var(--muted)">' + label + '</span>';
  }, 1000);
  try {
    const r = await fetch('/api/chat/' + state.editorJob, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    });
    const d = await r.json();
    clearInterval(timer);
    if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
    finishChat(wait, timer, d);
  } catch (e) {
    clearInterval(timer);
    wait.remove();
    edMsg('ai', 'Не получилось применить правку: ' + e.message + '\nПопробуйте переформулировать запрос.');
    state.editorBusy = false;
    $('#ed-send').disabled = false;
    inp.focus();
  }
}

async function editorUndo() {
  if (!state.editorJob || state.editorBusy) return;
  state.editorBusy = true;
  try {
    const r = await fetch('/api/undo/' + state.editorJob, { method: 'POST' });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
    if (d.version) { state.editorVersion = d.version; updateEdTitle(); }
    edMsg('ai', d.reply || 'Отменил последнюю правку.');
    refreshEditor();
  } catch (e) {
    edMsg('ai', e.message || 'Отменять нечего.');
  }
  state.editorBusy = false;
}
