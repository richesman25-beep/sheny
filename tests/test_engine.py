from io import StringIO

import numpy as np
import pandas as pd
import pytest

from trading_analysis_system import (
    EducationalTradingEngine, MarketDataSimulator, RiskManager, Settings,
    TechnicalIndicators, backtest, exit_on_bar, load_csv, validate_data,
)


def flat_data(bars=250):
    return pd.DataFrame(dict(open=100., high=101., low=99., close=100., volume=1000.),
                        index=pd.date_range("2025-01-01", periods=bars, freq="h", tz="UTC", name="timestamp"))


@pytest.mark.parametrize("series, expected", [
    (pd.Series(np.arange(30, dtype=float)), 100),
    (pd.Series(np.arange(30, 0, -1, dtype=float)), 0),
    (pd.Series(np.ones(30)), 50),
])
def test_rsi_monotonic_and_flat(series, expected):
    rsi = TechnicalIndicators.calculate_rsi(series)
    assert rsi.iloc[:14].isna().all()
    assert (rsi.iloc[14:] == expected).all()


def test_rsi_wilder_reference():
    prices = pd.Series([44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
                        45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03])
    rsi = TechnicalIndicators.calculate_rsi(prices)
    assert rsi.iloc[14] == pytest.approx(70.464135, abs=1e-5)
    assert rsi.iloc[15] == pytest.approx(66.249619, abs=1e-5)
    assert rsi.iloc[16] == pytest.approx(66.480942, abs=1e-5)


def test_atr_uses_only_past_data():
    df = flat_data()
    df.loc[df.index[-1], "high"] = 200
    atr = TechnicalIndicators.calculate_atr(df)
    assert atr.iloc[:13].isna().all()
    assert (atr.iloc[13:-1] == 2).all()
    assert atr.iloc[-1] == pytest.approx((2 * 13 + 101) / 14)
    pd.testing.assert_series_equal(atr.iloc[:100], TechnicalIndicators.calculate_atr(df.iloc[:100]))


@pytest.mark.parametrize("change", ["duplicate", "nan", "negative", "invalid_high", "unsorted"])
def test_reject_invalid_data(change):
    df = flat_data()
    if change == "duplicate":
        df.index = pd.DatetimeIndex([df.index[0]] * len(df))
    elif change == "nan":
        df.iloc[-1, 0] = np.nan
    elif change == "negative":
        df.iloc[-1, 4] = -1
    elif change == "invalid_high":
        df.iloc[-1, 1] = 98
    else:
        df = df.iloc[::-1]
    with pytest.raises(ValueError):
        validate_data(df)


def test_csv_round_trip_and_sort():
    df = flat_data()
    loaded = load_csv(StringIO(df.iloc[::-1].to_csv(sep=";")))
    pd.testing.assert_frame_equal(loaded, df, check_freq=False)


def test_csv_rejects_duplicate_normalized_columns():
    df = flat_data()
    df["OPEN"] = df["open"]
    with pytest.raises(ValueError, match="uniques"):
        load_csv(StringIO(df.to_csv()))


def test_checklist_requires_both_pullback_and_momentum():
    engine = EducationalTradingEngine()
    row = pd.Series(dict(close=120., ema_20=115., ema_50=110., ema_200=100., rsi=50., atr=2.))
    assert engine.checklist(row)[0] == 0  # momentum seul insuffisant
    row["close"] = 111
    row["rsi"] = 80
    assert engine.checklist(row)[0] == 0  # proximité seule insuffisante
    row["rsi"] = 50
    assert engine.checklist(row)[0] == 1
    assert all(engine.checklist(row)[1].values())


@pytest.mark.parametrize("stop", [98., 102.])
def test_position_risk_includes_costs_and_caps_exposure(stop):
    manager = RiskManager(10000, 1, 0.1, 0.05)
    p = manager.calculate_position(100, stop)
    assert p["risk_amount_usd"] <= 100 + 1e-9
    assert p["units"] * 100 * 1.001 <= 10000 + 1e-9
    very_close = manager.calculate_position(100, 99.999)
    assert very_close["notional_value"] < 10000


@pytest.mark.parametrize("entry, stop", [(0, 1), (1, 1), (np.inf, 2), (100, -1)])
def test_position_rejects_bad_prices(entry, stop):
    with pytest.raises(ValueError):
        RiskManager().calculate_position(entry, stop)


@pytest.mark.parametrize("side, opening, expected", [(1, 100, (95, "stop")),
                                                    (-1, 100, (105, "stop")),
                                                    (1, 90, (90, "gap_stop")),
                                                    (-1, 110, (110, "gap_stop"))])
def test_exit_order_and_gap(side, opening, expected):
    row = pd.Series(dict(open=opening, high=115, low=85))
    assert exit_on_bar(row, side, 95 if side == 1 else 105, 110 if side == 1 else 90) == expected


def test_no_signal_is_not_a_profitable_strategy():
    result = backtest(flat_data())
    assert result["metrics"]["trades"] == 0
    assert result["metrics"]["win_rate_pct"] is None
    assert result["metrics"]["final_balance"] == 10000


def test_backtest_next_open_and_fee_accounting(monkeypatch):
    monkeypatch.setattr(EducationalTradingEngine, "checklist", lambda self, row: (1, {}))
    s = Settings(fee_pct=0.1, slippage_pct=0)
    result = backtest(flat_data(), s)
    trades = result["trades"]
    assert len(trades) == 1
    first = trades.iloc[0]
    assert first.signal_time == flat_data().index[199]
    assert first.entry_time == flat_data().index[200]
    assert first.signal_time < first.entry_time
    assert first.entry == 100
    assert first.reason == "fin_echantillon"
    assert first.pnl == pytest.approx(-first.fees)
    assert result["metrics"]["final_balance"] == pytest.approx(10000 + first.pnl)
    assert result["equity"].iloc[0] == 10000
    assert result["equity"].iloc[-1] == pytest.approx(result["metrics"]["final_balance"])


def test_backtest_slippage_and_short_opt_in(monkeypatch):
    monkeypatch.setattr(EducationalTradingEngine, "checklist", lambda self, row: (-1, {}))
    assert backtest(flat_data())["metrics"]["trades"] == 0
    result = backtest(flat_data(), allow_short=True)
    t = result["trades"].iloc[0]
    assert t.direction == "SHORT"
    assert t.entry < 100 and t.exit > 100
    assert t.pnl < -t.fees


def test_indicators_have_no_future_leakage():
    df = MarketDataSimulator.generate_ohlcv(500)
    engine = EducationalTradingEngine()
    full = engine.indicators(df)
    prefix = engine.indicators(df.iloc[:300])
    pd.testing.assert_frame_equal(full.iloc[:300], prefix)


def test_real_demo_produces_consistent_accounting():
    result = backtest(MarketDataSimulator.generate_ohlcv(1500))
    trades = result["trades"]
    assert len(trades) > 0
    assert (trades.signal_time < trades.entry_time).all()
    assert result["metrics"]["final_balance"] == pytest.approx(10000 + trades.pnl.sum())
    assert (trades.entry_time.iloc[1:].reset_index(drop=True) >
            trades.exit_time.iloc[:-1].reset_index(drop=True)).all()


@pytest.mark.parametrize("kwargs", [{"account_balance": 0}, {"max_risk_pct": -1},
                                    {"reward_ratio": 1}, {"fee_pct": -0.1}, {"slippage_pct": np.nan}])
def test_settings_validation(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)
