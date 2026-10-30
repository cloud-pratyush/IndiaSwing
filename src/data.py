import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

FIELDS = ["Open", "High", "Low", "Close", "Volume"]


def download_all(symbols, period="2y", chunk=40, retries=3):
    """Batch download. Returns ({symbol: OHLCV df}, [failed symbols])."""
    out, failed = {}, []
    symbols = list(dict.fromkeys(symbols))
    for i in range(0, len(symbols), chunk):
        part = symbols[i:i + chunk]
        raw = None
        for attempt in range(retries):
            try:
                raw = yf.download(part, period=period, group_by="ticker", auto_adjust=True,
                                  progress=False, threads=True)
                if raw is not None and not raw.empty:
                    break
            except Exception as exc:  # network / rate limit
                print(f"  download retry {attempt + 1} for chunk {i}: {exc}")
            time.sleep(3 * (attempt + 1))
        if raw is None or raw.empty:
            failed.extend(part)
            continue
        for s in part:
            try:
                df = raw[s] if isinstance(raw.columns, pd.MultiIndex) else raw
                df = df[FIELDS].dropna(subset=["Close"])
                if df.empty:
                    raise ValueError("empty")
                out[s] = df
            except Exception:
                failed.append(s)
    return out, failed


def next_earnings(symbol):
    """Next earnings date (date) or None. Best effort; Yahoo data for NSE stocks can be sparse."""
    try:
        cal = yf.Ticker(symbol).calendar
        dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if dates:
            upcoming = [d for d in dates if d >= datetime.utcnow().date()]
            return min(upcoming) if upcoming else None
    except Exception:
        pass
    return None


def recent_earnings(symbol, today, days=3):
    """Date of an earnings report within the last `days` days, else None. Best effort."""
    try:
        ed = yf.Ticker(symbol).get_earnings_dates(limit=8)
        if ed is None or ed.empty:
            return None
        for ts in ed.index:
            d = ts.date()
            if 0 <= (today - d).days <= days:
                return d
    except Exception:
        pass
    return None


def drop_partial_bar(df, now_local, cutoff_minutes):
    """Remove today's bar if the run happens before the market-close cutoff (unfinished candle)."""
    if len(df) and df.index[-1].date() == now_local.date() and now_local.hour * 60 + now_local.minute < cutoff_minutes:
        return df.iloc[:-1]
    return df


def expected_last_session(now_local):
    """Most recent weekday strictly before today (local). Exchange holidays can make data legitimately older."""
    d = now_local.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d
