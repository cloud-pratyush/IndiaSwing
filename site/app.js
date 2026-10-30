const $ = (s) => document.querySelector(s);
const THEMES = {
  dark: { bg: "#161b23", text: "#98a2b3", grid: "#262d38" },
  light: { bg: "#ffffff", text: "#667085", grid: "#e3e6ec" },
};
let T = THEMES.light;
function currentMode() {
  return document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
function applyTheme(mode, persist) {
  document.documentElement.dataset.theme = mode;
  T = THEMES[mode];
  $("#theme-btn").textContent = mode === "dark" ? "☀ Light" : "☾ Dark";
  if (persist) { try { localStorage.setItem("theme", mode); } catch { /* ignore */ } }
}
(() => {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch { /* ignore */ }
  applyTheme(saved === "light" || saved === "dark" ? saved : currentMode(), false);
})();
const PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2",
                 "#db2777", "#65a30d", "#475569", "#ea580c", "#0d9488"];
const LABELS = {
  breakout: "Momentum Breakout", mean_reversion: "Mean Reversion", squeeze: "Volatility Squeeze",
  pullback: "Trend Pullback", shock: "Momentum Shock",
};
const SHORT = { breakout: "BRK", mean_reversion: "MR", squeeze: "SQZ", pullback: "PB", shock: "SHK" };
const STATUSES = [
  ["signal", "Signals"],
  ["wait", "Wait: earnings soon"],
  ["watch", "Watch only (shock)"],
  ["filtered", "Filtered by gates"],
];
// dir: -1 = highest first, 1 = lowest first
const SORTS = {
  rs: { label: "RS percentile", get: (r) => r.rs_pct, dir: -1 },
  chg: { label: "Change %", get: (r) => r.chg, dir: -1 },
  rsi: { label: "RSI", get: (r) => r.rsi, dir: -1 },
  vol: { label: "Volume ×", get: (r) => r.vol_ratio, dir: -1 },
  adx: { label: "ADX (trend strength)", get: (r) => r.adx, dir: -1 },
  atr: { label: "ATR % (volatility)", get: (r) => r.atr_pct, dir: -1 },
  high: { label: "Nearest 52-week high", get: (r) => r.dist_high, dir: -1 },
  score: { label: "Score (experimental)", get: (r) => r.score, dir: -1 },
  earn: { label: "Days to earnings", get: (r) => (r.earnings ? r.earnings.days : null), dir: 1 },
  close: { label: "Close", get: (r) => r.close, dir: -1 },
  ticker: { label: "Ticker", get: (r) => r.ticker, dir: 1 },
};
const COLUMNS = [["ticker", "Ticker"], ["close", "Close"], ["chg", "Chg"], ["rsi", "RSI"], ["vol", "Vol"], ["rs", "RS"]];
const FILTER_KEY = "india_filters";   // separate from the US dashboard, which shares this site's origin
let CUR = "₹";
const money = (x) => Number(x).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const cache = {};
const state = { rows: [], visible: [], selected: null, token: 0, filters: loadFilters() };

function loadFilters() {
  const d = { setups: Object.keys(LABELS), sector: "all", hideEarn: true, showFiltered: false, sortKey: "rs", sortDir: -1 };
  try {
    const s = JSON.parse(localStorage.getItem(FILTER_KEY) || "null");
    return s ? { ...d, ...s } : d;
  } catch { return d; }
}
function saveFilters() {
  try { localStorage.setItem(FILTER_KEY, JSON.stringify(state.filters)); } catch { /* ignore */ }
}

async function getJSON(path) {
  if (!cache[path]) {
    cache[path] = fetch(`data/${path}?v=${Date.now()}`).then((r) => {
      if (!r.ok) throw new Error(`${path}: ${r.status}`);
      return r.json();
    });
  }
  return cache[path];
}

