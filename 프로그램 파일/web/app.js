'use strict';
/* 로컬 AI 영어학습도구 — front end (no external resources) */

/* ================================================================ utils */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const escBr = s => esc(s).replace(/\n/g, '<br>');
const enc = encodeURIComponent;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const WORD_RE = /[A-Za-z0-9]+(?:['’][A-Za-z]+)*|['’](?:em|cause|til|bout)\b/gi;
const HANGUL = /[가-힣]/;

function fmtT(sec) {
  sec = Math.max(0, sec || 0);
  const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = Math.floor(sec % 60);
  return (h ? h + ':' + String(m).padStart(2, '0') : String(m)) + ':' + String(s).padStart(2, '0');
}
function fmtDur(sec) {
  const m = Math.round((sec || 0) / 60);
  return m >= 60 ? `${Math.floor(m / 60)}시간 ${m % 60}분` : `${m}분`;
}
function pct(x) { return Math.round((x || 0) * 100) + '%'; }
function mb(b) {
  b = b || 0;
  if (b < 1048576) return Math.max(1, Math.round(b / 1024)) + 'KB';
  const m = b / 1048576;
  return m >= 1024 ? (m / 1024).toFixed(1) + 'GB' : (m < 10 ? m.toFixed(1) : Math.round(m)) + 'MB';
}
const store = {
  get(k, d) { try { const v = localStorage.getItem('el.' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('el.' + k, JSON.stringify(v)); } catch (e) { /* storage may be blocked */ } },
};

async function api(path, opts = {}) {
  const o = { method: opts.method || (opts.body !== undefined ? 'POST' : 'GET'), headers: { 'X-EngLearn': '1' } };
  if (opts.body !== undefined) {
    if (opts.raw) { o.body = opts.body; o.headers['Content-Type'] = opts.type || 'application/octet-stream'; }
    else { o.body = JSON.stringify(opts.body); o.headers['Content-Type'] = 'application/json'; }
  }
  let r;
  try { r = await fetch(path, o); } catch (e) { throw new Error('프로그램과 연결이 끊겼어요. 실행 파일을 다시 실행해 주세요.'); }
  let data = {};
  try { data = await r.json(); } catch (e) { /* empty */ }
  if (!r.ok) { const err = new Error(data.error || ('오류 ' + r.status)); err.status = r.status; err.kind = data.kind; throw err; }
  return data;
}

function toast(msg, isErr) {
  const t = document.createElement('div');
  t.className = 'toast' + (isErr ? ' err' : '');
  t.textContent = msg;
  $('#toast').appendChild(t);
  setTimeout(() => t.remove(), isErr ? 7000 : 3200);
}
const errToast = e => toast(e && e.message ? e.message : String(e), true);

const I = {
  play: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M4.5 2.6v10.8L13 8z"/></svg>',
  pause: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M4 2.5h3v11H4zM9 2.5h3v11H9z"/></svg>',
  prev: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M3 2.5h2v11H3zM13 2.6v10.8L6 8z"/></svg>',
  next: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M11 2.5h2v11h-2zM3 2.6v10.8L10 8z"/></svg>',
  mic: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 1.5A2.5 2.5 0 0 0 5.5 4v4a2.5 2.5 0 0 0 5 0V4A2.5 2.5 0 0 0 8 1.5z"/><path d="M3.6 7.4a.7.7 0 0 1 1.4 0 3 3 0 0 0 6 0 .7.7 0 0 1 1.4 0 4.4 4.4 0 0 1-3.7 4.35v1.55h1.7a.7.7 0 0 1 0 1.4H5.6a.7.7 0 0 1 0-1.4h1.7v-1.55A4.4 4.4 0 0 1 3.6 7.4z"/></svg>',
  micOff: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 1.5A2.5 2.5 0 0 0 5.5 4v3.1l5 5V4A2.5 2.5 0 0 0 8 1.5z" opacity=".55"/><path d="M2.3 2.3a.7.7 0 0 1 1 0l10.4 10.4a.7.7 0 1 1-1 1L10.3 11.3A4.4 4.4 0 0 1 8.7 11.75v1.55h1.7a.7.7 0 0 1 0 1.4H5.6a.7.7 0 0 1 0-1.4h1.7v-1.55A4.4 4.4 0 0 1 3.6 7.4a.7.7 0 0 1 1.4 0 3 3 0 0 0 4.3 2.7L2.3 3.3a.7.7 0 0 1 0-1z"/></svg>',
  stop: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><rect x="3.5" y="3.5" width="9" height="9" rx="1.6"/></svg>',
  star: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 1.6l1.95 4.1 4.45.55-3.3 3.05.88 4.4L8 11.5l-3.98 2.2.88-4.4L1.6 6.25l4.45-.55z"/></svg>',
  speak: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M2.5 6h2.4L8.5 3v10L4.9 10H2.5z"/><path d="M10.8 5.1a4 4 0 0 1 0 5.8l-.95-.95a2.65 2.65 0 0 0 0-3.9z"/></svg>',
  trash: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M6.5 1.5h3a1 1 0 0 1 1 1V3H13a.75.75 0 0 1 0 1.5h-.6l-.62 8.6A1.75 1.75 0 0 1 10.04 14.7H5.96a1.75 1.75 0 0 1-1.74-1.6L3.6 4.5H3A.75.75 0 0 1 3 3h2.5v-.5a1 1 0 0 1 1-1zM5.1 4.5l.6 8.5c.01.14.12.25.26.25h4.08c.14 0 .25-.11.26-.25l.6-8.5zm1.65 1.75a.6.6 0 0 1 .6.56l.25 4.5a.6.6 0 1 1-1.2.06l-.25-4.5a.6.6 0 0 1 .6-.62zm2.5 0a.6.6 0 0 1 .6.62l-.25 4.5a.6.6 0 1 1-1.2-.06l.25-4.5a.6.6 0 0 1 .6-.56z"/></svg>',
  film: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M2 3.5A1.5 1.5 0 0 1 3.5 2h9A1.5 1.5 0 0 1 14 3.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12.5zm2 .5v1.5h1.5V4zm6.5 0v1.5H12V4zM4 7.25v1.5h1.5v-1.5zm6.5 0v1.5H12v-1.5zM4 10.5V12h1.5v-1.5zm6.5 0V12H12v-1.5z"/></svg>',
};

/* ================================================================ state */
const S = {
  st: null, ollama: null, view: store.get('view', 'home'), pid: store.get('pid', null),
  lines: [], lineMap: new Map(), linesPid: null, cur: null,
  filter: store.get('filter', 'key'), search: '',
  sub: store.get('sub', 'hidden'), speed: store.get('speed', 1), loops: store.get('loops', 1),
  tab: store.get('tab', 'dict'), hints: { count: false, first: false },
  detail: {}, dict: {}, speak: {}, revealed: new Set(), justChecked: null,
  sources: {}, srcSel: {}, exprs: null, exprCat: 'all', exprStar: false, exprBusy: {},
  talk: null, talkSetup: true, talkHideQ: store.get('hideQ', false), talkAuto: store.get('talkAuto', false),
  review: null, revIdx: 0, revShow: false,
  jobs: [], explaining: null, lastLinesLoad: 0,
  maskEdit: {}, maskBusy: null, micPanel: false, micErr: '', micTry: '', micBusy: false, mics: [], recs: null,
};
const CAT = () => (S.st && S.st.categories) || {};
const cur = () => (S.st && S.st.projects || []).find(p => p.id === S.pid) || null;

/* ================================================================ media player */
const Player = {
  v: null, src: '', clip: null, loopsLeft: 0, onDone: null, raf: 0, free: false, audioOnly: false, failed: false,
  init() {
    const v = this.v = document.createElement('video');
    v.preload = 'auto'; v.playsInline = true; v.setAttribute('playsinline', '');
    v.addEventListener('timeupdate', () => this._check());
    v.addEventListener('play', () => renderPlayState());
    v.addEventListener('pause', () => renderPlayState());
    v.addEventListener('error', () => { if (this.src) { this.failed = true; updateOverlay(); } });
    v.addEventListener('loadedmetadata', () => { this.failed = false; updateOverlay(); Mask.place(); });
    if (window.ResizeObserver) this.ro = new ResizeObserver(() => Mask.place());
  },
  mount(el) {
    if (el && this.v.parentNode !== el) el.prepend(this.v);
    if (el && this.ro) { this.ro.disconnect(); this.ro.observe(el); }
    Mask.place();
  },
  setSource(p) {
    this.pid = p ? p.id : null;
    const m = (p && p.media) || {};
    const ok = m.state === 'ready' || m.state === 'audio';
    const url = ok && m.file ? `/media/${enc(p.id)}?f=${enc(m.file)}` : '';
    this.audioOnly = !!m.audio_only;
    if (url !== this.src) {
      this.pause();
      this.src = url; this.failed = false;
      if (url) { this.v.src = url; this.v.load(); } else { this.v.removeAttribute('src'); this.v.load(); }
    }
    updateOverlay();
  },
  ready() { return !!this.src && !this.failed; },
  async playClip(cs, ce, { rate = 1, loops = 1, onDone = null } = {}) {
    if (!this.ready()) { toast(this.failed ? '이 영상은 창에서 재생되지 않아요. 영화 화면에서 재생용 영상을 만들어 주세요.' : '아직 재생 준비 중이에요. 잠시 뒤 다시 눌러 주세요.', !!this.failed); return false; }
    TTS.stop();
    this.free = false;
    this.clip = { cs, ce }; this.loopsLeft = loops; this.onDone = onDone;
    this.v.playbackRate = rate;
    return this._go(cs);
  },
  async _go(t) {
    try {
      this.v.currentTime = Math.max(0, t);
      await this.v.play();
      this._watch();
      return true;
    } catch (e) {
      if (e.name !== 'AbortError') toast('재생하지 못했어요: ' + e.message, true);
      return false;
    }
  },
  _watch() {
    cancelAnimationFrame(this.raf);
    const tick = () => { if (!this._check()) this.raf = requestAnimationFrame(tick); };
    this.raf = requestAnimationFrame(tick);
  },
  _check() {
    if (this.free) { onFreeTime(this.v.currentTime); return false; }
    if (!this.clip) return true;
    if (this.v.currentTime >= this.clip.ce || this.v.ended) {
      this.v.pause();
      this.loopsLeft -= 1;
      if (this.loopsLeft > 0) {
        const c = this.clip;
        setTimeout(() => { if (this.clip === c) this._go(c.cs); }, 520);
        return true;
      }
      const cb = this.onDone; this.clip = null; this.onDone = null;
      cancelAnimationFrame(this.raf);
      renderPlayState();
      if (cb) cb();
      return true;
    }
    return false;
  },
  async playFree(from) {
    if (!this.ready()) return;
    TTS.stop();
    this.clip = null; this.free = true; this.v.playbackRate = S.speed;
    try { this.v.currentTime = from; await this.v.play(); this._watch(); } catch (e) { /* ignore */ }
  },
  pause() { this.clip = null; this.onDone = null; this.free = false; cancelAnimationFrame(this.raf); if (this.v) this.v.pause(); },
  playing() { return this.v && !this.v.paused; },
};

/* ================================================================ cover for subtitles burned into the picture */
const MASK_DEFAULT = { on: false, top: 0.78, height: 0.16, style: 'solid' };
const Mask = {
  saveT: 0,
  get(pid) {
    const p = S.st && (S.st.projects || []).find(x => x.id === pid);
    return { ...MASK_DEFAULT, ...((p && p.mask) || {}), ...((S.maskEdit || {})[pid] || {}) };
  },
  set(pid, ch, save = true) {
    S.maskEdit[pid] = { ...(S.maskEdit[pid] || {}), ...ch };
    this.place();
    if (save) this.save(pid);
  },
  save(pid) {
    clearTimeout(this.saveT);
    this.saveT = setTimeout(async () => {
      const m = this.get(pid);
      try {
        const d = await api(`/api/projects/${enc(pid)}/mask`, { body: { mask: { on: m.on, top: m.top, height: m.height, style: m.style } } });
        const p = (S.st.projects || []).find(x => x.id === pid);
        if (p) p.mask = d.mask;
      } catch (e) { errToast(e); }
    }, 350);
  },
  rect(screen) {   // where the picture sits inside the 16:9 screen (letterboxed)
    const v = Player.v, W = screen.clientWidth, H = screen.clientHeight;
    const vw = v.videoWidth || 16, vh = v.videoHeight || 9;
    const k = Math.min(W / vw, H / vh);
    return { x: (W - vw * k) / 2, y: (H - vh * k) / 2, w: vw * k, h: vh * k };
  },
  place() {
    const v = Player.v;
    if (!v) return;
    const screen = v.parentNode;
    $$('.burn-mask').forEach(el => { if (el.parentNode !== screen) el.remove(); });
    if (!screen || !screen.classList || !screen.classList.contains('screen')) return;
    const pid = Player.pid;
    const m = pid ? this.get(pid) : null;
    let el = $('.burn-mask', screen);
    if (!m || !m.on || !Player.ready() || Player.audioOnly) { if (el) el.remove(); return; }
    if (!el) {
      el = document.createElement('div');
      el.className = 'burn-mask';
      el.tabIndex = 0;
      el.setAttribute('role', 'group');
      el.setAttribute('aria-label', '화면 자막 가림막. 위아래 화살표로 옮기고, Shift와 화살표로 높이를 바꿔요.');
      el.innerHTML = `<span class="bm-edge top" data-edge="top" title="끌어서 높이 조절"></span>
        <span class="bm-hint" aria-hidden="true">끌어서 옮기기 · 위아래 끝을 끌어 높이 맞추기</span>
        <span class="bm-tools"><button type="button" data-act="mask-style"></button><button type="button" data-act="mask-detect">자동 찾기</button><button type="button" data-act="mask-toggle">가림막 끄기</button></span>
        <span class="bm-edge bottom" data-edge="bottom" title="끌어서 높이 조절"></span>`;
      screen.appendChild(el);
    }
    const r = this.rect(screen);
    el.style.left = r.x + 'px';
    el.style.width = r.w + 'px';
    el.style.top = (r.y + m.top * r.h) + 'px';
    el.style.height = Math.max(6, m.height * r.h) + 'px';
    el.classList.toggle('blur', m.style === 'blur');
    el.classList.toggle('solid', m.style !== 'blur');
    el.classList.toggle('finding', S.maskBusy === pid);
    el.classList.toggle('thin', m.height * r.h < 34);
    const sb = $('[data-act="mask-style"]', el);
    if (sb) sb.textContent = m.style === 'blur' ? '덮기로' : '흐리게';
  },
  toggle(pid) {
    const m = this.get(pid);
    const first = !m.on && !((S.st.projects || []).find(x => x.id === pid) || {}).mask?.top;
    this.set(pid, { on: !m.on });
    renderTransport();
    if (!m.on) {
      if (first && S.lines.length >= 8) this.detect(pid, true);
      else toast('가림막을 끌어서 화면 자막 위에 맞추세요. 위아래 끝을 끌면 높이가 바뀌어요.');
    }
  },
  async detect(pid, first = false) {
    if (S.maskBusy) return;
    S.maskBusy = pid; this.place();
    toast('화면에 박힌 자막 위치를 찾고 있어요… (10초쯤)');
    try {
      const d = await api(`/api/projects/${enc(pid)}/mask/detect`, { body: {} });
      const p = (S.st.projects || []).find(x => x.id === pid);
      if (p) p.mask = d.mask;
      delete S.maskEdit[pid];
      if (d.found) toast('화면 자막을 찾아서 가렸어요. 어긋나면 가림막을 끌어서 맞추세요.');
      else {
        if (first) this.set(pid, { top: d.suggest.top, height: d.suggest.height });
        toast(d.reason === 'few' ? '대사가 적어서 자동으로 찾지 못했어요. 가림막을 끌어서 자막 위에 맞춰 주세요.' : '화면 자막을 찾지 못했어요. 가림막을 끌어서 자막 위에 맞춰 주세요.');
      }
    } catch (e) { errToast(e); }
    S.maskBusy = null; this.place(); renderTransport();
  },
};

function maskPointerDown(e) {
  const el = e.target.closest('.burn-mask');
  if (!el || e.button !== 0 || e.target.closest('button')) return;
  e.preventDefault();
  el.focus({ preventScroll: true });
  const pid = Player.pid, m = Mask.get(pid), r = Mask.rect(el.parentNode);
  const edge = e.target.dataset.edge || '';
  const y0 = e.clientY, top0 = m.top, h0 = m.height;
  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  el.setPointerCapture(e.pointerId);
  el.classList.add('drag');
  const move = ev => {
    const dy = (ev.clientY - y0) / r.h;
    let top = top0, height = h0;
    if (edge === 'top') { top = clamp(top0 + dy, 0, top0 + h0 - 0.03); height = h0 - (top - top0); }
    else if (edge === 'bottom') height = clamp(h0 + dy, 0.03, 1 - top0);
    else top = clamp(top0 + dy, 0, 1 - h0);
    Mask.set(pid, { top, height }, false);
  };
  const up = () => {
    el.classList.remove('drag');
    el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); el.removeEventListener('pointercancel', up);
    Mask.save(pid);
  };
  el.addEventListener('pointermove', move); el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up);
}

function maskKey(e) {
  if (!['ArrowUp', 'ArrowDown'].includes(e.key)) return false;
  e.preventDefault(); e.stopPropagation();
  const pid = Player.pid, m = Mask.get(pid), d = e.key === 'ArrowUp' ? -0.01 : 0.01;
  if (e.shiftKey) { const height = Math.min(1 - m.top, Math.max(0.03, m.height - d)); Mask.set(pid, { height }); }
  else Mask.set(pid, { top: Math.min(1 - m.height, Math.max(0, m.top + d)) });
  return true;
}

