const T = {
  title: { ru: "Intention", en: "Intention" },
  subtitle: { ru: "Доверься интуиции", en: "Trust your intuition" },
  play: { ru: "Играть", en: "Play" },
  settings: { ru: "Настройки", en: "Settings" },
  stats: { ru: "Статистика", en: "Statistics" },
  logout: { ru: "Выйти", en: "Log out" },
  back: { ru: "Назад", en: "Back" },
  login: { ru: "Вход", en: "Sign in" },
  register: { ru: "Регистрация", en: "Register" },
  name: { ru: "Имя", en: "Name" },
  password: { ru: "Пароль", en: "Password" },
  submitLogin: { ru: "Войти", en: "Sign in" },
  submitReg: { ru: "Создать аккаунт", en: "Create account" },
  needAccount: { ru: "Нет аккаунта? Регистрация", en: "No account? Register" },
  haveAccount: { ru: "Уже есть аккаунт? Вход", en: "Have an account? Sign in" },
  mode: { ru: "Режим", en: "Mode" },
  mode_colors: { ru: "Цвета", en: "Colors" },
  mode_numbers: { ru: "Цифры", en: "Numbers" },
  colors_2: { ru: "2 цвета", en: "2 colors" },
  colors_3: { ru: "3 цвета", en: "3 colors" },
  number_max: { ru: "Диапазон", en: "Range" },
  language: { ru: "Язык", en: "Language" },
  sound: { ru: "Звук", en: "Sound" },
  on: { ru: "Вкл", en: "On" },
  off: { ru: "Выкл", en: "Off" },
  prompt_color: { ru: "Какого цвета шарик?", en: "What color is the ball?" },
  prompt_number: { ru: "Какая цифра?", en: "What number?" },
  hint: { ru: "Почувствуй — и выбери", en: "Feel it — then choose" },
  match: { ru: "Верно!", en: "Correct!" },
  no_match: { ru: "Не верно!", en: "Wrong!" },
  streak: { ru: "Серия", en: "Streak" },
  best: { ru: "Рекорд серии", en: "Best streak" },
  accuracy: { ru: "Точность", en: "Accuracy" },
  best_acc: { ru: "Рекорд точности", en: "Best accuracy" },
  to_menu: { ru: "В меню", en: "To menu" },
  place: { ru: "Место", en: "Place" },
  player: { ru: "Игрок", en: "Player" },
  emptyTop: { ru: "Пока нет результатов", en: "No results yet" },
  you: { ru: "Вы", en: "You" },
  variant: { ru: "Вариант", en: "Variant" },
};

const COLORS = {
  black: { ru: "Чёрный", en: "Black" },
  white: { ru: "Белый", en: "White" },
  gray: { ru: "Серый", en: "Gray" },
};

const state = {
  screen: "auth",
  authTab: "login",
  lang: localStorage.getItem("lang") || "ru",
  token: localStorage.getItem("token") || "",
  username: "",
  records: { colors: {}, numbers: {} },
  settings: {
    mode: "colors",
    colorCount: 2,
    numberMax: 5,
    sound: true,
  },
  error: "",
  session: { streak: 0, rounds: 0, matches: 0 },
  round: { answer: null, chosen: null, matched: null, revealing: false },
  statsMode: "colors",
  statsVariant: "2",
  leaderboard: null,
};

function t(key) {
  return (T[key] && T[key][state.lang]) || key;
}

function rec() {
  const mode = state.settings.mode;
  const key = mode === "numbers" ? String(state.settings.numberMax) : String(state.settings.colorCount);
  const found = state.records[mode] && state.records[mode][key];
  return found || { best_streak: 0, best_accuracy: 0 };
}

function accuracy() {
  if (!state.session.rounds) return 0;
  return (100 * state.session.matches) / state.session.rounds;
}

function pool() {
  if (state.settings.mode === "numbers") {
    return Array.from({ length: state.settings.numberMax }, (_, i) => i + 1);
  }
  return state.settings.colorCount === 3 ? ["black", "white", "gray"] : ["black", "white"];
}