const pct = (x) => (x == null ? "–" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`);
const cls = (x) => (x == null ? "" : x >= 0 ? "up" : "down");

/* ---------- charts ---------- */
function makeChart(el, height) {
  el.innerHTML = "";
  const chart = LightweightCharts.createChart(el, {
    width: el.clientWidth, height,
    layout: { background: { color: T.bg }, textColor: T.text },
    grid: { vertLines: { color: T.grid }, horzLines: { color: T.grid } },
    rightPriceScale: { borderColor: T.grid },
    timeScale: { borderColor: T.grid, fixLeftEdge: true, fixRightEdge: true },
  });
  if (el._ro) el._ro.disconnect();
  el._ro = new ResizeObserver(() => { try { chart.applyOptions({ width: el.clientWidth }); } catch { /* disposed */ } });
  el._ro.observe(el);
  return chart;
}

function priceChart(el, bars, { candles = false, sma200 = false, mini = false, lines = [] } = {}) {
  const chart = makeChart(el, el.clientHeight || 200);
  chart.priceScale("right").applyOptions({ scaleMargins: { top: 0.1, bottom: 0.25 } });
  const common = { priceLineVisible: false, lastValueVisible: !mini };
  const main = candles
    ? chart.addCandlestickSeries({ upColor: "#16a34a", downColor: "#dc2626", borderVisible: false,
                                   wickUpColor: "#16a34a", wickDownColor: "#dc2626", ...common })
    : chart.addLineSeries({ color: "#2563eb", lineWidth: 2, ...common });
  main.setData(bars.map((b) => candles
    ? { time: b.t, open: b.o, high: b.h, low: b.l, close: b.c }
    : { time: b.t, value: b.c }));
  const line = (key, color, style = 0) => {
    const s = chart.addLineSeries({ color, lineWidth: 1, lineStyle: style, priceLineVisible: false, lastValueVisible: false });
    s.setData(bars.filter((b) => b[key] != null).map((b) => ({ time: b.t, value: b[key] })));
  };
  line("s50", "#f59e0b");
  if (sma200) line("s200", "#a855f7");
  line("bu", "#94a3b8", 2);
  line("bl", "#94a3b8", 2);
  lines.forEach((l) => main.createPriceLine({ price: l.price, color: l.color, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: l.title }));
  const vol = chart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false });
  chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  vol.setData(bars.map((b, i) => ({
    time: b.t, value: b.v,
    color: i > 0 && b.c < bars[i - 1].c ? "rgba(220,38,38,.45)" : "rgba(22,163,74,.45)",
  })));
  chart.timeScale().fitContent();
  return chart;
}

function rsiChart(el, bars) {
  const chart = makeChart(el, el.clientHeight || 90);
  const s = chart.addLineSeries({ color: "#7c3aed", lineWidth: 1.5, priceLineVisible: false, lastValueVisible: true });
  s.setData(bars.filter((b) => b.rsi != null).map((b) => ({ time: b.t, value: b.rsi })));
  [30, 70].forEach((p) => s.createPriceLine({ price: p, color: "#94a3b8", lineWidth: 1, lineStyle: 2, axisLabelVisible: false }));
  chart.timeScale().fitContent();
  return chart;
}

function spark(values) {
  const v = values.filter((x) => x != null);
  if (v.length < 2) return "";
  const lo = Math.min(...v), hi = Math.max(...v), w = 56, h = 22;
  const pts = v.map((x, i) => `${(i / (v.length - 1) * w).toFixed(1)},${(h - ((x - lo) / (hi - lo || 1)) * h).toFixed(1)}`).join(" ");
  const color = v[v.length - 1] >= v[0] ? "var(--up)" : "var(--down)";
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline fill="none" stroke="${color}" stroke-width="1.5" points="${pts}"/></svg>`;
}

/* ---------- left column ---------- */
async function renderMarket(m) {
  const s = await getJSON("sectors.json");
  priceChart($("#spy-chart"), await getJSON("charts/BENCH.json"), { sma200: true });
  const rc = m.direction === "Bull" ? "up" : m.direction === "Bear" ? "down" : "";
  $("#regime-box").innerHTML = `<div class="kv">
    <span>Regime</span><b class="${rc}">${m.regime}</b>
    <span>${m.name} close</span><span>${money(m.spy_close)}</span>
    <span>SMA50 / SMA200</span><span>${money(m.sma50)} / ${money(m.sma200)}</span>
    <span>Above SMA50 / 200</span><span>${m.breadth50}% / ${m.breadth200}%</span>
    <span>${m.vol_name}</span><span>${m.vix ?? "–"} ${m.vix_trend ? `(${m.vix_trend})` : ""}</span>
    <span>Data as of</span><span>${m.last_bar}</span></div>`;

  const chart = makeChart($("#sector-chart"), 200);
  const legend = [];
  Object.entries(s.series).forEach(([key, pts], i) => {
    const color = PALETTE[i % PALETTE.length];
    const ser = chart.addLineSeries({ color, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false });
    ser.setData(pts.map((p) => ({ time: p.t, value: p.v })));
    legend.push(`<span><i style="background:${color}"></i>${key}</span>`);
  });
  chart.priceScale("right").applyOptions({ scaleMargins: { top: 0.1, bottom: 0.1 } });
  chart.timeScale().fitContent();
  $("#sector-legend").innerHTML = legend.join("");
  $("#sector-table").innerHTML = `<tr><th>Sector</th><th>3M</th><th>1M</th><th>1W</th></tr>` +
    s.table.map((r) => `<tr><td>${r.name}</td><td class="${cls(r.r3m)}">${pct(r.r3m)}</td>
      <td class="${cls(r.r1m)}">${pct(r.r1m)}</td><td class="${cls(r.r1w)}">${pct(r.r1w)}</td></tr>`).join("");
}

