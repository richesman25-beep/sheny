"""Analyse pédagogique OHLCV. Aucun ordre n'est envoyé à un courtier."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path
import json

import numpy as np
import pandas as pd


def validate_data(data: pd.DataFrame, minimum: int = 200) -> pd.DataFrame:
    required = ["open", "high", "low", "close", "volume"]
    if not isinstance(data, pd.DataFrame) or not set(required).issubset(data.columns):
        raise ValueError("Colonnes requises : timestamp, open, high, low, close, volume.")
    if data.columns.has_duplicates:
        raise ValueError("Les noms de colonnes doivent être uniques.")
    if len(data) < minimum:
        raise ValueError(f"Au moins {minimum} bougies sont nécessaires (reçu : {len(data)}).")
    if not isinstance(data.index, pd.DatetimeIndex) or data.index.hasnans:
        raise ValueError("Les dates doivent former un index valide.")
    if data.index.has_duplicates or not data.index.is_monotonic_increasing:
        raise ValueError("Les dates doivent être uniques et classées dans l'ordre chronologique.")
    df = data[required].copy()
    try:
        df = df.apply(pd.to_numeric, errors="raise").astype(float)
    except (ValueError, TypeError) as exc:
        raise ValueError("Les prix et volumes doivent être numériques.") from exc
    if not np.isfinite(df.to_numpy()).all():
        raise ValueError("Données manquantes ou valeurs infinies : corrigez le fichier.")
    if (df[["open", "high", "low", "close"]] <= 0).any().any() or (df.volume < 0).any():
        raise ValueError("Les prix doivent être positifs et les volumes non négatifs.")
    if ((df.high < df[["open", "close", "low"]].max(axis=1)) |
        (df.low > df[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("Bougies incohérentes : high/low ne contiennent pas open et close.")
    return df


def load_csv(source) -> pd.DataFrame:
    """CSV séparé par virgule, point-virgule ou tabulation ; dates converties en UTC."""
    try:
        df = pd.read_csv(source, sep=None, engine="python", encoding="utf-8-sig")
        df.columns = [str(c).strip().lower() for c in df.columns]
        date_col = next((c for c in ("timestamp", "datetime", "date", "time") if c in df), None)
        if date_col is None:
            raise ValueError("Une colonne timestamp (date ISO 8601) est requise.")
        if pd.api.types.is_numeric_dtype(df[date_col]):
            raise ValueError("Utilisez des dates ISO 8601, pas des timestamps numériques.")
        df.index = pd.DatetimeIndex(pd.to_datetime(df.pop(date_col), utc=True, errors="raise"))
        df.index.name = "timestamp"
        return validate_data(df.sort_index())
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError) as exc:
        raise ValueError("CSV illisible : utilisez UTF-8 et les colonnes du modèle.") from exc


class MarketDataSimulator:
    @staticmethod
    def generate_ohlcv(bars=750, start_price=150.0, trend_bias=0.0005, volatility=0.015, seed=42):
        if bars < 2 or start_price <= 0 or volatility <= 0:
            raise ValueError("Paramètres de simulation invalides.")
        rng = np.random.default_rng(seed)
        # Une trajectoire log-normale reste positive, même en forte volatilité.
        closes = start_price * np.exp(np.cumsum(rng.normal(trend_bias, volatility, bars)))
        opens = np.r_[start_price, closes[:-1]]
        highs = np.maximum(opens, closes) * np.exp(np.abs(rng.normal(0, volatility / 2, bars)))
        lows = np.minimum(opens, closes) * np.exp(-np.abs(rng.normal(0, volatility / 2, bars)))
        end = pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(hours=1)
        return pd.DataFrame(dict(open=opens, high=highs, low=lows, close=closes,
                                 volume=rng.lognormal(10, 0.5, bars)),
                            index=pd.date_range(end=end, periods=bars, freq="h", name="timestamp"))


def wilder(series: pd.Series, period=14, start=0) -> pd.Series:
    out = pd.Series(np.nan, index=series.index, dtype=float)
    seed_at = start + period - 1
    if len(series) <= seed_at:
        return out
    out.iloc[seed_at] = series.iloc[start:seed_at + 1].mean()
    for i in range(seed_at + 1, len(series)):
        out.iloc[i] = (out.iloc[i - 1] * (period - 1) + series.iloc[i]) / period
    return out


class TechnicalIndicators:
    @staticmethod
    def calculate_ema(series, period):
        return series.ewm(span=period, adjust=False, min_periods=period).mean()

    @staticmethod
    def calculate_rsi(series, period=14):
        delta = series.diff()
        gain = wilder(delta.clip(lower=0), period, start=1)
        loss = wilder(-delta.clip(upper=0), period, start=1)
        rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
        rsi = rsi.mask((loss == 0) & (gain > 0), 100)
        rsi = rsi.mask((gain == 0) & (loss > 0), 0)
        return rsi.mask((gain == 0) & (loss == 0), 50)

    @staticmethod
    def calculate_atr(df, period=14):
        previous = df.close.shift(1)
        tr = pd.concat([df.high - df.low, (df.high - previous).abs(),
                        (df.low - previous).abs()], axis=1).max(axis=1)
        return wilder(tr, period)

    @staticmethod
    def find_support_resistance(df, window=15):
        return float(df.low.tail(window * 2).min()), float(df.high.tail(window * 2).max())


@dataclass(frozen=True)
class Settings:
    account_balance: float = 10000
    max_risk_pct: float = 1
    atr_multiple: float = 1.5
    reward_ratio: float = 2
    pullback_pct: float = 1.5
    fee_pct: float = 0.1
    slippage_pct: float = 0.05

    def __post_init__(self):
        if not all(np.isfinite(v) for v in asdict(self).values()):
            raise ValueError("Tous les paramètres doivent être finis.")
        if self.account_balance <= 0 or not 0 < self.max_risk_pct <= 100:
            raise ValueError("Capital positif et risque entre 0 et 100 % requis.")
        if self.atr_multiple <= 0 or self.reward_ratio < 2 or not 0 < self.pullback_pct <= 10:
            raise ValueError("ATR positif, ratio gain/risque ≥ 2 et proximité entre 0 et 10 % requis.")
        if not 0 <= self.fee_pct <= 5 or not 0 <= self.slippage_pct <= 5:
            raise ValueError("Frais et glissement doivent être compris entre 0 et 5 %.")


class RiskManager:
    def __init__(self, account_balance=10000, max_risk_pct=1, fee_pct=0.1, slippage_pct=0.05):
        self.settings = Settings(account_balance=account_balance, max_risk_pct=max_risk_pct,
                                 fee_pct=fee_pct, slippage_pct=slippage_pct)

    def calculate_position(self, entry, stop_loss):
        if not np.isfinite([entry, stop_loss]).all() or min(entry, stop_loss) <= 0 or entry == stop_loss:
            raise ValueError("Entrée et stop doivent être positifs, finis et distincts.")
        s = self.settings
        fee = s.fee_pct / 100
        # Réserve pour des frais aller-retour et un glissement adverse au stop.
        stop_fill = stop_loss * (1 - s.slippage_pct / 100 if stop_loss < entry
                                 else 1 + s.slippage_pct / 100)
        risk_per_unit = abs(entry - stop_fill) + (entry + stop_fill) * fee
        budget = s.account_balance * s.max_risk_pct / 100
        units = min(budget / risk_per_unit, s.account_balance / (entry * (1 + fee)))
        return dict(account_balance=s.account_balance, risk_amount_usd=units * risk_per_unit,
                    risk_budget=budget, risk_pct=s.max_risk_pct, units=units,
                    notional_value=units * entry, risk_per_unit=risk_per_unit)


@dataclass
class TradeSignal:
    timestamp: str
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    reasons: list[str]
    checklist_passed: bool
    position_sizing: dict


class EducationalTradingEngine:
    def __init__(self, symbol="DEMO", account_balance=10000, max_risk_pct=1, settings=None):
        self.symbol = symbol
        self.settings = settings or Settings(account_balance=account_balance, max_risk_pct=max_risk_pct)

    def indicators(self, data):
        df = validate_data(data)
        for period in (20, 50, 200):
            df[f"ema_{period}"] = TechnicalIndicators.calculate_ema(df.close, period)
        df["rsi"] = TechnicalIndicators.calculate_rsi(df.close)
        df["atr"] = TechnicalIndicators.calculate_atr(df)
        df["support"] = df.low.rolling(30, min_periods=30).min()
        df["resistance"] = df.high.rolling(30, min_periods=30).max()
        return df

    def checklist(self, row):
        ready = np.isfinite([row.ema_200, row.rsi, row.atr]).all() and row.atr > 0
        bullish = bool(ready and row.close > row.ema_200 and row.ema_20 > row.ema_50 > row.ema_200)
        bearish = bool(ready and row.close < row.ema_200 and row.ema_20 < row.ema_50 < row.ema_200)
        near = bool(ready and abs(row.close - row.ema_50) / row.close <= self.settings.pullback_pct / 100)
        momentum = bool(ready and 40 <= row.rsi <= 60)
        direction = 1 if bullish and near and momentum else -1 if bearish and near and momentum else 0
        return direction, {"Indicateurs disponibles et volatilité positive": bool(ready),
                           "Tendance et moyennes mobiles alignées": bullish or bearish,
                           "Prix proche de l’EMA 50": near, "RSI compris entre 40 et 60": momentum}

    def analyze(self, data):
        df = self.indicators(data)
        row = df.iloc[-1]
        direction, checklist = self.checklist(row)
        trend = ("HAUSSIÈRE" if row.close > row.ema_200 and row.ema_50 > row.ema_200
                 else "BAISSIÈRE" if row.close < row.ema_200 and row.ema_50 < row.ema_200 else "NEUTRE")
        signal = None
        if direction:
            entry = float(row.close)
            distance = float(row.atr * self.settings.atr_multiple)
            stop = entry - direction * distance
            target = entry + direction * distance * self.settings.reward_ratio
            if min(stop, target) > 0:
                s = self.settings
                sizing = RiskManager(s.account_balance, s.max_risk_pct, s.fee_pct,
                                     s.slippage_pct).calculate_position(entry, stop)
                signal = TradeSignal(str(df.index[-1]), self.symbol,
                                     "ACHAT (LONG)" if direction == 1 else "VENTE (SHORT)",
                                     entry, stop, target, s.reward_ratio,
                                     [text for text, passed in checklist.items() if passed], True, sizing)
        return dict(symbol=self.symbol, last_price=float(row.close), trend_regime=trend,
                    indicators={k: float(row[k]) for k in
                                ("ema_20", "ema_50", "ema_200", "rsi", "atr", "support", "resistance")},
                    checklist=checklist, signal=signal, df_analyzed=df)

    @staticmethod
    def print_educational_report(analysis):
        out = {k: v for k, v in analysis.items() if k != "df_analyzed"}
        if out["signal"]:
            out["signal"] = asdict(out["signal"])
        print(json.dumps(out, ensure_ascii=False, indent=2))


def exit_on_bar(row, side, stop, target):
    """Stop prioritaire si les deux seuils sont touchés ; gaps au stop défavorables."""
    if side == 1:
        if row.open <= stop:
            return float(row.open), "gap_stop"
        if row.open >= target:
            return target, "objectif"
        if row.low <= stop:
            return stop, "stop"
        if row.high >= target:
            return target, "objectif"
    else:
        if row.open >= stop:
            return float(row.open), "gap_stop"
        if row.open <= target:
            return target, "objectif"
        if row.high >= stop:
            return stop, "stop"
        if row.low <= target:
            return target, "objectif"
    return None


def backtest(data, settings=None, allow_short=False):
    """Une position à la fois, signal clôturé puis entrée à l'ouverture suivante."""
    s = settings or Settings()
    engine = EducationalTradingEngine(settings=s)
    df = engine.indicators(validate_data(data, minimum=202))
    fee, slip = s.fee_pct / 100, s.slippage_pct / 100
    balance = s.account_balance
    position = None
    trades, equity = [], []
    for i in range(199, len(df)):
        row = df.iloc[i]
        if position is None and i >= 200 and balance > 0:
            previous = df.iloc[i - 1]
            side, _ = engine.checklist(previous)
            if side and (side == 1 or allow_short):
                entry = float(row.open * (1 + side * slip))
                distance = float(previous.atr * s.atr_multiple)
                stop = entry - side * distance
                target = entry + side * distance * s.reward_ratio
                if min(stop, target) > 0:
                    sizing = RiskManager(balance, s.max_risk_pct, s.fee_pct,
                                         s.slippage_pct).calculate_position(entry, stop)
                    position = dict(entry_time=df.index[i], signal_time=df.index[i - 1],
                                    side=side, entry=entry, stop=stop, target=target,
                                    units=sizing["units"], entry_fee=entry * sizing["units"] * fee)
                    balance -= position["entry_fee"]
        if position is not None:
            p = position
            result = exit_on_bar(row, p["side"], p["stop"], p["target"])
            if result is None and i == len(df) - 1:
                result = float(row.close), "fin_echantillon"
            if result is not None:
                raw_exit, reason = result
                fill = max(0.0, raw_exit * (1 - p["side"] * slip))
                exit_fee = fill * p["units"] * fee
                gross = p["side"] * (fill - p["entry"]) * p["units"]
                balance += gross - exit_fee
                trades.append(dict(signal_time=p["signal_time"], entry_time=p["entry_time"],
                                   exit_time=df.index[i], direction="LONG" if p["side"] == 1 else "SHORT",
                                   entry=p["entry"], stop=p["stop"], target=p["target"], exit=fill,
                                   units=p["units"], fees=p["entry_fee"] + exit_fee,
                                   pnl=gross - p["entry_fee"] - exit_fee, reason=reason))
                position = None
        mark = balance
        if position:
            p = position
            mark += p["side"] * (row.close - p["entry"]) * p["units"] - row.close * p["units"] * fee
        equity.append((df.index[i], mark))
    curve = pd.Series(dict(equity), name="capital")
    journal = pd.DataFrame(trades, columns=["signal_time", "entry_time", "exit_time", "direction",
                                           "entry", "stop", "target", "exit", "units", "fees", "pnl", "reason"])
    pnl = journal.pnl.astype(float)
    gains, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    metrics = dict(initial_balance=s.account_balance, final_balance=balance,
                   return_pct=(balance / s.account_balance - 1) * 100,
                   max_drawdown_pct=float(((curve / curve.cummax()) - 1).min() * -100),
                   trades=len(journal), win_rate_pct=float((pnl > 0).mean() * 100) if len(pnl) else None,
                   profit_factor=float(gains / losses) if losses > 0 else None,
                   fees=float(journal.fees.sum()) if len(journal) else 0)
    return dict(metrics=metrics, trades=journal, equity=curve)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, help="CSV OHLCV de bougies clôturées")
    parser.add_argument("--symbol", default="DEMO")
    parser.add_argument("--capital", type=float, default=10000)
    parser.add_argument("--risk", type=float, default=1)
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--output", type=Path, help="Exporter le journal du backtest en CSV")
    args = parser.parse_args()
    try:
        data = load_csv(args.csv) if args.csv else MarketDataSimulator.generate_ohlcv()
        settings = Settings(account_balance=args.capital, max_risk_pct=args.risk)
        print("DONNÉES CSV" if args.csv else "DÉMONSTRATION : DONNÉES SYNTHÉTIQUES")
        EducationalTradingEngine.print_educational_report(
            EducationalTradingEngine(symbol=args.symbol, settings=settings).analyze(data))
        if args.backtest:
            result = backtest(data, settings)
            print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))
            if args.output:
                result["trades"].to_csv(args.output, index=False)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Erreur : {exc}\n")


if __name__ == "__main__":
    main()