function playTone(freq, ms, vol = 0.12) {
  if (!state.settings.sound) return;
  const ctx = playTone.ctx || (playTone.ctx = new (window.AudioContext || window.webkitAudioContext)());
  const o = ctx.createOscillator();
  const g = ctx.createGain();
  o.frequency.value = freq;
  o.type = "sine";
  g.gain.value = vol;
  o.connect(g);
  g.connect(ctx.destination);
  o.start();
  g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + ms / 1000);
  o.stop(ctx.currentTime + ms / 1000);
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(path, { ...opts, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.detail || "Error";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

function applyUser(data) {
  if (data.token) {
    state.token = data.token;
    localStorage.setItem("token", data.token);
  }
  state.username = data.username;
  state.records = data.records || { colors: {}, numbers: {} };
}

async function restoreSession() {
  if (!state.token) {
    render();
    return;
  }
  try {
    const me = await api("/api/me");
    applyUser(me);
    state.screen = "menu";
  } catch {
    state.token = "";
    localStorage.removeItem("token");
    state.screen = "auth";
  }
  render();
}

function statsLine(inGame) {
  const r = rec();
  const mode = t(state.settings.mode === "numbers" ? "mode_numbers" : "mode_colors");
  const scope =
    state.settings.mode === "numbers"
      ? `1…${state.settings.numberMax}`
      : t(state.settings.colorCount === 3 ? "colors_3" : "colors_2");
  if (inGame) {
    return `${mode} ${scope} · ${t("streak")}: ${state.session.streak} · ${t("accuracy")}: ${accuracy().toFixed(0)}% · ${t("best")}: ${r.best_streak} · ${t("best_acc")}: ${Number(r.best_accuracy).toFixed(0)}%`;
  }
  return `${mode} ${scope} · ${t("best")}: ${r.best_streak} · ${t("best_acc")}: ${Number(r.best_accuracy).toFixed(0)}%`;
}

function el(html) {
  const box = document.createElement("div");
  box.innerHTML = html.trim();
  return box.firstElementChild;
}

function render() {
  const app = document.getElementById("app");
  app.innerHTML = "";
  if (state.screen === "auth") app.append(viewAuth());
  else if (state.screen === "menu") app.append(viewMenu());
  else if (state.screen === "settings") app.append(viewSettings());
  else if (state.screen === "stats") app.append(viewStats());
  else if (state.screen === "play" || state.screen === "reveal") app.append(viewPlay());
}

function viewAuth() {
  const wrap = el(`<section class="col"></section>`);
  wrap.append(el(`<h1>${t("title")}</h1>`));
  wrap.append(el(`<p class="sub">${t("subtitle")}</p>`));
  const tabs = el(`<div class="tabs"></div>`);
  const loginBtn = el(`<button type="button">${t("login")}</button>`);
  const regBtn = el(`<button type="button">${t("register")}</button>`);
  if (state.authTab === "login") loginBtn.classList.add("active");
  else regBtn.classList.add("active");
  loginBtn.onclick = () => {
    state.authTab = "login";
    state.error = "";
    render();
  };
  regBtn.onclick = () => {
    state.authTab = "register";
    state.error = "";
    render();
  };
  tabs.append(loginBtn, regBtn);
  wrap.append(tabs);

  const form = el(`<form class="form"></form>`);
  form.innerHTML = `
    <label>${t("name")}</label>
    <input name="username" autocomplete="username" maxlength="24" required />
    <label>${t("password")}</label>
    <input name="password" type="password" autocomplete="${state.authTab === "login" ? "current-password" : "new-password"}" minlength="4" required />
    <p class="error">${state.error}</p>
    <button class="wide" type="submit">${state.authTab === "login" ? t("submitLogin") : t("submitReg")}</button>
  `;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    state.error = "";
    try {
      const data = await api(state.authTab === "login" ? "/api/login" : "/api/register", {
        method: "POST",
        body: JSON.stringify({
          username: String(fd.get("username") || "").trim(),
          password: String(fd.get("password") || ""),
        }),
      });
      applyUser(data);
      state.screen = "menu";
      render();
    } catch (err) {
      state.error = err.message;
      render();
    }
  };
  wrap.append(form);
  wrap.append(langToggle());
  return wrap;
}

function langToggle() {
  const b = el(`<button type="button" class="small">${state.lang === "ru" ? "EN" : "RU"}</button>`);
  b.onclick = () => {
    state.lang = state.lang === "ru" ? "en" : "ru";
    localStorage.setItem("lang", state.lang);
    render();
  };
  return b;
}

function viewMenu() {
  const wrap = el(`<section class="col"></section>`);
  wrap.append(el(`<p class="stats">${statsLine(false)}</p>`));
  wrap.append(el(`<h1>${t("title")}</h1>`));
  wrap.append(el(`<p class="sub">${t("subtitle")}</p>`));
  wrap.append(el(`<p class="user-line">${state.username}</p>`));
  const play = el(`<button type="button">${t("play")}</button>`);
  play.onclick = startGame;
  const settings = el(`<button type="button">${t("settings")}</button>`);
  settings.onclick = () => {
    state.screen = "settings";
    render();
  };
  const stats = el(`<button type="button">${t("stats")}</button>`);
  stats.onclick = () => {
    state.statsMode = state.settings.mode;
    state.statsVariant =
      state.settings.mode === "numbers" ? String(state.settings.numberMax) : String(state.settings.colorCount);
    state.screen = "stats";
    loadBoard();
    render();
  };
  const out = el(`<button type="button">${t("logout")}</button>`);
  out.onclick = () => {
    state.token = "";
    state.username = "";
    localStorage.removeItem("token");
    state.screen = "auth";
    render();
  };
  wrap.append(play, settings, stats, out, langToggle());
  return wrap;
}

function viewSettings() {
  const wrap = el(`<section class="col"></section>`);
  wrap.append(el(`<h2>${t("settings")}</h2>`));
  wrap.append(el(`<p class="hint">${t("mode")}</p>`));
  const modes = el(`<div class="row"></div>`);
  const c = el(`<button type="button">${t("mode_colors")}</button>`);
  const n = el(`<button type="button">${t("mode_numbers")}</button>`);
  if (state.settings.mode === "colors") c.classList.add("active");
  else n.classList.add("active");
  c.onclick = () => {
    state.settings.mode = "colors";
    render();
  };
  n.onclick = () => {
    state.settings.mode = "numbers";
    render();
  };
  modes.append(c, n);
  wrap.append(modes);

  if (state.settings.mode === "colors") {
    wrap.append(el(`<p class="hint">${t("mode_colors")}</p>`));
    const row = el(`<div class="row"></div>`);
    const a = el(`<button type="button">${t("colors_2")}</button>`);
    const b = el(`<button type="button">${t("colors_3")}</button>`);
    if (state.settings.colorCount === 2) a.classList.add("active");
    else b.classList.add("active");
    a.onclick = () => {
      state.settings.colorCount = 2;
      render();
    };
    b.onclick = () => {
      state.settings.colorCount = 3;
      render();
    };
    row.append(a, b);
    wrap.append(row);
  } else {
    wrap.append(el(`<p class="hint">${t("number_max")}</p>`));
    const row = el(`<div class="row"></div>`);
    const minus = el(`<button type="button" class="small">−</button>`);
    const label = el(`<button type="button" disabled>1 … ${state.settings.numberMax}</button>`);
    const plus = el(`<button type="button" class="small">+</button>`);
    minus.onclick = () => {
      state.settings.numberMax = Math.max(2, state.settings.numberMax - 1);
      render();
    };
    plus.onclick = () => {
      state.settings.numberMax = Math.min(10, state.settings.numberMax + 1);
      render();
    };
    row.append(minus, label, plus);
    wrap.append(row);
  }

  wrap.append(el(`<p class="hint">${t("language")}: ${state.lang === "ru" ? "Русский" : "English"}</p>`));
  wrap.append(langToggle());
  const sound = el(
    `<button type="button">${t("sound")}: ${t(state.settings.sound ? "on" : "off")}</button>`
  );
  sound.onclick = () => {
    state.settings.sound = !state.settings.sound;
    render();
  };
  wrap.append(sound);
  const back = el(`<button type="button">${t("back")}</button>`);
  back.onclick = () => {
    state.screen = "menu";
    render();
  };
  wrap.append(back);
  return wrap;
}

async function loadBoard() {
  try {
    state.leaderboard = await api(
      `/api/leaderboard?mode=${encodeURIComponent(state.statsMode)}&variant=${encodeURIComponent(state.statsVariant)}`
    );
  } catch {
    state.leaderboard = { top: [], me: { best_streak: 0, best_accuracy: 0 } };
  }
  if (state.screen === "stats") render();
}

function viewStats() {
  const wrap = el(`<section class="col"></section>`);
  wrap.append(el(`<h2>${t("stats")}</h2>`));
  const modes = el(`<div class="row"></div>`);
  const c = el(`<button type="button">${t("mode_colors")}</button>`);
  const n = el(`<button type="button">${t("mode_numbers")}</button>`);
  if (state.statsMode === "colors") c.classList.add("active");
  else n.classList.add("active");
  c.onclick = () => {
    state.statsMode = "colors";
    state.statsVariant = "2";
    loadBoard();
    render();
  };
  n.onclick = () => {
    state.statsMode = "numbers";
    state.statsVariant = "2";
    loadBoard();
    render();
  };
  modes.append(c, n);
  wrap.append(modes);

  const variants = el(`<div class="row"></div>`);
  const keys = state.statsMode === "colors" ? ["2", "3"] : Array.from({ length: 9 }, (_, i) => String(i + 2));
  keys.forEach((k) => {
    const label = state.statsMode === "colors" ? t(k === "3" ? "colors_3" : "colors_2") : `1…${k}`;
    const b = el(`<button type="button" class="small">${label}</button>`);
    if (state.statsVariant === k) b.classList.add("active");
    b.onclick = () => {
      state.statsVariant = k;
      loadBoard();
      render();
    };
    variants.append(b);
  });
  wrap.append(variants);

  const board = state.leaderboard;
  if (!board) {
    wrap.append(el(`<p class="empty">…</p>`));
  } else if (!board.top.length) {
    wrap.append(el(`<p class="empty">${t("emptyTop")}</p>`));
  } else {
    const table = el(`<div class="table-wrap"><table>
      <thead><tr><th>${t("place")}</th><th>${t("player")}</th><th>${t("best")}</th><th>${t("best_acc")}</th></tr></thead>
      <tbody></tbody>
    </table></div>`);
    const tb = table.querySelector("tbody");
    board.top.forEach((row) => {
      const tr = document.createElement("tr");
      if (row.username === state.username) tr.classList.add("me");
      tr.innerHTML = `<td>${row.place}</td><td>${escapeHtml(row.username)}</td><td>${row.best_streak}</td><td>${Number(row.best_accuracy).toFixed(0)}%</td>`;
      tb.append(tr);
    });
    wrap.append(table);
  }

  const back = el(`<button type="button">${t("back")}</button>`);
  back.onclick = () => {
    state.screen = "menu";
    render();
  };
  wrap.append(back);
  return wrap;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function startGame() {
  state.session = { streak: 0, rounds: 0, matches: 0 };
  startRound();
}

function startRound() {
  const p = pool();
  state.round = {
    answer: p[Math.floor(Math.random() * p.length)],
    chosen: null,
    matched: null,
    revealing: false,
  };
  state.screen = "play";
  render();
}

async function choose(value) {
  if (state.screen !== "play") return;
  const matched = value === state.round.answer;
  state.round.chosen = value;
  state.round.matched = matched;
  state.session.rounds += 1;
  if (matched) {
    state.session.streak += 1;
    state.session.matches += 1;
    playTone(523, 220, 0.16);
  } else {
    state.session.streak = 0;
    playTone(196, 260, 0.12);
  }
  state.screen = "reveal";
  render();
  await pushScore();
  setTimeout(() => {
    if (state.screen === "reveal") startRound();
  }, 1400);
}

async function pushScore() {
  try {
    const data = await api("/api/score", {
      method: "POST",
      body: JSON.stringify({
        mode: state.settings.mode,
        variant: state.settings.mode === "numbers" ? String(state.settings.numberMax) : String(state.settings.colorCount),
        streak: state.session.streak,
        accuracy: Number(accuracy().toFixed(1)),
      }),
    });
    const mode = state.settings.mode;
    const key = mode === "numbers" ? String(state.settings.numberMax) : String(state.settings.colorCount);
    state.records[mode] = state.records[mode] || {};
    state.records[mode][key] = data.record;
  } catch {
    /* keep playing locally if network drops */
  }
}

function endGame() {
  state.session = { streak: 0, rounds: 0, matches: 0 };
  state.screen = "menu";
  render();
}

function viewPlay() {
  const wrap = el(`<section class="play"></section>`);
  wrap.append(el(`<p class="stats">${statsLine(true)}</p>`));
  const prompt = t(state.settings.mode === "numbers" ? "prompt_number" : "prompt_color");
  wrap.append(el(`<p class="sub" style="margin-top:8px">${prompt}</p>`));
  wrap.append(el(`<p class="hint">${t("hint")}</p>`));

  const stage = el(`<div class="play-stage"></div>`);
  if (state.screen === "reveal") {
    const v = el(`<div class="verdict ${state.round.matched ? "good" : "miss"}">${state.round.matched ? t("match") : t("no_match")}</div>`);
    stage.append(v);
    if (state.settings.mode === "numbers") {
      const ball = el(`<div class="ball number ${state.round.matched ? "hit" : ""}">${state.round.answer}</div>`);
      stage.append(ball);
    } else {
      const ball = el(`<div class="ball ${state.round.answer} ${state.round.matched ? "hit" : ""}"></div>`);
      stage.append(ball);
      stage.append(el(`<p class="ball-name">${COLORS[state.round.answer][state.lang]}</p>`));
    }
  }
  wrap.append(stage);

  const choices = el(`<div class="choices"></div>`);
  pool().forEach((item) => {
    let b;
    if (state.settings.mode === "numbers") {
      b = el(`<button type="button" class="num-choice">${item}</button>`);
      if (state.round.chosen === item) b.classList.add("chosen");
    } else {
      b = el(`<button type="button" class="swatch ${item}" aria-label="${item}"></button>`);
      if (state.round.chosen === item) b.classList.add("chosen");
    }
    b.onclick = () => choose(item);
    choices.append(b);
  });
  wrap.append(choices);
  const menu = el(`<button type="button">${t("to_menu")}</button>`);
  menu.onclick = endGame;
  wrap.append(menu);
  return wrap;
}

restoreSession();
