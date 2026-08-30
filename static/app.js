/* 火花云续 · Douyin Cloud Streak — 液态玻璃前端逻辑
   零依赖(无 Vue/Element),直接对接 FastAPI 后端。
   页面对齐原版:概览 / 账号 / 好友 / 定时 / 凭证 / 日志 */
"use strict";

/* ---------------- 图标(内联 SVG,统一描边风格) ---------------- */
var ICONS = {
  grid: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
  users: '<svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3.4"/><path d="M3.5 20c.6-3.4 2.8-5 5.5-5s4.9 1.6 5.5 5"/><circle cx="17" cy="9" r="2.6"/><path d="M15.6 14.4c2.6.3 4.3 1.7 4.9 4.1"/></svg>',
  clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.6"/><path d="M12 7.4V12l3 2.4"/></svg>',
  key: '<svg viewBox="0 0 24 24"><circle cx="8" cy="15.5" r="4"/><path d="M10.8 12.7 20 3.5M14.5 7.2l2.6 2.6M18.5 3.2l2.2 2.2"/></svg>',
  terminal: '<svg viewBox="0 0 24 24"><path d="M4 6.5 9 11.5 4 16.5M12 17h8"/></svg>',
  flame: '<svg viewBox="0 0 24 24"><path d="M12 2.5c.8 2.4-.6 4-1.8 5.4C8.9 9 8 10.1 8 11.9 8 14.2 9.8 15.8 12 15.8s4-1.6 4-3.9c0-2-1-3.4-2.2-4.6.3 1.4.1 2.7-.7 3.8-.4-1.5-1-3-2.5-4.3C11.4 5.6 12 4.2 12 2.5z"/><path d="M7.4 13.2c-.9.9-1.5 2-1.5 3.2 0 2.8 2.4 4.8 5.3 4.8h.9a5.4 5.4 0 0 0 5.3-5.4c0-1.6-.7-3-1.8-4" fill="none" stroke-width="1.5" stroke-linecap="round"/></svg>',
  refresh: '<svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/></svg>',
  zap: '<svg viewBox="0 0 24 24"><path d="M13 2 4.5 13.5H11L9.5 22 19 10.5h-6.5L13 2z"/></svg>',
  send: '<svg viewBox="0 0 24 24"><path d="M21 3 10.8 13.2M21 3l-7 18-3.2-7.8L3 10l18-7z"/></svg>',
  plus: '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13M10 11v5M14 11v5"/></svg>',
  edit: '<svg viewBox="0 0 24 24"><path d="M4 20h4L20 8l-4-4L4 16v4zM13.5 6.5l4 4"/></svg>',
  search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg>',
  upload: '<svg viewBox="0 0 24 24"><path d="M12 15V4M7.5 8.5 12 4l4.5 4.5M4 15v4.5h16V15"/></svg>',
  qr: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14h1M14 20h1M18 18h3v3h-3z"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="M4 12.5 9.5 18 20 6.5"/></svg>',
  list: '<svg viewBox="0 0 24 24"><path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/></svg>',
  person: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="8" r="4"/><path d="M4.5 20c.7-4 3.6-6 7.5-6s6.8 2 7.5 6" stroke-linecap="round"/></svg>',
  gear: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2.6v2.6M12 18.8v2.6M2.6 12h2.6M18.8 12h2.6M5.3 5.3l1.9 1.9M16.8 16.8l1.9 1.9M18.7 5.3l-1.9 1.9M7.2 16.8l-1.9 1.9"/></svg>'
};

/* ---------------- 状态 ---------------- */
var state = {
  token: '', accountId: null, accounts: [], maxConcurrent: 5, slots: 5, running: false,
  page: 'overview', contacts: [], entries: [], config: null, status: null,
  loginTimer: null, pageTimers: []
};

var PAGES = [
  { id: 'overview', label: '概览', icon: 'grid' },
  { id: 'accounts', label: '账号', icon: 'users' },
  { id: 'friends', label: '好友', icon: 'list' },
  { id: 'settings', label: '定时', icon: 'clock' },
  { id: 'credentials', label: '凭证', icon: 'key' },
  { id: 'logs', label: '日志', icon: 'terminal' },
  { id: 'config', label: '设置', icon: 'gear' }
];

/* ---------------- 基础工具 ---------------- */
function $(sel) { return document.querySelector(sel); }
function el(tag, cls, html) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}
function fmtTime(iso) {
  if (!iso) return '—';
  var d = new Date(iso);
  if (isNaN(d)) return String(iso);
  function p(n) { return String(n).padStart(2, '0'); }
  return p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}