/* ================================================================ microphone */
// The microphone is opened only when the learner records or checks it, and closed again right after
// (unless they chose "연습하는 동안 켜 두기"). The rail always shows whether it is on.
const Rec = {
  stream: null, mr: null, live: false, ctx: null, src: null, an: null, buf: null, starting: null,
  level: 0, rms: 0, peak: 0, holdAt: 0, heardAt: 0, onAt: 0, raf: 0, idle: 0,
  isOn() { return !!(this.stream && this.stream.active); },
  track() { return this.stream ? this.stream.getAudioTracks()[0] || null : null; },
  async warm() {
    if (this.isOn()) { this._touch(); return this.stream; }
    if (!this.starting) this.starting = this._open().finally(() => { this.starting = null; });
    return this.starting;
  },
  async _open() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error('이 창에서는 마이크를 쓸 수 없어요.');
    const base = { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 };
    const dev = store.get('mic.device', '');
    let stream;
    try {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: dev ? { ...base, deviceId: { exact: dev } } : base });
      } catch (e) {
        if (!dev || !['OverconstrainedError', 'NotFoundError'].includes(e.name)) throw e;
        store.set('mic.device', '');   // the chosen microphone is gone: use the default one
        stream = await navigator.mediaDevices.getUserMedia({ audio: base });
      }
    } catch (e) {
      if (e.name === 'NotAllowedError') throw new Error('마이크 사용이 막혀 있어요. 창 위쪽의 마이크 아이콘에서 "허용"을 누르거나, Windows 설정 → 개인 정보 및 보안 → 마이크에서 데스크톱 앱의 마이크 사용을 켜 주세요.');
      if (e.name === 'NotFoundError') throw new Error('마이크를 찾을 수 없어요. 마이크(이어폰)를 연결해 주세요.');
      if (e.name === 'NotReadableError') throw new Error('다른 프로그램이 마이크를 쓰고 있어서 켤 수 없어요. 그 프로그램을 닫고 다시 해 보세요.');
      throw new Error('마이크를 켜지 못했어요: ' + e.message);
    }
    if (document.hidden) { stream.getTracks().forEach(t => t.stop()); throw new Error('창이 내려가 있어서 마이크를 켜지 않았어요.'); }
    this.stream = stream; this.onAt = performance.now(); this.heardAt = 0; this.peak = 0; this.level = 0; this.rms = 0;
    const tr = this.track();
    if (tr) {
      tr.onended = () => { if (this.stream === stream) { this.release(); toast('마이크 연결이 끊겼어요.', true); } };
      tr.onmute = tr.onunmute = () => renderMic();
    }
    try {
      const ctx = this.ctx || (this.ctx = new (window.AudioContext || window.webkitAudioContext)());
      if (ctx.state === 'suspended') await ctx.resume();
      this.src = ctx.createMediaStreamSource(stream);
      this.an = ctx.createAnalyser(); this.an.fftSize = 1024; this.src.connect(this.an);
      this.buf = new Float32Array(this.an.fftSize);
    } catch (e) { this.an = null; }
    this._meter();
    this._touch();
    renderMic();
    if (S.micPanel) { listMics(); renderMicPanel(); }
    return stream;
  },
  _meter() {
    cancelAnimationFrame(this.raf);
    const tick = () => {
      if (!this.isOn()) return;
      if (this.an) {
        this.an.getFloatTimeDomainData(this.buf);
        let sum = 0, pk = 0;
        for (let i = 0; i < this.buf.length; i++) { const x = this.buf[i]; sum += x * x; const ax = x < 0 ? -x : x; if (ax > pk) pk = ax; }
        const rms = Math.sqrt(sum / this.buf.length);
        const lv = Math.max(0, Math.min(1, (20 * Math.log10(rms + 1e-8) + 60) / 54));   // -60 dB … -6 dB
        this.level = lv > this.level ? lv : this.level * 0.82 + lv * 0.18;
        this.rms = rms;
        const now = performance.now();
        if (rms > 0.012) this.heardAt = now;
        if (pk >= this.peak || now - this.holdAt > 1500) { this.peak = pk; this.holdAt = now; }
      }
      drawMic();
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  },
  _touch() {
    clearTimeout(this.idle);
    if (S.st && S.st.settings.mic_keep) {
      this.idle = setTimeout(() => {
        if (this.isOn() && !this.live && !S.micPanel) { this.release(); toast('10분 동안 쓰지 않아서 마이크를 껐어요.'); }
      }, 10 * 60 * 1000);
    }
  },
  release() {
    clearTimeout(this.idle); cancelAnimationFrame(this.raf);
    if (this.live) this.stop();
    try { if (this.src) this.src.disconnect(); } catch (e) { /* ignore */ }
    this.src = null; this.an = null;
    if (this.stream) { this.stream.getTracks().forEach(t => { t.onended = null; t.stop(); }); this.stream = null; }
    if (this.ctx && this.ctx.state === 'running') this.ctx.suspend().catch(() => {});
    this.level = 0; this.rms = 0; this.peak = 0;
    renderMic(); drawMic();
  },
  doneUsing() {
    if (S.micPanel) return;                                  // the check window keeps it on until it closes
    if (S.st && S.st.settings.mic_keep) { this._touch(); renderMic(); return; }
    this.release();
  },
  record({ maxSec = 30, silenceMs = 1300, onLevel = null } = {}) {
    return new Promise(async (resolve, reject) => {
      let stream;
      try { stream = await this.warm(); } catch (e) { reject(e); return; }
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'].find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';
      let mr;
      try { mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined); } catch (e) { this.doneUsing(); reject(new Error('녹음을 시작하지 못했어요: ' + e.message)); return; }
      const chunks = [];
      let timer = 0;
      mr.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
      mr.onstop = () => {
        this.live = false; this.mr = null; clearTimeout(timer);
        renderRecButtons(); renderMic();
        this.doneUsing();
        resolve(chunks.length ? new Blob(chunks, { type: mr.mimeType || 'audio/webm' }) : null);
      };
      let spoke = false, quietSince = 0;
      const t0 = performance.now();
      const tick = () => {
        if (!this.live) return;
        const now = performance.now();
        if (onLevel) onLevel(this.level);
        if (this.an) {
          if (this.rms > 0.018) { spoke = true; quietSince = 0; }
          else if (spoke && silenceMs) { quietSince = quietSince || now; if (now - quietSince > silenceMs) { this.stop(); return; } }
        }
        if ((now - t0) / 1000 > maxSec) { this.stop(); return; }
        timer = setTimeout(tick, 50);
      };
      this.mr = mr; this.live = true; this.recAt = t0; mr.start(250);
      renderRecButtons(); renderMic();
      tick();
    });
  },
  stop() { if (this.mr && this.mr.state !== 'inactive') this.mr.stop(); },
};

let micDrawAt = 0;
function drawMic() {
  const on = Rec.isOn();
  const lv = on ? Rec.level : 0;
  const mini = $('#micMini'); if (mini) mini.style.transform = `scaleX(${lv.toFixed(3)})`;
  const big = $('#micBig'); if (big) big.style.transform = `scaleX(${lv.toFixed(3)})`;
  const now = performance.now();
  if (now - micDrawAt < 250) return;
  micDrawAt = now;
  const chip = $('#micChip');
  if (chip && on) {
    const quiet = now - Math.max(Rec.heardAt, Rec.onAt) > 3500;
    chip.classList.toggle('quiet', quiet);
    const m = $('#micChipMsg');
    if (m) m.textContent = Rec.track() && Rec.track().muted ? '음소거됨' : quiet ? '소리 없음' : Rec.live ? '녹음 중' : '켜짐';
  }
  if (S.micPanel) micVerdict();
}

function renderMic() {
  const box = $('#micChipBox');
  if (!box) return;
  if (Rec.isOn()) {
    box.innerHTML = `<div class="mic-chip on ${Rec.live ? 'rec' : ''}" id="micChip">
      <button class="mic-main" data-act="mic-panel" title="마이크 확인 창 열기"><span class="dot" aria-hidden="true"></span><span class="txt"><b>마이크</b> <span id="micChipMsg">${Rec.live ? '녹음 중' : '켜짐'}</span></span><span class="mini" aria-hidden="true"><i id="micMini"></i></span></button>
      <button class="mic-off" data-act="mic-off" title="마이크 끄기">끄기</button></div>`;
  } else {
    box.innerHTML = `<button class="mic-chip" id="micChip" data-act="mic-panel" title="마이크가 잘 되는지 확인해요">${I.micOff}<span class="txt"><b>마이크</b> 꺼짐</span></button>`;
  }
  if (S.view === 'settings' && $('#micState')) $('#micState').innerHTML = micStateHTML();
}

function micStateHTML() {
  return Rec.isOn()
    ? `<span class="chip rec-on">켜져 있음</span> <button class="btn small" data-act="mic-off">마이크 끄기</button>`
    : '<span class="chip">꺼져 있음</span>';
}

async function listMics() {
  try {
    const all = await navigator.mediaDevices.enumerateDevices();
    S.mics = all.filter(d => d.kind === 'audioinput');
  } catch (e) { S.mics = []; }
  const sel = $('#micDevice');
  if (!sel) return;
  const want = store.get('mic.device', '');
  const tr = Rec.track();
  const used = tr && tr.getSettings ? tr.getSettings().deviceId : '';
  sel.innerHTML = `<option value="">기본 마이크${!want && tr ? ` (${esc(tr.label || '지금 쓰는 것')})` : ''}</option>` +
    S.mics.filter(d => d.deviceId && d.deviceId !== 'default' && d.deviceId !== 'communications')
      .map((d, i) => `<option value="${esc(d.deviceId)}" ${want === d.deviceId ? 'selected' : ''}>${esc(d.label || `마이크 ${i + 1}`)}${used === d.deviceId && want ? ' · 사용 중' : ''}</option>`).join('');
}

function openMicPanel() {
  S.micPanel = true; S.micErr = ''; S.micTry = '';
  S.micReturn = document.activeElement;
  renderMicPanel();
  Rec.warm().then(() => { listMics(); renderMicPanel(); }).catch(e => { S.micErr = e.message; renderMicPanel(); });
}

function closeMicPanel(turnOff) {
  if (!S.micPanel) return;
  S.micPanel = false;
  if (Rec.live) Rec.stop();
  const m = $('#micModal'); if (m) m.remove();
  if (S.micAudio) { try { S.micAudio.pause(); } catch (e) { /* ignore */ } S.micAudio = null; }
  if (turnOff) Rec.release(); else if (!Rec.live) Rec.doneUsing();
  if (S.micReturn && document.contains(S.micReturn)) S.micReturn.focus();
}

function renderMicPanel() {
  let m = $('#micModal');
  if (!S.micPanel) { if (m) m.remove(); return; }
  if (!m) { m = document.createElement('div'); m.id = 'micModal'; m.className = 'modal'; document.body.appendChild(m); }
  const on = Rec.isOn();
  const keep = !!(S.st && S.st.settings.mic_keep);
  const busy = Rec.live || S.micBusy;
  m.innerHTML = `<div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="micTitle">
    <h2 id="micTitle">마이크 확인</h2>
    <p class="small muted" style="margin-top:0">영어로 아무 말이나 해 보세요. 말할 때 막대가 움직이면 마이크가 소리를 듣고 있는 거예요. 소리는 이 컴퓨터 안에서만 처리하고 인터넷으로 보내지 않아요.</p>
    ${S.micErr ? `<div class="note warn" style="margin-bottom:10px">${esc(S.micErr)}</div>` : ''}
    <label class="field"><span>쓸 마이크</span><select id="micDevice"><option value="">기본 마이크</option></select></label>
    <div class="mic-big ${on ? '' : 'off'}" aria-hidden="true"><i id="micBig"></i><span class="tick" style="left:30%"></span><span class="tick" style="left:85%"></span></div>
    <div class="mic-zones" aria-hidden="true"><span style="left:15%">작음</span><span style="left:57.5%">알맞음</span><span style="left:92.5%">너무 큼</span></div>
    <div class="mic-verdict" id="micVerdict" role="status">${on ? '말해 보세요…' : S.micErr ? '마이크를 켜지 못했어요.' : '마이크를 켜는 중…'}</div>
    <div class="row" style="margin-top:12px">
      <button class="btn" data-act="mic-try" ${on && !busy ? '' : 'disabled'}>${I.mic} 3초 녹음해서 들어 보기</button>
      <button class="btn" data-act="mic-stt" ${on && !busy ? '' : 'disabled'}>말한 내용을 알아듣는지 확인</button>
    </div>
    <div class="small mic-try" id="micTryOut" aria-live="polite">${esc(S.micTry || '')}</div>
    <div class="field" style="margin-top:16px"><span>녹음이 끝나면</span>
      <div class="seg" data-seg="micKeep"><button class="${keep ? '' : 'on'}" data-val="0">마이크 바로 끄기 (추천)</button><button class="${keep ? 'on' : ''}" data-val="1">연습하는 동안 켜 두기</button></div>
      <span class="faint xs">켜 두면 녹음이 조금 더 빨리 시작돼요. 그래도 10분 동안 안 쓰거나, 다른 화면으로 가거나, 창을 내리면 저절로 꺼져요.</span></div>
    <div class="row end" style="margin-top:18px"><button class="btn" data-act="mic-close">닫기</button><button class="btn primary" data-act="mic-off-close">마이크 끄고 닫기</button></div>
  </div>`;
  listMics();
  const first = $('#micModal [data-act="mic-off-close"]');
  if (first && !m.contains(document.activeElement)) first.focus();
}

function micVerdict() {
  const el = $('#micVerdict');
  if (!el || !Rec.isOn()) return;
  const tr = Rec.track(), now = performance.now();
  let cls = '', t;
  if (tr && tr.muted) { cls = 'warn'; t = '마이크가 음소거돼 있어요. 마이크·이어폰의 음소거 버튼이나 Windows 소리 설정을 확인해 주세요.'; }
  else if (!Rec.heardAt) {
    if (now - Rec.onAt > 4000) { cls = 'warn'; t = '아직 아무 소리도 안 들려요. 위에서 다른 마이크를 고르거나, 마이크가 꺼져 있지 않은지 확인해 주세요.'; }
    else t = '말해 보세요…';
  }
  else if (Rec.peak > 0.98) { cls = 'warn'; t = '소리가 너무 커서 찌그러질 수 있어요. 마이크에서 조금 떨어져 말해 보세요.'; }
  else if (now - Rec.heardAt < 1500 && Rec.peak < 0.06) { cls = 'warn'; t = '소리가 작아요. 마이크에 조금 더 가까이 대고 말해 보세요.'; }
  else if (now - Rec.heardAt < 2500) { cls = 'good'; t = '잘 들려요.'; }
  else t = '조용해요. 말하면 막대가 움직여요.';
  if (el.textContent !== t) { el.className = 'mic-verdict ' + cls; el.textContent = t; }
}

async function micTry(kind) {
  if (Rec.live || S.micBusy) return;
  S.micBusy = true;
  const out = t => { S.micTry = t; const o = $('#micTryOut'); if (o) o.textContent = t; };
  $$('#micModal [data-act="mic-try"], #micModal [data-act="mic-stt"]').forEach(b => { b.disabled = true; });
  try {
    if (kind === 'play') {
      out('3초 동안 말해 보세요…');
      const blob = await Rec.record({ maxSec: 3, silenceMs: 0 });
      if (!S.micPanel) return;   // the window was closed meanwhile
      if (!blob) { out('녹음된 소리가 없어요.'); return; }
      out('녹음한 소리를 들려 드려요. (저장하지 않아요)');
      const url = URL.createObjectURL(blob);
      const a = S.micAudio = new Audio(url);
      a.onended = () => { URL.revokeObjectURL(url); out('잘 들렸나요? 너무 작거나 지직거리면 다른 마이크를 골라 보세요.'); };
      await a.play();
    } else {
      out('영어로 한 문장 말해 보세요… (예: Nice to meet you)');
      const blob = await Rec.record({ maxSec: 6, silenceMs: 1200 });
      if (!S.micPanel) return;
      if (!blob) { out('녹음된 소리가 없어요.'); return; }
      out('알아듣는 중…');
      const r = await api('/api/stt?purpose=check', { body: blob, raw: true, type: blob.type });
      out(r.no_speech ? '목소리가 들리지 않았어요. 조금 더 크게, 마이크 가까이에서 말해 보세요.' : `알아들은 말: "${r.text}" (녹음은 알아들은 뒤 바로 지웠어요)`);
    }
  } catch (e) { out(e.message); }
  finally {
    S.micBusy = false;
    $$('#micModal [data-act="mic-try"], #micModal [data-act="mic-stt"]').forEach(b => { b.disabled = !Rec.isOn(); });
  }
}

/* ================================================================ text to speech */
const TALK_VOICE = { interview_basic: 'af_heart', interview_behavior: 'am_michael', meeting_update: 'bf_emma', meeting_discuss: 'bm_george', schedule: 'af_bella', smalltalk: 'am_fenrir', custom: 'af_heart' };
const TTS = {
  voices: [], audio: null, warned: false,
  init() {
    if (!window.speechSynthesis) return;
    const load = () => { this.voices = speechSynthesis.getVoices(); if (S.view === 'settings' && S.st) renderSettings(); };
    load();
    speechSynthesis.onvoiceschanged = load;
  },
  english() {
    const allow = S.st && S.st.settings.allow_online_voices;
    return this.voices.filter(v => /^en([-_]|$)/i.test(v.lang) && (allow || v.localService));
  },
  pick() {
    const name = S.st && S.st.settings.tts_voice;
    const list = this.english();
    return list.find(v => v.name === name) || list.find(v => /en[-_]US/i.test(v.lang)) || list[0] || null;
  },
  kokoro() { return !!(S.st && S.st.tts && S.st.tts.ready && S.st.settings.tts_engine !== 'browser'); },
  speak(text, { rate = null, onend = null, voice = null } = {}) {
    if (!text) { if (onend) onend(); return; }
    Player.pause();
    this.stop();
    const r = rate || (S.st && S.st.settings.tts_rate) || 0.95;
    if (this.kokoro()) {
      const v = voice || S.st.settings.tts_voice_k || 'af_heart';
      const a = this.audio = new Audio(`/api/tts?t=${enc(text)}&v=${enc(v)}&s=${r}`);
      a.onended = () => { if (this.audio === a) this.audio = null; if (onend) onend(); };
      a.onerror = () => { if (this.audio === a) { this.audio = null; this.browserSpeak(text, r, onend); } };
      a.play().catch(() => {});
      return;
    }
    this.browserSpeak(text, r, onend);
  },
  browserSpeak(text, rate, onend) {
    if (!window.speechSynthesis) { if (onend) onend(); return; }
    const v = this.pick();
    if (!v && !this.warned) {
      this.warned = true;
      const t = S.st && S.st.tts;
      toast(t && !t.ready ? '영어 음성을 준비하고 있어요. 끝나면 자연스러운 영어로 읽어 줘요.' : '이 컴퓨터에 영어 음성이 없어요. 설정에서 로컬 영어 음성을 설치해 주세요.', true);
    }
    const u = new SpeechSynthesisUtterance(text);
    if (v) { u.voice = v; u.lang = v.lang; } else { u.lang = 'en-US'; }
    u.rate = rate;
    u.onend = () => onend && onend();
    u.onerror = () => onend && onend();
    speechSynthesis.speak(u);
  },
  stop() {
    if (window.speechSynthesis) speechSynthesis.cancel();
    if (this.audio) { try { this.audio.pause(); } catch (e) { /* ignore */ } this.audio = null; }
  },
};

/* ================================================================ boot */
async function refreshState() {
  S.st = await api('/api/state');
  renderStatus();
  Mask.place();
  return S.st;
}

async function boot() {
  Player.init(); TTS.init();
  document.addEventListener('click', onClick);
  document.addEventListener('keydown', onKey);
  document.addEventListener('change', onChange);
  document.addEventListener('input', onInput);
  $('#railMovie').addEventListener('click', () => show('home'));
  document.addEventListener('pointerdown', maskPointerDown);
  window.addEventListener('pagehide', () => { Rec.release(); try { fetch('/api/bye', { method: 'POST', keepalive: true, headers: { 'X-EngLearn': '1' } }); } catch (e) { /* ignore */ } });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && Rec.isOn()) { closeMicPanel(true); Rec.release(); S.micHidden = true; }
    else if (!document.hidden && S.micHidden) { S.micHidden = false; toast('창을 내려 둔 동안 마이크를 껐어요.'); }
  });
  window.addEventListener('resize', () => Mask.place());
  window.addEventListener('pageshow', ping);
  try { await refreshState(); } catch (e) { document.body.innerHTML = `<div class="empty"><h2>프로그램에 연결하지 못했어요</h2><p>${esc(e.message)}</p></div>`; return; }
  reportClient();
  if (S.pid && !S.st.projects.some(p => p.id === S.pid)) S.pid = null;
  if (!S.pid && S.st.projects.length) S.pid = S.st.projects[0].id;
  store.set('pid', S.pid);
  const start = S.st.projects.length ? S.view : 'home';
  show(['home', 'study', 'expr', 'talk', 'review', 'settings'].includes(start) ? start : 'home');
  checkOllama();
  setInterval(() => { if (!S.ollama || !S.ollama.ok || S.view === 'settings') checkOllama(); }, 60000);
  ping(); setInterval(ping, 10000);
  pollJobs();
}

