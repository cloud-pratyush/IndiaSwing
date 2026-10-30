import math

import numpy as np
import pandas as pd


def _f(x, default=0.0):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(x) else x


def _clip01(x):
    return min(max(_f(x), 0.0), 1.0)


def metrics_frame(frames, bench_close):
    """One row of ranking inputs per ticker (percentiles are across the full liquid universe)."""
    rows = {}
    for t, df in frames.items():
        last = df.iloc[-1]
        rs = (df["Close"] / bench_close.reindex(df.index).ffill()).dropna()
        rs_up = bool(len(rs) > 50 and rs.iloc[-1] > rs.rolling(50).mean().iloc[-1])
        rows[t] = {
            "roc63": last["ROC63"],
            "roc126": last["ROC126"],
            "adx": last["ADX"],
            "stack": bool(last["Close"] > last["SMA50"] > last["SMA200"]),
            "near_high": last["Close"] / last["High52"] if last["High52"] else np.nan,
            "vol_ratio": last["Volume"] / last["Vol_Avg"] if last["Vol_Avg"] else np.nan,
            "obv_up": bool(last["OBV_Up"]),
            "rs_up": rs_up,
        }
    m = pd.DataFrame(rows).T
    m["rs_pct"] = (m["roc63"].astype(float).rank(pct=True) + m["roc126"].astype(float).rank(pct=True)) / 2
    return m


def _rs(m):
    return 0.5 * _f(m["rs_pct"]) + 0.5 * float(bool(m["rs_up"]))


def _trend(m):
    return 0.5 * float(bool(m["stack"])) + 0.5 * _clip01((_f(m["adx"]) - 15) / 20)


def _prox(m):
    return _clip01((_f(m["near_high"]) - 0.8) / 0.2)


def signal_score(setup, m, df, cfg):
    """Setup-specific 0-100 score plus a breakdown [{n, v, w}] (v = 0..1 component, w = weight)."""
    last = df.iloc[-1]
    close = _f(last["Close"])
    atr = _f(last["ATR"], 1e-9) or 1e-9
    vr = _f(m["vol_ratio"])
    rs, trend, prox = _rs(m), _trend(m), _prox(m)
    obv = float(bool(m["obv_up"]))
    sma200 = _f(last["SMA200"])
    above200 = float(sma200 > 0 and close > sma200)

    if setup == "breakout":
        parts = [("Relative strength", rs, 0.30), ("Trend quality", trend, 0.20),
                 ("Volume surge", _clip01((vr - 1) / 2), 0.20), ("Near 52-week high", prox, 0.20),
                 ("OBV rising", obv, 0.10)]
    elif setup == "pullback":
        tight = _clip01(1 - abs(close - _f(last["EMA21"])) / atr / 1.5)
        parts = [("Relative strength", rs, 0.30), ("Trend quality", trend, 0.25),
                 ("Tight to 21-EMA", tight, 0.15), ("Volume dry-up", _clip01(1 - vr), 0.15),
                 ("Near 52-week high", prox, 0.15)]
    elif setup == "mean_reversion":
        c = cfg["setups"]["mean_reversion"]
        parts = [("Oversold depth", _clip01((c["rsi_max"] - _f(last["RSI"], 50)) / 20), 0.30),
                 ("Long-term trend intact", above200, 0.25),
                 ("Reversal candle strength", _clip01((close - _f(last["Open"])) / atr), 0.20),
                 ("Relative strength floor", rs, 0.15), ("Capitulation volume", _clip01((vr - 1) / 2), 0.10)]
    elif setup == "squeeze":
        q = cfg["setups"]["squeeze"]
        minw = _f(df["BB_Width"].rolling(q["lookback"]).min().iloc[-1], 1e-9) or 1e-9
        ratio = _f(last["BB_Width"]) / minw
        tight = _clip01(1 - (ratio - 1) / max(q["width_tol"] - 1, 1e-9))
        parts = [("Squeeze tightness", tight, 0.25), ("Trend quality", trend, 0.25),
                 ("Relative strength", rs, 0.25), ("OBV rising", obv, 0.15), ("Near 52-week high", prox, 0.10)]
    else:  # shock: informational only
        parts = [("Relative strength", rs, 0.40), ("Above 200-day average", above200, 0.30),
                 ("Volume spike", _clip01((vr - 1) / 3), 0.30)]

    score = round(100 * sum(v * w for _, v, w in parts), 1)
    return score, [{"n": n, "v": round(v, 2), "w": w} for n, v, w in parts]


def status_for(passed, earnings_soon):
    """signal | wait (earnings soon) | watch (shock only) | filtered (failed every gate)."""
    if not passed:
        return "filtered"
    if earnings_soon:
        return "wait"
    if all(s == "shock" for s in passed):
        return "watch"
    return "signal"


def gate_reason(setup, direction, vol, sector_ok, cfg):
    g = cfg["gating"]
    if setup not in g["regime_allowed"][direction]:
        return f"not allowed in {direction} regime"
    if vol is not None and vol > g["vix_block"] and setup in ("breakout", "pullback"):
        return f"{cfg['market']['vol_name']} {vol:.0f} above {g['vix_block']}"
    if setup in g["sector_must_beat_spy"] and not sector_ok:
        return f"sector lagging {cfg['market']['name']}"
    return None


def trade_plan(last, cfg):
    t, a = cfg["trade_plan"], cfg["account"]
    close, atr = float(last["Close"]), float(last["ATR"])
    stop = close - t["stop_atr_mult"] * atr
    risk = close - stop
    if risk <= 0 or stop <= 0:
        return None
    target = close + t["reward_risk"] * risk
    shares = math.floor(min(a["size"] * a["risk_pct"] / risk, a["size"] * a["max_position_pct"] / close))
    return {
        "entry": round(close, 2),
        "stop": round(stop, 2),
        "target": round(target, 2),
        "rr": t["reward_risk"],
        "shares": max(shares, 0),
        "risk_amt": round(max(shares, 0) * risk, 2),
    }
