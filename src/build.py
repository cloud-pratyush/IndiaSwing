"""Daily build: download NSE data, compute signals, write JSON for the static dashboard.

Usage:  python -m src.build            (writes site/data/*.json)
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .data import download_all, drop_partial_bar, expected_last_session, next_earnings, recent_earnings
from .indicators import compute_indicators
from .regime import breadth, sector_series, sector_table, spy_regime
from .score import gate_reason, metrics_frame, signal_score, status_for, trade_plan
from .setups import SETUP_LABELS, detect_setups

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data"
STATUS_ORDER = {"signal": 0, "wait": 1, "watch": 2, "filtered": 3}


def num(x, nd=2):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else round(x, nd)


def write(name, obj):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def bars_json(df, n):
    d = df.tail(n)
    rows = []
    for ts, r in d.iterrows():
        rows.append({
            "t": ts.strftime("%Y-%m-%d"),
            "o": num(r["Open"]), "h": num(r["High"]), "l": num(r["Low"]), "c": num(r["Close"]),
            "v": int(r["Volume"]) if not math.isnan(r["Volume"]) else 0,
            "s50": num(r["SMA50"]), "s200": num(r["SMA200"]),
            "bu": num(r["BB_U20"]), "bl": num(r["BB_L20"]),
            "rsi": num(r["RSI"], 1),
        })
    return rows


def main():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    mk = cfg["market"]
    now_local = datetime.now(ZoneInfo(mk["timezone"]))
    h, mi = (int(x) for x in mk["close_cutoff"].split(":"))
    cutoff = h * 60 + mi
    suffix, bench, vol_index = mk["ticker_suffix"], mk["benchmark"], mk["vol_index"]
    warnings = []

    sectors = cfg["sectors"]
    ticker_sector = {t: key for key, s in sectors.items() for t in s["tickers"]}
    symbols = ([t + suffix for t in ticker_sector] + [s["index"] for s in sectors.values()]
               + [bench, vol_index])

    print(f"Downloading {len(symbols)} symbols...")
    raw, failed = download_all(symbols, cfg["data"]["period"], cfg["data"]["chunk_size"])
    if failed:
        warnings.append(f"No data for: {', '.join(sorted(set(failed)))}")
    if bench not in raw:
        raise SystemExit(f"{mk['name']} index data unavailable; aborting so yesterday's page is kept.")
    raw = {k: drop_partial_bar(v, now_local, cutoff) for k, v in raw.items()}

    ind = cfg["indicators"]
    bench_df = compute_indicators(raw[bench], ind)
    direction, vol_state = spy_regime(bench_df)
    vol = num(raw[vol_index]["Close"].iloc[-1]) if vol_index in raw else None
    vol_trend = None
    if vol_index in raw and len(raw[vol_index]) > 20:
        vc = raw[vol_index]["Close"]
        vol_trend = "rising" if vc.iloc[-1] > vc.tail(20).mean() else "falling"

    last_bar = bench_df.index[-1].date()
    if last_bar < expected_last_session(now_local):
        warnings.append(f"Data may be stale: latest {mk['name']} bar is {last_bar} (could be an exchange holiday).")

    # Universe: enough history + liquidity filter
    frames, dropped = {}, []
    liq = cfg["liquidity"]
    for t in ticker_sector:
        df = raw.get(t + suffix)
        if df is None or len(df) < cfg["data"]["min_bars"]:
            continue
        df = compute_indicators(df, ind)
        last = df.iloc[-1]
        if last["Close"] < liq["min_price"] or not last["Dollar_Vol"] >= liq["min_turnover"]:
            dropped.append(t)
            continue
        frames[t] = df

    b50, b200 = breadth(frames)
    bench_close = bench_df["Close"]
    metrics = metrics_frame(frames, bench_close)

    # Sector indices; a sector with no data skips the sector rule instead of blocking its stocks
    etf_closes = {k: raw[s["index"]]["Close"] for k, s in sectors.items() if s["index"] in raw}
    missing = [s["index"] for k, s in sectors.items() if k not in etf_closes]
    if missing:
        warnings.append(f"Sector index missing, sector rule skipped: {', '.join(missing)}")
    sec_rows = sector_table(etf_closes, sectors)
    bench_3m = float(bench_close.iloc[-1] / bench_close.iloc[-64] - 1)
    sector_beats = {r["etf"]: (r["r3m"] is not None and r["r3m"] >= bench_3m) for r in sec_rows}

    # Signals
    ranking = []
    for t, df in frames.items():
        found = detect_setups(df, cfg)
        if not found:
            continue
        key = ticker_sector[t]
        m = metrics.loc[t]
        sector_ok = sector_beats.get(key, True)
        passed, filtered = [], {}
        for s in found:
            reason = gate_reason(s, direction, vol, sector_ok, cfg)
            if reason:
                filtered[s] = reason
            else:
                passed.append(s)

        signals = {}
        for s, checks in found.items():
            sc, breakdown = signal_score(s, m, df, cfg)
            signals[s] = {"score": sc, "checks": checks, "breakdown": breakdown}

        pool = passed or list(found)
        top = max(pool, key=lambda s: signals[s]["score"])
        bonus = min(max(len(passed) - 1, 0) * 5, 10)  # confluence
        score = round(min(signals[top]["score"] + bonus, 100), 1)

        last = df.iloc[-1]
        flags = []
        if "shock" in passed:
            flags.append("Watch only: sharp drop, no confirmation (falling-knife risk)")
        for s, why in filtered.items():
            flags.append(f"{SETUP_LABELS[s]} filtered: {why}")
        if not sector_ok:
            flags.append(f"Sector lagging {mk['name']} (3M)")

        ranking.append({
            "ticker": t,
            "sector": sectors[key]["name"],
            "open": num(last["Open"]), "close": num(last["Close"]),
            "chg": num(last["Ret"] * 100),
            "rsi": num(last["RSI"], 1),
            "vol_ratio": num(last["Volume"] / last["Vol_Avg"]),
            "adx": num(last["ADX"], 1),
            "atr_pct": num(last["ATR"] / last["Close"] * 100),
            "dist_high": num((last["Close"] / last["High52"] - 1) * 100, 1),
            "rs_pct": num(m["rs_pct"] * 100, 0),
            "score": score,
            "setups": passed,
            "filtered": filtered,
            "signals": signals,
            "flags": flags,
            "status": None,
            "post_earnings": False,
            "plan": trade_plan(last, cfg),
            "earnings": None,
            "spark": [num(x) for x in df["Close"].tail(30)],
        })

    # Earnings check, only for names with signals; earnings soon -> "wait"
    warn_days = cfg["earnings"]["warn_days"]
    today = now_local.date()
    for r in ranking:
        d = next_earnings(r["ticker"] + suffix)
        soon = False
        if d:
            days = (d - today).days
            soon = 0 <= days <= warn_days
            r["earnings"] = {"date": d.isoformat(), "days": days, "soon": soon}
            if soon:
                r["flags"].insert(0, f"Earnings in {days} day(s): wait until after the report")
        if "shock" in r["signals"]:
            rep = recent_earnings(r["ticker"] + suffix, today)
            if rep:
                r["post_earnings"] = True
                r["flags"].append(f"Likely post-earnings reaction (reported {rep.isoformat()})")
            else:
                r["flags"].append("No recent earnings found: possible news event, check headlines")
        r["status"] = status_for(r["setups"], soon)
    ranking.sort(key=lambda r: (STATUS_ORDER[r["status"]], -(r["rs_pct"] if r["rs_pct"] is not None else -1)))

    # Per-setup cards: every non-filtered stock, best relative strength first, capped
    cap = cfg["output"]["max_per_setup"]
    setups_out = {}
    for key, label in SETUP_LABELS.items():
        members = [r for r in ranking if key in r["setups"]]
        setups_out[key] = {
            "label": label,
            "tickers": [r["ticker"] for r in members[:cap]],
            "filtered": sum(key in r["filtered"] for r in ranking),
        }

    # Charts for every signal ticker (ranking order, capped)
    n = cfg["output"]["chart_bars"]
    for r in ranking[: cfg["output"]["max_chart_tickers"]]:
        write(f"charts/{r['ticker']}.json", bars_json(frames[r["ticker"]], n))
    write("charts/BENCH.json", bars_json(bench_df, n))

    write("market.json", {
        "name": mk["name"],
        "vol_name": mk["vol_name"],
        "regime": f"{direction} {vol_state}",
        "direction": direction,
        "vol_state": vol_state,
        "spy_close": num(bench_close.iloc[-1]),
        "sma50": num(bench_df["SMA50"].iloc[-1]),
        "sma200": num(bench_df["SMA200"].iloc[-1]),
        "breadth50": b50,
        "breadth200": b200,
        "vix": vol,
        "vix_trend": vol_trend,
        "last_bar": last_bar.isoformat(),
        "spy_3m": num(bench_3m * 100),
    })
    write("sectors.json", {"table": sec_rows, "series": sector_series(etf_closes)})
    write("ranking.json", ranking)
    write("setups.json", setups_out)
    write("meta.json", {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "universe": len(frames),
        "excluded_illiquid": dropped,
        "warnings": warnings,
        "rules": {
            "vix_block": cfg["gating"]["vix_block"],
            "earnings_days": warn_days,
            "gated_setups": cfg["gating"]["sector_must_beat_spy"],
            "benchmark_name": mk["name"],
            "vol_name": mk["vol_name"],
            "currency": mk["currency"],
        },
    })
    shown = sum(r["status"] == "signal" for r in ranking)
    print(f"Done: {len(frames)} stocks scanned, {len(ranking)} with setups, {shown} signals. "
          f"Regime {direction} {vol_state}.")


if __name__ == "__main__":
    main()
