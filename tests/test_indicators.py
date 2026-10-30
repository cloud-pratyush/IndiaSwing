import numpy as np
import pandas as pd

from src.indicators import adx, rsi, wilder


def test_rsi_all_gains_is_100():
    close = pd.Series(np.arange(1.0, 60.0))
    assert rsi(close).iloc[-1] == 100


def test_rsi_bounds():
    rng = np.random.default_rng(0)
    close = pd.Series(100 + rng.normal(0, 1, 300).cumsum())
    r = rsi(close).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_wilder_of_constant_is_constant():
    s = pd.Series([5.0] * 50)
    assert abs(wilder(s, 14).iloc[-1] - 5.0) < 1e-9


def test_adx_strong_trend_is_high():
    c = pd.Series(np.arange(100.0, 200.0))
    assert adx(c + 1, c - 1, c).iloc[-1] > 40
