import numpy as np
import pandas as pd


def wilder(s, n):
    """Wilder smoothing (RMA), the convention used by most charting platforms."""
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close, n=14):
    delta = close.diff()
    gain = wilder(delta.clip(lower=0), n)
    loss = wilder(-delta.clip(upper=0), n)
    out = 100 - 100 / (1 + gain / loss)
    return out.where(loss != 0, 100.0)


def true_range(h, l, c):
    prev = c.shift(1)
    return pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)


def adx(h, l, c, n=14):
    up, dn = h.diff(), -l.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=c.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=c.index)
    atr = wilder(true_range(h, l, c), n)
    plus_di = 100 * wilder(plus_dm, n) / atr
    minus_di = 100 * wilder(minus_dm, n) / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return wilder(dx, n)


def compute_indicators(df, p):
    df = df.copy()
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]

    df["SMA50"] = c.rolling(p["sma_fast"]).mean()
    df["SMA200"] = c.rolling(p["sma_slow"]).mean()
    df["EMA21"] = c.ewm(span=p["ema_trend"], adjust=False).mean()

    # Bollinger (20, 2) and (80, 2)
    m20 = c.rolling(p["bb_short"]).mean()
    s20 = c.rolling(p["bb_short"]).std()
    df["BB_U20"], df["BB_L20"] = m20 + 2 * s20, m20 - 2 * s20
    df["BB_Width"] = df["BB_U20"] - df["BB_L20"]
    m80 = c.rolling(p["bb_long"]).mean()
    df["BB_L80"] = m80 - 2 * c.rolling(p["bb_long"]).std()

    # ATR (Wilder) and Keltner (EMA20 +/- 1.5 ATR)
    df["ATR"] = wilder(true_range(h, l, c), 14)
    ema20 = c.ewm(span=20, adjust=False).mean()
    df["KC_U"], df["KC_L"] = ema20 + 1.5 * df["ATR"], ema20 - 1.5 * df["ATR"]

    df["RSI"] = rsi(c)
    lo14, hi14 = l.rolling(14).min(), h.rolling(14).max()
    df["Stoch_K"] = 100 * (c - lo14) / (hi14 - lo14)
    df["Stoch_D"] = df["Stoch_K"].rolling(3).mean()
    df["ADX"] = adx(h, l, c)

    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    df["MACD_Hist"] = macd - macd.ewm(span=9, adjust=False).mean()

    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    df["OBV_Up"] = obv > obv.rolling(20).mean()

    df["Vol_Avg"] = v.rolling(20).mean()
    df["Dollar_Vol"] = (c * v).rolling(20).mean()   # turnover in local currency
    df["Range"] = h - l
    df["Range_Avg3"] = df["Range"].shift(1).rolling(3).mean()
    df["Ret"] = c.pct_change()
    df["ROC63"] = c.pct_change(63)
    df["ROC126"] = c.pct_change(126)
    df["High52"] = h.rolling(252, min_periods=200).max()
    return df
