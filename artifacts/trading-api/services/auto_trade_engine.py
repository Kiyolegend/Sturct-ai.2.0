"""
Auto Trade Engine — 5m/15m fresh/tested-zone scalping.

BIAS:       15m EMA21/EMA50 alignment (price > fast > slow = bull, mirrored for bear)
            Kept on 15m (slower than entry TF) so bias doesn't whipsaw on 5m noise.
ENTRY:      Zone check — accepts FRESH or TESTED zones (not WORN).
            15m checked first, falls back to 5m if 15m has none.
CONFIRM:    RSI score (not a hard gate) — momentum agreement or opposition, ±weight
SL:         Beyond the far side of the entry zone
TP:         RR >= MIN_RR from risk, nudged toward the $ reward target
LOT SIZE:   Auto-picked in [LOT_MIN, LOT_MAX] to land risk near TARGET_RISK_USD

Paper mode  -> logs signal, does NOT send to MT5
Live mode   -> queues order via routers.trading.queue_order()
"""

from __future__ import annotations
import asyncio
import time
import logging
from typing import Optional

from services.data_service import fetch_ohlc
from services.zigzag_engine import detect_swings
from services.zones_engine import detect_zones
from services.framework_checker import _pip
from services.indicator_engine import compute_ema, compute_rsi, EMA_FAST, EMA_SLOW
from services.mt5_store import get_latest_timestamp as _get_broker_time

log = logging.getLogger(__name__)

PAIRS = [
    "USD/JPY", "EUR/USD", "GBP/USD", "EUR/JPY", "GBP/JPY",
    "AUD/USD", "USD/CAD", "USD/CHF", "NZD/USD", "AUD/JPY", "CAD/JPY", "DXY","BTCUSD",
]

MIN_RR              = 1.3
TARGET_RISK_USD     = (2.0, 4.0)       # SL band
TARGET_REWARD_USD   = (4.0, 7.0)       # TP band
LOT_MIN, LOT_MAX     = 0.01, 0.03
ZONE_TFS             = ["15m", "5m"]   # checked in priority order — 15m preferred, 5m fallback
ACCEPTED_FRESHNESS  = ("fresh", "tested")  # WORN is excluded — too many retests, statistically weak
BIAS_TF              = "15m"           # EMA direction timeframe
LOOP_SECONDS        = 20
_FIRED_TTL_S        = 6 * 3600         # scalp signals go stale fast — 6h not 7d

# ── Module-level state ────────────────────────────────────────────────────────
_enabled:     bool = False
_paper_mode:  bool = True
_pair_status: dict[str, dict] = {}
_trade_log:   list[dict] = []
_fired_ids:   set[str] = set()
_fired_times: dict[str, float] = {}
_bg_task: Optional[asyncio.Task] = None


# ── Public state accessors ────────────────────────────────────────────────────

def get_state() -> dict:
    return {
        "enabled":    _enabled,
        "paper_mode": _paper_mode,
        "pairs":      dict(_pair_status),
        "log_count":  len(_trade_log),
    }

def get_log() -> list[dict]:
    return list(_trade_log)

def set_enabled(v: bool) -> None:
    global _enabled
    _enabled = v

def set_paper_mode(v: bool) -> None:
    global _paper_mode
    _paper_mode = v


# ── Sizing ─────────────────────────────────────────────────────────────────────

def _pip_value_per_lot(symbol: str) -> float:
    if "BTC" in symbol:   return 1.0
    if "XAU" in symbol:   return 10.0
    if "JPY" in symbol:   return 9.0
    return 10.0

