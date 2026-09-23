import threading
import time
import unittest
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from cache import TTLCache, background_refresh


class BackgroundRefreshTests(unittest.TestCase):
    def test_background_refresh_coalesces_same_key(self):
        cache = TTLCache(ttl_seconds=60)
        calls = 0
        started = threading.Event()
        release = threading.Event()

        def compute():
            nonlocal calls
            calls += 1
            started.set()
            release.wait(timeout=1)
            return {"ok": True}

        background_refresh(cache, "volume", compute)
        self.assertTrue(started.wait(timeout=1))

        background_refresh(cache, "volume", compute)
        release.set()

        deadline = time.time() + 1
        while cache.get("volume") is None and time.time() < deadline:
            time.sleep(0.01)

        self.assertEqual(calls, 1)
        self.assertEqual(cache.get("volume"), {"ok": True})


if __name__ == "__main__":
    unittest.main()
