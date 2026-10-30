from src.score import status_for


def test_filtered_when_nothing_passes():
    assert status_for([], False) == "filtered"
    assert status_for([], True) == "filtered"


def test_earnings_soon_waits():
    assert status_for(["breakout"], True) == "wait"


def test_shock_only_is_watch():
    assert status_for(["shock"], False) == "watch"


def test_shock_plus_other_is_signal():
    assert status_for(["shock", "mean_reversion"], False) == "signal"
    assert status_for(["pullback"], False) == "signal"