function reportClient() {
  const v = document.createElement('video');
  const t = 'video/mp4; codecs="hvc1.1.6.L93.B0"';
  const hevc = !!(v.canPlayType(t) || (window.MediaSource && MediaSource.isTypeSupported && MediaSource.isTypeSupported(t)));
  api('/api/client', { body: { hevc } }).catch(() => {});
}
function ping() {
  fetch('/api/ping').then(r => r.json()).then(d => {
    // the program was updated and restarted: load the new screen
    if (S.st && d.version && d.version !== S.st.version) location.reload();
  }).catch(() => {});
}

async function checkOllama() {
  const before = S.ollamaKey;
  try { S.ollama = await api('/api/ollama'); } catch (e) { S.ollama = { ok: false, error: e.message, models: [] }; }
  // re-draw the screens that show the AI note only when what they show changed (keeps typed text)
  S.ollamaKey = [S.ollama.ok, S.ollama.need_model, S.ollama.installed, S.ollama.model].join('|');
  renderStatus();
  if (S.view === 'settings') renderSettings();
  if (S.view === 'home') renderHome();
  if (S.view === 'talk' && (!S.talk || S.talkSetup) && before !== S.ollamaKey) renderTalkSetup();
  if (S.ollama.pull && S.ollama.pull.running) watchPull();
}

/* Ollama missing / off / without a model: one note, used on the home, talk and settings screens. */
function aiNote(where) {
  const ol = S.ollama;
  if (!ol) return '';
  const tail = where === 'talk' ? '면접·미팅 연습은 AI가 있어야 시작할 수 있어요.'
    : where === 'home' ? '자막 준비, 받아쓰기, 따라 말하기는 지금도 할 수 있어요.' : '';
  if (!ol.ok) {
    if (ol.installed) return `<div class="note warn ai-note">Ollama가 꺼져 있어요. ${tail}
      <div class="row"><button class="btn small primary" data-act="start-ollama">Ollama 켜기</button><button class="btn small" data-act="recheck-ollama">다시 확인</button></div></div>`;
    return `<div class="note warn ai-note">AI 대화·분석에 쓰는 <b>Ollama</b>가 이 컴퓨터에 없어요. ${tail}
      <div class="small" style="margin-top:4px">프로그램 창을 닫고 <b>영어학습도구 실행.bat</b>을 다시 실행하면 설치를 도와줘요. 직접 설치해도 돼요.</div>
      <div class="row"><a class="btn small" href="https://ollama.com/download" target="_blank" rel="noopener">Ollama 내려받는 곳 열기</a><button class="btn small" data-act="recheck-ollama">다시 확인</button></div></div>`;
  }
  if (!ol.need_model) return '';
  const p = ol.pull || {};
  if (p.running) return `<div class="note ai-note" data-pullbox>${pullHtml(p)}</div>`;
  return `<div class="note warn ai-note" data-pullbox>AI 언어 모델이 아직 없어요. ${tail}
    ${p.error ? `<div class="small" style="margin-top:4px">지난번 받기 실패: ${esc(p.error)}</div>` : ''}
    <div class="row"><button class="btn small primary" data-act="pull-model">${esc(ol.recommended)} 받기 (약 ${ol.gb}GB)</button>
    <span class="faint small">한 번만 받으면 그다음부터는 인터넷 없이 써요.</span></div></div>`;
}

function pullHtml(p) {
  const f = p.frac == null ? 0 : p.frac;
  const gb = n => (n / 1e9).toFixed(2);
  return `<b>${esc(p.model)}</b> 받는 중… <span class="num">${p.frac == null ? '' : Math.floor(f * 100) + '%'}</span>
    <span class="faint small num">${p.total ? `${gb(p.done)} / ${gb(p.total)} GB` : esc(p.status || '')}</span>
    <div class="bar" style="margin-top:8px"><i style="width:${(f * 100).toFixed(1)}%"></i></div>
    <div class="faint xs" style="margin-top:6px">프로그램을 계속 써도 돼요. 창을 닫으면 멈추고, 다시 누르면 받은 데서 이어 받아요.</div>`;
}

function watchPull() {
  if (S.pullTimer) return;
  S.pullTimer = setInterval(async () => {
    let d;
    try { d = await api('/api/ollama/pull'); } catch (e) { return; }
    const p = d.pull;
    if (S.ollama) S.ollama.pull = p;
    if (p.running) { document.querySelectorAll('[data-pullbox]').forEach(b => { b.innerHTML = pullHtml(p); }); return; }
    clearInterval(S.pullTimer); S.pullTimer = null;
    if (p.finished) toast(`${p.model} 준비 완료! 이제 AI 기능을 쓸 수 있어요.`);
    else if (p.error) toast('모델을 받지 못했어요: ' + p.error, true);
    await checkOllama();
    if (!S.ollama.need_model) document.querySelectorAll('[data-pullbox]').forEach(b => b.remove());
  }, 1000);
}

function show(v) {
  if (v !== S.view) { Player.pause(); TTS.stop(); if (Rec.live) Rec.stop(); }
  if (v !== 'study' && v !== 'talk' && v !== 'expr') Rec.release();
  S.view = v; store.set('view', v);
  $$('.view').forEach(s => { s.hidden = s.id !== 'view-' + v; });
  if (v === 'settings') { S.recs = null; loadRecs(); }
  renderRail();
  ({ home: renderHome, study: openStudy, expr: openExpr, talk: renderTalk, review: openReview, settings: renderSettings })[v]();
}

function renderRail() {
  const p = cur();
  $('#railMovie').innerHTML = p
    ? `<span class="lbl">지금 공부하는 영화</span><b>${esc(p.title)}</b>`
    : `<span class="lbl">영화</span><b>아직 고른 영화가 없어요</b>`;
  const c = (S.st && S.st.review && S.st.review.due) || 0;
  const rc = $('#reviewCount'); rc.hidden = !c; rc.textContent = c;
  $$('.nav').forEach(b => b.classList.toggle('on', b.dataset.view === S.view));
  renderRailJobs();
  renderStatus();
}

function renderStatus() {
  const el = $('#railStatus');
  if (!el || !S.st) return;
  const ol = S.ollama, se = S.st.settings;
  let ai;
  if (!ol) ai = '<b class="rs-v">확인하는 중…</b>';
  else if (!ol.ok) ai = '<b class="rs-v warn">Ollama 꺼짐</b><span class="rs-n">AI 기능을 쓰려면 켜 주세요</span>';
  else ai = `<b class="rs-v num">${esc(ol.model || '모델 없음')}</b><span class="rs-n">${se.model && se.model === ol.model ? '직접 고름' : '자동으로 고름'} · Ollama</span>`;
  const stt = S.st.stt || {};
  const voice = se.tts_engine === 'browser' ? 'Windows 음성' : (S.st.tts && S.st.tts.ready ? `Kokoro` : 'Kokoro (준비 중)');
  el.innerHTML = `<button class="rs-ai" data-act="nav" data-view="settings" title="설정에서 AI 모델 바꾸기"><span class="rs-k">지금 쓰는 AI</span>${ai}</button>
    <div class="rs-mini"><span>음성 인식</span><b class="num">${stt.available === false ? '설치 안 됨' : 'Whisper ' + esc(stt.model || se.stt_model) + (((stt.models || {})[stt.model || se.stt_model] || {}).ready === false ? ' (준비 중)' : '')}</b></div>
    <div class="rs-mini"><span>영어 음성</span><b>${esc(voice)}</b></div>
    <div id="micChipBox"></div>`;
  renderMic();
}

function renderRailJobs() {
  const run = S.jobs.filter(j => j.state === 'running');
  $('#railJobs').innerHTML = run.map(j => `<div class="rail-job">${esc(j.msg || j.title)}<div class="bar"><i style="width:${pct(j.progress)}"></i></div></div>`).join('');
}

/* ================================================================ jobs */
async function pollJobs() {
  try {
    const d = await api('/api/jobs');
    onJobs(d.jobs || []);
  } catch (e) { /* server may be restarting */ }
  const busy = S.jobs.some(j => j.state === 'running');
  setTimeout(pollJobs, busy ? 1000 : 4000);
}

function onJobs(list) {
  const prev = new Map(S.jobs.map(j => [j.id, j]));
  S.jobs = list;
  const started = list.filter(j => j.state === 'running' && !prev.has(j.id));
  const finished = list.filter(j => j.state !== 'running' && prev.get(j.id) && prev.get(j.id).state === 'running');
  finished.forEach(j => {
    if (j.state === 'error') toast(`${j.title}: ${j.error}`, true);
    else if (j.state === 'done') toast(`${j.title} 완료${j.msg ? ' — ' + j.msg : ''}`);
  });
  renderRailJobs();
  if (started.length || finished.length) {
    refreshState().then(() => {
      renderRail();
      if (S.view === 'home') renderHome();
      if (finished.some(j => j.pid === S.pid && ['prepare', 'analyze', 'media'].includes(j.kind))) {
        if (finished.some(j => j.kind === 'prepare' || j.kind === 'analyze')) S.linesPid = null;
        if (S.view === 'study') openStudy();
        if (S.view === 'expr') openExpr();
      }
      if (S.view === 'expr' && finished.some(j => j.kind === 'examples')) openExpr();
      if (S.view === 'settings' && finished.some(j => j.kind === 'download')) renderSettings();
    }).catch(() => {});
  } else {
    updateJobBars();
    const an = list.find(j => j.kind === 'analyze' && j.pid === S.pid && j.state === 'running');
    if (an && S.view === 'study' && Date.now() - S.lastLinesLoad > 15000) reloadLinesQuiet();
    if (S.view === 'settings' && list.some(j => j.kind === 'download' && j.state === 'running')) updateJobBars();
  }
}

function jobFor(kind, pid) { return S.jobs.find(j => j.kind === kind && j.pid === pid && j.state === 'running'); }

function jobBar(kind, pid) {
  const j = jobFor(kind, pid);
  if (!j) return '';
  return `<div class="jobline" data-kind="${kind}" data-pid="${esc(pid)}"><div class="row small muted" style="justify-content:space-between"><span class="msg">${esc(j.msg || '진행 중…')}</span><span class="num p">${pct(j.progress)}</span></div><div class="bar"><i style="width:${pct(j.progress)}"></i></div><div class="row" style="margin-top:6px"><button class="btn quiet small" data-act="cancel-job" data-id="${j.id}">멈추기</button></div></div>`;
}

function updateJobBars() {
  $$('.jobline').forEach(el => {
    const j = jobFor(el.dataset.kind, el.dataset.pid);
    if (!j) return;
    $('.msg', el).textContent = j.msg || '진행 중…';
    $('.p', el).textContent = pct(j.progress);
    $('.bar > i', el).style.width = pct(j.progress);
  });
}

/* ================================================================ home */
function renderHome() {
  const el = $('#view-home');
  if (!S.st) return;
  const ps = S.st.projects;
  const p = cur();
  const sampleAdded = ps.some(x => x.movie === S.st.sample.path);
  const ol = S.ollama;
  el.innerHTML = `
  <div class="view-head"><div><h1>영화</h1>
    <p>공부할 영화를 고르면 영어 대사를 꺼내고, 재생을 준비하고, 로컬 AI가 면접·미팅에 다시 쓸 수 있는 문장을 골라 줘요.</p></div></div>
  ${aiNote('home')}
  <div class="home">
    <div>
      <div class="add-box">
        <button class="btn primary big" data-act="pick-movie">영화 파일 고르기</button>
        <div class="paste"><input type="text" id="pastePath" placeholder="또는 파일 위치를 붙여 넣기"><button class="btn" data-act="add-path">추가</button></div>
        ${S.st.sample.exists && !sampleAdded ? `<button class="btn" data-act="add-sample">${I.film} 예제 장면으로 먼저 해 보기</button>` : ''}
      </div>
      <ul class="movies">${ps.map(movieRow).join('')}</ul>
    </div>
    <div id="homeDetail">${p ? detailHTML(p) : homeEmpty()}</div>
  </div>`;
  if (p && !p.lines_ready && !jobFor('prepare', p.id)) loadSources(p);
}

function homeEmpty() {
  return `<div class="panel empty"><h2>영화 한 편으로 시작해요</h2>
  <p>영어 자막(.srt, .smi)이 같은 폴더에 있으면 바로 쓰고, 없으면 이 컴퓨터의 음성 인식으로 대사를 만들어요.<br>처음이라면 예제 장면(짧은 면접과 회의)으로 먼저 해 보세요.</p></div>`;
}

function movieRow(p) {
  const a = p.analysis || {};
  const bits = [];
  if (p.duration) bits.push(fmtDur(p.duration));
  if (p.lines_ready) bits.push(`대사 ${p.line_count}줄`);
  if (a.state === 'done') bits.push(`핵심 ${a.keys ?? ''}문장`);
  else if (jobFor('analyze', p.id) || jobFor('prepare', p.id)) bits.push('준비 중');
  if (p.studied) bits.push(`공부 ${p.studied}문장`);
  return `<li class="movie-li"><button class="movie-row ${p.id === S.pid ? 'on' : ''}" data-act="select-movie" data-pid="${esc(p.id)}"><b>${esc(p.title)}</b><span class="meta">${bits.map(b => `<span>${esc(b)}</span>`).join('')}</span></button>
    <button class="movie-del" data-act="ask-delete" data-pid="${esc(p.id)}" title="이 영화 지우기" aria-label="${esc(p.title)} 지우기">${I.trash}</button></li>`;
}

function detailHTML(p) {
  const prepJob = jobFor('prepare', p.id), mediaJob = jobFor('media', p.id), anJob = jobFor('analyze', p.id);
  const m = p.media || {};
  const a = p.analysis || {};
  const pauseInfo = p.prep && p.prep.state === 'running' && !prepJob && !p.lines_ready;
  // step 1
  let s1;
  if (p.lines_ready) {
    s1 = `<div class="muted small">영어: ${esc(p.en ? p.en.name : '')} · ${p.line_count}줄<br>한국어: ${esc(p.ko ? p.ko.name : '없음 (필요할 때 AI가 번역해요)')}</div>
      <div class="row" style="margin-top:8px"><button class="btn quiet small" data-act="redo-lines">다른 자막으로 다시 준비</button></div>`;
  } else if (prepJob) {
    s1 = jobBar('prepare', p.id);
  } else {
    s1 = `<div id="srcBox">${pauseInfo ? '<div class="note" style="margin-bottom:8px">지난번에 멈춘 곳부터 이어서 할 수 있어요.</div>' : ''}<span class="spin"></span> 자막을 찾는 중…</div>`;
  }
  // step 2
  let s2;
  if (mediaJob) s2 = jobBar('media', p.id);
  else if (m.state === 'ready') s2 = `<div class="muted small">${m.audio_only ? '소리만으로 학습해요.' + (m.note ? ' ' + esc(m.note) : '') : (m.plan === 'direct' ? '원본 영상을 그대로 재생해요.' : '재생용 영상이 준비됐어요.')}</div>
      <div class="row" style="margin-top:6px"><button class="btn quiet small" data-act="media-transcode">화면이 안 나오면 재생용 영상 만들기</button></div>`;
  else if (m.state === 'audio') s2 = `<div class="muted small">소리는 준비됐어요. 영상은 아직 변환 전이에요.</div><div class="row" style="margin-top:6px"><button class="btn small" data-act="media-start">영상 변환 이어서 하기</button></div>`;
  else s2 = `<div class="muted small">${p.lines_ready || prepJob ? '' : '대사 준비를 시작하면 함께 준비해요.'}</div>${p.lines_ready ? '<button class="btn small" data-act="media-start">재생 준비 시작</button>' : ''}`;
  // step 3
  let s3;
  const depthSeg = `<div class="seg" data-seg="depth">${[['quick', '빠르게 60문장'], ['normal', '보통 120문장'], ['deep', '꼼꼼히 250문장']].map(([k, t]) => `<button class="${(S.st.settings.analysis_depth || 'normal') === k ? 'on' : ''}" data-val="${k}">${t}</button>`).join('')}</div>`;
  if (anJob) s3 = jobBar('analyze', p.id) + '<div class="faint xs" style="margin-top:4px">분석하는 동안에도 공부할 수 있어요. 고른 문장이 차례로 표시돼요.</div>';
  else if (a.state === 'done') s3 = `<div class="muted small">핵심 문장 ${a.keys ?? 0}개를 골랐어요 (${a.total}문장 검토${a.model ? ` · AI ${esc(a.model)}` : ''}).</div><div class="row" style="margin-top:6px">${depthSeg}<button class="btn quiet small" data-act="reanalyze">처음부터 다시 분석</button></div>`;
  else if (!p.lines_ready) s3 = `<div class="muted small">대사가 준비되면 자동으로 시작해요.</div>`;
  else s3 = `<div class="row">${depthSeg}<button class="btn small primary" data-act="analyze">${a.state === 'running' || a.state === 'paused' ? '이어서 분석' : 'AI 분석 시작'}</button></div>
      ${a.total ? `<div class="faint xs" style="margin-top:6px">${a.done || 0} / ${a.total}문장까지 했어요.</div>` : ''}`;
  const td = p.today || {};
  return `
  <h2 class="detail-title">${esc(p.title)}</h2>
  <div class="detail-path">${esc(p.movie)}${p.movie_exists ? '' : ' <b class="err">(파일이 없어요)</b>'}</div>
  ${p.lines_ready ? `<div class="stats">
    <div><b>${p.line_count}</b>대사</div><div><b>${(p.analysis || {}).keys ?? '–'}</b>핵심 문장</div>
    <div><b>${p.studied || 0}</b>공부한 문장</div><div><b>${(td.dict || 0) + (td.speak || 0)}</b>오늘 연습</div><div><b>${p.streak || 0}일</b>연속 학습</div></div>` : ''}
  <ol class="steps">
    <li class="step ${p.lines_ready ? 'done' : prepJob ? 'busy' : ''}"><div class="body"><h3>영어 대사 준비</h3>${s1}</div></li>
    <li class="step ${m.state === 'ready' ? 'done' : mediaJob ? 'busy' : ''}"><div class="body"><h3>재생 준비</h3>${s2}</div></li>
    <li class="step ${a.state === 'done' ? 'done' : anJob ? 'busy' : ''}"><div class="body"><h3>AI가 공부할 문장 고르기</h3>${s3}</div></li>
  </ol>
  <div class="cta-row">
    <button class="btn primary big" data-act="go-study" ${p.lines_ready ? '' : 'disabled'}>장면 학습 시작</button>
    <button class="btn big" data-act="go-talk">면접·미팅 연습</button>
  </div>
  <div class="danger-zone">
    <button class="btn quiet small" data-act="open-folder" data-what="movie">영화 폴더 열기</button>
    <button class="btn quiet small" data-act="open-folder" data-what="project">학습 기록 폴더 열기</button>
    ${m.plan && m.plan !== 'direct' && m.state !== 'none' ? '<button class="btn quiet small" data-act="delete-media">재생용 사본 지우기</button>' : ''}
    <button class="btn quiet small danger" data-act="ask-delete" data-pid="${esc(p.id)}">${I.trash} 이 영화 지우기</button>
  </div>`;
}

/* ---------------------------------------------------------------- deleting a movie */
async function askDelete(pid) {
  const p = (S.st.projects || []).find(x => x.id === pid);
  if (!p || S.del) return;
  S.del = { pid, info: null, busy: false, trash: false, err: '' };
  S.delReturn = document.activeElement;
  renderDelModal();
  try { S.del.info = await api(`/api/projects/${enc(pid)}/delete-info`); } catch (e) { if (S.del) S.del.err = e.message; }
  if (S.del && S.del.pid === pid) renderDelModal();
}

function closeDelModal() {
  if (!S.del || S.del.busy) return;
  S.del = null;
  const m = $('#delModal'); if (m) m.remove();
  if (S.delReturn && document.contains(S.delReturn)) S.delReturn.focus();
}

