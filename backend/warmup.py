from __future__ import annotations

import threading
from typing import Any, Callable

from cache import save_json_snapshot
from routes.asura import _build_and_save_local_snapshot as build_asura_local_snapshot
from routes.asura import _has_precomputed_source as asura_has_precomputed_source
from routes.trend import _compute_trend_payload, _snapshot_path as trend_snapshot_path
from routes.momentum import _compute_payload as _compute_macd_payload, _snapshot_path as MOMENTUM_SNAPSHOT
from routes.rsi50 import _compute_payload as _compute_rsi_payload, _snapshot_path as RSI_SNAPSHOT


def warm_in_background() -> None:
    def _run(task: Callable[..., dict], path: str, *task_args: Any) -> None:
        try:
            payload = task(*task_args)
            save_json_snapshot(path, payload)
        except Exception:
            pass

    threading.Thread(
        target=_run,
        args=(_compute_trend_payload, trend_snapshot_path('daily'), 'daily'),
        daemon=True,
        name='warm:trend-daily',
    ).start()
    threading.Thread(target=_run, args=(_compute_macd_payload, MOMENTUM_SNAPSHOT), daemon=True, name='warm:macd').start()
    threading.Thread(target=_run, args=(_compute_rsi_payload, RSI_SNAPSHOT), daemon=True, name='warm:rsi50').start()
    try:
        should_warm_asura = not asura_has_precomputed_source()
    except Exception:
        should_warm_asura = True
    if should_warm_asura:
        threading.Thread(
            target=build_asura_local_snapshot,
            args=('daily',),
            daemon=True,
            name='warm:asura-daily',
        ).start()