function fmtNext(iso) {
  if (!iso) return '未安排';
  var d = new Date(iso);
  if (isNaN(d)) return String(iso);
  function p(n) { return String(n).padStart(2, '0'); }
  var today = new Date(); today.setHours(0, 0, 0, 0);
  var day = new Date(d); day.setHours(0, 0, 0, 0);
  var diff = Math.round((day - today) / 86400000);
  var hm = p(d.getHours()) + ':' + p(d.getMinutes());
  if (diff === 0) return '今天 ' + hm;
  if (diff === 1) return '明天 ' + hm;
  return p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + hm;
}
/* ---------------- 主题切换(暗色/亮色/跟随系统) ---------------- */
var THEME_ICONS = {
  dark: '<svg viewBox="0 0 24 24"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z"/></svg>',
  light: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M19.1 4.9l-1.6 1.6M6.5 17.5l-1.6 1.6"/></svg>',
  system: '<svg viewBox="0 0 24 24"><rect x="2.5" y="4" width="19" height="13" rx="2"/><path d="M8.5 21h7M12 17v4"/></svg>'
};
function currentTheme() { return localStorage.getItem('sc_theme') || 'dark'; }
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  var btn = document.getElementById('themeBtn');
  if (btn) {
    btn.innerHTML = THEME_ICONS[t] || THEME_ICONS.dark;
    btn.title = '主题:' + (t === 'dark' ? '暗色' : (t === 'light' ? '亮色' : '跟随系统')) + '(点击切换)';
  }
}
/* ---- 自定义主题颜色(强调色,仅当前浏览器生效) ---- */
var ACCENT_PRESETS = [
  { id: 'sunset', name: '落日橙', a1: '#ffb35c', a2: '#ff7a3d' },
  { id: 'sakura', name: '樱花粉', a1: '#ff9ad5', a2: '#ff5c8a' },
  { id: 'mint',   name: '薄荷青', a1: '#8ff0d4', a2: '#2fbf9b' },
  { id: 'ocean',  name: '海盐蓝', a1: '#7cc7ff', a2: '#3d8bff' },
  { id: 'grape',  name: '葡萄紫', a1: '#c9a4ff', a2: '#8b5cf6' },
  { id: 'gold',   name: '鎏金',   a1: '#ffe08a', a2: '#f0b429' }
];
function hexRgb(h) {
  h = String(h || '').replace('#', '');
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  var n = parseInt(h, 16);
  if (isNaN(n) || h.length !== 6) return null;
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function rgbHex(r, g, b) {
  var c = function (v) { v = Math.max(0, Math.min(255, Math.round(v))); return ('0' + v.toString(16)).slice(-2); };
  return '#' + c(r) + c(g) + c(b);
}
function shiftHue(hex, deg) { /* RGB→HSL→旋转→RGB,用于派生第三色 */
  var v = hexRgb(hex); if (!v) return hex;
  var r = v[0] / 255, g = v[1] / 255, b = v[2] / 255;
  var mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn, h = 0, s = 0, l = (mx + mn) / 2;
  if (d) {
    s = l > .5 ? d / (2 - mx - mn) : d / (mx + mn);
    if (mx === r) h = (g - b) / d + (g < b ? 6 : 0);
    else if (mx === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
  }
  h = (h + deg + 360) % 360;
  var q = l < .5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
  var f = function (t) {
    if (t < 0) t += 1; if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  return rgbHex(f(h / 360 + 1 / 3) * 255, f(h / 360) * 255, f(h / 360 - 1 / 3) * 255);
}
function deriveAccents(a1, a2) {
  var a3 = shiftHue(a2, -30);
  var t = function (hex, al) { var v = hexRgb(hex); return v ? 'rgba(' + v[0] + ',' + v[1] + ',' + v[2] + ',' + al + ')' : hex; };
  return {
    a3: a3,
    grad: 'linear-gradient(135deg,' + a1 + ' 0%,' + a2 + ' 48%,' + a3 + ' 100%)',
    tint1_16: t(a1, .16), tint1_35: t(a1, .35),
    tint2_10: t(a2, .10), tint2_16: t(a2, .16), tint2_62: t(a2, .62),
    tint3_12: t(a3, .12), tint3_50: t(a3, .50)
  };
}
function currentAccent() {
  try { return JSON.parse(localStorage.getItem('sc_accent') || 'null'); } catch (e) { return null; }
}
function applyAccent(a1, a2, save) {
  var st = document.documentElement.style;
  if (!a1 || !a2 || !hexRgb(a1) || !hexRgb(a2)) {
    ['--accent-1', '--accent-2', '--accent-3', '--grad',
     '--tint1-16', '--tint1-35', '--tint2-10', '--tint2-16', '--tint2-62', '--tint3-12', '--tint3-50'
    ].forEach(function (k) { st.removeProperty(k); });
    if (save) { localStorage.removeItem('sc_accent'); }
    return;
  }
  var d = deriveAccents(a1, a2);
  st.setProperty('--accent-1', a1);
  st.setProperty('--accent-2', a2);
  st.setProperty('--accent-3', d.a3);
  st.setProperty('--grad', d.grad);
  st.setProperty('--tint1-16', d.tint1_16); st.setProperty('--tint1-35', d.tint1_35);
  st.setProperty('--tint2-10', d.tint2_10); st.setProperty('--tint2-16', d.tint2_16); st.setProperty('--tint2-62', d.tint2_62);
  st.setProperty('--tint3-12', d.tint3_12); st.setProperty('--tint3-50', d.tint3_50);
  if (save) { try { localStorage.setItem('sc_accent', JSON.stringify({ a1: a1, a2: a2 })); } catch (e) {} }
}
function markSwatch() {
  var box = document.getElementById('cfgSwatches');
  if (!box) return;
  var acc = currentAccent();
  var preset = ACCENT_PRESETS[0];
  if (acc) {
    for (var i = 0; i < ACCENT_PRESETS.length; i++) {
      if (ACCENT_PRESETS[i].a1.toLowerCase() === String(acc.a1).toLowerCase() &&
          ACCENT_PRESETS[i].a2.toLowerCase() === String(acc.a2).toLowerCase()) { preset = ACCENT_PRESETS[i]; break; }
    }
    if (preset.a1.toLowerCase() !== String(acc.a1).toLowerCase()) preset = null; /* 自定义色,无预设命中 */
    else if (ACCENT_PRESETS.indexOf(preset) === -1) preset = null;
  }
  var bs = box.querySelectorAll('.swatch');
  for (var j = 0; j < bs.length; j++) {
    var on = preset && bs[j].dataset.id === preset.id;
    bs[j].classList.toggle('sw-on', !!on);
  }
}
var _retryTimer = null;
var _retrying = false;
function showConnBanner(show) {
  var b = document.getElementById('connBanner');
  if (b) b.style.display = show ? 'block' : 'none';
}
/* 页面加载失败时自动重试(服务启动稍慢的场景) */
function schedulePageRetry() {
  if (_retrying) return;
  _retrying = true;
  _retryTimer = setTimeout(function () {
    _retrying = false;
    renderPage();
  }, 3000);
}

function toast(msg, type, ms) {
  type = type || 'info'; ms = ms || 3200;
  var box = $('#toasts');
  var t = el('div', 'toast ' + type, esc(msg));
  box.appendChild(t);
  setTimeout(function () { t.style.opacity = '0'; t.style.transform = 'translateX(16px)'; t.style.transition = 'all .3s'; }, ms);
  setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, ms + 320);
}

/* ---------------- API ---------------- */
function token() {
  if (state.token) return state.token;
  var injected = (typeof window !== 'undefined' && window.__SERVER_AUTH_TOKEN__) ? window.__SERVER_AUTH_TOKEN__ : '';
  var stored = localStorage.getItem('dcs_auth_token') || '';
  state.token = injected || stored;
  return state.token;
}
function setToken(t) { state.token = t; localStorage.setItem('dcs_auth_token', t); }
function sessionToken() { return localStorage.getItem('spark_session') || ''; }
function setSession(t) { if (t) localStorage.setItem('spark_session', t); else localStorage.removeItem('spark_session'); }
function api(method, path, body, opts) {
  opts = opts || {};
  var headers = {};
  var tk = token();
  if (tk) headers['x-token'] = tk;
  var ss = sessionToken();
  if (ss) headers['x-session'] = ss;
  var qi = path.indexOf('?');
  var pathBase = qi >= 0 ? path.slice(0, qi) : path;
  var q = new URLSearchParams(qi >= 0 ? path.slice(qi + 1) : '');
  if (state.accountId && !opts.noAccount) q.set('account_id', state.accountId);
  var url = '/api' + pathBase + (q.toString() ? '?' + q.toString() : '');
  var init = { method: method, headers: headers };
  if (body instanceof FormData) { init.body = body; }
  else if (body !== undefined) { headers['content-type'] = 'application/json'; init.body = JSON.stringify(body); }
  return fetch(url, init).then(function (res) {
    if (res.status === 401) {
      return res.json().catch(function () { return null; }).then(function (d2) {
        if (d2 && d2.detail === '请先登录') { showLogin(); }
        else { openTokenModal(); }
        throw new Error((d2 && d2.detail) || '访问令牌不正确');
      });
    }
    return res.json().catch(function () { return null; }).then(function (data) {
      if (!res.ok) {
        var msg = (data && (data.detail || data.message)) || ('请求失败 (' + res.status + ')');
        throw new Error(msg);
      }
      showConnBanner(false);
      return data;
    });
  }).catch(function (e) {
    showConnBanner(true);
    throw new Error('无法连接服务器,请确认服务已启动(见页面顶部提示)');
  });
}
function get(p, o) { return api('GET', p, undefined, o); }
function post(p, b, o) { return api('POST', p, (b === undefined ? {} : b), o); }
function put(p, b, o) { return api('PUT', p, (b === undefined ? {} : b), o); }
function patch(p, b, o) { return api('PATCH', p, (b === undefined ? {} : b), o); }
function del(p, o) { return api('DELETE', p, undefined, o); }
/* 当前账号资源路径前缀 */
function accPath(p) { return '/accounts/' + encodeURIComponent(state.accountId || 'default') + p; }

/* ---------------- 模态框 ---------------- */
function openModal(title, sub, bodyHtml, actionsHtml) {
  $('#modalBody').innerHTML = '<h3>' + esc(title) + '</h3>' +
    (sub ? '<div class="m-sub">' + sub + '</div>' : '') +
    bodyHtml +
    (actionsHtml ? '<div class="m-actions">' + actionsHtml + '</div>' : '');
  $('#modalMask').classList.add('show');
}
function closeModal() { $('#modalMask').classList.remove('show'); }
function bindClose() {
  $('#modalClose').onclick = closeModal;
  $('#modalMask').addEventListener('click', function (e) { if (e.target.id === 'modalMask') closeModal(); });
  var arr = document.querySelectorAll('[data-close]');
  for (var i = 0; i < arr.length; i++) arr[i].onclick = closeModal;
}
function confirmDlg(title, text, onOk, okLabel) {
  openModal(title, '', '<div style="font-size:13.5px;color:var(--text-2);line-height:1.7">' + text + '</div>',
    '<button class="btn btn-ghost" data-close>取消</button><button class="btn btn-danger" id="cfOk">' + (okLabel || '确定') + '</button>');
  bindClose();
  $('#cfOk').onclick = function () { closeModal(); onOk(); };
}
/* ---------------- 自定义背景 ---------------- */
function applyBg(url) {
  document.body.style.backgroundImage = 'url(' + url + ')';
  document.body.style.backgroundSize = 'cover';
  document.body.style.backgroundPosition = 'center';
  document.body.style.backgroundAttachment = 'fixed';
  document.body.classList.add('has-bg');
}
function clearBg() {
  document.body.style.backgroundImage = '';
  document.body.style.backgroundSize = '';
  document.body.style.backgroundPosition = '';
  document.body.style.backgroundAttachment = '';
  document.body.classList.remove('has-bg');
}
function loadBg() {
  get('/settings/bg', { noAccount: true }).then(function (info) {
    if (info && info.exists && info.url) applyBg(info.url);
  }).catch(function () {});
}
/* ---------------- 导航 / 顶栏 ---------------- */
function renderNav() {
  var nav = $('#nav');
  var first = nav.childNodes.length === 0;
  nav.classList.remove('enter');
  nav.innerHTML = '';
  for (var i = 0; i < PAGES.length; i++) {
    var p = PAGES[i];
    var a = el('a', 'nav-item' + (state.page === p.id ? ' active' : ''));
    a.href = '#/' + p.id;
    a.innerHTML = ICONS[p.icon] + '<span class="t">' + p.label + '</span>';
    if (p.id === 'friends') a.innerHTML += '<span class="badge" id="navSparkBadge" style="display:none"></span>';
    nav.appendChild(a);
  }
  if (first) nav.classList.add('enter');
}
/* 手机端:左侧抽屉导航(汉堡键开,遮罩/选中页面后收) */
(function () {
  var t = $('#navToggle'), m = $('#navMask');
  if (t) t.addEventListener('click', function () { document.body.classList.toggle('nav-open'); });
  if (m) m.addEventListener('click', function () { document.body.classList.remove('nav-open'); });
})();
function pageMeta(page) {
  for (var i = 0; i < PAGES.length; i++) if (PAGES[i].id === page) return PAGES[i];
  return PAGES[0];
}
function pageSubText(page) {
  if (page === 'overview') return '当前账号运行状态与快捷操作';
  if (page === 'accounts') return '多账号独立数据、独立定时、互不干扰';
  if (page === 'friends') return '同步联系人 · 一键勾选火花好友 · 发送目标管理';
  if (page === 'settings') return '每日发送时间 · 随机浮动 · 文案池';
  if (page === 'credentials') return '登录态上传 / 网页扫码登录';
  if (page === 'logs') return '实时运行日志与台账健康度';
  if (page === 'config') return '主题 · 令牌 · 端口 · 背景 · 账号';
  return '';
}
function route() {
  var h = (location.hash || '#/overview').replace(/^#\//, '');
  var page = pageMeta(h).id;
  state.page = page;
  document.body.classList.remove('nav-open');  /* 手机端:切换页面后收起抽屉 */
  document.title = pageMeta(page).label + ' · 火花云续';
  $('#pageTitle').textContent = pageMeta(page).label;
  $('#pageSub').textContent = pageSubText(page);
  renderNav();
  stopTimers();
  var pg = $('#page');
  pg.classList.remove('poll');
  pg.classList.remove('page-enter');
  renderPage();
  void pg.offsetWidth;
  pg.classList.add('page-enter');
}
var pollers = {};
function stopTimers() {
  for (var k in pollers) { clearInterval(pollers[k]); }
  pollers = {};
  if (state.loginTimer) { clearInterval(state.loginTimer); state.loginTimer = null; }
}
function every(name, ms, fn) {
  if (pollers[name]) clearInterval(pollers[name]);
  pollers[name] = setInterval(fn, ms);
}
function dataChanged(key, data) {
  var sig = JSON.stringify(data);
  state._sigs = state._sigs || {};
  if (state._sigs[key] === sig) return false;
  state._sigs[key] = sig;
  return true;
}
function accSig() {
  return JSON.stringify([state.accountId, state.accounts.map(function (a) {
    var o = {}; for (var k in a) if (k !== 'updated_at' && k !== 'created_at') o[k] = a[k];
    return o;
  }), state.slots, state.maxConcurrent]);
}

/* ---------------- 账号 ---------------- */
function loadAccounts(silent) {
  return get('/accounts', { noAccount: true }).then(function (data) {
    var prevSig = accSig();
    state.accounts = data.accounts || [];
    state.maxConcurrent = data.max_concurrent || 5;
    state.slots = data.browser_slots_available != null ? data.browser_slots_available : state.maxConcurrent;
    if (!state.accounts.length) state.accounts = [{ id: 'default', name: '默认账号', is_default: true }];
    var saved = localStorage.getItem('dcs_account');
    if (!state.accountId || !state.accounts.some(function (a) { return a.id === state.accountId; })) {
      var found = saved && state.accounts.some(function (a) { return a.id === saved; });
      state.accountId = found ? saved : state.accounts[0].id;
    }
    state.accountsChanged = accSig() !== prevSig;
    if (state.accountsChanged || !$('#accountSelect').options.length) fillAccountSelect();
    updateTopbarState();
  }).catch(function (e) {
    if (!silent) toast(e.message, 'err');
  });
}
function fillAccountSelect() {
  var sel = $('#accountSelect');
  sel.innerHTML = '';
  for (var i = 0; i < state.accounts.length; i++) {
    var a = state.accounts[i];
    var o = el('option', '', esc(a.name) + (a.is_default ? ' (默认)' : ''));
    o.value = a.id;
    sel.appendChild(o);
  }
  sel.value = state.accountId;
}
function updateTopbarState() {
  var acc = null;
  for (var i = 0; i < state.accounts.length; i++) if (state.accounts[i].id === state.accountId) acc = state.accounts[i];
  var running = acc ? !!acc.running : false;
  state.running = running;
  var dot = $('#runDot'), txt = $('#runPillText');
  dot.className = 'dot ' + (running ? 'warn' : (acc && acc.session_status === 'expired' ? 'err' : 'ok'));
  txt.textContent = running ? '任务运行中' : (acc && acc.session_status === 'expired' ? '登录已失效' : '空闲');
  $('#slotsText').textContent = '并发 ' + state.slots + '/' + state.maxConcurrent;
}

/* ---------------- 页面渲染 ---------------- */
function renderPage() {
  if (state.page === 'overview') renderOverview();
  else if (state.page === 'accounts') renderAccounts();
  else if (state.page === 'friends') renderFriends();
  else if (state.page === 'settings') renderSettings();
  else if (state.page === 'config') renderConfig();
  else if (state.page === 'credentials') renderCredentials();
  else if (state.page === 'logs') renderLogs();
}

/* ================= 概览 ================= */
function statCard(k, v, d, icon) {
  var c = el('div', 'glass stat');
  c.innerHTML = '<div class="k">' + ICONS[icon] + esc(k) + '</div><div class="v">' + v + '</div><div class="d">' + esc(d) + '</div>';
  return c;
}
function renderOverview() {
  var page = $('#page');
  page.innerHTML = '<div class="empty"><div class="spinner"></div><div class="t">加载中…</div></div>';
  Promise.all([get(accPath('/status')), get(accPath('/friends'))]).then(function (res) {
    var status = res[0], ledgerData = res[1];
    state.status = status; state.entries = ledgerData.entries || []; state.contacts = ledgerData.contacts || [];
    var spark = state.contacts.filter(function (c) { return (c.spark_days || 0) > 0; });
    var top = 0;
    state.contacts.forEach(function (c) { top = Math.max(top, c.spark_days || 0); });
    var last = status.last_run || {};
    var okCount = (last.ok || []).length, failCount = (last.failed || []).length;
    var pending = ledgerData.pending_send || [];
    var bDaily = ledgerData.b_channel_daily || {};
    var harvest = ledgerData.harvest_last || null;

    page.innerHTML = '';
    var cards = el('div', 'cards');
    cards.appendChild(statCard('联系人', state.contacts.length, '总联系人 / 同步结果', 'users'));
    cards.appendChild(statCard('已勾选', ledgerData.selected_count || 0, '本次发送目标数', 'check'));
    var sc = statCard('火花好友', spark.length, '🔥 连续聊天 ≥3 天', 'flame'); sc.classList.add('accent'); cards.appendChild(sc);
    cards.appendChild(statCard('最高天数', top + ' <small>天</small>', '当前台账最长的火花', 'zap'));
    page.appendChild(cards);
    appendHistoryBlock(page, 8);

    var grid = el('div');
    grid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px;margin-bottom:22px';
    var statusCard = el('div', 'glass');
    statusCard.style.cssText = 'padding:20px';
    statusCard.innerHTML = '<div class="section-head"><h3>运行状态</h3><span class="spacer"></span>' +
      (status.running ? '<span class="tag warn"><span class="dot warn"></span> 运行中</span>' : '<span class="tag ok"><span class="dot ok"></span> 空闲</span>') + '</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px 18px;font-size:13px">' +
      '<div style="color:var(--text-3)">登录态文件</div><div>' + (status.state_file_exists ? '<span class="tag ok">✓ 已就绪</span>' : '<span class="tag err">✗ 缺失</span>') + ' <span class="mono" style="color:var(--text-3)">' + esc(status.session_status || 'unknown') + '</span></div>' +
      '<div style="color:var(--text-3)">下次自动发送</div><div style="font-weight:600;color:var(--accent-1)">' + fmtNext(status.next_run) + '</div>' +
      '<div style="color:var(--text-3)">上次运行</div><div>' + (status.last_run ? fmtTime(status.last_run.at) + (status.last_run.dry_run ? ' (演练)' : '') : '—') + '</div>' +
      '<div style="color:var(--text-3)">上次结果</div><div>' + (status.last_run ? ('<span style="color:var(--ok)">成功 ' + okCount + '</span>' + (failCount ? ' / <span style="color:var(--err)">失败 ' + failCount + '</span>' : '')) : '—') + '</div>' +
      '<div style="color:var(--text-3)">B 通道今日</div><div>' + (bDaily.date ? (bDaily.count + ' 条 (首条消息)') : '—') + '</div>' +
      '<div style="color:var(--text-3)">Creator 采集</div><div>' + (harvest ? ('上次 ' + fmtTime(harvest.at) + ' · ' + (harvest.count || 0) + ' 条' + (harvest.merge ? ' · join ' + (harvest.merge.joined || 0) : '')) : '未执行') + '</div>' +
      '</div>' +
      '<div class="runline">' +
      '<button class="btn btn-primary btn-sm" id="runReal"' + (status.running ? ' disabled' : '') + '>' + ICONS.zap + '立即续火花</button>' +
      '<button class="btn btn-sm" id="runDry"' + (status.running ? ' disabled' : '') + '>演练模式</button>' +
      '<button class="btn btn-sm" id="btnSync">' + ICONS.refresh + '同步联系人</button>' +
      '<button class="btn btn-sm" id="btnHarvest">' + ICONS.qr + 'Creator 采集</button>' +
      '</div>';
    grid.appendChild(statusCard);

    var pendingCard = el('div', 'glass');
    pendingCard.style.cssText = 'padding:20px';
    pendingCard.innerHTML = '<div class="section-head"><h3>本次预计发送</h3><span class="spacer"></span><span class="sub">' + pending.length + ' 人</span></div>';
    if (pending.length) {
      var ul = el('div');
      ul.style.cssText = 'display:flex;flex-direction:column;gap:8px;max-height:220px;overflow:auto';
      for (var i = 0; i < Math.min(pending.length, 40); i++) {
        var p = pending[i];
        ul.appendChild(el('div', '', '<span style="display:inline-flex;align-items:center;gap:8px">' +
          '<span class="streak-badge' + (p.send_channel === 'consumer' ? '' : ' off') + '">' + (p.send_channel === 'consumer' ? 'A·会话' : 'B·首条') + '</span>' +
          '<span style="font-size:13px">' + esc(p.display_name) + '</span></span>'));
      }
      pendingCard.appendChild(ul);
    } else {
      pendingCard.appendChild(el('div', 'empty', '<div class="t">暂无待发送目标</div>请在「好友」页勾选好友'));
    }
    grid.appendChild(pendingCard);
    page.appendChild(grid);

    get(accPath('/logs?n=50')).then(function (logsRes) {
      var logCard = el('div', 'glass');
      logCard.style.cssText = 'padding:20px';
      logCard.innerHTML = '<div class="section-head"><h3>最近日志</h3><span class="spacer"></span><a class="btn btn-ghost btn-sm" href="#/logs">全部日志 →</a></div>';
      var lp = el('div', 'log-panel');
      lp.style.maxHeight = '200px';
      lp.innerHTML = renderLogLines((logsRes.logs || '').split('\n').slice(-50));
      logCard.appendChild(lp);
      page.appendChild(logCard);
    }).catch(function () {});

    $('#runReal').onclick = function () { runNow(false); };
    $('#runDry').onclick = function () { runNow(true); };
    $('#btnSync').onclick = syncContacts;
    $('#btnHarvest').onclick = harvestCreator;
    every('overview', 8000, function () {
      loadAccounts(true).then(function () {
        if (!state.accountsChanged) return;
        $('#page').classList.add('poll');
        renderOverview();
      }).catch(function () {});
    });
  }).catch(function (e) {
    page.innerHTML = '<div class="empty"><div class="t">加载失败</div>' + esc(e.message) + '</div>';
    schedulePageRetry();
  });
}

/* ================= 账号 ================= */
function renderAccounts() {
  var page = $('#page');
  page.innerHTML = '<div class="empty"><div class="spinner"></div><div class="t">加载中…</div></div>';
  loadAccounts(true).then(function () {
    page.innerHTML = '';
    var head = el('div', 'section-head');
    head.innerHTML = '<h3>全部账号</h3><span class="sub">每个账号独立目录 · 独立定时 · 互不干扰</span><span class="spacer"></span>' +
      '<span class="pill">浏览器并发 ' + state.slots + '/' + state.maxConcurrent + '</span>' +
      '<button class="btn btn-primary btn-sm" id="btnNewAcc">' + ICONS.plus + '新建账号</button>';
    page.appendChild(head);

    var wrap = el('div');
    wrap.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px';
    for (var i = 0; i < state.accounts.length; i++) {
      var a = state.accounts[i];
      var card = el('div', 'glass');
      card.style.cssText = 'padding:18px 20px;display:flex;flex-direction:column;gap:10px';
      var dot = a.session_status === 'expired' ? 'err' : (a.running ? 'warn' : 'ok');
      var statusTxt = a.running ? '任务运行中' : (a.session_status === 'expired' ? '登录失效' : (a.session_status === 'ok' || a.session_status === 'partial' ? '正常' : '未知'));
      card.innerHTML =
        '<div style="display:flex;align-items:center;gap:10px">' +
        '<div style="flex:1;min-width:0"><div style="font-weight:700;font-size:14.5px;overflow:hidden;text-overflow:ellipsis">' + esc(a.name) + (a.is_default ? ' <span class="tag idle">默认</span>' : '') + '</div>' +
        '<div class="mono" style="color:var(--text-3);font-size:11px">' + esc(a.id) + '</div></div>' +
        '<span class="pill"><span class="dot ' + dot + '"></span>' + statusTxt + '</span></div>' +
        '<div style="display:flex;gap:8px;flex-wrap:wrap;font-size:12px">' +
        (a.state_file_exists ? '<span class="tag ok">登录态 ✓</span>' : '<span class="tag err">无登录态</span>') +
        (a.contacts_fetching ? '<span class="tag warn">同步中</span>' : '') +
        (a.harvesting ? '<span class="tag warn">采集中</span>' : '') + '</div>' +
        '<div style="font-size:12px;color:var(--text-3);display:flex;justify-content:space-between"><span>下次发送</span><span style="color:var(--accent-1);font-weight:600">' + fmtNext(a.next_run) + '</span></div>' +
        '<div style="font-size:12px;color:var(--text-3);display:flex;justify-content:space-between"><span>上次运行</span><span>' + (a.last_run ? fmtTime(a.last_run.at) : '—') + '</span></div>' +
        '<div style="display:flex;align-items:center;gap:10px;border-top:1px solid var(--line);padding-top:12px">' +
        '<label class="switch" title="启用/停用自动续火花"><input type="checkbox" ' + (a.enabled ? 'checked' : '') + ' data-toggle data-id="' + esc(a.id) + '" /><span class="track"></span><span class="switch-label">自动运行</span></label>' +
        '<span class="spacer" style="flex:1"></span>' +
        '<button class="btn btn-ghost btn-sm" data-rename="' + esc(a.id) + '">' + ICONS.edit + '改名</button>' +
        (a.is_default ? '' : '<button class="btn btn-ghost btn-sm btn-danger" data-del="' + esc(a.id) + '">' + ICONS.trash + '删除</button>') +
        '</div>';
      wrap.appendChild(card);
    }
    page.appendChild(wrap);
    if (!state.accounts.length) page.appendChild(el('div', 'empty', '<div class="t">还没有账号</div>点击右上角「新建账号」开始'));

    $('#btnNewAcc').onclick = function () {
      openModal('新建账号', '每个账号拥有独立登录态、好友勾选与定时设置。',
        '<div class="field"><label>账号名称</label><input class="input" id="accName" placeholder="例如:大号 / 小号" /></div>' +
        '<div class="field"><label>备注 / 设备标识 (可选)</label><input class="input" id="accDevice" placeholder="例如:家里电脑 / 云服务器" /></div>',
        '<button class="btn btn-ghost" data-close>取消</button><button class="btn btn-primary" id="accOk">创建</button>');
      bindClose();
      $('#accOk').onclick = function () {
        var name = $('#accName').value.trim(), device = $('#accDevice').value.trim();
        post('/accounts', { name: name, note: device }).then(function (r) {
          toast('账号已创建: ' + r.account.name, 'ok');
          closeModal();
          loadAccounts(true).then(renderAccounts);
        }).catch(function (e) { toast(e.message, 'err'); });
      };
    };
    var toggles = document.querySelectorAll('[data-toggle]');
    for (var t = 0; t < toggles.length; t++) {
      toggles[t].onchange = function () {
        var b = this;
        patch('/accounts/' + b.dataset.id, { enabled: b.checked }).then(function (r) {
          toast((b.checked ? '已启用' : '已停用') + ' ' + r.account.name, 'ok');
          loadAccounts(true).then(renderAccounts);
        }).catch(function (e) { toast(e.message, 'err'); b.checked = !b.checked; });
      };
    }
    var renames = document.querySelectorAll('[data-rename]');
    for (var rn = 0; rn < renames.length; rn++) {
      renames[rn].onclick = function () {
        var id = this.dataset.rename;
        var acc = null;
        for (var k = 0; k < state.accounts.length; k++) if (state.accounts[k].id === id) acc = state.accounts[k];
        openModal('重命名账号', '', '<input class="input" id="rnName" value="' + esc(acc.name) + '" />',
          '<button class="btn btn-ghost" data-close>取消</button><button class="btn btn-primary" id="rnOk">保存</button>');
        bindClose();
        $('#rnOk').onclick = function () {
          patch('/accounts/' + id, { name: $('#rnName').value.trim() }).then(function () {
            toast('已改名', 'ok'); closeModal(); renderAccounts();
          }).catch(function (e) { toast(e.message, 'err'); });
        };
      };
    }
    var dels = document.querySelectorAll('[data-del]');
    for (var d = 0; d < dels.length; d++) {
      dels[d].onclick = function () {
        var id = this.dataset.del;
        var acc = null;
        for (var k = 0; k < state.accounts.length; k++) if (state.accounts[k].id === id) acc = state.accounts[k];
        confirmDlg('删除账号 · ' + acc.name, '将删除该账号的独立数据目录(登录态、好友台账、日志)并归档到 <span class="mono">data/archived/</span>,不影响其他账号。确定删除?', function () {
          del('/accounts/' + id).then(function () {
            toast('账号已删除', 'ok');
            loadAccounts(true).then(renderAccounts);
          }).catch(function (e) { toast(e.message, 'err'); });
        }, '删除');
      };
    }
    every('accounts', 6000, function () { loadAccounts(true).then(function () { if (!state.accountsChanged) return; $('#page').classList.add('poll'); renderAccounts(); }).catch(function () {}); });
  }).catch(function (e) {
    page.innerHTML = '<div class="empty"><div class="t">加载失败</div>' + esc(e.message) + '</div>';
    schedulePageRetry();
  });
}

/* ================= 好友 ================= */
var friendsLoaded = false;
function renderFriends() {
  var page = $('#page');
  if (!friendsLoaded) page.innerHTML = '<div class="empty"><div class="spinner"></div><div class="t">加载中…</div></div>';
  get(accPath('/friends')).then(function (res) {
    var ledgerData = res, contactsRes = res;
    state.contacts = ledgerData.contacts || [];
    state.entries = ledgerData.entries || [];
    friendsLoaded = true;
    var spark = state.contacts.filter(function (c) { return (c.spark_days || 0) > 0; }).length;
    var badge = $('#navSparkBadge');
    if (badge) { badge.style.display = spark ? 'inline-block' : 'none'; badge.textContent = spark; }

    page.innerHTML = '';
    var bar = el('div', 'glass');
    bar.style.cssText = 'padding:16px 20px;margin-bottom:16px;display:flex;gap:10px;flex-wrap:wrap;align-items:center';
    bar.innerHTML =
      '<button class="btn btn-primary btn-sm" id="syncBtn">' + ICONS.refresh + '同步联系人</button>' +
      '<button class="btn btn-sm" id="autoSparkBtn">' + ICONS.flame + '一键勾选火花好友</button>' +
      '<button class="btn btn-sm" id="harvestBtn">' + ICONS.qr + 'Creator 采集</button>' +
      '<span class="spacer" style="flex:1"></span>' +
      '<div style="position:relative">' + ICONS.search.replace('<svg', '<svg style="position:absolute;left:10px;top:50%;transform:translateY(-50%);width:14px;height:14px;stroke:var(--text-3)"') +
      '<input class="input" id="friendSearch" placeholder="搜索昵称 / 天数" style="padding-left:32px;width:180px" /></div>' +
      '<button class="btn btn-primary btn-sm" id="saveSelBtn">' + ICONS.check + '保存勾选</button>';
    page.appendChild(bar);

    var chips = el('div', 'cards');
    chips.style.cssText = 'grid-template-columns:repeat(auto-fit,minmax(140px,1fr));margin-bottom:16px';
    chips.appendChild(statCard('联系人', state.contacts.length, contactsRes.contacts_at ? '同步于 ' + fmtTime(contactsRes.contacts_at) : '尚未同步', 'users'));
    chips.appendChild(statCard('已勾选', ledgerData.selected_count || 0, '发送目标', 'check'));
    chips.appendChild(statCard('火花好友', spark, '🔥 天数 ≥ 3', 'flame'));
    if (ledgerData.b_channel_daily && ledgerData.b_channel_daily.date) chips.appendChild(statCard('B 通道今日', ledgerData.b_channel_daily.count + ' <small>条</small>', '首条消息发送数', 'send'));
    page.appendChild(chips);
    if (contactsRes.contacts_error) {
      var errBox = el('div', 'glass-soft');
      errBox.innerHTML = '<div style="padding:10px 14px;font-size:12px;color:var(--err)">⚠ ' + esc(contactsRes.contacts_error) + '</div>';
      page.appendChild(errBox);
    }

    var kwEl = $('#friendSearch');
    var kw = kwEl ? kwEl.value.trim().toLowerCase() : '';
    var list = state.contacts.slice().sort(function (a, b) { return (b.spark_days || 0) - (a.spark_days || 0); });
    var filtered = kw ? list.filter(function (c) {
      return (c.nickname || c.display_name || '').toLowerCase().indexOf(kw) >= 0 || String(c.spark_days || '').indexOf(kw) >= 0;
    }) : list;
    var tbl = el('div', 'glass table-wrap');
    if (!filtered.length) {
      tbl.innerHTML = '<div class="empty">' + ICONS.users + '<div class="t">暂无联系人</div>点击「同步联系人」拉取抖音聊天列表</div>';
    } else {
      var table = el('table', 'data');
      table.innerHTML = '<thead><tr><th>好友</th><th>火花</th><th>会话</th><th>最后发送</th><th style="text-align:right">勾选</th></tr></thead>';
      var tbody = el('tbody');
      for (var i = 0; i < filtered.length; i++) {
        var c = filtered[i];
        var name = c.display_name || c.nickname || '';
        var sd = c.spark_days || c.streak_days || 0;
        var hasConv = c.last_status !== 'pending' && (c.last_sent_at || c.selected);
        var tr = el('tr');
        var avatarHtml = '<span class="avatar">' + ICONS.person +
          (c.avatar ? '<img src="' + esc(c.avatar) + '" alt="" onerror="this.remove()" />' : '') + '</span>';
        tr.innerHTML =
          '<td><div style="display:flex;align-items:center;gap:11px">' + avatarHtml +
          '<div><div style="font-weight:600">' + esc(name) + '</div>' +
          ((c.nickname && c.nickname !== name) || c.account ? '<div style="font-size:11px;color:var(--text-3)">' + (c.nickname && c.nickname !== name ? esc(c.nickname) : '') + (c.account ? ' @' + esc(c.account) : '') + '</div>' : '') + '</div></div></td>' +
          '<td>' + (sd > 0 ? '<span class="streak-badge">🔥 ' + sd + ' 天</span>' : '<span class="streak-badge off">无</span>') + '</td>' +
          '<td>' + (hasConv ? '<span class="tag ok">有会话</span>' : '<span class="tag idle">待确认</span>') + '</td>' +
          '<td style="color:var(--text-3);font-size:12px">' + (c.last_sent_at ? fmtTime(c.last_sent_at) : '—') + '</td>' +
          '<td style="text-align:right"><div style="display:inline-flex;align-items:center;gap:8px">' +
          '<button class="btn btn-ghost btn-sm" data-ov="' + esc(name) + '" title="好友差异设置">⚙</button>' +
          '<button class="btn btn-ghost btn-sm" data-del="' + esc(name) + '" title="从台账中移除">' + ICONS.trash + '</button>' +
          '<label class="switch"><input type="checkbox" data-sel="' + esc(name) + '"' + (c.selected ? ' checked' : '') + ' /><span class="track"></span></label></div></td>';
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      tbl.appendChild(table);
    }
    page.appendChild(tbl);

    $('#syncBtn').onclick = syncContacts;
    $('#autoSparkBtn').onclick = function () {
      var total = state.contacts.filter(function (c) { return (c.spark_days || 0) > 0; }).length;
      if (!total) { toast('当前没有检测到火花好友,请先同步联系人', 'err'); return; }
      var boxes = document.querySelectorAll('[data-sel]');
      for (var b = 0; b < boxes.length; b++) {
        var c = state.contacts.find(function (x) { return (x.display_name || x.nickname) === boxes[b].dataset.sel; });
        if (c && (c.spark_days || 0) > 0) boxes[b].checked = true;
      }
      toast('已勾选 ' + total + ' 位火花好友,点击「保存勾选」生效', 'ok');
    };
    $('#harvestBtn').onclick = harvestCreator;
    $('#saveSelBtn').onclick = saveSelection;
    var ovBtns = document.querySelectorAll('[data-ov]');
    for (var ov = 0; ov < ovBtns.length; ov++) {
      ovBtns[ov].onclick = function () { openOverrideDlg(this.dataset.ov); };
    }
    var dels = document.querySelectorAll('[data-del]');
    for (var d = 0; d < dels.length; d++) {
      dels[d].onclick = function () {
        var delName = this.dataset.del;
        var self = this;
        confirmDlg('移除好友 · ' + delName,
          '将把该好友<b style="color:var(--text)">从本工具的台账中移除</b>,同步时也不会再出现。' +
          '<br/><span style="color:var(--text-3);font-size:12px">不会取消抖音好友关系,也不影响对方。</span>',
          function () {
            post(accPath('/friends/remove'), { names: [delName] }).then(function (r) {
              if (!r || !r.removed) {
                toast('未找到该好友(可能已被移除),列表已刷新', 'warn', 4000);
              } else {
                toast('已移除:' + delName, 'ok');
              }
              renderFriends();
            }).catch(function (e) { toast(e.message, 'err'); });
          }, '移除');
      };
    }
    var fs = $('#friendSearch');
    if (fs) fs.oninput = function () { renderFriends(); };
    every('friends', 9000, function () {
      get(accPath('/friends')).then(function (r) {
        if (!dataChanged('fr:' + state.accountId, r)) return;
        $('#page').classList.add('poll');
        renderFriends();
      }).catch(function () {});
    });
  }).catch(function (e) {
    if (!friendsLoaded) page.innerHTML = '<div class="empty"><div class="t">加载失败</div>' + esc(e.message) + '</div>';
    schedulePageRetry();
  });
}
function saveSelection() {
  var entries = [];
  var order = 0;
  var boxes = document.querySelectorAll('[data-sel]');
  for (var i = 0; i < boxes.length; i++) {
    var cb = boxes[i];
    var sel = cb.checked;
    if (sel) order++;
    entries.push({ display_name: cb.dataset.sel, selected: sel, selected_order: sel ? order : null });
  }
  put(accPath('/friends'), { entries: entries }).then(function (r) {
    toast('已保存勾选: 更新 ' + (r.updated || 0) + ', 新增 ' + (r.added || 0), 'ok');
    renderFriends();
  }).catch(function (e) { toast(e.message, 'err'); });
}
function syncContacts() {
  post(accPath('/sync')).then(function () {
    toast('正在后台同步联系人…', 'info');
    setTimeout(function () { renderFriends(); }, 1500);
  }).catch(function (e) { toast(e.message, 'err'); });
}
function harvestCreator() {
  post(accPath('/harvest')).then(function () {
    toast('Creator 采集已启动(只读,不发送消息)', 'info');
  }).catch(function (e) { toast(e.message, 'err'); });
}

/* ================= 设置(端口/背景/账号) ================= */
function renderConfig() {
  var page = $('#page');
  page.innerHTML = '<div class="empty"><div class="spinner"></div><div class="t">加载中…</div></div>';
  Promise.all([
    get('/settings/port', { noAccount: true }),
    get('/settings/bg', { noAccount: true }),
    get('/auth/status', { noAccount: true })
  ]).then(function (rs) {
    var portInfo = rs[0], bgInfo = rs[1], authInfo = rs[2];
    page.innerHTML = '';
    var wrap = el('div');
    wrap.style.cssText = 'max-width:820px;display:flex;flex-direction:column;gap:16px';
    // ---- 端口卡片 ----
    var portCard = el('div', 'glass');
    portCard.style.cssText = 'padding:22px 24px';
    var locked = !!portInfo.locked;
    var lockNote = locked
      ? '<div class="hint" style="color:var(--warn);margin-top:6px">' + (portInfo.docker ? 'Docker 部署端口已固定,请修改 compose 的 ports 映射。' : '端口被环境变量 SPARK_PORT 固定,网页修改无效。') + '</div>'
      : '';
    portCard.innerHTML =
      '<h3 style="margin:0 0 4px">🖧 端口设置</h3>' +
      '<div class="hint" style="margin-bottom:12px">修改管理后台的访问端口,保存后需重启服务生效。</div>' +
      '<div class="field"><label>监听端口</label>' +
      '<input class="input" id="cfgPort" type="number" min="1" max="65535" style="max-width:160px" value="' + (portInfo.saved_port || portInfo.port) + '" ' + (locked ? 'disabled' : '') + ' />' +
      (locked ? '<div class="hint" style="color:var(--warn)">当前生效端口:' + portInfo.port + '(已锁定)</div>' : '') +
      lockNote + '</div>' +
      (locked ? '' : '<div style="display:flex;gap:8px;margin-top:4px">' +
        '<button class="btn" id="cfgPortSave">仅保存</button>' +
        '<button class="btn btn-primary" id="cfgPortRestart">保存并重启</button></div>');
    // ---- 背景卡片 ----
    var bgCard = el('div', 'glass');
    bgCard.style.cssText = 'padding:22px 24px';
    var curBg = bgInfo.exists ? bgInfo.url : null;
    bgCard.innerHTML =
      '<h3 style="margin:0 0 4px">🖼 背景设置</h3>' +
      '<div class="hint" style="margin-bottom:12px">上传本地图片作为页面背景,玻璃面板会透出图片(支持 jpg/png/webp/gif,≤12MB)。</div>' +
      '<div style="width:100%;height:120px;border-radius:14px;overflow:hidden;border:1px solid var(--line-strong);margin-bottom:12px;background:#000 ' + (curBg ? 'url(' + esc(curBg) + ') center/cover no-repeat' : '') + '"></div>' +
      '<div style="display:flex;gap:8px">' +
      '<input type="file" id="cfgBgFile" accept="image/*" style="display:none" />' +
      '<button class="btn" id="cfgBgPick">' + ICONS.upload + ' 选择图片</button>' +
      (curBg ? '<button class="btn btn-ghost" id="cfgBgReset">恢复默认</button>' : '') +
      '</div>';
    // ---- 账号卡片 ----
    var acCard = el('div', 'glass');
    acCard.style.cssText = 'padding:22px 24px';
    if (authInfo.enabled) {
      acCard.innerHTML =
        '<h3 style="margin:0 0 4px">🔐 账号系统</h3>' +
        '<div class="hint" style="margin-bottom:12px">登录已开启。当前账号:<b>' + esc(authInfo.username || '') + '</b>(会话 7 天内有效)</div>' +
        '<div class="field"><label>新用户名</label><input class="input" id="cfgUser" placeholder="留空则保持不变" /></div>' +
        '<div class="field"><label>新密码(至少 4 位)</label><input class="input" type="password" id="cfgPass" placeholder="留空则保持不变" /></div>' +
        '<div class="field"><label>确认新密码</label><input class="input" type="password" id="cfgPass2" placeholder="与上方一致" /></div>' +
        '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
        '<button class="btn btn-primary" id="cfgAcSave">保存修改</button>' +
        '<button class="btn btn-ghost" id="cfgAcDisable">关闭登录</button>' +
        '<button class="btn btn-ghost" id="cfgAcLogout">退出登录</button>' +
        '</div>';
    } else {
      acCard.innerHTML =
        '<h3 style="margin:0 0 4px">🔐 账号系统</h3>' +
        '<div class="hint" style="margin-bottom:12px">当前未开启登录。设置管理员账号密码后,打开网页需要先登录。</div>' +
        '<div class="field"><label>用户名</label><input class="input" id="cfgUser" placeholder="例如 admin" /></div>' +
        '<div class="field"><label>密码(至少 4 位)</label><input class="input" type="password" id="cfgPass" /></div>' +
        '<div class="field"><label>确认密码</label><input class="input" type="password" id="cfgPass2" /></div>' +
        '<button class="btn btn-primary" id="cfgAcEnable">开启登录</button>';
    }
    // ---- 主题外观卡片(原顶栏「主题」按钮归档至此) ----
    var curTheme = currentTheme();
    var _cs = getComputedStyle(document.documentElement);
    var curA1 = (_cs.getPropertyValue('--accent-1') || '#ffb35c').trim();
    var curA2 = (_cs.getPropertyValue('--accent-2') || '#ff7a3d').trim();
    var themeCard = el('div', 'glass');
    themeCard.style.cssText = 'padding:22px 24px';
    themeCard.innerHTML =
      '<h3 style="margin:0 0 4px">🎨 主题外观</h3>' +
      '<div class="hint" style="margin-bottom:12px">暗色 / 亮色 / 跟随系统,仅对当前浏览器生效。</div>' +
      '<div class="seg" id="cfgThemeSeg">' +
      '<button class="btn seg-btn' + (curTheme === 'dark' ? ' seg-on' : '') + '" data-theme="dark">' + THEME_ICONS.dark + '<span>暗色</span></button>' +
      '<button class="btn seg-btn' + (curTheme === 'light' ? ' seg-on' : '') + '" data-theme="light">' + THEME_ICONS.light + '<span>亮色</span></button>' +
      '<button class="btn seg-btn' + (curTheme === 'system' ? ' seg-on' : '') + '" data-theme="system">' + THEME_ICONS.system + '<span>跟随系统</span></button>' +
      '</div>' +
      '<div class="field" style="margin-top:14px"><label>主题颜色</label>' +
      '<div class="swatches" id="cfgSwatches">' +
      ACCENT_PRESETS.map(function (p) {
        return '<button type="button" class="swatch" data-id="' + p.id + '" data-a1="' + p.a1 + '" data-a2="' + p.a2 + '" title="' + p.name + '" style="background:linear-gradient(135deg,' + p.a1 + ',' + p.a2 + ')" aria-label="' + p.name + '"></button>';
      }).join('') +
      '</div>' +
      '<div class="accent-row"><span class="hint" style="margin:0">自定义</span>' +
      '<input type="color" id="cfgA1" value="' + curA1 + '" title="主色(浅)">' +
      '<input type="color" id="cfgA2" value="' + curA2 + '" title="副色(深)">' +
      '<button type="button" class="btn btn-sm" id="cfgAccentReset">恢复默认</button>' +
      '</div></div>';
    // ---- 访问令牌卡片(原顶栏「令牌」按钮归档至此) ----
    var tokCard = el('div', 'glass');
    tokCard.style.cssText = 'padding:22px 24px';
    tokCard.innerHTML =
      '<h3 style="margin:0 0 4px">🔑 访问令牌</h3>' +
      '<div class="hint" style="margin-bottom:12px">部署时配置的 AUTH_TOKEN(见 .env)。保存在当前浏览器,用于访问接口;留空表示未启用鉴权。</div>' +
      '<div class="field"><label>访问令牌</label>' +
      '<input class="input" id="cfgToken" value="' + esc(token() || '') + '" placeholder="spark_secret_token_change_me" autocomplete="off" /></div>' +
      '<button class="btn btn-primary" id="cfgTokenSave">保存令牌</button>';
    wrap.appendChild(portCard);
    wrap.appendChild(bgCard);
    wrap.appendChild(acCard);
    wrap.appendChild(themeCard);
    wrap.appendChild(tokCard);
    page.appendChild(wrap);

    // ---- 端口事件 ----
    function readCfgPort() {
      var v = parseInt($('#cfgPort').value, 10);
      if (isNaN(v) || v < 1 || v > 65535) { toast('请输入 1~65535 之间的端口', 'err'); return null; }
      return v;
    }
    var ps = $('#cfgPortSave');
    if (ps) ps.onclick = function () {
      var p = readCfgPort(); if (!p) return;
      put('/settings/port', { port: p }, { noAccount: true }).then(function (r) {
        toast('端口已保存为 ' + r.port + ',重启服务后生效', 'ok');
      }).catch(function (e) { toast(e.message, 'err'); });
    };
    var pr = $('#cfgPortRestart');
    if (pr) pr.onclick = function () {
      var p = readCfgPort(); if (!p) return;
      put('/settings/port', { port: p }, { noAccount: true }).then(function (r) {
        toast('已保存,正在重启服务…', 'info', 4000);
        return post('/settings/restart', {}, { noAccount: true }).then(function () {
          var host = location.hostname || '127.0.0.1';
          var url = (location.protocol === 'https:' ? 'http:' : location.protocol) + '//' + host + ':' + r.port + '/#/overview';
          toast('服务重启中,5 秒后自动跳转到新端口 ' + r.port + '…', 'info', 8000);
          setTimeout(function () { location.href = url; }, 5000);
        });
      }).catch(function (e) { toast(e.message, 'err'); });
    };
    // ---- 背景事件 ----
    $('#cfgBgPick').onclick = function () { $('#cfgBgFile').click(); };
    $('#cfgBgFile').onchange = function (e) {
      var f = e.target.files[0];
      if (!f) return;
      if (f.size > 12 * 1024 * 1024) { toast('图片过大(>12MB)', 'err'); return; }
      var fd = new FormData();
      fd.append('file', f);
      api('POST', '/settings/bg', fd, { noAccount: true }).then(function (r) {
        applyBg(r.url);
        renderConfig();
        toast('背景已更新', 'ok');
      }).catch(function (err) { toast(err.message, 'err'); });
    };
    var br = $('#cfgBgReset');
    if (br) br.onclick = function () {
      del('/settings/bg', { noAccount: true }).then(function () {
        clearBg();
        renderConfig();
        toast('已恢复默认背景', 'ok');
      }).catch(function (e) { toast(e.message, 'err'); });
    };
    // ---- 账号事件 ----
    function readCfgAc() {
      var u = $('#cfgUser').value.trim();
      var p = $('#cfgPass').value;
      var p2 = $('#cfgPass2').value;
      if (p || p2) {
        if (p.length < 4) { toast('密码至少 4 位', 'err'); return null; }
        if (p !== p2) { toast('两次输入的密码不一致', 'err'); return null; }
      }
      if (!u && !p) { toast('请填写要修改的用户名或密码', 'err'); return null; }
      return { username: u, password: p };
    }
    var ae = $('#cfgAcEnable');
    if (ae) ae.onclick = function () {
      var v = readCfgAc(); if (!v) return;
      post('/auth/setup', v, { noAccount: true }).then(function (r) {
        toast('登录已开启,账号「' + r.username + '」。下次打开网页需登录', 'ok');
        renderConfig();
      }).catch(function (e) { toast(e.message, 'err'); });
    };
    var asv = $('#cfgAcSave');
    if (asv) asv.onclick = function () {
      var v = readCfgAc(); if (!v) return;
      post('/auth/setup', v, { noAccount: true }).then(function () {
        toast('账号已更新', 'ok');
        renderConfig();
      }).catch(function (e) { toast(e.message, 'err'); });
    };
    var ad = $('#cfgAcDisable');
    if (ad) ad.onclick = function () {
      if (!confirm('确定关闭登录吗?关闭后任何人打开网页都能直接使用。')) return;
      post('/auth/setup', { disable: true }, { noAccount: true }).then(function () {
        toast('已关闭登录', 'ok');
        renderConfig();
      }).catch(function (e) { toast(e.message, 'err'); });
    };
    var al = $('#cfgAcLogout');
    if (al) al.onclick = function () {
      post('/auth/logout', {}, { noAccount: true }).then(function () {
        setSession('');
        toast('已退出登录', 'ok');
        renderConfig();
      }).catch(function (e) { toast(e.message, 'err'); });
    };
    // ---- 主题事件 ----
    var seg = $('#cfgThemeSeg');
    if (seg) seg.onclick = function (ev) {
      var b = ev.target.closest ? ev.target.closest('[data-theme]') : null;
      if (!b || !seg.contains(b)) return;
      var t = b.dataset.theme;
      localStorage.setItem('sc_theme', t);
      applyTheme(t);
      var bs = seg.querySelectorAll('.seg-btn');
      for (var i = 0; i < bs.length; i++) bs[i].classList.toggle('seg-on', bs[i].dataset.theme === t);
      toast('已切换到' + (t === 'dark' ? '暗色' : t === 'light' ? '亮色' : '跟随系统') + '主题', 'ok', 1600);
    };
    // ---- 主题颜色事件 ----
    markSwatch();
    var swBox = $('#cfgSwatches');
    if (swBox) swBox.onclick = function (ev) {
      var b = ev.target.closest ? ev.target.closest('.swatch') : null;
      if (!b || !swBox.contains(b)) return;
      applyAccent(b.dataset.a1, b.dataset.a2, true);
      var i1 = $('#cfgA1'), i2 = $('#cfgA2');
      if (i1) i1.value = b.dataset.a1;
      if (i2) i2.value = b.dataset.a2;
      markSwatch();
      toast('主题颜色:' + b.title, 'ok', 1600);
    };
    var a1Input = $('#cfgA1'), a2Input = $('#cfgA2');
    if (a1Input && a2Input) {
      a1Input.oninput = function () { applyAccent(a1Input.value, a2Input.value, true); markSwatch(); };
      a2Input.oninput = function () { applyAccent(a1Input.value, a2Input.value, true); markSwatch(); };
    }
    var accentReset = $('#cfgAccentReset');
    if (accentReset) accentReset.onclick = function () {
      applyAccent(null, null, true);
      var cs2 = getComputedStyle(document.documentElement);
      if (a1Input) a1Input.value = (cs2.getPropertyValue('--accent-1') || '#ffb35c').trim();
      if (a2Input) a2Input.value = (cs2.getPropertyValue('--accent-2') || '#ff7a3d').trim();
      markSwatch();
      toast('已恢复默认主题颜色', 'ok', 1600);
    };
    // ---- 令牌事件 ----
    var tsv = $('#cfgTokenSave');
    if (tsv) tsv.onclick = function () {
      setToken($('#cfgToken').value.trim());
      toast('令牌已保存', 'ok');
      loadAccounts();
    };
    appendNotifyCard(page);
  }).catch(function (e) {
    page.innerHTML = '<div class="empty"><div class="t">加载失败:' + esc(e.message) + '</div></div>';
  });
}

/* ---------------- 登录流程 ---------------- */
function showLogin() {
  var o = $('#loginOverlay');
  if (!o) return;
  o.style.display = 'flex';
  var err = $('#loginErr');
  if (err) err.style.display = 'none';
  setTimeout(function () { var u = $('#loginUser'); if (u) u.focus(); }, 60);
}
function hideLogin() {
  var o = $('#loginOverlay');
  if (o) o.style.display = 'none';
}
function doLogin() {
  var u = $('#loginUser').value.trim();
  var p = $('#loginPass').value;
  var err = $('#loginErr');
  if (!u || !p) { err.textContent = '请输入用户名和密码'; err.style.display = 'block'; return; }
  post('/auth/login', { username: u, password: p }, { noAccount: true }).then(function (r) {
    setSession(r.token);
    hideLogin();
    $('#loginUser').value = '';
    $('#loginPass').value = '';
    loadAccounts(true).then(function () { route(); });
  }).catch(function (e) {
    err.textContent = e.message;
    err.style.display = 'block';
  });
}
function checkAuth() {
  get('/auth/status', { noAccount: true }).then(function (s) {
    if (s.enabled && !s.logged_in) showLogin();
    else hideLogin();
  }).catch(function () {});
}

/* ================= 定时 ================= */
var THEME_META = [
  { id: 'warm', label: '🔥 暖心问候', count: 12 },
  { id: 'funny', label: '😂 火花调侃', count: 12 },
  { id: 'morning_night', label: '🌅 早安晚安', count: 12 },
  { id: 'weather', label: '🌦️ 天气关心', count: 12 },
  { id: 'festival', label: '🎊 节日祝福', count: 12 },
  { id: 'daily', label: '🥤 沙雕日常', count: 12 }
];
function renderSettings() {
  var page = $('#page');
  page.innerHTML = '<div class="empty"><div class="spinner"></div><div class="t">加载中…</div></div>';
  get(accPath('/config')).then(function (cfg) {
    state.config = cfg;
    var dayMap = { mon: '周一', tue: '周二', wed: '周三', thu: '周四', fri: '周五', sat: '周六', sun: '周日', off: '关闭' };
    page.innerHTML = '';
    var form = el('div', 'glass');
    form.style.cssText = 'padding:24px;max-width:780px';
    var pad2 = function (n) { return (n < 10 ? '0' : '') + n; };
    var jitHint = function (timeStr, jit) {
      var p = String(timeStr || '21:00').split(':');
      var h = parseInt(p[0], 10) || 0, m = parseInt(p[1], 10) || 0;
      var j = parseInt(jit, 10); if (isNaN(j) || j < 0) j = 0;
      var end = h * 60 + m + j;
      var t0 = pad2(h) + ':' + pad2(m), t1 = pad2(Math.floor(end / 60) % 24) + ':' + pad2(end % 60);
      return j === 0 ? '0 = 每天 ' + t0 + ' 准时发送' : '每天在 ' + t0 + ' ~ ' + t1 + ' 之间随机挑一个时刻发送';
    };
    var dayOpts = '';
    for (var k in dayMap) dayOpts += '<option value="' + k + '"' + ((cfg.harvest_day || 'off') === k ? ' selected' : '') + '>' + dayMap[k] + '</option>';
    form.innerHTML =
      '<div class="section-head"><h3>每日自动发送</h3><span class="sub">服务器时区 Asia/Shanghai,保存后实时生效</span></div>' +
      '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px 20px">' +
      '<div class="field"><label>每天发送时间</label><input type="time" class="input" id="cfgTime" value="' + esc(cfg.schedule_time || '21:00') + '" /></div>' +
      '<div class="field"><label>随机浮动窗口(分钟)</label><input type="number" class="input input-num" id="cfgJitter" value="' + (cfg.jitter_minutes != null ? cfg.jitter_minutes : 30) + '" min="0" max="120" /><div class="hint" id="cfgJitterHint">' + jitHint(cfg.schedule_time, cfg.jitter_minutes != null ? cfg.jitter_minutes : 30) + '</div></div>' +
      '<div class="field"><label>相邻好友间隔(秒)</label><div class="input-row"><input type="number" class="input input-num" id="cfgGapMin" value="' + (cfg.gap_min != null ? cfg.gap_min : 6) + '" min="1" /> ~ <input type="number" class="input input-num" id="cfgGapMax" value="' + (cfg.gap_max != null ? cfg.gap_max : 12) + '" min="1" /></div></div>' +
      '<div class="field"><label>每次最多发送(0=不限)</label><input type="number" class="input input-num" id="cfgMaxN" value="' + (cfg.max_per_run || 0) + '" min="0" /></div>' +
      '<div class="field"><label>周级 Creator 采集</label><select class="input" id="cfgHarvestDay">' + dayOpts + '</select><div class="hint">每周自动滚动采集一次好友抖音号(只读)</div></div>' +
      '</div>' +
      '<div class="field" style="margin-top:8px"><label>发送文案池(每行一条)</label>' +
      '<textarea class="input" id="cfgMsgs" rows="7" style="font-family:var(--mono)">' + esc((cfg.messages || []).join('\n')) + '</textarea>' +
      '<div class="hint">发送时随机抽取,自动避免与上次相同;支持变量 [日期] [时间]。首次发送给无会话好友需开启「允许首条消息」。</div>' +
      '<div class="theme-chips" id="cfgThemes"></div>' +
      '<div class="hint">随机主题文案:点选后并入文案池一起抽 · 当前池共 <b class="mono" id="poolCount">0</b> 条</div></div>' +
      '<div class="field" style="margin-top:14px"><label>表情包(文字发出后按概率随机追加一张)</label>' +
      '<div style="display:flex;gap:22px;flex-wrap:wrap;align-items:center">' +
      '<label class="switch"><input type="checkbox" id="cfgSticker"' + (cfg.sticker_enabled ? ' checked' : '') + ' /><span class="track"></span><span class="switch-label">启用随机表情包</span></label>' +
      '<div class="input-row"><span class="hint" style="margin:0">触发概率</span>' +
      '<input type="number" class="input input-num" id="cfgStickerChance" value="' + (cfg.sticker_chance != null ? cfg.sticker_chance : 30) + '" min="0" max="100" style="width:86px" /><span class="hint" style="margin:0">%</span></div>' +
      '</div>' +
      '<div style="display:flex;gap:10px;margin-top:10px;align-items:center;flex-wrap:wrap">' +
      '<button type="button" class="btn btn-ghost btn-sm" id="cfgStickerPick">' + ICONS.upload + '添加表情包</button>' +
      '<input type="file" id="cfgStickerFile" accept=".jpg,.jpeg,.png,.webp,.gif" multiple style="display:none" />' +
      '<span class="hint" style="margin:0">jpg / png / webp / gif,单张 ≤8MB,可多选</span></div>' +
      '<div class="sticker-grid" id="stickerGrid"></div></div>' +
      '<div style="display:flex;gap:26px;flex-wrap:wrap;margin:6px 0 4px">' +
      '<label class="switch"><input type="checkbox" id="cfgAuto"' + (cfg.auto_enabled !== false ? ' checked' : '') + ' /><span class="track"></span><span class="switch-label">自动运行总开关</span></label>' +
      '<label class="switch"><input type="checkbox" id="cfgFirst"' + (cfg.allow_first ? ' checked' : '') + ' /><span class="track"></span><span class="switch-label">允许对无会话好友发首条消息(高风险)</span></label>' +
      '</div>' +
      '<div class="field" style="max-width:240px"><label>首条消息单日上限</label><input type="number" class="input input-num" id="cfgFirstLimit" value="' + (cfg.first_limit || 1) + '" min="1" max="10" /></div>' +
      '<div style="display:flex;gap:10px;margin-top:18px">' +
      '<button class="btn btn-primary" id="cfgSave">' + ICONS.check + '保存设置</button>' +
      '<a class="btn btn-ghost" href="#/friends">去勾选好友 →</a></div>';
    page.appendChild(form);

    /* ---- 浮动窗口说明随时间/浮动值实时更新 ---- */
    function syncJitHint() {
      var h = $('#cfgJitterHint');
      if (h) h.textContent = jitHint($('#cfgTime').value, $('#cfgJitter').value);
    }
    $('#cfgTime').addEventListener('input', syncJitHint);
    $('#cfgJitter').addEventListener('input', syncJitHint);

    /* ---- 随机主题文案 chips ---- */
    var selThemes = (cfg.themes || []).slice();
    var chipsBox = $('#cfgThemes');
    function poolCount() {
      var n = $('#cfgMsgs').value.split('\n').filter(function (s) { return s.trim(); }).length;
      THEME_META.forEach(function (t) { if (selThemes.indexOf(t.id) >= 0) n += t.count; });
      $('#poolCount').textContent = n;
    }
    THEME_META.forEach(function (t) {
      var chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chip' + (selThemes.indexOf(t.id) >= 0 ? ' chip-on' : '');
      chip.innerHTML = t.label + ' <span class="mono">' + t.count + '</span>';
      chip.onclick = function () {
        var i = selThemes.indexOf(t.id);
        if (i >= 0) { selThemes.splice(i, 1); chip.classList.remove('chip-on'); }
        else { selThemes.push(t.id); chip.classList.add('chip-on'); }
        poolCount();
      };
      chipsBox.appendChild(chip);
    });
    $('#cfgMsgs').addEventListener('input', poolCount);
    poolCount();

    /* ---- 表情包管理 ---- */
    function renderStickers(list) {
      var grid = $('#stickerGrid');
      grid.innerHTML = '';
      if (!list.length) { grid.innerHTML = '<div class="hint">还没有表情包,点「添加表情包」上传,发送时随机抽取</div>'; return; }
      list.forEach(function (s) {
        var cell = el('div', 'sticker-cell');
        cell.innerHTML = '<img src="' + esc(s.url) + '" alt="" loading="lazy" />' +
          '<button type="button" class="sticker-del" title="删除">×</button>';
        cell.querySelector('.sticker-del').onclick = function () {
          del(accPath('/stickers/' + encodeURIComponent(s.name))).then(function () {
            toast('已删除', 'ok');
            return get(accPath('/stickers'));
          }).then(function (r) { renderStickers((r && r.stickers) || []); }).catch(function (e) { toast(e.message, 'err'); });
        };
        grid.appendChild(cell);
      });
    }
    get(accPath('/stickers')).then(function (r) { renderStickers((r && r.stickers) || []); }).catch(function () { renderStickers([]); });
    $('#cfgStickerPick').onclick = function () { $('#cfgStickerFile').click(); };
    $('#cfgStickerFile').onchange = function () {
      var files = Array.prototype.slice.call(this.files || []);
      if (!files.length) return;
      var fd = new FormData();
      files.forEach(function (f) { fd.append('file', f); });
      post(accPath('/stickers'), fd).then(function (r) {
        var skip = (r.skipped || []).length;
        toast('已添加 ' + (r.saved || []).length + ' 张' + (skip ? ',跳过 ' + skip + ' 张' : ''), skip && !(r.saved || []).length ? 'err' : 'ok');
        return get(accPath('/stickers'));
      }).then(function (r) { renderStickers((r && r.stickers) || []); }).catch(function (e) { toast(e.message, 'err'); });
      this.value = '';
    };

    $('#cfgSave').onclick = function () {
      function num(id, def) { var v = parseInt($('#' + id).value, 10); return (isNaN(v) || v < 0) ? def : v; }
      var msgs = $('#cfgMsgs').value.split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
      if (!msgs.length && !selThemes.length) { toast('文案池和主题文案至少要有一样', 'err'); return; }
      var cfg2 = {
        schedule_time: $('#cfgTime').value || '21:00',
        jitter_minutes: num('cfgJitter', 30),
        gap_min: num('cfgGapMin', 6),
        gap_max: num('cfgGapMax', 12),
        max_per_run: num('cfgMaxN', 0),
        messages: msgs,
        themes: selThemes,
        sticker_enabled: $('#cfgSticker').checked,
        sticker_chance: Math.min(100, num('cfgStickerChance', 30)),
        auto_enabled: $('#cfgAuto').checked,
        allow_first: $('#cfgFirst').checked,
        first_limit: num('cfgFirstLimit', 1),
        harvest_day: $('#cfgHarvestDay').value
      };
      put(accPath('/config'), { config: cfg2 }).then(function (r) {
        toast('设置已保存并实时生效', 'ok');
        state.config = r.config;
      }).catch(function (e) { toast(e.message, 'err'); });
    };
  }).catch(function (e) {
    page.innerHTML = '<div class="empty"><div class="t">加载失败</div>' + esc(e.message) + '</div>';
    schedulePageRetry();
  });
}

/* ================= 凭证 ================= */
function renderCredentials() {
  var page = $('#page');
  page.innerHTML = '<div class="empty"><div class="spinner"></div><div class="t">加载中…</div></div>';
  get(accPath('/status')).then(function (st) {
    state.status = st;
    page.innerHTML = '';
    var grid = el('div');
    grid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px';

    var up = el('div', 'glass');
    up.style.cssText = 'padding:22px';
    up.innerHTML =
      '<div class="section-head"><h3>上传登录态</h3><span class="spacer"></span>' + (st.state_file_exists ? '<span class="tag ok">✓ 已就绪</span>' : '<span class="tag err">✗ 缺失</span>') + '</div>' +
      '<div class="drop-zone" id="dropZone">' + ICONS.upload + '<div>点击选择或拖入 <span class="mono">state.json</span></div>' +
      '<div style="font-size:11.5px;color:var(--text-3);margin-top:4px">由「1.本地提取通行证.bat」或 extract_cookie.py 生成</div></div>' +
      '<input type="file" id="stateFile" accept=".json" style="display:none" />' +
      '<div class="hint" style="margin-top:10px">更新后云端立即采用,无需重启。凭证过期时在此重新上传即可。</div>';
    grid.appendChild(up);

    var qr = el('div', 'glass');
    qr.style.cssText = 'padding:22px';
    qr.id = 'qrCard';
    qr.innerHTML =
      '<div class="section-head"><h3>网页扫码登录</h3><span class="spacer"></span><span class="tag idle" id="qrStateTag">空闲</span></div>' +
      '<div id="qrBody"><div style="font-size:13px;color:var(--text-2);line-height:1.8;margin-bottom:14px">' +
      '服务器上直接打开抖音登录页生成二维码,用手机抖音 App 扫码即可登录并自动保存登录态。<br/>' +
      '如遇二次安全验证(刷脸),页面会出现新二维码,按提示用手机扫描即可。</div>' +
      '<button class="btn btn-primary" id="qrStart">' + ICONS.qr + '开始扫码登录</button></div>';
    grid.appendChild(qr);
    page.appendChild(grid);

    $('#dropZone').onclick = function () { $('#stateFile').click(); };
    $('#stateFile').onchange = function (e) {
      var f = e.target.files[0];
      if (!f) return;
      if (f.size > 5 * 1024 * 1024) { toast('文件过大(>5MB)', 'err'); return; }
      uploadFile(f);
    };
    $('#dropZone').addEventListener('dragover', function (e) { e.preventDefault(); $('#dropZone').classList.add('drag'); });
    $('#dropZone').addEventListener('dragleave', function () { $('#dropZone').classList.remove('drag'); });
    $('#dropZone').addEventListener('drop', function (e) {
      e.preventDefault(); $('#dropZone').classList.remove('drag');
      if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
    });
    $('#qrStart').onclick = startLogin;
    function uploadFile(f) {
      var fd = new FormData();
      fd.append('file', f);
      post(accPath('/credential'), fd).then(function (r) {
        toast('登录态已上传 (' + r.size + ' 字节),立即生效', 'ok');
        renderCredentials();
      }).catch(function (e) { toast(e.message, 'err'); });
    }
  }).catch(function (e) {
    page.innerHTML = '<div class="empty"><div class="t">加载失败</div>' + esc(e.message) + '</div>';
    schedulePageRetry();
  });
}
function startLogin() {
  confirmDlg('扫码登录须知', '<b style="color:var(--text)">1.</b> 请提前准备好手机抖音 App;<br/><b style="color:var(--text)">2.</b> 点击「开始」后约 20~40 秒生成二维码;<br/><b style="color:var(--text)">3.</b> 用抖音 App 扫一扫(支持从相册选图);<br/><b style="color:var(--text)">4.</b> 若提示二次验证,扫描页面上的新二维码继续。', function () {
    post(accPath('/qr')).then(function () {
      pollLogin();
      renderCredentials();
    }).catch(function (e) { toast(e.message, 'err'); });
  }, '已备好手机,开始扫码');
}
function pollLogin() {
  if (state.loginTimer) clearInterval(state.loginTimer);
  state.loginTimer = setInterval(function () {
    get(accPath('/qr')).then(function (s) {
      var card = $('#qrCard');
      if (!card) { clearInterval(state.loginTimer); state.loginTimer = null; return; }
      var tag = $('#qrStateTag');
      var map = { idle: ['空闲', 'idle'], preparing: ['启动中', 'warn'], waiting: ['等待扫码', 'warn'], done: ['登录成功', 'ok'], failed: ['失败', 'err'], expired: ['超时', 'err'], canceled: ['已取消', 'idle'] };
      var pair = map[s.status] || [s.status, 'idle'];
      tag.textContent = pair[0];
      tag.className = 'tag ' + pair[1];
      var body = '';
      if (s.status === 'waiting' && s.qrcode) {
        body = '<div class="qr-frame"><div class="qr-box"><img src="' + s.qrcode + '" alt="二维码" /></div>' +
          '<div class="qr-status"><span class="spinner"></span>' + esc(s.message || '请用抖音 App 扫码') + '</div>' +
          '<div style="display:flex;gap:10px"><button class="btn btn-danger btn-sm" id="qrCancel">取消</button></div></div>';
      } else if (s.status === 'preparing') {
        body = '<div class="qr-frame"><div class="qr-status"><span class="spinner"></span>' + esc(s.message || '准备中…') + '</div><button class="btn btn-danger btn-sm" id="qrCancel">取消</button></div>';
      } else if (s.status === 'done') {
        body = '<div class="qr-frame"><div style="font-size:34px;color:var(--ok)">✓</div><div class="qr-status" style="color:var(--ok)">' + esc(s.message || '登录成功') + '</div></div>';
        setTimeout(function () { clearInterval(state.loginTimer); state.loginTimer = null; renderCredentials(); loadAccounts(true); }, 1600);
      } else if (s.status === 'failed' || s.status === 'expired' || s.status === 'canceled') {
        body = '<div class="qr-frame"><div class="qr-status" style="color:var(--err)">' + esc(s.message || s.status) + '</div>' +
          (s.error ? '<div class="mono" style="font-size:11px;color:var(--text-3);max-width:300px;word-break:break-all">' + esc(s.error) + '</div>' : '') +
          '<button class="btn btn-primary btn-sm" id="qrRestart">重新扫码</button></div>';
      } else {
        body = '<div class="qr-frame"><button class="btn btn-primary" id="qrStart2">' + ICONS.qr + '开始扫码登录</button></div>';
      }
      $('#qrBody').innerHTML = body;
      var c1 = $('#qrCancel');
      if (c1) c1.onclick = function () { del(accPath('/qr')).then(function () { toast('已取消扫码', 'info'); }).catch(function () {}); };
      var c2 = $('#qrRestart');
      if (c2) c2.onclick = startLogin;
      var c3 = $('#qrStart2');
      if (c3) c3.onclick = startLogin;
      if ((s.status === 'failed' || s.status === 'expired' || s.status === 'canceled') && s.status !== 'done') {
        clearInterval(state.loginTimer); state.loginTimer = null;
      }
    }).catch(function () {});
  }, 1800);
}

/* ================= 日志 ================= */
function renderLogLines(lines) {
  var out = '';
  for (var i = 0; i < lines.length; i++) {
    var l = lines[i];
    var m = l.match(/^(\S+ \S+) \[(\w+)\] (.*)$/);
    if (!m) { out += '<div class="log-line"><span class="msg">' + esc(l) + '</span></div>'; continue; }
    out += '<div class="log-line lv-' + esc(m[2]) + '"><span class="ts">' + esc(m[1]) + '</span><span class="lv">' + esc(m[2]) + '</span><span class="msg">' + esc(m[3]) + '</span></div>';
  }
  return out;
}
/* ================= 发送历史 / 统计(功能1) ================= */
function appendHistoryBlock(container, initLimit) {
  var wrap = el('div');
  container.appendChild(wrap);
  var limit = initLimit || 10;
  function draw() {
    Promise.all([
      get(accPath('/stats')).catch(function () { return null; }),
      get(accPath('/history?limit=' + limit)).catch(function () { return null; })
    ]).then(function (rs) {
      var st = rs[0] && rs[0].stats, recs = rs[1] && rs[1].records;
      if (!st && !recs) return; /* 旧后端无此 API,静默跳过 */
      wrap.innerHTML = '';
      var chips = el('div', 'cards');
      chips.style.cssText = 'margin-bottom:16px';
      chips.appendChild(statCard('本月成功', (st && st.month_ok) || 0, '自动 + 手动发送', 'check'));
      chips.appendChild(statCard('本月失败', (st && st.month_fail) || 0, st && st.month_fail ? '需要关注' : '一切正常', 'flame'));
      chips.appendChild(statCard('成功率', st && st.month_rate != null ? st.month_rate + '<small>%</small>' : '—', '本月发送成功率', 'zap'));
      chips.appendChild(statCard('累计成功', (st && st.total_ok) || 0, '历史总计', 'users'));
      wrap.appendChild(chips);
      var card = el('div', 'glass');
      card.style.cssText = 'padding:16px 18px;margin-bottom:16px';
      var rows = (recs || []).map(function (r) {
        var d = (r.ts || '').replace('T', ' ');
        return '<div class="hist-row' + (r.ok ? '' : ' bad') + '">' +
          '<span class="h-time">' + esc(d) + '</span>' +
          '<span class="h-name">' + esc(r.name) + (r.sticker ? ' 🖼' : '') + '</span>' +
          '<span class="tag ' + (r.ok ? 'ok' : 'err') + '">' + (r.ok ? '成功' : '失败') + '</span>' +
          '<span class="h-txt">' + esc(r.ok ? (r.text || '—') : (r.reason || '失败')) + '</span></div>';
      }).join('');
      card.innerHTML = '<div class="section-head"><h3>📜 发送记录</h3><span class="spacer"></span>' +
        '<span style="font-size:12px;color:var(--text-3)">最近 ' + (recs || []).length + ' 条</span></div>' +
        '<div class="hist-list">' + (rows || '<div class="empty"><div class="t">暂无发送记录</div>发送成功 / 失败都会记录在这里</div>') + '</div>' +
        '<div style="text-align:center;margin-top:10px"><button class="btn btn-sm" id="histMore">加载更多</button></div>';
      wrap.appendChild(card);
      var more = $('#histMore');
      if (more) more.onclick = function () { limit += 30; draw(); };
    });
  }
  draw();
}

/* ================= 好友差异(功能5) ================= */
function openOverrideDlg(name) {
  var old = document.getElementById('ovMask');
  if (old) old.remove();
  var mask = el('div', 'modal-mask');
  mask.id = 'ovMask';
  var card = el('div', 'glass modal-card ov-card');
  card.innerHTML =
    '<div class="section-head"><h3>⚙ 好友差异 · ' + esc(name) + '</h3></div>' +
    '<label class="switch-row ov-line"><span>跳过此好友(不自动发送)</span><span class="switch"><input type="checkbox" id="ovSkip" /><span class="track"></span></span></label>' +
    '<div class="ov-field"><label>专属文案池(每行一条,留空跟随全局)</label><textarea class="input" id="ovPool" rows="4" placeholder="🔥 只发给 TA 的专属问候"></textarea></div>' +
    '<div class="ov-field"><label>表情包概率 %(留空跟随全局)</label><input class="input" id="ovSticker" type="number" min="0" max="100" inputmode="numeric" placeholder="如 80" /></div>' +
    '<div style="display:flex;gap:10px;margin-top:14px"><button class="btn btn-primary" id="ovSave" style="flex:1">保存</button><button class="btn" id="ovCancel" style="flex:1">取消</button></div>';
  mask.appendChild(card);
  mask.classList.add('show');
  document.body.appendChild(mask);
  mask.addEventListener('click', function (e) { if (e.target === mask) mask.remove(); });
  get(accPath('/config')).then(function (cfg) {
    var o = (cfg.friend_overrides || {})[name] || {};
    $('#ovSkip').checked = !!o.skip;
    $('#ovPool').value = (o.pool || []).join('\n');
    if (o.sticker_chance != null) $('#ovSticker').value = o.sticker_chance;
  }).catch(function () {});
  $('#ovCancel').onclick = function () { mask.remove(); };
  $('#ovSave').onclick = function () {
    get(accPath('/config')).then(function (cfg) {
      var all = cfg.friend_overrides || {};
      var pool = $('#ovPool').value.split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
      var scRaw = $('#ovSticker').value.trim();
      var rule = { skip: $('#ovSkip').checked, pool: pool, sticker_chance: scRaw === '' ? null : Number(scRaw) };
      if (!rule.skip && !pool.length && rule.sticker_chance == null) delete all[name];
      else all[name] = rule;
      return put(accPath('/config'), { friend_overrides: all });
    }).then(function () {
      mask.remove();
      toast('已保存好友差异:' + name, 'ok');
    }).catch(function (e) { toast('保存失败:' + e.message, 'err'); });
  };
}

/* ================= 通知推送(功能2,挂在设置页) ================= */
function appendNotifyCard(container) {
  get('/notify').catch(function () { return null; }).then(function (r) {
    if (!r || !r.notify) return; /* 旧后端无此 API,静默跳过 */
    var n = r.notify;
    var card = el('div', 'glass');
    card.style.cssText = 'padding:20px;margin-top:16px';
    var chOpts = [['wx_direct', '微信直连(扫码绑定,推荐)'], ['clawbot', 'Clawbot / OpenClaw 网关(微信)'], ['bark', 'Bark(iOS)'], ['serverchan', 'Server酱'], ['webhook', '自定义 Webhook']];
    var opts = chOpts.map(function (o) {
      return '<option value="' + o[0] + '"' + (n.channel === o[0] ? ' selected' : '') + '>' + o[1] + '</option>';
    }).join('');
    card.innerHTML =
      '<div class="section-head"><h3>🔔 通知推送</h3><span class="spacer"></span>' +
      '<label class="switch"><input type="checkbox" id="ntfOn"' + (n.enabled ? ' checked' : '') + ' /><span class="track"></span></label></div>' +
      '<div class="ntf-hint">开启后:好友发送失败 / 登录态失效 / 触发限流 时,自动推送到微信等渠道。</div>' +
      '<div class="field-row"><label>渠道</label><select class="input" id="ntfCh">' + opts + '</select></div>' +
      '<div class="ntf-hint" id="ntfClawHint" style="display:none">微信登录由 OpenClaw 网关负责:在网关所在机器执行 <span class="mono">openclaw channels login --channel openclaw-weixin</span>,用手机微信扫码确认即可;本工具只负责把通知投递给网关,把发送接口 URL / 令牌填到下面。</div>' +
      '<div class="field-row"><label>地址 / Key</label><input class="input" id="ntfUrl" placeholder="clawbot=网关发送接口完整 URL;bark=Key;Server酱=SendKey" value="' + esc(n.url || '') + '" /></div>' +
      '<div class="field-row"><label>网关令牌</label><input class="input" id="ntfToken" placeholder="Clawbot 网关 API Token(可选)" value="' + esc(n.token || '') + '" /></div>' +
      '<div class="field-row"><label>接收目标</label><input class="input" id="ntfTo" placeholder="微信联系人 / 群 id(可选,如 filehelper)" value="' + esc(n.to || '') + '" /></div>' +
      '<div class="ntf-evs" id="ntfEvs"></div>' +
      '<div style="display:flex;gap:10px;margin-top:12px"><button class="btn btn-primary" id="ntfSave" style="flex:1">保存设置</button><button class="btn" id="ntfTest" style="flex:1">发送测试</button></div>';
    container.appendChild(card);
    /* ---- 微信直连绑定区(wx_direct) ---- */
    var wxBox = el('div', '');
    wxBox.id = 'wxBox';
    wxBox.style.cssText = 'display:none;margin-top:12px';
    wxBox.innerHTML =
      '<div class="ntf-hint">无需 OpenClaw:点「生成二维码」→ 微信扫码 → 绑定后状态实时推到你微信。绑定后请在微信里给机器人发一条消息,开通推送通道。</div>' +
      '<div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">' +
      '<img id="wxQr" alt="二维码" style="width:132px;height:132px;border-radius:10px;background:var(--panel-inner);display:none" />' +
      '<div style="flex:1;min-width:180px"><div class="hint" id="wxState">未绑定</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">' +
      '<button type="button" class="btn btn-sm" id="wxQrBtn">生成二维码</button>' +
      '<button type="button" class="btn btn-sm" id="wxTest">发送测试</button>' +
      '<button type="button" class="btn btn-sm" id="wxOut">解除绑定</button></div>' +
      '<div id="wxVerifyRow" style="display:none;gap:8px;margin-top:8px;flex-wrap:wrap"><input class="input" id="wxCode" placeholder="微信里显示的配对码" style="max-width:180px" /><button type="button" class="btn btn-sm btn-primary" id="wxVerifyBtn">提交配对码</button></div>' +
      '</div></div>';
    card.insertBefore(wxBox, card.querySelector('.ntf-evs'));
    function syncCh() {
      var h = $('#ntfClawHint');
      if (h) h.style.display = $('#ntfCh').value === 'clawbot' ? '' : 'none';
      wxBox.style.display = $('#ntfCh').value === 'wx_direct' ? '' : 'none';
    }
    $('#ntfCh').addEventListener('change', syncCh);
    syncCh();
    var wxTimer = null;
    function wxPoll() {
      if (wxTimer) return;
      function tick() {
        if (!$('#wxState')) { clearInterval(wxTimer); wxTimer = null; return; }
        get('/wx/status').then(function (r) {
          var w = (r && r.wx) || {};
          if (!$('#wxState')) return;
          var img = $('#wxQr');
          if (w.qr_svg || (w.qr_content && w.qr_content.indexOf('data:') === 0)) {
            img.src = w.qr_svg || w.qr_content; img.style.display = '';
          } else if (w.phase !== 'qr_ready') { img.style.display = 'none'; }
          $('#wxState').textContent =
            w.phase === 'bound' ? (w.has_contact ? '✅ 已绑定,推送通道就绪' : '✅ 已绑定 — 请在微信里给机器人发一条消息以开通推送')
            : w.phase === 'qr_ready' ? '📲 请用微信扫码'
            : w.phase === 'scanned' ? '已扫码,请在手机上确认'
            : w.phase === 'need_verifycode' ? '需要配对码:查看微信里机器人发来的数字'
            : w.phase === 'expired' ? '⚠️ 登录已过期,请重新扫码'
            : w.phase === 'error' ? ('❌ ' + (w.last_error || '出错,请重试'))
            : '未绑定';
          $('#wxVerifyRow').style.display = w.phase === 'need_verifycode' ? 'flex' : 'none';
        }).catch(function () {});
      }
      tick();
      wxTimer = setInterval(tick, 2000);
    }
    setInterval(function () { if ($('#wxState') && $('#ntfCh') && $('#ntfCh').value === 'wx_direct') wxPoll(); }, 2000);
    $('#wxQrBtn').onclick = function () { post('/wx/login', {}); toast('正在生成二维码…', 'info'); };
    $('#wxTest').onclick = function () {
      post('/wx/test', {}).then(function (r) {
        toast((r && r.ok) ? '测试消息已发送,请查收微信' : '发送失败:' + ((r && r.detail) || ''), r && r.ok ? 'ok' : 'err', 5000);
      });
    };
    $('#wxOut').onclick = function () {
      confirmDlg('解除微信绑定', '将清除本机保存的微信登录令牌,推送停用。', function () {
        post('/wx/logout', {}); toast('已解除绑定', 'ok');
      }, '解除');
    };
    $('#wxVerifyBtn').onclick = function () {
      post('/wx/verify', { code: $('#wxCode').value }).then(function (r) {
        toast(r && r.ok ? '配对码已提交' : '提交失败', r && r.ok ? 'ok' : 'err');
      });
    };
    var evMeta = [['send_ok', '发送成功(实时)'], ['send_fail', '好友发送失败'], ['login_expired', '登录态失效'], ['rate_limited', '触发限流']];
    $('#ntfEvs').innerHTML = evMeta.map(function (m) {
      var on = (n.events || {})[m[0]] !== false;
      return '<label class="switch-row"><span>' + m[1] + '</span><span class="switch"><input type="checkbox" data-ev="' + m[0] + '"' + (on ? ' checked' : '') + ' /><span class="track"></span></span></label>';
    }).join('');
    function collect() {
      var events = {};
      document.querySelectorAll('#ntfEvs [data-ev]').forEach(function (b) { events[b.dataset.ev] = b.checked; });
      return { enabled: $('#ntfOn').checked, channel: $('#ntfCh').value, url: $('#ntfUrl').value.trim(), token: $('#ntfToken').value.trim(), to: $('#ntfTo').value.trim(), events: events };
    }
    $('#ntfSave').onclick = function () {
      put('/notify', collect()).then(function () { toast('通知设置已保存', 'ok'); })
        .catch(function (e) { toast('保存失败:' + e.message, 'err'); });
    };
    $('#ntfTest').onclick = function () {
      var btn = this;
      btn.disabled = true;
      put('/notify', collect()).then(function () { return post('/notify/test'); }).then(function (r2) {
        var res = (r2 && r2.result) || {};
        toast(res.ok ? '测试推送已发送,请查收' : '测试失败:' + (res.skipped || res.error || 'HTTP ' + res.status), res.ok ? 'ok' : 'err', 5000);
      }).catch(function (e) { toast('测试失败:' + e.message, 'err', 5000); })
        .finally(function () { btn.disabled = false; });
    };
  });
}

function renderLogs() {
  var page = $('#page');
  Promise.all([get(accPath('/logs?n=300')), get(accPath('/report')), get(accPath('/friends'))]).then(function (res) {
    var logsRes = res[0], stats = res[1] || {}, ledgerData = res[2];
    page.innerHTML = '';
    var grid = el('div', 'no-anim');
    grid.style.cssText = 'display:grid;grid-template-columns:minmax(0,1fr);gap:16px';
    var logCard = el('div', 'glass');
    logCard.style.cssText = 'padding:20px';
    logCard.innerHTML = '<div class="section-head"><h3>实时日志</h3><span class="spacer"></span><span class="sub">每 3 秒自动刷新</span></div>';
    var lp = el('div', 'log-panel');
    lp.innerHTML = renderLogLines((logsRes.logs || '').split('\n'));
    logCard.appendChild(lp);
    grid.appendChild(logCard);

    var topStreak = (stats.top || []).slice(0, 8);
    var noConv = (stats.no_chat || []).slice(0, 8);
    var statsCard = el('div', 'glass');
    statsCard.style.cssText = 'padding:20px';
    statsCard.innerHTML = '<div class="section-head"><h3>台账健康度</h3><span class="spacer"></span><span class="pill">共 ' + (stats.total || 0) + ' 人 · 勾选 ' + (stats.selected || 0) + '</span></div>';
    var cols = el('div');
    cols.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px';
    var topHtml = '';
    if (topStreak.length) {
      topHtml = '<div style="display:flex;flex-direction:column;gap:5px">';
      for (var i = 0; i < topStreak.length; i++) {
        topHtml += '<div style="display:flex;justify-content:space-between;font-size:12.5px"><span>' + esc(topStreak[i].name) + '</span><span class="streak-badge">🔥 ' + topStreak[i].days + '</span></div>';
      }
      topHtml += '</div>';
    } else topHtml = '<div style="font-size:12.5px;color:var(--text-3)">暂无数据,请先同步联系人</div>';
    var noConvHtml = noConv.length
      ? '<div style="display:flex;flex-direction:column;gap:5px;font-size:12.5px">' + noConv.map(function (n) {
          return '<div>' + esc(n.name) + ' <span class="tag idle">' + esc(n.source || 'sync') + '</span></div>';
        }).join('') + '</div>'
      : '<div style="font-size:12.5px;color:var(--text-3)">全部联系人都有会话 ✓</div>';
    cols.innerHTML =
      '<div><div class="k" style="font-size:11.5px;color:var(--text-3);letter-spacing:1px;margin-bottom:8px">🔥 火花 Top</div>' + topHtml + '</div>' +
      '<div><div class="k" style="font-size:11.5px;color:var(--text-3);letter-spacing:1px;margin-bottom:8px">⚠ 无会话 / 待确认</div>' + noConvHtml + '</div>' +
      '<div><div class="k" style="font-size:11.5px;color:var(--text-3);letter-spacing:1px;margin-bottom:8px">识别置信度</div>' +
      '<div style="font-size:12.5px;line-height:2">High <span style="color:var(--ok);font-weight:700">' + ((stats.high) || 0) + '</span> · Low <span style="color:var(--warn)">' + (((stats.total || 0) - (stats.high || 0))) + '</span><br/>已绑定抖音号 <span style="color:var(--accent-1);font-weight:700">' + (stats.with_short_id || 0) + '</span> · 近7天发送 <span style="font-weight:700">' + ((stats.recent7 && stats.recent7.length) || 0) + '</span> 人</div></div>';
    statsCard.appendChild(cols);
    grid.appendChild(statsCard);
    page.appendChild(grid);
    every('logs', 3000, function () {
      get(accPath('/logs'), { n: 300 }).then(function (r) {
        if (!dataChanged('lg:' + state.accountId, r)) return;
        renderLogs();
      }).catch(function () {});
    });
  }).catch(function (e) {
    page.innerHTML = '<div class="empty"><div class="t">加载失败</div>' + esc(e.message) + '</div>';
    schedulePageRetry();
  });
}

/* ---------------- 操作 ---------------- */
function runNow(dry) {
  post(accPath('/run'), { dry: dry }).then(function () {
    toast(dry ? '演练模式已启动(不真实发送)' : '正式发送任务已启动', 'ok');
    setTimeout(function () { loadAccounts(true); renderOverview(); }, 1200);
  }).catch(function (e) { toast(e.message, 'err'); });
}
function resetRunning() {
  post(accPath('/stop')).then(function () {
    toast('已强制停止任务并重置运行锁', 'ok');
    loadAccounts(true);
    if (state.page === 'overview') renderOverview();
    else if (state.page === 'accounts') renderAccounts();
  }).catch(function (e) { toast(e.message, 'err'); });
}

/* ---------------- 顶栏事件 ---------------- */
function bindTopbar() {
  $('#accountSelect').onchange = function () {
    state.accountId = $('#accountSelect').value;
    localStorage.setItem('dcs_account', state.accountId);
    friendsLoaded = false;
    var acc = null;
    for (var i = 0; i < state.accounts.length; i++) if (state.accounts[i].id === state.accountId) acc = state.accounts[i];
    toast('已切换到: ' + (acc ? acc.name : ''), 'info');
    route();
  };
  $('#btnReset').onclick = resetRunning;
}

/* ---------------- 启动 ---------------- */
(function init() {
  /* 直接双击 index.html 打开时给出指引 */
  if (location.protocol !== 'http:' && location.protocol !== 'https:') {
    document.getElementById('fileGuard').style.display = 'grid';
    return;
  }
  applyTheme(currentTheme());   // 主题切换入口已归档到「设置」页
  var _acc = currentAccent();
  if (_acc && _acc.a1 && _acc.a2) applyAccent(_acc.a1, _acc.a2, false);   // 自定义主题颜色
  var mq = window.matchMedia('(prefers-color-scheme: light)');
  if (mq.addEventListener) mq.addEventListener('change', function () { if (currentTheme() === 'system') applyTheme('system'); });
  renderNav();
  bindTopbar();
  window.addEventListener('hashchange', route);
  var lb = $('#loginBtn');
  if (lb) lb.onclick = doLogin;
  var lp = $('#loginPass');
  if (lp) lp.addEventListener('keydown', function (e) { if (e.key === 'Enter') doLogin(); });
  checkAuth();
  loadAccounts(true).then(function () { route(); loadBg(); });
  setInterval(function () { loadAccounts(true); }, 6000);
})();