/* ---------- filters and sorting ---------- */
function rowVisible(r) {
  const f = state.filters;
  const keys = [...new Set([...r.setups, ...Object.keys(r.filtered)])];
  if (!keys.some((k) => f.setups.includes(k))) return false;
  if (f.sector !== "all" && r.sector !== f.sector) return false;
  if (r.status === "wait") return !f.hideEarn;
  if (r.status === "filtered") return f.showFiltered;
  return true;
}

function sortRows(rows) {
  const s = SORTS[state.filters.sortKey] || SORTS.rs;
  const d = state.filters.sortDir;
  return rows.slice().sort((a, b) => {
    const x = s.get(a), y = s.get(b);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (x < y ? -1 : x > y ? 1 : 0) * d;
  });
}

function syncSortControls() {
  $("#f-sort").value = state.filters.sortKey;
  $("#f-dir").textContent = state.filters.sortDir < 0 ? "High → low" : "Low → high";
}

function setSort(key) {
  const f = state.filters;
  if (f.sortKey === key) f.sortDir *= -1;
  else { f.sortKey = key; f.sortDir = SORTS[key].dir; }
  syncSortControls();
  onFilterChange();
}

function initFilters(rules) {
  const f = state.filters;
  $("#chips-setup").innerHTML = Object.keys(LABELS).map((k) =>
    `<button class="chip ${f.setups.includes(k) ? "on" : ""}" data-k="${k}" title="${LABELS[k]}">${SHORT[k]} · ${LABELS[k]}</button>`).join("");
  document.querySelectorAll("#chips-setup .chip").forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.k;
    f.setups = f.setups.includes(k) ? f.setups.filter((x) => x !== k) : [...f.setups, k];
    b.classList.toggle("on", f.setups.includes(k));
    onFilterChange();
  }));
  const sectors = [...new Set(state.rows.map((r) => r.sector))].sort();
  $("#f-sector").innerHTML = `<option value="all">All sectors</option>` + sectors.map((s) => `<option>${s}</option>`).join("");
  $("#f-sector").value = sectors.includes(f.sector) ? f.sector : "all";
  $("#f-sort").innerHTML = Object.entries(SORTS).map(([k, s]) => `<option value="${k}">Sort: ${s.label}</option>`).join("");
  if (!SORTS[f.sortKey]) { f.sortKey = "rs"; f.sortDir = -1; }
  syncSortControls();
  $("#f-earn").checked = f.hideEarn;
  $("#show-filtered").checked = f.showFiltered;
  $("#f-earn").parentElement.lastChild.textContent = ` hide earnings ≤${rules.earnings_days}d`;
  $("#f-sector").addEventListener("change", (e) => { f.sector = e.target.value; onFilterChange(); });
  $("#f-sort").addEventListener("change", (e) => { f.sortKey = e.target.value; f.sortDir = SORTS[f.sortKey].dir; syncSortControls(); onFilterChange(); });
  $("#f-dir").addEventListener("click", () => { f.sortDir *= -1; syncSortControls(); onFilterChange(); });
  $("#f-earn").addEventListener("change", (e) => { f.hideEarn = e.target.checked; onFilterChange(); });
  $("#show-filtered").addEventListener("change", (e) => { f.showFiltered = e.target.checked; onFilterChange(); });
}

function onFilterChange() {
  saveFilters();
  renderRanking();
  renderSections();
}

