"""
In-memory store for live MT5 symbol specs (contract size, tick value,
tick size), pushed by the Windows bridge. Kept separate from mt5_store.py
(candle storage) so a problem here can never affect candle streaming.
"""

from __future__ import annotations

import time

_specs: dict[str, dict] = {}


def store_specs(symbol: str, contract_size: float, tick_value: float, tick_size: float) -> None:
    _specs[symbol] = {
        "contract_size": contract_size,
        "tick_value": tick_value,
        "tick_size": tick_size,
        "updated_at": time.time(),
    }


def get_specs(symbol: str) -> dict | None:
    return _specs.get(symbol)