function delButtonText() {
  const d = S.del;
  return d.busy ? '<span class="spin"></span> 지우는 중…' : d.trash ? '지우고 원본은 휴지통으로' : '지우기';
}

function renderDelModal() {
  let m = $('#delModal');
  if (!S.del) { if (m) m.remove(); return; }
  if (!m) { m = document.createElement('div'); m.id = 'delModal'; m.className = 'modal'; document.body.appendChild(m); }
  const d = S.del, i = d.info;
  const p = (S.st.projects || []).find(x => x.id === d.pid) || { title: i ? i.title : '' };
  const gone = ['대사와 AI 분석'];
  if (i && i.studied) gone.push(`받아쓰기·말하기 기록 ${i.studied}문장`);
  if (i && i.recordings) gone.push(`내 녹음 ${i.recordings}개`);
  if (i && i.cards) gone.push(`복습 카드 ${i.cards}장`);
  m.innerHTML = `<div class="modal-card" role="alertdialog" aria-modal="true" aria-labelledby="delTitle" aria-describedby="delBody">
    <h2 id="delTitle">이 영화를 지울까요?</h2>
    <p class="del-name">${esc(p.title)}</p>
    <div id="delBody">
    ${!i && !d.err ? '<p class="small muted"><span class="spin"></span> 지울 내용을 확인하는 중…</p>' : ''}
    ${d.err ? `<div class="note warn" style="margin-top:8px">${esc(d.err)}</div>` : ''}
    ${i ? `<p class="small" style="margin:12px 0 6px">영화 목록에서 빠지고, 이 영화로 공부한 기록이 지워져요. 되돌릴 수 없어요.</p>
      <ul class="del-list small muted"><li>${gone.join(' · ')}</li><li>학습 기록 ${mb(i.study_bytes)}를 비워요${i.playback_bytes ? ` (재생용 사본 ${mb(i.playback_bytes)} 포함)` : ''}</li>${i.jobs ? '<li>이 영화로 하고 있던 준비 작업을 멈춰요</li>' : ''}<li>면접·미팅 연습 기록은 그대로 남아요</li></ul>
      ${i.movie ? `<label class="del-trash"><input type="checkbox" id="delTrash" ${d.trash ? 'checked' : ''} ${d.busy ? 'disabled' : ''}>
        <span><b>원본 영화 파일도 휴지통으로 보내기</b>
        <span class="del-path">${esc(i.movie)} · ${mb(i.movie_bytes)}${i.subs.length ? ` · 같은 이름의 자막 파일 ${i.subs.length}개도 함께` : ''}</span>
        <span class="faint xs">휴지통에서 되살릴 수 있어요. 고르지 않으면 원본 파일은 그대로 둬요.</span></span></label>`
      : i.sample ? '<p class="faint xs" style="margin-top:10px">예제 장면은 영화 화면의 [예제 장면으로 먼저 해 보기]로 언제든 다시 넣을 수 있어요.</p>' : ''}` : ''}
    </div>
    <div class="row end" style="margin-top:18px"><button class="btn" data-act="del-cancel" ${d.busy ? 'disabled' : ''}>취소</button>
      <button class="btn danger-fill" data-act="del-confirm" ${i && !d.busy ? '' : 'disabled'}>${delButtonText()}</button></div>
  </div>`;
  if (!m.contains(document.activeElement)) { const b = $('#delModal [data-act="del-cancel"]'); if (b) b.focus(); }
}

async function doDelete() {
  const d = S.del;
  if (!d || d.busy || !d.info) return;
  d.busy = true; d.err = '';
  renderDelModal();
  if (Player.pid === d.pid) { Player.pause(); Player.setSource(null); }   // the window lets go of the video file
  if (S.pid === d.pid && Rec.live) Rec.stop();
  try {
    const r = await api(`/api/projects/${enc(d.pid)}/delete`, { body: { trash_movie: !!d.trash } });
    d.busy = false;
    closeDelModal();
    if (S.pid === d.pid) {
      S.pid = null; S.linesPid = null; S.lines = []; S.cur = null; S.exprs = null;
      S.detail = {}; S.dict = {}; S.speak = {};
    }
    delete S.maskEdit[d.pid]; delete S.sources[d.pid]; delete S.srcSel[d.pid];
    await refreshState();
    if (!S.pid && S.st.projects.length) S.pid = S.st.projects[0].id;
    store.set('pid', S.pid);
    toast(`'${r.title}' 영화를 지웠어요.${r.trashed.length ? ` 원본 파일 ${r.trashed.length}개는 휴지통에 있어요.` : ''}`);
    if (r.trash_failed.length) toast('원본 파일을 휴지통으로 보내지 못했어요. ' + r.trash_failed.join(' / '), true);
    show('home');
  } catch (e) {
    d.busy = false; d.err = e.message;
    renderDelModal();
  }
}

async function loadSources(p, force) {
  const box = () => $('#srcBox');
  try {
    if (force || !S.sources[p.id]) S.sources[p.id] = await api(`/api/projects/${enc(p.id)}/sources`);
  } catch (e) {
    if (box()) box().innerHTML = `<div class="err">${esc(e.message)}</div>`;
    return;
  }
  const d = S.sources[p.id];
  const sel = S.srcSel[p.id] || (S.srcSel[p.id] = {
    en: (p.prep && p.prep.en) || d.default_en, ko: (p.prep && p.prep.ko) ?? d.default_ko,
    model: (p.prep && p.prep.model) || S.st.settings.movie_stt_model || 'small.en',
  });
  if (!d.en.some(o => o.id === sel.en)) sel.en = d.default_en;
  if (box()) box().innerHTML = sourcesHTML(p, d, sel);
}

function srcRow(group, o, sel) {
  const dis = o.usable === false;
  const on = sel === o.id;
  const count = o.count ? ` · ${o.count}줄` : '';
  return `<label class="src ${on ? 'on' : ''} ${dis ? 'off' : ''}">
    <input type="radio" name="src-${group}" value="${esc(o.id)}" ${on ? 'checked' : ''} ${dis ? 'disabled' : ''}>
    <span><span class="nm">${esc(o.name)}</span><span class="sm">${o.lang === 'en' ? ' 영어' : o.lang === 'ko' ? ' 한국어' : ''}${count}</span>
    ${o.sample ? `<div class="sample">${esc(o.sample)}</div>` : ''}${o.note ? `<div class="sm">${esc(o.note)}</div>` : ''}</span></label>`;
}

function sourcesHTML(p, d, sel) {
  const koNone = { id: '', kind: 'none', name: '한국어 자막 없음 (AI가 필요할 때 번역)', usable: true };
  const whisper = sel.en === 'whisper';
  return `
    <div class="field"><span>영어 대사를 어디서 가져올까요?</span><div class="src-list">${d.en.map(o => srcRow('en', o, sel.en)).join('')}</div></div>
    ${whisper ? `<div class="field" style="margin:4px 0 10px"><span>음성 인식 정확도</span><div class="seg" data-seg="whisper">
      <button class="${sel.model === 'base.en' ? 'on' : ''}" data-val="base.en">빠르게 (base)</button>
      <button class="${sel.model === 'small.en' ? 'on' : ''}" data-val="small.en">정확하게 (small)</button>
      <button class="${sel.model === 'medium.en' ? 'on' : ''}" data-val="medium.en">아주 정확하게 (medium, 느림)</button></div></div>` : ''}
    <div class="field"><span>한국어 자막 (있으면 뜻을 바로 보여 줘요)</span><div class="src-list">${[koNone, ...d.ko].map(o => srcRow('ko', o, sel.ko)).join('')}</div></div>
    <div class="row" style="margin-top:6px">
      <button class="btn primary" data-act="prepare">학습 준비 시작</button>
      <button class="btn" data-act="pick-sub">다른 자막 파일 고르기</button>
    </div>
    <div class="faint xs" style="margin-top:8px">준비가 끝나면 AI 분석이 이어서 자동으로 시작돼요.</div>`;
}

/* ================================================================ study */
async function loadLines() {
  const d = await api(`/api/projects/${enc(S.pid)}/lines`);
  S.lines = d.lines; S.lineMap = new Map(d.lines.map(l => [l.id, l])); S.linesPid = S.pid;
  S.lastLinesLoad = Date.now();
  const i = (S.st.projects || []).findIndex(p => p.id === S.pid);
  if (i >= 0) S.st.projects[i] = d.project;
}

async function reloadLinesQuiet() {
  S.lastLinesLoad = Date.now();
  try {
    const keep = S.cur ? S.cur.id : null;
    await loadLines();
    if (keep != null) S.cur = S.lineMap.get(keep) || S.cur;
    renderScript(false);
    if (S.tab === 'mean') renderPractice();
  } catch (e) { /* ignore */ }
}

async function openStudy() {
  const el = $('#view-study');
  const p = cur();
  if (!p) { el.innerHTML = `<div class="empty"><h2>먼저 영화를 골라 주세요</h2><button class="btn primary" data-act="nav" data-view="home">영화 고르기</button></div>`; el.dataset.pid = ''; return; }
  if (!p.lines_ready) {
    el.innerHTML = `<div class="empty"><h2>대사를 준비하고 있어요</h2><p>영화 화면에서 진행 상황을 볼 수 있어요.</p><button class="btn" data-act="nav" data-view="home">영화 화면으로</button></div>`;
    el.dataset.pid = ''; return;
  }
  if (S.linesPid !== p.id) {
    el.innerHTML = '<div class="empty"><span class="spin"></span></div>'; el.dataset.pid = '';
    try { await loadLines(); } catch (e) { el.innerHTML = `<div class="empty err">${esc(e.message)}</div>`; return; }
    S.cur = null;
  }
  if (el.dataset.pid !== p.id || !$('#strip', el)) buildStudy(el, p.id);
  Player.mount($('#screen'));
  Player.setSource(cur());
  renderScript(true);
  const want = S.cur ? S.cur.id : store.get('line.' + p.id, null);
  const first = visibleLines()[0];
  selectLine(S.lineMap.has(want) ? want : (first ? first.id : 0), { scroll: true });
}

function buildStudy(el, pid) {
  el.dataset.pid = pid;
  el.innerHTML = `
  <div class="study">
    <div class="stage-col">
      <div class="stage">
        <div class="screen" id="screen"><div class="overlay" id="overlay"></div><span class="tc" id="tc"></span></div>
        <div class="strip" id="strip"></div>
      </div>
      <div class="transport" id="transport"></div>
      <div class="practice">
        <div class="tabs" role="tablist">
          <button data-act="tab" data-tab="dict">받아쓰기</button>
          <button data-act="tab" data-tab="speak">따라 말하기</button>
          <button data-act="tab" data-tab="mean">뜻·발음</button>
        </div>
        <div class="tab-body" id="practice"></div>
      </div>
    </div>
    <aside class="script-col">
      <div class="script-head">
        <div class="chips" id="filters"></div>
        <input type="text" id="scriptSearch" placeholder="대본에서 찾기 (영어·한국어)" value="${esc(S.search)}">
      </div>
      <ol class="script" id="script"></ol>
      <div class="script-foot"><span id="scriptCount"></span>
        <span class="row" style="gap:4px"><span>싱크</span><button class="btn quiet small" data-act="offset" data-d="-0.25">−0.25초</button><span class="num" id="offsetVal"></span><button class="btn quiet small" data-act="offset" data-d="0.25">+0.25초</button></span>
      </div>
    </aside>
  </div>`;
}

function visibleLines() {
  const f = S.filter;
  const q = S.search.trim().toLowerCase();
  const anyKey = S.lines.some(l => l.key);
  let list = S.lines.filter(l => {
    if (f === 'key') return anyKey ? l.key : l.pk;
    if (f === 'hard') return l.lv === 3;
    if (f === 'again') return (l.bd != null && l.bd < 0.8) || (l.bs != null && l.bs < 0.75);
    if (f === 'star') return l.st;
    return true;
  });
  if (q) list = list.filter(l => l.t.toLowerCase().includes(q) || (l.ko || '').toLowerCase().includes(q));
  return list;
}

function renderScript(scroll) {
  const box = $('#script');
  if (!box) return;
  const anyKey = S.lines.some(l => l.key);
  const counts = {
    key: S.lines.filter(l => anyKey ? l.key : l.pk).length, all: S.lines.length,
    hard: S.lines.filter(l => l.lv === 3).length,
    again: S.lines.filter(l => (l.bd != null && l.bd < 0.8) || (l.bs != null && l.bs < 0.75)).length,
    star: S.lines.filter(l => l.st).length,
  };
  const names = { key: anyKey ? '핵심 문장' : '추천 문장', all: '전체', hard: '빠른 문장', again: '다시 볼 문장', star: '★ 고른 문장' };
  $('#filters').innerHTML = Object.keys(names).map(k => `<button class="chip ${S.filter === k ? 'on' : ''}" data-act="filter" data-f="${k}">${names[k]} <span class="num">${counts[k]}</span></button>`).join('');
  const list = visibleLines();
  const hide = S.sub === 'hidden';
  box.innerHTML = list.length ? list.map(l => {
    const done = l.bd != null || l.bs != null;
    const m = [];
    if (l.key) m.push('<span class="chip key">핵심</span>');
    if (l.ai && l.ai.c && l.ai.c !== 'other') m.push(`<span class="chip">${esc(CAT()[l.ai.c] || '')}</span>`);
    m.push(`<span class="lvl" title="빠르기">${'●'.repeat(l.lv || 1)}${'○'.repeat(3 - (l.lv || 1))}</span>`);
    if (l.bd != null) m.push(`<span class="done-mark">받아쓰기 ${pct(l.bd)}</span>`);
    if (l.bs != null) m.push(`<span class="done-mark">말하기 ${pct(l.bs)}</span>`);
    if (l.st) m.push('<span class="done-mark" style="color:#9A7600">★</span>');
    return `<li data-id="${l.id}" class="${S.cur && S.cur.id === l.id ? 'on' : ''}"><span class="t">${fmtT(l.s)}</span><div><div class="x ${hide && !done && !S.revealed.has(l.id) ? 'blur' : ''}">${escBr(l.t)}</div><div class="m">${m.join('')}</div></div></li>`;
  }).join('') : `<div class="script-empty">${S.filter === 'key' && !anyKey ? 'AI 분석이 끝나면 핵심 문장이 여기에 모여요.' : '해당하는 문장이 없어요.'}</div>`;
  $('#scriptCount').textContent = `${list.length}문장`;
  const p = cur();
  $('#offsetVal').textContent = ((p && p.offset) || 0).toFixed(2) + '초';
  if (scroll && S.cur) { const li = $(`#script li[data-id="${S.cur.id}"]`); if (li) li.scrollIntoView({ block: 'center' }); }
}

function selectLine(id, { play = false, scroll = true } = {}) {
  const l = S.lineMap.get(id);
  if (!l) { renderStrip(); renderTransport(); renderPractice(); return; }
  if (Rec.live) Rec.stop();
  S.cur = l; store.set('line.' + S.pid, id);
  S.justChecked = null;
  $$('#script li.on').forEach(x => x.classList.remove('on'));
  const li = $(`#script li[data-id="${id}"]`);
  if (li) { li.classList.add('on'); if (scroll) li.scrollIntoView({ block: 'nearest' }); }
  renderStrip(); renderTransport(); renderPractice();
  loadDetail(l);
  if (play) playCur();
}

async function loadDetail(l) {
  if (S.detail[l.id]) return;
  try {
    const d = await api(`/api/projects/${enc(S.pid)}/lines/${l.id}`);
    S.detail[l.id] = d;
    if (S.cur && S.cur.id === l.id && S.tab === 'mean') renderPractice();
  } catch (e) { /* ignore */ }
}

function wordsHTML(text, { hide = false, status = null, anim = false } = {}) {
  let out = '', last = 0, k = 0, m;
  WORD_RE.lastIndex = 0;
  while ((m = WORD_RE.exec(text))) {
    out += escBr(text.slice(last, m.index));
    const st = status ? (status.get(m.index) || 'hit') : null;
    const cls = ['w'];
    if (hide && !status) cls.push('hid');
    if (st) cls.push('st-' + st);
    if (anim) cls.push('reveal');
    out += `<span class="${cls.join(' ')}"${anim ? ` style="animation-delay:${k * 38}ms"` : ''}>${esc(m[0])}</span>`;
    last = m.index + m[0].length; k++;
  }
  return out + escBr(text.slice(last));
}

function renderStrip() {
  const el = $('#strip');
  if (!el) return;
  const l = S.cur;
  if (!l) { el.innerHTML = '<div class="placeholder">오른쪽 대본에서 문장을 고르세요</div>'; return; }
  const dr = S.dict[l.id], sr = S.speak[l.id];
  const res = (dr && dr.result && dr.shown) ? dr.result : (sr && sr.align && sr.shown ? sr.align : null);
  const status = res ? new Map(res.ref.map(w => [w.a, w.s])) : null;
  const reveal = S.sub === 'en' || S.sub === 'enko' || !!res || S.revealed.has(l.id);
  let html = '';
  if (S.sub !== 'ko' || res || S.revealed.has(l.id)) html += `<div class="en-line">${wordsHTML(l.t, { hide: !reveal, status, anim: S.justChecked === l.id })}</div>`;
  if (S.sub === 'enko' || S.sub === 'ko') html += `<div class="ko-line">${esc(l.ko || '한국어 뜻이 아직 없어요. 뜻·발음 탭에서 AI 설명을 받아 보세요.')}</div>`;
  el.innerHTML = html;
}

function renderTransport() {
  const el = $('#transport');
  if (!el) return;
  const l = S.cur;
  const list = visibleLines();
  const idx = l ? list.findIndex(x => x.id === l.id) : -1;
  const segs = (name, opts, val) => `<div class="seg" data-seg="${name}">${opts.map(([v, t]) => `<button class="${String(val) === String(v) ? 'on' : ''}" data-val="${v}">${t}</button>`).join('')}</div>`;
  el.innerHTML = `
    <div class="grp">
      <button class="btn" data-act="step" data-d="-1" title="이전 문장 (←)">${I.prev}</button>
      <button class="btn primary play" data-act="play" title="듣기 (Space)">${Player.playing() ? I.pause + ' 멈춤' : I.play + ' 듣기'}</button>
      <button class="btn" data-act="step" data-d="1" title="다음 문장 (→)">${I.next}</button>
    </div>
    <div class="grp"><span class="lbl">반복</span>${segs('loops', [[1, '1번'], [3, '3번'], [5, '5번']], S.loops)}</div>
    <div class="grp"><span class="lbl">속도</span>${segs('speed', [[0.6, '0.6'], [0.75, '0.75'], [0.9, '0.9'], [1, '1.0']], S.speed)}</div>
    <div class="grp"><span class="lbl">자막</span>${segs('sub', [['hidden', '숨김'], ['en', '영어'], ['enko', '영어+한국어'], ['ko', '한국어']], S.sub)}</div>
    <div class="grp"><span class="lbl">화면 자막</span>${maskButton()}</div>
    <div class="grp">
      <button class="btn small star ${l && l.st ? 'on' : ''}" data-act="star" title="복습 카드에 넣기">${I.star} ${l && l.st ? '고른 문장' : '복습에 넣기'}</button>
      <button class="btn quiet small" data-act="watch" title="이 문장부터 이어서 보기">${I.film} 이어 보기</button>
    </div>
    <span class="faint xs num" style="margin-left:auto">${idx >= 0 ? `${idx + 1} / ${list.length}` : ''}</span>`;
  const tc = $('#tc');
  if (tc) tc.textContent = l ? fmtT(l.s) : '';
}