/* ---------- ranking table ---------- */
function renderRanking() {
  const f = state.filters;
  state.visible = [];
  let body = "";
  for (const [status, title] of STATUSES) {
    const rows = sortRows(state.rows.filter((r) => r.status === status && rowVisible(r)));
    if (!rows.length) continue;
    body += `<tr class="group"><td colspan="7">${title} (${rows.length})</td></tr>`;
    for (const r of rows) {
      state.visible.push(r.ticker);
      const tags = r.setups.map((s) => `<span class="tag" title="${LABELS[s]}">${SHORT[s]}</span>`).join("") +
        Object.keys(r.filtered).map((s) => `<span class="tag off" title="${LABELS[s]}: ${r.filtered[s]}">${SHORT[s]}</span>`).join("") +
        (r.earnings && r.earnings.soon ? `<span class="tag warn">Earn ${r.earnings.days}d</span>` : "") +
        (r.post_earnings ? `<span class="tag warn">Post-earn</span>` : "");
      body += `<tr class="row ${state.selected === r.ticker ? "sel" : ""}" data-t="${r.ticker}">
        <td><b>${r.ticker}</b><div class="tags">${tags}</div></td><td>${r.close}</td>
        <td class="${cls(r.chg)}">${r.chg > 0 ? "+" : ""}${r.chg}%</td><td>${r.rsi}</td><td>${r.vol_ratio}×</td>
        <td>${r.rs_pct ?? "–"}</td><td>${spark(r.spark)}</td></tr>`;
    }
  }
  const arrow = (k) => (f.sortKey === k ? (f.sortDir < 0 ? " ▼" : " ▲") : "");
  const head = `<tr>${COLUMNS.map(([k, t]) => `<th class="sortable" data-s="${k}">${t}${arrow(k)}</th>`).join("")}<th></th></tr>`;
  $("#ranking").innerHTML = head + (body || `<tr><td colspan="7" class="empty">Nothing matches the current filters.</td></tr>`);
  document.querySelectorAll("#ranking th.sortable").forEach((th) => th.addEventListener("click", () => setSort(th.dataset.s)));
  document.querySelectorAll("#ranking tr.row").forEach((tr) => tr.addEventListener("click", () => select(tr.dataset.t)));
}

/* ---------- selection (big chart + detail) ---------- */
function highlight() {
  document.querySelectorAll("[data-t]").forEach((el) => el.classList.toggle("sel", el.dataset.t === state.selected));
}

