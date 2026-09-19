"""
Indicator Engine — EMA and RSI, shared across timeframes and instruments.

Both indicators are dimensionless with respect to price scale, so unlike
zones/OB/FVG/pip_utils there is no per-asset-class branching needed here:
EMA is a weighted average of close, RSI is a 0-100 ratio of average gains
to average losses. The same code and constants apply identically whether
the instrument is USD/JPY at 150 or BTC/USD at 80,000.

EMA_FAST/EMA_SLOW/RSI_PERIOD are the single source of truth for these
settings — import them here rather than hardcoding 21/50/14 elsewhere.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

EMA_FAST = 21
EMA_SLOW = 50
RSI_PERIOD = 14


def _df_time_ints(df: pd.DataFrame) -> pd.Series:
    col = df["time"]
    if pd.api.types.is_datetime64_any_dtype(col):
        return col.astype("datetime64[s]").astype("int64")
    return col.astype("int64")


def compute_ema(df: pd.DataFrame, period: int) -> list[dict]:
    """
    Exponential moving average of close, one point per bar.
    Returns [{time, value}, ...] — ready to feed a lightweight-charts
    line series directly.
    """
    if df is None or len(df) == 0:
        return []
    times = _df_time_ints(df)
    ema = df["close"].ewm(span=period, adjust=False).mean()
    return [
        {"time": int(t), "value": round(float(v), 5)}
        for t, v in zip(times, ema)
    ]


def compute_rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> list[dict]:
    """
    Wilder-smoothed RSI (the standard definition — not a simple moving
    average of gains/losses, which drifts from the textbook value).
    The first `period` bars have no valid RSI and are omitted from the
    result rather than sent as NaN.
    """
    if df is None or len(df) < period + 1:
        return []

    close = df["close"]
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(avg_loss != 0, 100.0)
    rsi = rsi.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)

    times = _df_time_ints(df)
    result = []
    for i in range(period, len(df)):
        val = rsi.iloc[i]
        if pd.isna(val):
            continue
        result.append({"time": int(times.iloc[i]), "value": round(float(val), 2)})
    return result


def compute_ma_state(
    df: pd.DataFrame,
    fast: int = EMA_FAST,
    slow: int = EMA_SLOW,
) -> dict:
    """
    Compact snapshot of where price sits relative to both EMAs, for the
    narrative engine / framework checker to consume without redoing the
    EMA math themselves.

    Returns:
      {
        current_price, ema_fast, ema_slow,
        price_vs_fast: "above" | "below" | "equal",
        price_vs_slow: "above" | "below" | "equal",
        fast_vs_slow:  "above" | "below" | "equal",
        cross: "golden" | "death" | None,
        bars_since_cross: int | None,
      }
    """
    if df is None or len(df) < 2:
        return {
            "current_price": None, "ema_fast": None, "ema_slow": None,
            "price_vs_fast": "equal", "price_vs_slow": "equal",
            "fast_vs_slow": "equal", "cross": None, "bars_since_cross": None,
        }

    close = df["close"]
    fast_series = close.ewm(span=fast, adjust=False).mean()
    slow_series = close.ewm(span=slow, adjust=False).mean()

    current_price = float(close.iloc[-1])
    fast_val = float(fast_series.iloc[-1])
    slow_val = float(slow_series.iloc[-1])

    def _cmp(a: float, b: float) -> str:
        if a > b:
            return "above"
        if a < b:
            return "below"
        return "equal"

    diff = fast_series - slow_series
    sign = np.sign(diff)
    changes = sign.diff().fillna(0) != 0
    change_idx = np.where(changes.values)[0]

    cross: str | None = None
    bars_since_cross: int | None = None
    if len(change_idx) > 0:
        idx = int(change_idx[-1])
        cross = "golden" if sign.iloc[idx] > 0 else "death"
        bars_since_cross = len(df) - 1 - idx

    return {
        "current_price": round(current_price, 5),
        "ema_fast": round(fast_val, 5),
        "ema_slow": round(slow_val, 5),
        "price_vs_fast": _cmp(current_price, fast_val),
        "price_vs_slow": _cmp(current_price, slow_val),
        "fast_vs_slow": _cmp(fast_val, slow_val),
        "cross": cross,
        "bars_since_cross": bars_since_cross,
    }