function maskButton() {
  const m = Mask.get(S.pid);
  if (S.maskBusy === S.pid) return '<button class="btn small mask-btn on" disabled><span class="spin"></span> 찾는 중…</button>';
  return `<button class="btn small mask-btn ${m.on ? 'on' : ''}" data-act="mask-toggle" aria-pressed="${m.on}" title="영상에 박혀 있는 자막(한국어 등)을 가려요">${m.on ? '가리는 중' : '가리기'}</button>`;
}

function renderPlayState() {
  const b = $('#transport [data-act="play"]');
  if (b) b.innerHTML = Player.playing() ? I.pause + ' 멈춤' : I.play + ' 듣기';
}

function updateOverlay() {
  const ov = $('#overlay');
  if (!ov) return;
  const p = cur();
  const m = (p && p.media) || {};
  ov.className = 'overlay';
  if (Player.failed) {
    ov.style.pointerEvents = 'auto';
    ov.innerHTML = `<div>이 영상 형식은 창에서 바로 재생되지 않아요.</div><button class="btn small" data-act="media-transcode">재생용 영상 만들기</button>`;
    return;
  }
  ov.style.pointerEvents = 'none';
  if (!Player.src) {
    const j = p && jobFor('media', p.id);
    ov.innerHTML = j ? `<div>재생 준비 중… ${pct(j.progress)}</div><div class="xs">${esc(j.msg || '')}</div>` : '<div>재생 파일을 준비하지 않았어요.</div>';
    return;
  }
  if (Player.audioOnly) { ov.className = 'overlay audio'; ov.innerHTML = `<div>${I.speak} 소리로 듣는 중</div><div class="xs">${m.state === 'audio' ? '영상은 변환하고 있어요' : ''}</div>`; return; }
  ov.innerHTML = '';
}

function playCur(rate) {
  const l = S.cur;
  if (!l) return;
  if (S.tab === 'dict' && S.sub === 'hidden') { /* keep hidden */ }
  Player.playClip(l.cs, l.ce, { rate: rate || S.speed, loops: S.loops });
  renderPlayState();
}

function togglePlay() {
  if (Player.playing()) { Player.pause(); renderPlayState(); } else playCur();
}

function stepLine(d) {
  const list = visibleLines();
  if (!list.length) return;
  const i = S.cur ? list.findIndex(x => x.id === S.cur.id) : -1;
  const j = Math.max(0, Math.min(list.length - 1, i + d));
  if (j !== i || i === -1) selectLine(list[j].id, { play: true });
}

function onFreeTime(t) {
  // continuous watching: follow the line under the playhead
  const l = S.lines.find(x => t >= x.cs && t < x.ce);
  if (l && (!S.cur || S.cur.id !== l.id)) {
    S.cur = l;
    $$('#script li.on').forEach(x => x.classList.remove('on'));
    const li = $(`#script li[data-id="${l.id}"]`);
    if (li) { li.classList.add('on'); li.scrollIntoView({ block: 'nearest' }); }
    renderStrip(); renderTransport(); renderPractice();
  }
}

/* ---------------------------------------------------------------- practice tabs */
function renderPractice() {
  const el = $('#practice');
  if (!el) return;
  $$('.tabs [data-tab]').forEach(b => b.classList.toggle('on', b.dataset.tab === S.tab));
  const l = S.cur;
  if (!l) { el.innerHTML = '<p class="muted">문장을 고르면 연습을 시작할 수 있어요.</p>'; return; }
  if (S.tab === 'dict') el.innerHTML = dictHTML(l);
  else if (S.tab === 'speak') el.innerHTML = speakHTML(l);
  else el.innerHTML = meanHTML(l);
}

function hintText(text, h) {
  WORD_RE.lastIndex = 0;
  return (text.match(WORD_RE) || []).map(w => h.first ? w[0] + '_'.repeat(Math.max(0, w.length - 1)) : '_'.repeat(w.length)).join('  ');
}

function dictHTML(l) {
  const r = S.dict[l.id] || {};
  return `
  <div class="row" style="justify-content:space-between;margin-bottom:8px">
    <span class="muted small">들리는 대로 영어로 적고 <kbd>Enter</kbd> · 다시 듣기 <kbd>Tab</kbd> · 느리게 <kbd>Shift</kbd>+<kbd>Tab</kbd></span>
    <span class="row" style="gap:6px"><button class="chip ${S.hints.count ? 'on' : ''}" data-act="hint" data-h="count">단어 수</button><button class="chip ${S.hints.first ? 'on' : ''}" data-act="hint" data-h="first">첫 글자</button></span>
  </div>
  ${S.hints.count || S.hints.first ? `<div class="hint-line">${esc(hintText(l.t, S.hints))}</div>` : ''}
  <textarea class="dict-input" id="dictInput" rows="2" placeholder="Type what you hear" spellcheck="false" autocomplete="off" autocapitalize="off">${esc(r.typed || '')}</textarea>
  <div class="small err" id="imeWarn" hidden>한글로 입력되고 있어요. 한/영 키를 눌러 영어로 바꿔 주세요.</div>
  <div class="row" style="margin-top:10px">
    <button class="btn primary" data-act="dict-check">확인하기</button>
    <button class="btn" data-act="dict-reveal">정답 보기</button>
    ${l.bd != null ? `<span class="faint small">지금까지 최고 ${pct(l.bd)}</span>` : ''}
  </div>
  <div id="dictResult">${r.result ? dictResultHTML(l, r) : ''}</div>`;
}

function scoreClass(s) { return s >= 0.85 ? 'good' : s >= 0.6 ? 'mid' : 'low'; }

function dictResultHTML(l, r) {
  const res = r.result;
  const missed = res.ref.filter(w => w.s === 'miss').map(w => w.w);
  const near = res.ref.filter(w => w.s === 'near').map(w => w.w);
  const extras = res.hyp.filter(w => w.s === 'extra').map(w => w.w);
  const hitNotes = (r.notes || []).filter(n => n.hit);
  const msg = res.score >= 0.95 ? '완벽해요! 다음 문장으로 가 볼까요?' : res.score >= 0.8 ? '거의 다 들었어요.' : res.score >= 0.5 ? '절반 넘게 들었어요. 놓친 부분을 느리게 다시 들어 보세요.' : '어려운 문장이에요. 자막을 켜고 들은 뒤 다시 도전해 보세요.';
  return `
  <div class="score ${scoreClass(res.score)}"><b>${pct(res.score)}</b><span>${msg}</span></div>
  <div class="said">${res.hyp.map(w => `<span class="w st-${w.s}">${esc(w.w)}</span>`).join(' ')}</div>
  <div class="small muted" style="margin-top:6px">
    ${missed.length ? `놓친 단어: <b style="color:var(--miss)">${esc(missed.join(', '))}</b>` : ''}
    ${near.length ? ` · 철자 확인: <b style="color:var(--near)">${esc(near.join(', '))}</b>` : ''}
    ${extras.length ? ` · 원문에 없는 단어: ${esc(extras.join(', '))}` : ''}
  </div>
  ${hitNotes.length ? `<h3 style="margin-top:14px">놓친 부분이 잘 안 들리는 이유</h3>${notesHTML(hitNotes)}` : ''}
  <div class="row" style="margin-top:12px">
    <button class="btn" data-act="replay-slow">${I.play} 느리게 다시 듣기</button>
    <button class="btn" data-act="tab" data-tab="speak">${I.mic} 따라 말하기로</button>
    <button class="btn primary" data-act="step" data-d="1">다음 문장 ${I.next}</button>
  </div>`;
}

function notesHTML(notes) {
  if (!notes || !notes.length) return '<p class="muted small" style="margin:4px 0">특별히 줄어드는 소리가 없는 문장이에요. 또박또박 들려요.</p>';
  return `<ul class="notes">${notes.map(n => `<li class="${n.hit ? 'hit' : ''}"><span class="k">${esc(n.kind)}</span><span>${n.text ? `<span class="say">${esc(n.text)}</span> → ` : ''}<span class="say">${esc(n.say)}</span><br><span class="muted">${esc(n.ko)}</span></span></li>`).join('')}</ul>`;
}

async function dictCheck() {
  const l = S.cur;
  const inp = $('#dictInput');
  if (!l || !inp) return;
  const typed = inp.value.trim();
  if (!typed) { toast('들은 문장을 먼저 적어 주세요.'); inp.focus(); return; }
  try {
    const d = await api(`/api/projects/${enc(S.pid)}/lines/${l.id}/dictation`, { body: { text: typed } });
    S.dict[l.id] = { typed, result: d.result, notes: d.notes, shown: true };
    if (S.speak[l.id]) S.speak[l.id].shown = false;
    l.bd = Math.max(l.bd ?? 0, d.result.score);
    S.justChecked = l.id;
    renderStrip(); renderPractice(); renderScript(false);
    const li = $(`#script li[data-id="${l.id}"]`); if (li) li.classList.add('on');
    if (d.result.score < 0.8) refreshReviewCount();
  } catch (e) { errToast(e); }
}

function dictReveal() {
  const l = S.cur;
  if (!l) return;
  S.revealed.add(l.id);
  renderStrip(); renderScript(false);
}

function speakHTML(l) {
  const r = S.speak[l.id];
  const sttOk = S.st.stt.available && S.st.stt.models[S.st.stt.model] && S.st.stt.models[S.st.stt.model].ready;
  const dl = S.jobs.find(j => j.kind === 'download' && j.state === 'running');
  const dlErr = !dl && [...S.jobs].reverse().find(j => j.kind === 'download' && j.state === 'error');
  return `
  <p class="muted small" style="margin:0 0 12px">원어민 소리를 듣고 똑같이 따라 말해 보세요. 이 컴퓨터의 음성 인식이 알아들은 말과 원문을 비교해요. 단축키 <kbd>R</kbd></p>
  ${!S.st.stt.available ? `<div class="note warn">음성 인식 부품이 설치되지 않았어요. 실행 파일을 다시 실행하면 설치를 다시 시도해요.</div>` :
    !sttOk ? (dlErr ? `<div class="note warn">음성 인식 모델을 내려받지 못했어요. ${esc(dlErr.error)} <button class="btn small" data-act="stt-download" data-name="${esc(S.st.stt.model)}">다시 받기</button></div>`
      : `<div class="note warn">음성 인식 모델을 내려받는 중이에요. ${dl ? pct(dl.progress) : ''} 끝나면 바로 쓸 수 있어요. (처음 한 번만)</div>`) : ''}
  <div class="row">
    <button class="btn rec ${Rec.live ? 'live' : ''}" data-act="shadow">${Rec.live ? I.stop + ' 말하기 끝' : I.mic + ' 듣고 따라 말하기'}</button>
    <button class="btn" data-act="rec-only" ${Rec.live ? 'disabled' : ''}>${I.mic} 바로 말하기</button>
    <div class="rec-state" id="recState" ${Rec.live || S.speakBusy ? '' : 'hidden'}><span class="dot"></span><span id="recMsg">${S.speakBusy ? '알아듣는 중…' : '말해 보세요'}</span><div class="meter"><i id="recMeter"></i></div></div>
  </div>
  <div id="speakResult">${r ? speakResultHTML(l, r) : (l.bs != null ? `<p class="faint small" style="margin-top:12px">지금까지 최고 ${pct(l.bs)}</p>` : '')}</div>`;
}

function speedText(sp) {
  if (!sp) return '';
  if (sp > 1.3) return `원어민보다 ${Math.round((sp - 1) * 100)}% 느렸어요. 끊지 말고 한 호흡에 이어서 말해 보세요.`;
  if (sp > 1.1) return '원어민보다 조금 느렸어요. 거의 다 왔어요.';
  if (sp < 0.8) return '원어민보다 빨랐어요. 또박또박 말해도 괜찮아요.';
  return '빠르기가 원어민과 비슷해요.';
}

function speakResultHTML(l, r) {
  if (r.no_speech) return `<div class="note warn" style="margin-top:12px">목소리가 들리지 않았어요. 마이크 가까이에서 조금 더 크게 말해 보세요.</div>`;
  const a = r.align;
  const missed = a.ref.filter(w => w.s === 'miss').map(w => w.w);
  return `
  <div class="score ${scoreClass(a.score)}"><b>${pct(a.score)}</b><span>${a.score >= 0.9 ? '원어민이 알아들을 만큼 또렷했어요.' : a.score >= 0.7 ? '대부분 잘 전달됐어요.' : '몇 단어가 다르게 들렸어요. 원본을 한 번 더 듣고 따라 해 보세요.'}</span></div>
  <div class="small muted">AI가 알아들은 말</div>
  <div class="said">${a.hyp.map(w => `<span class="w st-${w.s}">${esc(w.w)}</span>`).join(' ') || '<span class="faint">(없음)</span>'}</div>
  <div class="small" style="margin-top:8px">${esc(speedText(r.speed))}</div>
  ${missed.length ? `<div class="small muted" style="margin-top:4px">전달되지 않은 단어: <b style="color:var(--miss)">${esc(missed.join(', '))}</b></div>` : ''}
  ${r.unclear && r.unclear.length ? `<div class="small muted" style="margin-top:4px">발음이 흐릿하게 들린 단어: ${esc(r.unclear.join(', '))}</div>` : ''}
  <div class="row" style="margin-top:12px">
    <button class="btn" data-act="play">${I.play} 원본</button>
    <button class="btn" data-act="play-mine">${I.speak} 내 목소리</button>
    <button class="btn" data-act="ab">번갈아 듣기</button>
    <button class="btn primary" data-act="step" data-d="1">다음 문장 ${I.next}</button>
  </div>`;
}

function renderRecButtons() {
  if (S.view === 'study' && S.tab === 'speak') {
    const keep = $('#speakResult') ? $('#speakResult').innerHTML : '';
    renderPractice();
    if (keep && $('#speakResult') && !S.speak[S.cur && S.cur.id]) $('#speakResult').innerHTML = keep;
  }
  if (S.view === 'talk') renderAnswerBar();
  if (S.view === 'expr') $$('[data-act="expr-speak"]').forEach(b => { b.classList.toggle('live', Rec.live && S.exprRec === b.dataset.eid); });
}

function setLevel(v) { const m = $('#recMeter'); if (m) m.style.width = Math.round(v * 100) + '%'; }
function setRecMsg(t) { const s = $('#recState'); if (s) { s.hidden = false; $('#recMsg').textContent = t; } }

async function shadow(direct) {
  if (Rec.live) { Rec.stop(); return; }
  if (S.speakBusy) return;
  const l = S.cur;
  if (!l) return;
  try { await Rec.warm(); } catch (e) { errToast(e); return; }
  if (direct) { recordLine(l); return; }
  setRecMsg('먼저 들어 보세요…');
  const ok = await Player.playClip(l.cs, l.ce, { rate: S.speed, loops: 1, onDone: () => recordLine(l) });
  if (!ok) recordLine(l);
}

async function recordLine(l) {
  if (!S.cur || S.cur.id !== l.id) return;
  const dur = Math.max(2.5, (l.ce - l.cs) / Math.min(1, S.speed) * 2 + 1.5);
  let blob;
  try {
    const p = Rec.record({ maxSec: dur + 4, silenceMs: 1300, onLevel: setLevel });
    setRecMsg('지금 말하세요');
    blob = await p;
  } catch (e) { errToast(e); renderPractice(); return; }
  if (!blob) return;
  S.speakBusy = true; renderPractice(); setRecMsg('알아듣는 중…');
  try {
    const r = await api(`/api/projects/${enc(S.pid)}/lines/${l.id}/speak`, { body: blob, raw: true, type: blob.type });
    S.speak[l.id] = { ...r, shown: !r.no_speech };
    if (S.dict[l.id]) S.dict[l.id].shown = false;
    if (r.align) { l.bs = Math.max(l.bs ?? 0, r.align.score); S.justChecked = l.id; if (r.align.score < 0.75) refreshReviewCount(); }
  } catch (e) { errToast(e); }
  S.speakBusy = false;
  if (S.cur && S.cur.id === l.id) { renderStrip(); renderPractice(); renderScript(false); }
}

function playMine(after) {
  const r = S.speak[S.cur && S.cur.id];
  if (!r || !r.rec) return;
  Player.pause();
  const a = new Audio(r.rec);
  a.onended = () => after && after();
  a.play().catch(e => errToast(e));
}

function abCompare() {
  const l = S.cur;
  if (!l) return;
  Player.playClip(l.cs, l.ce, { rate: 1, loops: 1, onDone: () => setTimeout(() => playMine(() => setTimeout(() => Player.playClip(l.cs, l.ce, { rate: 1, loops: 1 }), 500)), 400) });
}

function meanHTML(l) {
  const d = S.detail[l.id];
  const ex = d && d.explain;
  const lvName = ['', '느린 편', '보통', '빠른 편'][l.lv || 2];
  return `
  <dl class="kv">
    <dt>뜻</dt><dd class="big-ko">${esc(l.ko || (ex && ex.ko) || '아직 없어요')} ${l.kos === 'ai' ? '<span class="chip">AI 번역</span>' : ''}</dd>
    ${l.ai && l.ai.x ? `<dt>핵심 표현</dt><dd><span class="expr-pill">${esc(l.ai.x)}</span> ${esc(l.ai.xk || '')} ${l.ai.c && l.ai.c !== 'other' ? `<span class="chip navy">${esc(CAT()[l.ai.c] || '')}</span>` : ''}</dd>` : ''}
    ${l.tags && l.tags.length ? `<dt>대화 기능</dt><dd>${l.tags.map(t => `<span class="chip">${esc(CAT()[t] || t)}</span>`).join(' ')}</dd>` : ''}
    <dt>빠르기</dt><dd>초당 ${l.wps ?? '–'}단어 (${lvName}) · ${l.n}단어</dd>
  </dl>
  <h3 style="margin-top:16px">발음 포인트</h3>
  ${d ? notesHTML(d.notes) : '<span class="spin"></span>'}
  <h3 style="margin-top:16px">AI 설명</h3>
  ${ex ? explainHTML(ex) : `<button class="btn" data-act="explain" ${S.explaining === l.id ? 'disabled' : ''}>${S.explaining === l.id ? '<span class="spin"></span> AI가 설명을 쓰는 중…' : '이 문장 AI 설명 받기'}</button>`}`;
}

function explainHTML(ex) {
  return `<div class="stack">
    ${ex.points && ex.points.length ? `<div>${ex.points.map(p => `<div style="margin-bottom:4px"><span class="expr-pill">${esc(p.en)}</span> ${esc(p.ko)}</div>`).join('')}</div>` : ''}
    ${ex.nuance_ko ? `<div class="small">${esc(ex.nuance_ko)}</div>` : ''}
    ${ex.example_en ? `<div class="note"><div class="small faint">면접·미팅에서 이렇게</div><div class="en" style="font-size:var(--t-l);color:var(--ink)">${esc(ex.example_en)}</div><div>${esc(ex.example_ko || '')}</div>
      <div class="row" style="margin-top:6px"><button class="btn small" data-act="tts" data-text="${esc(ex.example_en)}">${I.speak} 들어 보기</button></div></div>` : ''}
  </div>`;
}

async function explain() {
  const l = S.cur;
  if (!l || S.explaining) return;
  S.explaining = l.id; renderPractice();
  try {
    const d = await api(`/api/projects/${enc(S.pid)}/lines/${l.id}/explain`, { body: {} });
    S.detail[l.id] = { ...(S.detail[l.id] || {}), explain: d.explain };
  } catch (e) { errToast(e); }
  S.explaining = null;
  if (S.cur && S.cur.id === l.id) renderPractice();
}

async function toggleStar() {
  const l = S.cur;
  if (!l) return;
  try {
    const d = await api(`/api/projects/${enc(S.pid)}/lines/${l.id}/star`, { body: { on: !l.st } });
    l.st = d.on; renderTransport(); renderScript(false); refreshReviewCount();
    toast(l.st ? '복습 카드에 넣었어요.' : '복습 카드에서 뺐어요.');
  } catch (e) { errToast(e); }
}