async function select(ticker, scroll = true) {
  const r = state.rows.find((x) => x.ticker === ticker);
  if (!r) return;
  state.selected = ticker;
  const my = ++state.token;
  if (location.hash !== `#${ticker}`) history.replaceState(null, "", `#${ticker}`);
  highlight();
  renderDetail(r);
  $("#big-title").textContent = `${r.ticker} · ${r.sector}`;
  $("#big-sub").textContent = "6M · SMA50 (orange) · Bollinger 20,2 (dashed)";
  let bars = null;
  try { bars = await getJSON(`charts/${ticker}.json`); } catch { /* handled below */ }
  if (my !== state.token) return;
  if (!bars) {
    $("#big-chart").innerHTML = '<div class="empty">Chart not available for this ticker.</div>';
    $("#big-rsi").innerHTML = "";
    return;
  }
  const p = r.plan;
  const lines = p ? [
    { price: p.entry, color: "#2563eb", title: "entry" },
    { price: p.stop, color: "#dc2626", title: "stop" },
    { price: p.target, color: "#16a34a", title: "target" },
  ] : [];
  priceChart($("#big-chart"), bars, { candles: true, lines });
  rsiChart($("#big-rsi"), bars);
  if (scroll && matchMedia("(max-width: 1100px)").matches) $("#big").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderDetail(r) {
  const p = r.plan;
  const sigs = [...r.setups, ...Object.keys(r.filtered)].map((k) => {
    const s = r.signals[k];
    if (!s) return "";
    const off = r.filtered[k] ? `<span class="tag warn">filtered: ${r.filtered[k]}</span>` : "";
    return `<div class="sig"><h3><span>${LABELS[k]} ${off}</span><span class="muted small">score ${s.score} (experimental)</span></h3>
      <ul class="checks">${s.checks.map((c) => `<li class="${c.ok ? "ok" : "no"}">${c.ok ? "✓" : "✗"} ${c.t}</li>`).join("")}</ul>
      <div class="bars">${s.breakdown.map((b) => `<span>${b.n}</span><span class="bar"><i style="width:${Math.round(b.v * 100)}%"></i></span><span>${Math.round(b.v * b.w * 100)}/${Math.round(b.w * 100)}</span>`).join("")}</div></div>`;
  }).join("");
  $("#detail").innerHTML = `
    <div class="mini-title"><span>${r.ticker} trade plan</span><span class="muted small">RS pctile ${r.rs_pct ?? "–"} · ADX ${r.adx ?? "–"} · ATR ${r.atr_pct ?? "–"}%</span></div>
    ${r.flags.length ? `<div class="flags">${r.flags.map((f) => `<span class="tag warn">${f}</span>`).join("")}</div>` : ""}
    <div class="kv">
      ${p ? `<span>Entry / Stop / Target (${p.rr}R)</span><span>${CUR}${p.entry} / ${CUR}${p.stop} / ${CUR}${p.target}</span>
      <span>Suggested shares (risk ${CUR}${money(p.risk_amt)})</span><span>${p.shares}</span>` : "<span>Trade plan</span><span>n/a</span>"}
      ${r.earnings ? `<span>Next earnings</span><span class="${r.earnings.soon ? "down" : ""}">${r.earnings.date} (${r.earnings.days}d)</span>` : ""}
    </div>${sigs}`;
}

/* ---------- setup sections (cards select into the big chart; no cards for filtered stocks) ---------- */
async function miniCard(parent, r) {
  const card = document.createElement("div");
  card.className = "card";
  card.dataset.t = r.ticker;
  const earn = r.earnings && r.earnings.soon ? ` · Earn ${r.earnings.days}d` : "";
  card.innerHTML = `<div class="mini-title"><span>${r.ticker}</span><span class="muted small">RS ${r.rs_pct ?? "–"}${earn}</span></div><div class="chart"></div>`;
  card.addEventListener("click", () => select(r.ticker));
  parent.appendChild(card);
  try {
    priceChart(card.querySelector(".chart"), await getJSON(`charts/${r.ticker}.json`), { mini: true });
  } catch { card.querySelector(".chart").innerHTML = '<div class="empty">chart unavailable</div>'; }
}

async function renderSections() {
  const setups = await getJSON("setups.json");
  const host = $("#setup-sections");
  host.innerHTML = "";
  for (const [key, s] of Object.entries(setups)) {
    if (!state.filters.setups.includes(key)) continue;
    const rows = s.tickers.map((t) => state.rows.find((r) => r.ticker === t)).filter((r) => r && rowVisible(r));
    const h = document.createElement("h2");
    h.textContent = `${s.label} (${rows.length})`;
    host.appendChild(h);
    if (!rows.length) {
      host.insertAdjacentHTML("beforeend", `<div class="empty">None today${s.filtered ? ` · ${s.filtered} filtered by gates` : ""}</div>`);
      continue;
    }
    const wrap = document.createElement("div");
    wrap.className = "minis";
    host.appendChild(wrap);
    for (const r of rows) await miniCard(wrap, r);
  }
  highlight();
}

/* ---------- init ---------- */
document.addEventListener("keydown", (e) => {
  if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  const v = state.visible;
  if (!v.length) return;
  let i = v.indexOf(state.selected);
  i = e.key === "ArrowDown" ? Math.min(i + 1, v.length - 1) : Math.max(i - 1, 0);
  e.preventDefault();
  select(v[i]);
  const row = document.querySelector(`#ranking tr[data-t="${v[i]}"]`);
  if (row) row.scrollIntoView({ block: "nearest" });
});
window.addEventListener("hashchange", () => {
  const t = location.hash.slice(1);
  if (t && t !== state.selected) select(t);
});

function rulesText(m, rules) {
  const gated = rules.gated_setups.map((k) => LABELS[k]).join(" and ");
  return `Membership rule: a stock is listed when its latest daily bar meets every condition of at least one setup (see its checklist), ` +
    `then passes the gates: the setup must be allowed in the current regime (${m.regime}), and ${gated} also need ${rules.vol_name} ≤ ${rules.vix_block} ` +
    `and a sector beating ${rules.benchmark_name} over 3 months. Earnings within ${rules.earnings_days} days moves a stock to Wait, Momentum Shock is watch-only, ` +
    `and stocks failing every gate appear only under "show filtered".`;
}

async function init() {
  try {
    const [meta, m] = await Promise.all([getJSON("meta.json"), getJSON("market.json")]);
    CUR = meta.rules.currency || CUR;
    $("#updated").textContent = `Updated ${new Date(meta.generated).toLocaleString()}`;
    $("#rules").textContent = rulesText(m, meta.rules);
    state.market = m;
    if (meta.warnings.length) { const b = $("#banner"); b.textContent = meta.warnings.join(" | "); b.hidden = false; }
    state.rows = await getJSON("ranking.json");
    await renderMarket(m);
    initFilters(meta.rules);
    renderRanking();
    const fromHash = location.hash.slice(1);
    const first = state.rows.find((r) => r.ticker === fromHash) || state.rows.find((r) => state.visible.includes(r.ticker)) || state.rows[0];
    if (first) await select(first.ticker);
    else $("#detail").innerHTML = '<div class="empty">No signals today.</div>';
    await renderSections();
  } catch (e) {
    const b = $("#banner"); b.textContent = `Could not load data: ${e.message}`; b.hidden = false;
  }
}

$("#theme-btn").addEventListener("click", async () => {
  applyTheme(currentMode() === "dark" ? "light" : "dark", true);
  if (!state.market) return;
  await renderMarket(state.market);
  if (state.selected) await select(state.selected, false);
  await renderSections();
});

init();
