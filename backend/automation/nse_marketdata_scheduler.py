from __future__ import annotations

from .nse_market_data_scheduler import main, run_scheduler

__all__ = ["main", "run_scheduler"]


if __name__ == "__main__":
  raise SystemExit(main())