def _pick_lot_and_sl_tp(symbol: str, entry: float, zone_far: float, is_bull: bool) -> Optional[dict]:
    """
    Given the entry price and the far boundary of the entry zone (used as
    the structural SL anchor), pick a lot size in [LOT_MIN, LOT_MAX] that
    lands dollar risk inside TARGET_RISK_USD, then set TP so RR >= MIN_RR
    and dollar reward lands as close to TARGET_REWARD_USD as achievable.
    Returns None if no lot in range can hit an acceptable risk.
    """
    pip = _pip(entry, symbol)
    pip_val = _pip_value_per_lot(symbol)

    sl_pips = abs(entry - zone_far) / pip
    if sl_pips <= 0:
        return None

    best = None
    lot = LOT_MIN
    while lot <= LOT_MAX + 1e-9:
        risk_usd = sl_pips * pip_val * lot
        if TARGET_RISK_USD[0] <= risk_usd <= TARGET_RISK_USD[1]:
            best = lot
            break
        lot = round(lot + 0.01, 2)

    if best is None:
        risk_at_min = sl_pips * pip_val * LOT_MIN
        risk_at_max = sl_pips * pip_val * LOT_MAX
        if TARGET_RISK_USD[0] <= risk_at_min <= TARGET_RISK_USD[1] * 1.5:
            best = LOT_MIN
        elif risk_at_max <= TARGET_RISK_USD[1] * 1.2:
            best = LOT_MAX
        else:
            return None  # zone is simply too wide/narrow for this risk band

    risk_usd = round(sl_pips * pip_val * best, 2)
    sl_p = round(entry - sl_pips * pip if is_bull else entry + sl_pips * pip, 5)

    reward_pips = sl_pips * MIN_RR
    reward_usd  = reward_pips * pip_val * best
    if reward_usd < TARGET_REWARD_USD[0]:
        needed_pips = TARGET_REWARD_USD[0] / (pip_val * best)
        reward_pips = max(reward_pips, needed_pips)
    tp_p = round(entry + reward_pips * pip if is_bull else entry - reward_pips * pip, 5)

    rr = round(reward_pips / sl_pips, 2) if sl_pips > 0 else 0.0
    reward_usd = round(reward_pips * pip_val * best, 2)

    if rr < MIN_RR:
        return None

    return {"lot": best, "sl": sl_p, "tp": tp_p, "rr": rr, "risk_usd": risk_usd, "reward_usd": reward_usd}


# ── RSI confirmation (score, not a hard gate) ────────────────────────────────

def _rsi_confirmation_score(rsi_series: list[dict], is_bull: bool) -> tuple[int, str]:
    if not rsi_series:
        return 50, "no RSI data — neutral"
    val = rsi_series[-1]["value"]

    if is_bull:
        if val >= 55: return 80, f"RSI {val:.1f} confirms bullish momentum"
        if val >= 50: return 60, f"RSI {val:.1f} mildly bullish"
        if val <= 30: return 55, f"RSI {val:.1f} oversold — possible bounce into demand"
        return 25, f"RSI {val:.1f} opposes bullish bias"
    else:
        if val <= 45: return 80, f"RSI {val:.1f} confirms bearish momentum"
        if val <= 50: return 60, f"RSI {val:.1f} mildly bearish"
        if val >= 70: return 55, f"RSI {val:.1f} overbought — possible drop into supply"
        return 25, f"RSI {val:.1f} opposes bearish bias"


# ── Core evaluation for one pair ──────────────────────────────────────────────

async def _evaluate_pair(symbol: str) -> dict:
    """Full scalp evaluation for one pair. Never raises."""
    try:
        try:
            df_bias = await fetch_ohlc(symbol, BIAS_TF, 200)
        except ValueError:
            return {"status": "WAITING", "reason": f"No {BIAS_TF} data yet", "symbol": symbol}

        current_price = float(df_bias["close"].iloc[-1])
        ema_fast = compute_ema(df_bias, EMA_FAST)
        ema_slow = compute_ema(df_bias, EMA_SLOW)
        if not ema_fast or not ema_slow:
            return {"status": "WAITING", "reason": "Not enough bars for EMA", "symbol": symbol}

        fast_val = ema_fast[-1]["value"]
        slow_val = ema_slow[-1]["value"]

        is_bull = current_price > fast_val > slow_val
        is_bear = current_price < fast_val < slow_val
        if not is_bull and not is_bear:
            return {
                "status": "NEUTRAL",
                "reason": "EMA21/EMA50 not aligned — choppy, no scalp bias",
                "symbol": symbol, "price": current_price,
            }

        want_type = "demand" if is_bull else "supply"
        direction  = "BUY" if is_bull else "SELL"

        candidate = None
        used_tf   = None
        used_freshness = None
        df_zone   = None

        for tf in ZONE_TFS:
            try:
                _df = await fetch_ohlc(symbol, tf, 300 if tf == "15m" else 400)
            except ValueError:
                continue
            _swings = detect_swings(_df, fractal_n=5, timeframe=tf)
            _zones  = detect_zones(_swings, tf, current_price, df=_df)
            _hit = next(
                (z for z in _zones
                 if z.get("type") == want_type
                 and z.get("freshness") in ACCEPTED_FRESHNESS
                 and z.get("bottom", 0) <= current_price <= z.get("top", 0)),
                None,
            )
            if _hit is not None:
                candidate = _hit
                used_tf   = tf
                used_freshness = _hit.get("freshness")
                df_zone   = _df
                break

        if candidate is None:
            return {
                "status": "WATCHING",
                "reason": f"EMA bias {direction} ✓ — waiting for price inside a fresh/tested 15m/5m {want_type} zone",
                "symbol": symbol, "price": current_price,
            }

        zone_far = candidate["bottom"] if is_bull else candidate["top"]
        sizing = _pick_lot_and_sl_tp(symbol, current_price, zone_far, is_bull)
        if sizing is None:
            return {
                "status": "WATCHING",
                "reason": f"EMA bias {direction} ✓  zone ✓ — zone width can't hit R:R ≥ {MIN_RR} within lot/risk limits",
                "symbol": symbol, "price": current_price,
            }

        rsi_series = compute_rsi(df_zone)
        rsi_score, rsi_reason = _rsi_confirmation_score(rsi_series, is_bull)

        MIN_CONFIRM_SCORE = 40
        if rsi_score < MIN_CONFIRM_SCORE:
            return {
                "status": "WATCHING",
                "reason": f"EMA bias {direction} ✓  zone ✓  R:R {sizing['rr']} ✓ — {rsi_reason} (below confirm threshold)",
                "symbol": symbol, "price": current_price,
                "rr": sizing["rr"], "rsi_score": rsi_score,
            }

        _now = _get_broker_time() or int(time.time())
        zone_id = candidate.get("id") or f"{round(candidate.get('top',0),3)}_{round(candidate.get('bottom',0),3)}"
        signal_id = f"{symbol}_{direction}_{zone_id}_{int(_now // 300)}"

        return {
            "status":         "READY",
            "reason":         f"EMA bias {direction} ✓  {used_freshness} {used_tf} {want_type} ✓  R:R {sizing['rr']} ✓  {rsi_reason}",
            "symbol":         symbol,
            "direction":      direction,
            "entry":          round(current_price, 5),
            "sl":             sizing["sl"],
            "tp":             sizing["tp"],
            "rr":             sizing["rr"],
            "lot":            sizing["lot"],
            "risk_usd":       sizing["risk_usd"],
            "reward_usd":     sizing["reward_usd"],
            "rsi_score":      rsi_score,
            "entry_source":   f"{used_tf} {want_type} ({used_freshness})",
            "zone_freshness": used_freshness,
            "signal_id":      signal_id,
            "price":          current_price,
        }

    except Exception as e:
        log.exception(f"[AutoTrade] Eval error for {symbol}: {e}")
        return {"status": "ERROR", "reason": str(e), "symbol": symbol}


