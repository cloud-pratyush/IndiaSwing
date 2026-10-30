SETUP_LABELS = {
    "breakout": "Momentum Breakout",
    "mean_reversion": "Mean Reversion",
    "squeeze": "Volatility Squeeze",
    "pullback": "Trend Pullback",
    "shock": "Momentum Shock",
}


def detect_setups(df, cfg):
    """Return {setup_key: [{"t": explanation, "ok": True}, ...]} for every setup the latest bar satisfies.

    Each setup is a list of plain-English conditions; a setup fires only when all are true.
    The same list is shown on the dashboard as the "why" checklist.
    """
    s = cfg["setups"]
    last, prev = df.iloc[-1], df.iloc[-2]
    vr = last["Volume"] / last["Vol_Avg"] if last["Vol_Avg"] else float("nan")
    found = {}

    def add(key, checks):
        if all(ok for _, ok in checks):
            found[key] = [{"t": text, "ok": bool(ok)} for text, ok in checks]

    b = s["breakout"]
    atr_pct = last["ATR"] / last["Close"]
    add("breakout", [
        (f"Close {last['Close']:.2f} at/above upper Bollinger {last['BB_U20']:.2f}", last["Close"] >= last["BB_U20"]),
        (f"ATR {atr_pct:.1%} of price (min {b['atr_pct']:.1%})", atr_pct >= b["atr_pct"]),
        (f"Volume {vr:.1f}x 20-day average (min {b['vol_mult']}x)", vr > b["vol_mult"]),
        ("Range wider than the previous 3 days", last["Range"] > last["Range_Avg3"]),
        (f"Above 200-day average {last['SMA200']:.2f}", last["Close"] > last["SMA200"]),
    ])

    m = s["mean_reversion"]
    add("mean_reversion", [
        (f"Close {last['Close']:.2f} near lower 80-day Bollinger {last['BB_L80']:.2f}", last["Close"] <= last["BB_L80"] * m["bb80_tol"]),
        (f"RSI {last['RSI']:.0f} below {m['rsi_max']}", last["RSI"] < m["rsi_max"]),
        (f"Stochastic %K crossed above %D below {m['stoch_max']}",
         prev["Stoch_K"] <= prev["Stoch_D"] and last["Stoch_K"] > last["Stoch_D"] and last["Stoch_K"] < m["stoch_max"]),
        ("Stabilising candle (close above open)", last["Close"] > last["Open"]),
    ])

    p = s["pullback"]
    add("pullback", [
        (f"Uptrend: close {last['Close']:.2f} above SMA50 {last['SMA50']:.2f}", last["Close"] > last["SMA50"]),
        (f"Trend structure: SMA50 {last['SMA50']:.2f} above SMA200 {last['SMA200']:.2f}", last["SMA50"] > last["SMA200"]),
        (f"Trending: ADX {last['ADX']:.0f} (min {p['min_adx']})", last["ADX"] >= p["min_adx"]),
        ("Touched the 21-day EMA and closed back above it",
         last["Low"] <= last["EMA21"] * p["ema_tol"] and last["Close"] >= last["EMA21"]),
        (f"Quiet pullback: volume {vr:.1f}x average (below 1x)", last["Volume"] < last["Vol_Avg"]),
    ])

    q = s["squeeze"]
    min_width = df["BB_Width"].rolling(q["lookback"]).min().iloc[-1]
    ratio = last["BB_Width"] / min_width if min_width else float("nan")
    add("squeeze", [
        (f"Bollinger width {ratio:.2f}x its {q['lookback']}-day low (max {q['width_tol']}x)", ratio <= q["width_tol"]),
        ("Bollinger Bands inside Keltner Channel",
         last["BB_U20"] <= last["KC_U"] and last["BB_L20"] >= last["KC_L"]),
        (f"RSI {last['RSI']:.0f} neutral ({q['rsi_min']}-{q['rsi_max']})", q["rsi_min"] <= last["RSI"] <= q["rsi_max"]),
    ])

    drop = s["shock"]["drop_pct"]
    add("shock", [
        (f"One-day move {last['Ret']:.1%} (threshold {drop:.0%})", last["Ret"] <= drop),
    ])

    return found