async function changeOffset(d) {
  const p = cur();
  const off = Math.round(((p.offset || 0) + d) * 100) / 100;
  try {
    await api(`/api/projects/${enc(S.pid)}/offset`, { body: { offset: off } });
    p.offset = off;
    S.lines.forEach(l => { l.s += d; l.e += d; l.cs = Math.max(0, l.cs + d); l.ce += d; });
    renderScript(false); renderTransport();
    toast(`대사 시간을 ${off.toFixed(2)}초로 맞췄어요. 듣기로 확인해 보세요.`);
  } catch (e) { errToast(e); }
}

async function refreshReviewCount() {
  try { await refreshState(); renderRail(); } catch (e) { /* ignore */ }
}

/* ================================================================ expressions */
async function openExpr() {
  const el = $('#view-expr');
  const p = cur();
  if (!p) { el.innerHTML = `<div class="empty"><h2>먼저 영화를 골라 주세요</h2><button class="btn primary" data-act="nav" data-view="home">영화 고르기</button></div>`; return; }
  if (!S.exprs || S.exprs.pid !== p.id) el.innerHTML = '<div class="empty"><span class="spin"></span></div>';
  try {
    const d = await api(`/api/projects/${enc(p.id)}/expressions`);
    S.exprs = { ...d, pid: p.id };
  } catch (e) { el.innerHTML = `<div class="empty err">${esc(e.message)}</div>`; return; }
  renderExpr();
}

function renderExpr() {
  const el = $('#view-expr');
  const d = S.exprs;
  const p = cur();
  const items = d.items.filter(e => (S.exprCat === 'all' || e.cat === S.exprCat) && (!S.exprStar || e.st));
  const cats = {};
  d.items.forEach(e => { cats[e.cat] = (cats[e.cat] || 0) + 1; });
  const exJob = jobFor('examples', p.id);
  const anJob = jobFor('analyze', p.id);
  const missing = d.items.filter(e => !e.example).length;
  el.innerHTML = `
  <div class="view-head"><div><h1>표현 노트</h1><p>${esc(p.title)}에서 AI가 고른, 면접·미팅에 다시 쓸 수 있는 표현이에요. 장면을 듣고, 내 문장으로 말해 보세요.</p></div></div>
  ${!d.items.length ? `<div class="panel empty"><h2>${anJob ? 'AI가 표현을 고르는 중이에요' : '아직 모인 표현이 없어요'}</h2>
     <p>${anJob ? esc(anJob.msg) : 'AI 분석이 끝나면 영화 속 쓸모 있는 표현이 여기에 모여요.'}</p>
     ${anJob ? '' : `<button class="btn primary" data-act="analyze">AI 분석 시작</button>`}</div>` : `
  <div class="expr-tools">
    <button class="chip ${S.exprCat === 'all' ? 'on' : ''}" data-act="expr-cat" data-c="all">전체 ${d.items.length}</button>
    ${Object.entries(cats).sort((a, b) => b[1] - a[1]).map(([c, n]) => `<button class="chip ${S.exprCat === c ? 'on' : ''}" data-act="expr-cat" data-c="${c}">${esc(CAT()[c] || c)} ${n}</button>`).join('')}
    <button class="chip ${S.exprStar ? 'on' : ''}" data-act="expr-staronly">★ 외우는 표현</button>
    <span style="flex:1"></span>
    ${exJob ? `<span class="small muted"><span class="spin"></span> ${esc(exJob.msg)}</span>` : missing ? `<button class="btn small" data-act="examples-all">예문 ${missing}개 한꺼번에 만들기</button>` : ''}
  </div>
  <div class="expr-list">${items.map(exprCard).join('') || '<p class="muted">해당하는 표현이 없어요.</p>'}</div>`}
  <div class="mini-player" id="mini" hidden><button class="close" data-act="mini-close">닫기</button><div class="screen" id="miniScreen"></div><div class="cap" id="miniCap"></div></div>`;
}

function exprCard(e) {
  const ex = e.example;
  const busy = S.exprBusy[e.id];
  const chk = S.exprCheck && S.exprCheck[e.id];
  return `<article class="expr" data-eid="${e.id}">
    <div>
      <div class="head"><span class="x">${esc(e.text)}</span><span class="ko">${esc(e.ko)}</span>${e.cat && e.cat !== 'other' ? `<span class="chip navy">${esc(CAT()[e.cat] || '')}</span>` : ''}</div>
      <button class="src" data-act="expr-scene" data-eid="${e.id}" title="장면 듣기"><span class="num">${fmtT(e.cs)}</span>${esc(e.line_text)}</button>
    </div>
    <div class="acts">
      <button class="btn small star ${e.st ? 'on' : ''}" data-act="expr-star" data-eid="${e.id}">${I.star} ${e.st ? '외우는 중' : '외우기'}</button>
      <button class="btn small" data-act="expr-scene" data-eid="${e.id}">${I.play} 장면</button>
    </div>
    <div class="ex">${ex ? `
      <div class="e">${esc(ex.example_en)}</div><div class="muted">${esc(ex.example_ko)}</div>
      ${ex.when_ko ? `<div class="small faint">${esc(ex.when_ko)}</div>` : ''}${ex.caution_ko ? `<div class="small" style="color:#A63D12">${esc(ex.caution_ko)}</div>` : ''}
      <div class="row"><button class="btn small" data-act="tts" data-text="${esc(ex.example_en)}">${I.speak} 예문 듣기</button></div>`
      : `<div><button class="btn small" data-act="expr-example" data-eid="${e.id}" ${busy ? 'disabled' : ''}>${busy === 'ex' ? '<span class="spin"></span> 만드는 중…' : '면접·미팅 예문 만들기'}</button></div>`}
    </div>
    <div class="check">
      <div class="row">
        <button class="btn small rec ${Rec.live && S.exprRec === e.id ? 'live' : ''}" data-act="expr-speak" data-eid="${e.id}" ${busy === 'chk' ? 'disabled' : ''}>${Rec.live && S.exprRec === e.id ? I.stop + ' 말하기 끝' : I.mic + ' 이 표현으로 말해 보기'}</button>
        <input type="text" class="en" style="flex:1;min-width:200px" placeholder="또는 이 표현을 넣은 문장을 적어 보기" data-eid="${e.id}" id="chkin-${e.id}">
        <button class="btn small" data-act="expr-check" data-eid="${e.id}" ${busy === 'chk' ? 'disabled' : ''}>${busy === 'chk' ? '<span class="spin"></span>' : '확인'}</button>
      </div>
      ${chk ? `<div class="note ${chk.check.natural && chk.check.used_expr ? 'ok' : ''}" style="margin-top:8px">
        <div class="en" style="color:var(--ink)">내 문장: ${esc(chk.text)}</div>
        ${!chk.check.used_expr ? '<div>표현이 문장에 들어가지 않았어요. 표현을 그대로 넣어 다시 말해 보세요.</div>' : ''}
        <div>${esc(chk.check.feedback_ko)}</div>
        ${chk.check.corrected && chk.check.corrected !== chk.text ? `<div class="en" style="color:var(--good);margin-top:4px">${esc(chk.check.corrected)}</div><div class="row" style="margin-top:4px"><button class="btn small" data-act="tts" data-text="${esc(chk.check.corrected)}">${I.speak} 들어 보기</button></div>` : ''}
      </div>` : ''}
    </div>
  </article>`;
}

function exprById(id) { return S.exprs && S.exprs.items.find(e => e.id === id); }

function playScene(cs, ce, cap, container) {
  const p = cur();
  Player.setSource(p);
  Player.mount(container);
  if ($('#miniCap')) $('#miniCap').textContent = cap || '';
  Player.playClip(cs, ce, { rate: 1, loops: 1 });
}

async function exprExample(id) {
  S.exprBusy[id] = 'ex'; renderExpr();
  try {
    const d = await api(`/api/projects/${enc(S.pid)}/expressions/${id}/example`, { body: {} });
    const e = exprById(id); if (e) e.example = d.example;
  } catch (e) { errToast(e); }
  delete S.exprBusy[id]; renderExpr();
}

async function exprCheckText(id) {
  const inp = $('#chkin-' + id);
  const text = inp ? inp.value.trim() : '';
  if (!text) { toast('표현을 넣은 문장을 적어 주세요.'); return; }
  S.exprBusy[id] = 'chk'; renderExpr();
  try {
    const d = await api(`/api/projects/${enc(S.pid)}/expressions/${id}/check`, { body: { text } });
    S.exprCheck = S.exprCheck || {}; S.exprCheck[id] = d;
  } catch (e) { errToast(e); }
  delete S.exprBusy[id]; renderExpr();
}

async function exprSpeak(id) {
  if (Rec.live) { Rec.stop(); return; }
  S.exprRec = id;
  let blob;
  try { blob = await Rec.record({ maxSec: 25, silenceMs: 1800 }); } catch (e) { errToast(e); S.exprRec = null; renderExpr(); return; }
  S.exprRec = null;
  if (!blob) { renderExpr(); return; }
  S.exprBusy[id] = 'chk'; renderExpr();
  try {
    const d = await api(`/api/projects/${enc(S.pid)}/expressions/${id}/speak`, { body: blob, raw: true, type: blob.type });
    if (d.no_speech) toast('목소리가 들리지 않았어요. 조금 더 크게 말해 보세요.', true);
    else { S.exprCheck = S.exprCheck || {}; S.exprCheck[id] = d; }
  } catch (e) { errToast(e); }
  delete S.exprBusy[id]; renderExpr();
}

async function exprStar(id) {
  const e = exprById(id);
  if (!e) return;
  try {
    const d = await api(`/api/projects/${enc(S.pid)}/expressions/${id}/star`, { body: { on: !e.st } });
    e.st = d.on; renderExpr(); refreshReviewCount();
  } catch (err) { errToast(err); }
}

/* ================================================================ talk (interview / meeting) */
function renderTalk() {
  if (S.talk && !S.talkSetup) renderSession(); else renderTalkSetup();
}

function renderTalkSetup() {
  const el = $('#view-talk');
  const st = S.st;
  const sel = S.talkSel || (S.talkSel = { scenario: 'interview_basic', level: st.settings.level || 'normal', n: 5, custom: '', project: S.pid || '' });
  const prof = st.settings.profile || {};
  const ol = S.ollama;
  el.innerHTML = `
  <div class="view-head"><div><h1>면접·미팅 연습</h1><p>로컬 AI가 면접관이나 동료가 되어 영어로 묻고, 내 답을 듣고 고쳐 줘요. 질문은 소리로 들려 주니 듣기 연습도 함께 돼요.</p></div></div>
  ${aiNote('talk')}
  <div class="talk">
    <div class="stack">
      <div class="field"><span>상황</span><div class="scen">${st.scenarios.map(s => `
        <label class="${sel.scenario === s.id ? 'on' : ''}"><input type="radio" name="scen" value="${s.id}" ${sel.scenario === s.id ? 'checked' : ''}><span><b>${esc(s.title)}</b><span>${esc(s.desc)}</span></span></label>`).join('')}</div></div>
    </div>
    <div class="stack">
      ${sel.scenario === 'custom' ? `<label class="field"><span>어떤 상황인가요? (한국어로 적어도 돼요)</span><textarea id="tCustom" rows="3" placeholder="예: 해외 거래처와 첫 화상 회의에서 회사 소개하기">${esc(sel.custom)}</textarea></label>` : ''}
      <div class="field"><span>난이도</span><div class="seg" data-seg="tlevel">
        ${[['easy', '쉽게'], ['normal', '보통'], ['real', '실전처럼']].map(([k, t]) => `<button class="${sel.level === k ? 'on' : ''}" data-val="${k}">${t}</button>`).join('')}</div></div>
      <div class="field"><span>질문 수</span><div class="seg" data-seg="tn">${[3, 5, 7].map(n => `<button class="${sel.n === n ? 'on' : ''}" data-val="${n}">${n}개</button>`).join('')}</div></div>
      <label class="field"><span>지원하는 일 / 하는 일 (선택)</span><input type="text" id="pJob" value="${esc(prof.job || '')}" placeholder="예: 신입 엔지니어, 해외 영업"></label>
      <label class="field"><span>회사·분야 (선택)</span><input type="text" id="pCompany" value="${esc(prof.company || '')}" placeholder="예: 물류 회사"></label>
      <label class="field"><span>내 경험 한 줄 (선택)</span><input type="text" id="pBg" value="${esc(prof.background || '')}" placeholder="예: 대학에서 팀 프로젝트를 이끌었음"></label>
      <label class="field"><span>함께 쓸 영화 표현</span><select id="tProject"><option value="">쓰지 않기</option>${st.projects.filter(p => p.analysis && p.analysis.state === 'done').map(p => `<option value="${esc(p.id)}" ${sel.project === p.id ? 'selected' : ''}>${esc(p.title)}</option>`).join('')}</select></label>
      <div class="row"><button class="btn primary big" data-act="talk-start" ${ol && !ol.ok ? 'disabled' : ''}>${S.talkBusy ? '<span class="spin"></span> 준비 중…' : '연습 시작'}</button>
        ${S.talk ? '<button class="btn" data-act="talk-resume">하던 연습으로</button>' : ''}</div>
      <div id="talkHistory"></div>
    </div>
  </div>`;
  loadTalkHistory();
}

