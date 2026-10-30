import pandas as pd


def spy_regime(spy):
    """Trend direction and volatility state of the benchmark index."""
    last = spy.iloc[-1]
    if last["Close"] > last["SMA50"] > last["SMA200"]:
        direction = "Bull"
    elif last["Close"] < last["SMA50"] < last["SMA200"]:
        direction = "Bear"
    else:
        direction = "Sideways"
    atr_med = spy["ATR"].rolling(100).median().iloc[-1]
    vol = "Volatile" if spy["ATR"].iloc[-1] > 1.15 * atr_med else "Quiet"
    return direction, vol


def breadth(frames):
    """Share of the universe trading above its SMA50 / SMA200."""
    a50 = [f["Close"].iloc[-1] > f["SMA50"].iloc[-1] for f in frames.values()]
    a200 = [f["Close"].iloc[-1] > f["SMA200"].iloc[-1] for f in frames.values()]
    n = max(len(a50), 1)
    return round(100 * sum(a50) / n, 1), round(100 * sum(a200) / n, 1)


def period_return(close, bars):
    if len(close) <= bars:
        return None
    return float(close.iloc[-1] / close.iloc[-1 - bars] - 1)


def sector_table(etf_closes, sectors):
    rows = []
    for etf, close in etf_closes.items():
        rows.append({
            "etf": etf,
            "name": sectors[etf]["name"],
            "r3m": period_return(close, 63),
            "r1m": period_return(close, 21),
            "r1w": period_return(close, 5),
        })
    rows.sort(key=lambda r: (r["r3m"] is None, -(r["r3m"] or 0)))
    return rows


def sector_series(etf_closes, bars=126):
    """Each sector rebased to 100 over the last `bars` sessions."""
    out = {}
    for etf, close in etf_closes.items():
        c = close.tail(bars)
        if len(c) < 2:
            continue
        base = c.iloc[0]
        out[etf] = [{"t": d.strftime("%Y-%m-%d"), "v": round(float(x / base * 100), 2)}
                    for d, x in c.items()]
    return out