# ── Background loop ────────────────────────────────────────────────────────────

async def _run_loop() -> None:
    global _pair_status, _trade_log, _fired_ids
    log.info("[AutoTrade] Engine started")

    while _enabled:
        for symbol in PAIRS:
            if not _enabled:
                break
            result = await _evaluate_pair(symbol)
            _pair_status[symbol] = {**result, "evaluated_at": _get_broker_time() or int(time.time())}

            if result.get("status") == "READY":
                sid = result.get("signal_id", "")
                if sid and sid not in _fired_ids:
                    _fired_ids.add(sid)
                    _fired_times[sid] = _get_broker_time() or int(time.time())
                    entry = {**result, "fired_at": _get_broker_time() or int(time.time()), "paper_mode": _paper_mode}
                    _trade_log.insert(0, entry)
                    if len(_trade_log) > 100:
                        _trade_log.pop()

                    if not _paper_mode:
                        try:
                            from routers.trading import queue_order
                            order_id = queue_order({
                                "symbol":     symbol,
                                "direction":  result["direction"],
                                "order_type": "MARKET",
                                "price":      result["entry"],
                                "sl":         result["sl"],
                                "tp":         result["tp"],
                                "lots":       result["lot"],
                                "comment":    "STRUCT.ai-Scalp",
                            })
                            _pair_status[symbol]["order_id"] = order_id
                            log.info(f"[AutoTrade] LIVE order: {symbol} {result['direction']} lot={result['lot']} id={order_id}")
                        except Exception as e:
                            log.error(f"[AutoTrade] Failed to queue order: {e}")
                    else:
                        log.info(f"[AutoTrade] PAPER: {symbol} {result['direction']} entry={result['entry']} lot={result['lot']} R:R={result['rr']}")

                now_t = _get_broker_time() or int(time.time())
                expired = [k for k, v in _fired_times.items() if now_t - v > _FIRED_TTL_S]
                for k in expired:
                    _fired_ids.discard(k)
                    del _fired_times[k]

        if _enabled:
            await asyncio.sleep(LOOP_SECONDS)

    log.info("[AutoTrade] Engine stopped")


def start_engine() -> None:
    global _bg_task
    if _bg_task and not _bg_task.done():
        return
    _bg_task = asyncio.ensure_future(_run_loop())

def stop_engine() -> None:
    global _bg_task
    if _bg_task:
        _bg_task.cancel()
        _bg_task = None