async function loadTalkHistory() {
  try {
    const d = await api('/api/roleplay');
    const box = $('#talkHistory');
    if (!box) return;
    if (!d.sessions.length) { box.innerHTML = ''; return; }
    box.innerHTML = `<div class="field" style="margin-top:12px"><span>지난 연습</span>${d.sessions.slice(0, 8).map(s => `
      <div class="hist-row"><button class="btn quiet small" data-act="talk-open" data-sid="${esc(s.id)}">${esc(new Date(s.created * 1000).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' }))} · ${esc(s.title)} · 답 ${s.answers}개${s.model ? ` · ${esc(s.model)}` : ''}</button>
      <button class="btn quiet small del" data-act="talk-del" data-sid="${esc(s.id)}" aria-label="${esc(s.title)} 기록 지우기">지우기</button></div>`).join('')}</div>`;
  } catch (e) { /* ignore */ }
}

async function talkStart() {
  const sel = S.talkSel;
  const profile = { job: ($('#pJob') || {}).value || '', company: ($('#pCompany') || {}).value || '', background: ($('#pBg') || {}).value || '' };
  if ($('#tCustom')) sel.custom = $('#tCustom').value;
  sel.project = ($('#tProject') || {}).value || '';
  if (sel.scenario === 'custom' && !sel.custom.trim()) { toast('어떤 상황인지 적어 주세요.'); return; }
  S.talkBusy = true; renderTalkSetup();
  try {
    const d = await api('/api/roleplay/start', { body: { scenario: sel.scenario, level: sel.level, n: sel.n, profile, project: sel.project, custom: sel.custom } });
    S.talk = d.session; S.talkSetup = false; S.talkDraft = ''; S.talkShown = new Set();
    S.st.settings.profile = profile; S.st.settings.level = sel.level;
    S.talkBusy = false;
    renderSession();
    speakLastQuestion();
    return;
  } catch (e) { errToast(e); }
  S.talkBusy = false;
  if (S.talkSetup) renderTalkSetup();
}

function speakLastQuestion() {
  const t = S.talk && [...S.talk.turns].reverse().find(x => x.role === 'ai');
  if (!t) return;
  const rate = S.talk.rate || { easy: 0.85, normal: 0.95, real: 1.02 }[S.talk.level] || 0.95;
  TTS.speak(t.text, { rate, voice: S.talk.voice || TALK_VOICE[S.talk.scenario] });
}

function renderSession() {
  const el = $('#view-talk');
  const s = S.talk;
  const answered = s.turns.filter(t => t.role === 'me').length;
  const lastAi = s.turns.length - 1 - [...s.turns].reverse().findIndex(t => t.role === 'ai');
  el.innerHTML = `
  <div class="session">
    ${voiceNote()}
    <div class="session-head">
      <div><h2 style="margin:0">${esc(s.title)}</h2><div class="small muted">질문 ${Math.min(s.asked, s.n)} / ${s.n} · 답 ${answered}개${s.model ? ` · AI <span class="num">${esc(s.model)}</span>` : ''}</div></div>
      <div class="row">
        <label class="row small"><input type="checkbox" id="hideQ" ${S.talkHideQ ? 'checked' : ''}> 질문 글자 가리기 (듣기 연습)</label>
        <button class="btn" data-act="talk-new">새 연습</button>
      </div>
    </div>
    <div class="script-talk" id="talkScript">
      ${s.turns.map((t, i) => turnHTML(s, t, i, i === lastAi)).join('')}
      ${s.summary ? summaryHTML(s.summary) : ''}
    </div>
    <div id="answerBar"></div>
  </div>`;
  renderAnswerBar();
  const sc = $('#talkScript');
  if (sc) sc.lastElementChild && sc.lastElementChild.scrollIntoView({ block: 'end' });
}

function voiceNote() {
  const t = S.st.tts;
  if (!t || t.ready || S.st.settings.tts_engine === 'browser') return '';
  const j = S.jobs.find(x => x.kind === 'tts' && x.state === 'running');
  return `<div class="note warn" style="margin-bottom:12px">${j ? `자연스러운 영어 음성을 준비하는 중이에요 (${pct(j.progress)}). 끝나면 질문을 소리로 들려줘요.` : `영어 음성이 아직 없어요. <button class="btn small" data-act="tts-install">로컬 영어 음성 설치 (약 120MB)</button>`}</div>`;
}

function turnHTML(s, t, i, isLastAi) {
  if (t.role === 'ai') {
    const hidden = S.talkHideQ && !(S.talkShown || new Set()).has(i);
    return `<div class="turn ai"><div class="who">${esc(s.ai)}</div><div class="line ${hidden ? 'hidden-q' : ''}">${esc(t.text)}</div>
      <div class="tools"><button class="btn quiet small" data-act="tts" data-voice="${s.voice || TALK_VOICE[s.scenario] || ''}" data-rate="${s.rate || ''}" data-text="${esc(t.text)}">${I.speak} 다시 듣기</button>
      <button class="btn quiet small" data-act="tts-slow" data-voice="${s.voice || TALK_VOICE[s.scenario] || ''}" data-text="${esc(t.text)}">천천히</button>
      ${hidden ? `<button class="btn quiet small" data-act="show-q" data-i="${i}">글자 보기</button>` : ''}</div></div>`;
  }
  const fb = t.fb || {};
  return `<div class="turn me"><div class="who">${esc(s.me)} (나)</div><div class="line en">${esc(t.text)}</div>
    <div class="fb">
      ${fb.feedback_ko ? `<div class="ko">${esc(fb.feedback_ko)}</div>` : ''}
      ${(fb.fixes || []).length ? `<div class="fixes"><span class="lbl">고쳐 말하기</span>${fb.fixes.map(f =>
        `<span class="fix" aria-label="${esc(f.from)} 대신 ${esc(f.to)}"><span class="from">${esc(f.from)}</span><span class="arrow" aria-hidden="true">→</span><span class="to">${esc(f.to)}</span></span>`).join('')}</div>` : ''}
      ${fb.better ? `<div><div class="lbl">더 자연스럽게</div><div class="better">${esc(fb.better)}</div>
        <div class="tools"><button class="btn quiet small" data-act="tts" data-text="${esc(fb.better)}">${I.speak} 들어 보기</button>
        <button class="btn quiet small" data-act="add-phrase" data-en="${esc(fb.better)}">복습에 넣기</button></div></div>` : ''}
      ${fb.tip_expr ? `<div><span class="lbl">영화 표현을 써 보세요</span> <span class="expr-pill">${esc(fb.tip_expr)}</span></div>` : ''}
    </div></div>`;
}

function summaryHTML(sm) {
  return `<div class="summary panel" style="background:var(--paper)">
    <h3>오늘 연습 정리</h3>${sm.model ? `<div class="faint xs" style="margin:-4px 0 6px">정리한 AI: <span class="num">${esc(sm.model)}</span></div>` : ''}<p>${esc(sm.overall_ko)}</p>
    ${sm.good_ko.length ? `<div class="lbl small faint">잘한 점</div><ul>${sm.good_ko.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
    ${sm.improve_ko.length ? `<div class="lbl small faint">다음에 고칠 점</div><ul>${sm.improve_ko.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
    ${sm.phrases.length ? `<div class="lbl small faint">외워 둘 문장</div>${sm.phrases.map(p => `<div class="phrase"><div><div class="e">${esc(p.en)}</div><div class="small muted">${esc(p.ko)}</div></div>
      <div class="row"><button class="btn small" data-act="tts" data-text="${esc(p.en)}">${I.speak}</button><button class="btn small" data-act="add-phrase" data-en="${esc(p.en)}" data-ko="${esc(p.ko)}">복습에 넣기</button></div></div>`).join('')}` : ''}
  </div>`;
}

function renderAnswerBar() {
  const box = $('#answerBar');
  if (!box || !S.talk) return;
  const s = S.talk;
  if (s.done) {
    box.innerHTML = `<div class="answer-bar" style="justify-content:space-between;align-items:center"><span class="muted">연습이 끝났어요.</span>
      <div class="row">${s.summary ? '' : `<button class="btn primary" data-act="talk-summary" ${S.talkBusy ? 'disabled' : ''}>${S.talkBusy ? '<span class="spin"></span> 정리하는 중…' : 'AI에게 정리 받기'}</button>`}
      <button class="btn" data-act="talk-new">새 연습</button></div></div>`;
    return;
  }
  const busy = S.talkBusy;
  box.innerHTML = `<div class="answer-bar">
    <button class="btn rec ${Rec.live ? 'live' : ''}" data-act="talk-rec" ${busy ? 'disabled' : ''} title="Space">${Rec.live ? I.stop + ' 말하기 끝' : I.mic + ' 말로 답하기'}</button>
    <textarea id="answerText" rows="2" placeholder="말로 답하면 여기에 글자로 나와요. 고친 뒤 Enter로 보내기 (직접 적어도 돼요)" ${busy ? 'disabled' : ''}>${esc(S.talkDraft || '')}</textarea>
    <div class="stack" style="gap:6px">
      <button class="btn primary" data-act="talk-send" ${busy ? 'disabled' : ''}>${busy ? '<span class="spin"></span> ' + esc(S.talkBusyMsg || 'AI가 듣는 중…') : '보내기'}</button>
      <label class="row xs muted"><input type="checkbox" id="talkAuto" ${S.talkAuto ? 'checked' : ''}> 말한 뒤 바로 보내기</label>
    </div></div>
    ${Rec.live ? '<div class="rec-state" style="margin-top:8px"><span class="dot"></span> 듣고 있어요. 다 말했으면 버튼이나 Space를 눌러 주세요.<div class="meter"><i id="recMeter"></i></div></div>' : ''}`;
}

async function talkRecord() {
  if (Rec.live) { Rec.stop(); return; }
  if (S.talkBusy) return;
  TTS.stop();
  let blob;
  try { blob = await Rec.record({ maxSec: 120, silenceMs: 4000, onLevel: setLevel }); } catch (e) { errToast(e); renderAnswerBar(); return; }
  if (!blob) return;
  S.talkBusy = true; S.talkBusyMsg = '알아듣는 중…'; renderAnswerBar();
  try {
    const r = await api('/api/stt?purpose=talk', { body: blob, raw: true, type: blob.type });
    if (r.no_speech) { toast('목소리가 들리지 않았어요. 조금 더 크게 말해 보세요.', true); S.talkBusy = false; renderAnswerBar(); return; }
    S.talkDraft = r.text;
    S.talkBusy = false; renderAnswerBar();
    if (S.talkAuto) talkSend();
    else { const t = $('#answerText'); if (t) { t.focus(); t.setSelectionRange(t.value.length, t.value.length); } }
  } catch (e) { errToast(e); S.talkBusy = false; renderAnswerBar(); }
}

async function talkSend() {
  const t = $('#answerText');
  const text = (t ? t.value : S.talkDraft || '').trim();
  if (!text) { toast('답을 말하거나 적어 주세요.'); return; }
  S.talkDraft = text; S.talkBusy = true; S.talkBusyMsg = 'AI가 답을 읽는 중…'; renderAnswerBar();
  try {
    const d = await api(`/api/roleplay/${enc(S.talk.id)}/answer`, { body: { text } });
    S.talk = d.session; S.talkDraft = '';
    S.talkBusy = false; renderSession(); speakLastQuestion();
  } catch (e) { errToast(e); S.talkBusy = false; renderAnswerBar(); }
}

async function talkSummary() {
  S.talkBusy = true; renderAnswerBar();
  try { const d = await api(`/api/roleplay/${enc(S.talk.id)}/summary`, { body: {} }); S.talk = d.session; } catch (e) { errToast(e); }
  S.talkBusy = false; renderSession();
}

async function addPhrase(en, ko) {
  try { await api('/api/review/add', { body: { type: 'phrase', en, ko: ko || '', note: S.talk ? S.talk.title : '' } }); toast('복습 카드에 넣었어요.'); refreshReviewCount(); } catch (e) { errToast(e); }
}

/* ================================================================ review */
async function openReview() {
  const el = $('#view-review');
  el.innerHTML = '<div class="empty"><span class="spin"></span></div>';
  try { S.review = await api('/api/review'); } catch (e) { el.innerHTML = `<div class="empty err">${esc(e.message)}</div>`; return; }
  S.revIdx = 0; S.revShow = false;
  renderReview();
}

function renderReview() {
  const el = $('#view-review');
  const r = S.review;
  const c = r.cards[S.revIdx];
  const kind = { line: '영화 문장', expr: '영화 표현', phrase: '면접·미팅 문장' };
  el.innerHTML = `
  <div class="view-head"><div><h1>복습</h1><p>받아쓰기·말하기에서 어려웠던 문장, 내가 고른 문장과 표현이 날짜에 맞춰 다시 나와요. 잘 알수록 더 늦게 나와요.</p></div></div>
  <div class="review">
    <div class="rcounts"><div><b>${Math.max(0, r.cards.length - S.revIdx)}</b>오늘 남은 카드</div><div><b>${r.counts.total}</b>전체 카드</div><div><b>${r.counts.learned}</b>익힌 카드</div></div>
    ${!c ? `<div class="panel empty"><h2>오늘 복습은 끝났어요</h2><p>장면 학습에서 틀린 문장과 ★로 고른 문장이 여기로 모여요.</p><button class="btn primary" data-act="nav" data-view="study">장면 학습으로</button></div>` : `
    <div class="card">
      <div class="row"><span class="chip navy">${kind[c.type] || '카드'}</span>${c.title ? `<span class="faint small">${esc(c.title)}</span>` : ''}${c.note ? `<span class="faint small">${esc(c.type === 'expr' ? '' : c.note)}</span>` : ''}</div>
      ${c.type === 'line' ? `
        ${c.cs != null && c.media_ok ? `<div class="stage-mini"><div class="screen" id="revScreen"></div></div>` : ''}
        <div class="front">${c.cs != null && c.media_ok ? '장면을 듣고 무슨 말인지 떠올린 뒤 따라 말해 보세요.' : '이 뜻을 영어로 말해 보세요: ' + esc(c.ko || '')}</div>
        <div class="row">${c.cs != null && c.media_ok ? `<button class="btn primary" data-act="rev-play">${I.play} 듣기 <kbd>Space</kbd></button><button class="btn" data-act="rev-slow">느리게</button>` : `<button class="btn" data-act="tts" data-text="${esc(c.en)}">${I.speak} 듣기</button>`}</div>`
      : `<div class="front">${esc(c.ko || '')}</div><div class="muted small">이 뜻을 영어로 말해 본 뒤 정답을 확인하세요.</div>`}
      ${S.revShow ? `<div class="back"><div class="e">${esc(c.en)}</div><div class="muted" style="margin-top:4px">${esc(c.ko || '')}</div>
        ${c.type === 'expr' && c.note ? `<div class="small" style="margin-top:8px"><span class="faint">예문</span> <span class="en">${esc(c.note)}</span></div>` : ''}
        ${c.line_text ? `<div class="small faint en" style="margin-top:6px">${esc(c.line_text)}</div>` : ''}
        <div class="row" style="margin-top:8px"><button class="btn small" data-act="tts" data-text="${esc(c.en)}">${I.speak} 읽어 주기</button></div></div>
        <div class="grades"><button class="btn" data-act="rev-grade" data-g="again">다시 볼래요 <kbd>1</kbd></button><button class="btn" data-act="rev-grade" data-g="hard">애매해요 <kbd>2</kbd></button><button class="btn primary" data-act="rev-grade" data-g="good">알아요 <kbd>3</kbd></button></div>`
      : `<div class="grades"><button class="btn primary" data-act="rev-show">정답 보기 <kbd>Enter</kbd></button></div>`}
    </div>`}
  </div>`;
  if (c && c.type === 'line' && c.cs != null && c.media_ok) {
    const p = (S.st.projects || []).find(x => x.id === c.pid);
    if (p) { Player.setSource(p); Player.mount($('#revScreen')); }
  }
}

function revPlay(rate) {
  const c = S.review && S.review.cards[S.revIdx];
  if (!c) return;
  if (c.type === 'line' && c.cs != null && c.media_ok) Player.playClip(c.cs, c.ce, { rate: rate || 1, loops: 1 });
  else TTS.speak(c.en, { rate: rate ? 0.8 : null });
}

async function revGrade(g) {
  const c = S.review.cards[S.revIdx];
  if (!c) return;
  try { const d = await api('/api/review/grade', { body: { key: c.key, grade: g } }); S.review.counts = d.counts; S.st.review = d.counts; } catch (e) { errToast(e); return; }
  if (g === 'again') S.review.cards.push(c);
  S.revIdx += 1; S.revShow = false;
  Player.pause();
  renderReview(); renderRail();
}

/* ================================================================ settings */
function renderSettings() {
  const el = $('#view-settings');
  if (!S.st) return;
  const st = S.st, se = st.settings, ol = S.ollama;
  const voices = TTS.english();
  const allVoices = TTS.voices.filter(v => /^en/i.test(v.lang));
  const sttModels = [['base.en', '빠름', '이 컴퓨터에서 가장 가볍게'], ['small.en', '정확', '추천: 말하기 채점에 알맞아요'], ['medium.en', '아주 정확', '느리고 1.5GB']];
  const dl = n => S.jobs.find(j => j.kind === 'download' && j.pid === n && j.state === 'running');
  el.innerHTML = `
  <div class="view-head"><div><h1>설정</h1><p>모든 AI는 이 컴퓨터에서만 돌아가요. 처음 한 번 음성 인식 모델과 영어 음성 모델만 인터넷에서 내려받아요.</p></div></div>
  <div class="settings">
    <div class="panel">
      <h2>AI 모델 (Ollama)</h2>
      ${!ol ? '<span class="spin"></span> 확인 중…' : ol.ok ? `<div class="small muted">Ollama ${esc(ol.version)} 연결됨 · 지금 쓰는 모델: <b>${esc(ol.model)}</b></div>
        <div class="row" style="margin-top:10px"><select id="modelSel"><option value="">자동으로 고르기 (추천)</option>${ol.models.map(m => `<option value="${esc(m)}" ${se.model === m ? 'selected' : ''}>${esc(m)}${(ol.capabilities && (ol.capabilities[m] || []).includes('thinking')) ? ' (생각 기능은 꺼서 사용)' : ''}</option>`).join('')}</select>
        <button class="btn small" data-act="recheck-ollama">다시 확인</button></div>
        <div class="faint xs" style="margin-top:6px">qwen3.5:4b처럼 4B 이상 모델이 영어 예문과 피드백을 더 잘 만들어요.</div>`
      : `<div class="small muted" style="margin-bottom:8px">${esc(ol.error || 'Ollama에 연결하지 못했어요.')}</div>`}
      ${aiNote('settings')}
    </div>
    <div class="panel">
      <h2>음성 인식 (내 목소리 알아듣기)</h2>
      ${!st.stt.available ? `<div class="note warn">음성 인식 부품이 설치되지 않았어요: ${esc(st.stt.error)}<br>실행 파일을 다시 실행하면 설치를 다시 시도해요.</div>` : `
      <div class="models">${sttModels.map(([n, t, d]) => {
        const m = st.stt.models[n] || {}; const j = dl(n);
        return `<label class="${se.stt_model === n ? 'on' : ''}"><input type="radio" name="sttModel" value="${n}" ${se.stt_model === n ? 'checked' : ''}><span><b>${t}</b> <span class="faint small">${n} · ${m.mb}MB · ${d}</span></span>
          <span>${m.ready ? '<span class="chip good">준비됨</span>' : j ? `<span class="jobline small" data-kind="download" data-pid="${n}"><span class="msg" hidden></span><span class="num p">${pct(j.progress)}</span><span class="bar" style="width:90px;display:inline-block;vertical-align:middle;margin-left:6px"><i style="width:${pct(j.progress)}"></i></span></span>` : `<button class="btn small" data-act="stt-download" data-name="${n}">내려받기</button>`}</span></label>`;
      }).join('')}</div>
`}
    </div>
    <div class="panel">
      <h2>마이크와 녹음</h2>
      <div class="row"><button class="btn" data-act="mic-panel">${I.mic} 마이크 확인</button><span class="small muted">지금 마이크:</span><span id="micState">${micStateHTML()}</span></div>
      <div class="field" style="margin-top:12px"><span>녹음이 끝나면</span>
        <div class="seg" data-seg="micKeep"><button class="${se.mic_keep ? '' : 'on'}" data-val="0">마이크 바로 끄기 (추천)</button><button class="${se.mic_keep ? 'on' : ''}" data-val="1">연습하는 동안 켜 두기</button></div></div>
      <p class="small muted" style="margin:10px 0 6px">마이크는 녹음 버튼을 누르거나 마이크 확인을 열 때만 켜져요. 켜져 있으면 왼쪽 아래에 빨간 점으로 보이고, [끄기]로 바로 끌 수 있어요.</p>
      <p class="small muted" style="margin:0 0 8px">따라 말하기·표현 말하기 녹음은 '내 녹음 듣기'를 위해 학습 기록 폴더에 남아요. 면접·미팅 연습 답과 마이크 확인 녹음은 글자로 바꾼 뒤 바로 지워요.</p>
      <div class="row"><span class="small" id="recInfo">${S.recs ? (S.recs.count ? `저장된 내 녹음 ${S.recs.count}개 · ${mb(S.recs.bytes)}` : '저장된 내 녹음이 없어요.') : '저장된 녹음을 세는 중…'}</span>
        ${S.recs && S.recs.count ? '<button class="btn small" data-act="recs-delete">녹음 모두 지우기</button>' : ''}</div>
    </div>
    <div class="panel">
      <h2>영어 읽어 주는 목소리</h2>
      <div class="seg" data-seg="ttsEngine" style="margin-bottom:12px">
        <button class="${se.tts_engine !== 'browser' ? 'on' : ''}" data-val="kokoro">로컬 AI 음성 (자연스러움, 추천)</button>
        <button class="${se.tts_engine === 'browser' ? 'on' : ''}" data-val="browser">Windows 음성</button></div>
      ${se.tts_engine !== 'browser' ? kokoroPanel(st, se) : browserVoicePanel(se, voices, allVoices)}
    </div>
    <div class="panel">
      <h2>전체 점검</h2>
      <p class="small muted" style="margin:0 0 8px">영상 도구, Ollama 응답, 음성 인식이 제대로 되는지 한 번에 확인해요. (30초쯤 걸려요)</p>
      <button class="btn" data-act="self-check" ${S.checking ? 'disabled' : ''}>${S.checking ? '<span class="spin"></span> 점검 중…' : '점검 시작'}</button>
      ${S.checks ? `<ul class="checks">${S.checks.map(c => `<li><span class="${c.ok ? 'ok' : 'no'}">${c.ok ? '✓' : '✕'}</span><b>${esc(c.name)}</b><span class="muted">${esc(c.detail)}</span></li>`).join('')}</ul>` : ''}
    </div>
    <div class="panel">
      <h2>학습 기록</h2>
      <div class="small muted">${esc(st.data_dir)}</div>
      <div class="row" style="margin-top:8px"><button class="btn small" data-act="open-folder" data-what="data">폴더 열기</button></div>
      <div class="faint xs" style="margin-top:10px">버전 ${esc(st.version)}</div>
    </div>
  </div>`;
}

async function loadRecs() {
  try { S.recs = await api('/api/recordings'); } catch (e) { S.recs = { count: 0, bytes: 0 }; }
  if (S.view === 'settings') renderSettings();
}

function kokoroPanel(st, se) {
  const t = st.tts || {};
  const j = S.jobs.find(x => x.kind === 'tts' && x.state === 'running');
  const err = [...S.jobs].reverse().find(x => x.kind === 'tts' && x.state === 'error');
  if (t.ready) {
    return `<div class="row"><select id="voiceKSel">${(t.voices || []).map(v => `<option value="${v.id}" ${se.tts_voice_k === v.id ? 'selected' : ''}>${esc(v.name)}</option>`).join('')}</select>
      <label class="row small">빠르기 <input type="range" id="ttsRate" min="0.7" max="1.2" step="0.05" value="${se.tts_rate || 0.95}"> <span class="num" id="ttsRateVal">${(se.tts_rate || 0.95).toFixed(2)}</span></label>
      <button class="btn small" data-act="tts" data-text="Thanks for coming in today. Could you briefly introduce yourself?">${I.speak} 들어 보기</button></div>
      <div class="faint xs" style="margin-top:6px">면접·미팅 연습에서는 상황마다 다른 목소리(미국·영국 억양)로 들려줘요.</div>`;
  }
  if (j) return `<div class="jobline" data-kind="tts" data-pid="kokoro"><div class="row small muted" style="justify-content:space-between"><span class="msg">${esc(j.msg)}</span><span class="num p">${pct(j.progress)}</span></div><div class="bar"><i style="width:${pct(j.progress)}"></i></div></div>`;
  return `<div class="note">이 컴퓨터에서 돌아가는 자연스러운 영어 음성(Kokoro)이에요. 처음 한 번 약 120MB를 내려받아요.</div>
    ${err || t.error ? `<div class="err" style="margin-top:6px">${esc((err && err.error) || t.error)}</div>` : ''}
    <div class="row" style="margin-top:8px"><button class="btn small primary" data-act="tts-install">설치하기</button></div>`;
}

function browserVoicePanel(se, voices, allVoices) {
  return voices.length ? `<div class="row"><select id="voiceSel">${voices.map(v => `<option value="${esc(v.name)}" ${TTS.pick() && TTS.pick().name === v.name ? 'selected' : ''}>${esc(v.name)}</option>`).join('')}</select>
      <label class="row small">빠르기 <input type="range" id="ttsRate" min="0.7" max="1.2" step="0.05" value="${se.tts_rate || 0.95}"> <span class="num" id="ttsRateVal">${(se.tts_rate || 0.95).toFixed(2)}</span></label>
      <button class="btn small" data-act="tts" data-text="Thanks for coming in today. Could you briefly introduce yourself?">${I.speak} 들어 보기</button></div>`
    : `<div class="note warn">이 컴퓨터에 Windows 영어 음성이 없어요. 위의 "로컬 AI 음성"을 쓰거나, Windows 설정 → 시간 및 언어 → 음성 → "음성 추가"에서 English (United States)를 추가하세요.${allVoices.length ? ' 인터넷 음성은 아래에서 켤 수 있어요.' : ''}</div>
      <label class="row small" style="margin-top:10px"><input type="checkbox" id="allowOnline" ${se.allow_online_voices ? 'checked' : ''}> 인터넷 음성도 쓰기 (더 자연스럽지만, 읽을 문장이 Microsoft 서버로 보내져요)</label>`;
}

async function saveSettings(changes) {
  try { const d = await api('/api/settings', { body: { changes } }); S.st.settings = d.settings; } catch (e) { errToast(e); }
}

async function selfCheck() {
  S.checking = true; S.checks = null; renderSettings();
  try { const d = await api('/api/check', { body: {} }); S.checks = d.checks; } catch (e) { errToast(e); }
  S.checking = false; renderSettings();
}

/* ================================================================ events */
async function addMovie(path, sample) {
  try {
    const d = await api('/api/projects', { body: sample ? { sample: true } : { path } });
    await refreshState();
    S.pid = d.project.id; store.set('pid', S.pid);
    S.linesPid = null; S.exprs = null;
    if (d.existing) toast('이미 추가한 영화예요. 이어서 공부해요.');
    show('home');
  } catch (e) { errToast(e); }
}

async function prepare() {
  const p = cur();
  const sel = S.srcSel[p.id];
  if (!sel || !sel.en) { toast('영어 대사를 어디서 가져올지 골라 주세요.'); return; }
  try {
    await api(`/api/projects/${enc(p.id)}/prepare`, { body: { en: sel.en, ko: sel.ko || '', model: sel.en === 'whisper' ? sel.model : null, depth: S.st.settings.analysis_depth || 'normal' } });
    await sleep(300);
    const d = await api('/api/jobs'); onJobs(d.jobs);
    await refreshState(); renderHome();
  } catch (e) { errToast(e); }
}

async function startJob(path, body) {
  try { await api(path, { body: body || {} }); const d = await api('/api/jobs'); onJobs(d.jobs); await refreshState(); renderRail(); if (S.view === 'home') renderHome(); }
  catch (e) { errToast(e); }
}

const ACT = {
  nav: a => show(a.dataset.view),
  'recheck-ollama': () => { S.ollama = null; if (S.view === 'settings') renderSettings(); checkOllama(); },
  'start-ollama': async a => {
    a.disabled = true; a.textContent = '켜는 중…';
    try { await api('/api/ollama/start', { body: {} }); toast('Ollama를 켰어요.'); } catch (e) { errToast(e); }
    checkOllama();
  },
  'pull-model': async a => {
    a.disabled = true;
    try { const d = await api('/api/ollama/pull', { body: { model: (S.ollama && S.ollama.recommended) || '' } }); if (S.ollama) S.ollama.pull = d.pull; }
    catch (e) { errToast(e); a.disabled = false; return; }
    document.querySelectorAll('[data-pullbox]').forEach(b => { b.classList.remove('warn'); b.innerHTML = pullHtml(S.ollama.pull); });
    watchPull();
  },
  'pick-movie': async () => {
    try { const d = await api('/api/pick', { body: { kind: 'movie' } }); if (d.path) addMovie(d.path); } catch (e) { errToast(e); }
  },
  'add-path': () => { const v = $('#pastePath').value.trim().replace(/^"|"$/g, ''); if (v) addMovie(v); else toast('영화 파일 위치를 붙여 넣어 주세요.'); },
  'add-sample': () => addMovie(null, true),
  'select-movie': a => { S.pid = a.dataset.pid; store.set('pid', S.pid); S.linesPid = null; S.exprs = null; S.cur = null; S.detail = {}; S.dict = {}; S.speak = {}; renderRail(); renderHome(); },
  prepare,
  'pick-sub': async () => {
    const p = cur();
    try {
      const d = await api('/api/pick', { body: { kind: 'subtitle', dir: p.movie.replace(/[\\/][^\\/]*$/, '') } });
      if (!d.path) return;
      const r = await api(`/api/projects/${enc(p.id)}/sources/file`, { body: { path: d.path } });
      const src = S.sources[p.id];
      r.options.forEach(o => { (o.lang === 'ko' ? src.ko : src.en).unshift(o); });
      const sel = S.srcSel[p.id];
      const en = r.options.find(o => o.lang === 'en'), ko = r.options.find(o => o.lang === 'ko');
      if (en) sel.en = en.id; if (ko) sel.ko = ko.id;
      if (!en && !ko) { src.en.unshift(r.options[0]); sel.en = r.options[0].id; }
      $('#srcBox').innerHTML = sourcesHTML(p, src, sel);
    } catch (e) { errToast(e); }
  },
  'redo-lines': () => { const p = cur(); p.lines_ready = false; S.sources[p.id] = null; renderHome(); },
  'media-start': () => startJob(`/api/projects/${enc(S.pid)}/media`, {}),
  'media-transcode': () => { if (confirm('영상을 재생용 형식(H.264)으로 바꿀게요. 컴퓨터에 따라 영화 한 편에 10~40분 걸릴 수 있어요. 바꾸는 동안에도 소리로 공부할 수 있어요.')) { Player.failed = false; startJob(`/api/projects/${enc(S.pid)}/media`, { plan: 'transcode' }); } },
  analyze: () => startJob(`/api/projects/${enc(S.pid)}/analyze`, { depth: S.st.settings.analysis_depth || 'normal' }),
  reanalyze: () => { if (confirm('AI가 고른 문장과 표현을 지우고 처음부터 다시 분석할까요? (받아쓰기·말하기 기록은 그대로예요)')) { S.linesPid = null; S.exprs = null; startJob(`/api/projects/${enc(S.pid)}/analyze`, { depth: S.st.settings.analysis_depth || 'normal', redo: true }); } },
  'examples-all': () => startJob(`/api/projects/${enc(S.pid)}/examples`, {}).then(() => renderExpr()),
  'cancel-job': a => api(`/api/jobs/${a.dataset.id}/cancel`, { body: {} }).then(() => toast('멈추는 중이에요. 다음에 이어서 할 수 있어요.')).catch(errToast),
  'go-study': () => show('study'),
  'go-talk': () => show('talk'),
  'open-folder': a => api('/api/open', { body: { what: a.dataset.what, pid: S.pid } }).catch(errToast),
  'delete-media': async () => {
    if (!confirm('재생용 사본을 지울까요? 원본 영화와 학습 기록은 그대로 남아요.')) return;
    try { const d = await api(`/api/projects/${enc(S.pid)}/delete`, { body: { media_only: true } }); toast(`${Math.round(d.freed / 1e6)}MB를 비웠어요.`); Player.setSource(null); await refreshState(); renderHome(); } catch (e) { errToast(e); }
  },
  'ask-delete': a => askDelete(a.dataset.pid),
  'delete-project': () => askDelete(S.pid),
  'del-cancel': () => closeDelModal(),
  'del-confirm': () => doDelete(),
  tab: a => { S.tab = a.dataset.tab; store.set('tab', S.tab); renderPractice(); if (S.tab === 'dict') { const i = $('#dictInput'); if (i) i.focus(); } },
  play: () => togglePlay(),
  step: a => stepLine(Number(a.dataset.d)),
  star: () => toggleStar(),
  watch: () => { if (Player.free && Player.playing()) { Player.pause(); } else if (S.cur) Player.playFree(S.cur.cs); },
  filter: a => { S.filter = a.dataset.f; store.set('filter', S.filter); renderScript(true); renderTransport(); },
  offset: a => changeOffset(Number(a.dataset.d)),
  hint: a => { S.hints[a.dataset.h] = !S.hints[a.dataset.h]; const keep = ($('#dictInput') || {}).value; renderPractice(); if (keep != null && $('#dictInput')) $('#dictInput').value = keep; },
  'dict-check': () => dictCheck(),
  'dict-reveal': () => dictReveal(),
  'replay-slow': () => playCur(0.75),
  shadow: () => shadow(false),
  'rec-only': () => shadow(true),
  'play-mine': () => playMine(),
  ab: () => abCompare(),
  explain: () => explain(),
  tts: a => TTS.speak(a.dataset.text, { voice: a.dataset.voice || null, rate: Number(a.dataset.rate) || null }),
  'tts-slow': a => TTS.speak(a.dataset.text, { rate: 0.78, voice: a.dataset.voice || null }),
  'tts-install': () => startJob('/api/tts/install', {}).then(() => { if (S.view === 'settings') renderSettings(); }),
  'expr-cat': a => { S.exprCat = a.dataset.c; renderExpr(); },
  'expr-staronly': () => { S.exprStar = !S.exprStar; renderExpr(); },
  'expr-scene': a => {
    const e = exprById(a.dataset.eid);
    if (!e) return;
    const mini = $('#mini'); mini.hidden = false;
    playScene(e.cs, e.ce, e.line_text, $('#miniScreen'));
  },
  'mini-close': () => { Player.pause(); $('#mini').hidden = true; },
  'expr-example': a => exprExample(a.dataset.eid),
  'expr-check': a => exprCheckText(a.dataset.eid),
  'expr-speak': a => exprSpeak(a.dataset.eid),
  'expr-star': a => exprStar(a.dataset.eid),
  'talk-start': () => talkStart(),
  'talk-resume': () => { S.talkSetup = false; renderSession(); },
  'talk-new': () => { TTS.stop(); S.talkSetup = true; renderTalkSetup(); },
  'talk-del': async a => {
    if (!confirm('이 연습 기록을 지울까요? 지운 기록은 되돌릴 수 없어요.')) return;
    try {
      await api(`/api/roleplay/${enc(a.dataset.sid)}/delete`, { body: {} });
      if (S.talk && S.talk.id === a.dataset.sid) S.talk = null;
      toast('연습 기록을 지웠어요.');
      loadTalkHistory();
    } catch (e) { errToast(e); }
  },
  'talk-open': async a => { try { const d = await api(`/api/roleplay/${enc(a.dataset.sid)}`); S.talk = d.session; S.talkSetup = false; renderSession(); } catch (e) { errToast(e); } },
  'talk-rec': () => talkRecord(),
  'talk-send': () => talkSend(),
  'talk-summary': () => talkSummary(),
  'show-q': a => { S.talkShown = S.talkShown || new Set(); S.talkShown.add(Number(a.dataset.i)); renderSession(); },
  'add-phrase': a => addPhrase(a.dataset.en, a.dataset.ko),
  'rev-play': () => revPlay(),
  'rev-slow': () => revPlay(0.75),
  'rev-show': () => { S.revShow = true; renderReview(); },
  'rev-grade': a => revGrade(a.dataset.g),
  'stt-download': a => startJob('/api/stt/download', { name: a.dataset.name }).then(() => { if (S.view === 'settings') renderSettings(); else if (S.view === 'study') renderPractice(); }),
  'mic-test': () => openMicPanel(),
  'mic-panel': () => { if (S.micPanel) return; openMicPanel(); },
  'mic-off': () => { Rec.release(); toast('마이크를 껐어요.'); },
  'mic-close': () => closeMicPanel(false),
  'mic-off-close': () => { closeMicPanel(true); toast('마이크를 껐어요.'); },
  'mic-try': () => micTry('play'),
  'mic-stt': () => micTry('stt'),
  'mask-toggle': () => Mask.toggle(Player.pid || S.pid),
  'mask-style': () => { const pid = Player.pid || S.pid; Mask.set(pid, { style: Mask.get(pid).style === 'blur' ? 'solid' : 'blur' }); },
  'mask-detect': () => Mask.detect(Player.pid || S.pid),
  'recs-delete': async () => {
    const r = S.recs;
    if (!r || !r.count) return;
    if (!confirm(`저장된 내 녹음 ${r.count}개(${mb(r.bytes)})를 지울까요? 지운 녹음은 되돌릴 수 없어요. 점수와 학습 기록은 그대로 남아요.`)) return;
    try {
      S.recs = await api('/api/recordings/delete', { body: {} });
      Object.values(S.speak).forEach(x => { if (x) x.rec = null; });
      toast(`녹음 ${S.recs.deleted}개를 지웠어요.`);
    } catch (e) { errToast(e); }
    if (S.view === 'settings') renderSettings();
  },
  'self-check': () => selfCheck(),
};

function onClick(e) {
  const nav = e.target.closest('.nav[data-view]');
  if (nav) { show(nav.dataset.view); return; }
  const seg = e.target.closest('.seg[data-seg] button');
  if (seg) { onSeg(seg.closest('.seg').dataset.seg, seg.dataset.val); return; }
  const li = e.target.closest('#script li[data-id]');
  if (li) { selectLine(Number(li.dataset.id), { play: true, scroll: false }); return; }
  const a = e.target.closest('[data-act]');
  if (a && ACT[a.dataset.act]) { e.preventDefault(); ACT[a.dataset.act](a, e); }
}

function onSeg(name, val) {
  if (name === 'loops') { S.loops = Number(val); store.set('loops', S.loops); renderTransport(); }
  else if (name === 'speed') { S.speed = Number(val); store.set('speed', S.speed); if (Player.v) Player.v.playbackRate = S.speed; renderTransport(); }
  else if (name === 'sub') { S.sub = val; store.set('sub', S.sub); renderTransport(); renderStrip(); renderScript(false); }
  else if (name === 'depth') { saveSettings({ analysis_depth: val }).then(() => { if (S.view === 'home') renderHome(); }); }
  else if (name === 'whisper') { const sel = S.srcSel[S.pid]; sel.model = val; $('#srcBox').innerHTML = sourcesHTML(cur(), S.sources[S.pid], sel); }
  else if (name === 'tlevel') { S.talkSel.level = val; keepTalkFields(); renderTalkSetup(); }
  else if (name === 'tn') { S.talkSel.n = Number(val); keepTalkFields(); renderTalkSetup(); }
  else if (name === 'ttsEngine') { saveSettings({ tts_engine: val }).then(renderSettings); }
  else if (name === 'micKeep') {
    saveSettings({ mic_keep: val === '1' }).then(() => { Rec._touch(); if (S.micPanel) renderMicPanel(); if (S.view === 'settings') renderSettings(); });
  }
}

function keepTalkFields() {
  const prof = S.st.settings.profile = S.st.settings.profile || {};
  if ($('#pJob')) prof.job = $('#pJob').value;
  if ($('#pCompany')) prof.company = $('#pCompany').value;
  if ($('#pBg')) prof.background = $('#pBg').value;
  if ($('#tCustom')) S.talkSel.custom = $('#tCustom').value;
  if ($('#tProject')) S.talkSel.project = $('#tProject').value;
}

function onChange(e) {
  const t = e.target;
  if (t.name === 'src-en' || t.name === 'src-ko') {
    const sel = S.srcSel[S.pid];
    sel[t.name === 'src-en' ? 'en' : 'ko'] = t.value;
    $('#srcBox').innerHTML = sourcesHTML(cur(), S.sources[S.pid], sel);
  } else if (t.name === 'scen') { keepTalkFields(); S.talkSel.scenario = t.value; renderTalkSetup(); }
  else if (t.id === 'hideQ') { S.talkHideQ = t.checked; store.set('hideQ', S.talkHideQ); renderSession(); }
  else if (t.id === 'talkAuto') { S.talkAuto = t.checked; store.set('talkAuto', S.talkAuto); }
  else if (t.id === 'modelSel') saveSettings({ model: t.value }).then(checkOllama);
  else if (t.id === 'delTrash' && S.del) {
    S.del.trash = t.checked;
    const b = $('#delModal [data-act="del-confirm"]'); if (b) b.innerHTML = delButtonText();
  }
  else if (t.id === 'micDevice') {
    store.set('mic.device', t.value);
    const wasOn = Rec.isOn();
    Rec.release();
    if (wasOn || S.micPanel) Rec.warm().then(() => { listMics(); if (S.micPanel) renderMicPanel(); }).catch(e => { S.micErr = e.message; renderMicPanel(); });
  }
  else if (t.name === 'sttModel') saveSettings({ stt_model: t.value }).then(() => { S.st.stt.model = t.value; renderSettings(); });
  else if (t.id === 'voiceSel') saveSettings({ tts_voice: t.value });
  else if (t.id === 'voiceKSel') saveSettings({ tts_voice_k: t.value }).then(() => TTS.speak('Nice to meet you. Let me tell you a little about myself.'));
  else if (t.id === 'ttsRate') saveSettings({ tts_rate: Number(t.value) });
  else if (t.id === 'allowOnline') saveSettings({ allow_online_voices: t.checked }).then(renderSettings);
}

function onInput(e) {
  const t = e.target;
  if (t.id === 'scriptSearch') { S.search = t.value; renderScript(false); }
  else if (t.id === 'dictInput') { const w = $('#imeWarn'); if (w) w.hidden = !HANGUL.test(t.value); if (S.cur) S.dict[S.cur.id] = { ...(S.dict[S.cur.id] || {}), typed: t.value }; }
  else if (t.id === 'answerText') S.talkDraft = t.value;
  else if (t.id === 'ttsRate') { const v = $('#ttsRateVal'); if (v) v.textContent = Number(t.value).toFixed(2); if (S.st) S.st.settings.tts_rate = Number(t.value); }
}

function onKey(e) {
  const t = e.target;
  if (S.micPanel || S.del) {
    const box = S.del ? '#delModal' : '#micModal';
    if (e.key === 'Escape') { e.preventDefault(); if (S.del) closeDelModal(); else closeMicPanel(false); return; }
    if (e.key === 'Tab') {   // keep the focus inside the window
      const f = $$(`${box} button:not([disabled]), ${box} select, ${box} input:not([disabled])`);
      if (f.length) {
        const i = f.indexOf(document.activeElement);
        if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus(); }
      }
    }
    return;
  }
  if (t.classList && t.classList.contains('burn-mask') && maskKey(e)) return;
  const typing = t.tagName === 'TEXTAREA' || t.tagName === 'INPUT' || t.tagName === 'SELECT' || t.isContentEditable;
  if (S.view === 'study') {
    if (t.id === 'dictInput') {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); dictCheck(); }
      else if (e.key === 'Tab') { e.preventDefault(); playCur(e.shiftKey ? 0.75 : null); }
      return;
    }
    if (typing) return;
    if (e.key === ' ') { e.preventDefault(); togglePlay(); }
    else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); stepLine(1); }
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); stepLine(-1); }
    else if ((e.key === 'r' || e.key === 'R' || e.key === 'ㄱ') && !e.ctrlKey && !e.metaKey) { e.preventDefault(); if (S.tab !== 'speak') { S.tab = 'speak'; store.set('tab', 'speak'); renderPractice(); } shadow(false); }
    else if (e.key === 'Enter' && S.tab === 'dict') { const i = $('#dictInput'); if (i) { e.preventDefault(); i.focus(); } }
    return;
  }
  if (S.view === 'talk' && S.talk && !S.talkSetup) {
    if (t.id === 'answerText' && e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); talkSend(); return; }
    if (!typing && e.key === ' ') { e.preventDefault(); talkRecord(); }
    return;
  }
  if (S.view === 'review' && !typing && S.review) {
    if (e.key === ' ') { e.preventDefault(); revPlay(); }
    else if (e.key === 'Enter' && !S.revShow) { e.preventDefault(); S.revShow = true; renderReview(); }
    else if (S.revShow && ['1', '2', '3'].includes(e.key)) revGrade({ 1: 'again', 2: 'hard', 3: 'good' }[e.key]);
  }
}

boot();
