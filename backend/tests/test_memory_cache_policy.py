import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from cache import TTLCache, estimate_size_bytes
from services.job_memory_policy import prune_finished_jobs
from services.sector_cache_service import SectorCacheService
from services.sector_stock_cache_service import SectorStockCacheService


class TTLCacheMemoryPolicyTests(unittest.TestCase):
    def test_lru_byte_limit_releases_oldest_entry(self):
        payload = {'rows': [{'symbol': 'ABC', 'value': 'x' * 128}]}
        payload_bytes = estimate_size_bytes(payload)
        cache = TTLCache(ttl_seconds=60, max_items=10, max_bytes=payload_bytes * 2)

        cache.set('a', payload)
        cache.set('b', payload)
        self.assertEqual(cache.get('a'), payload)
        cache.set('c', payload)

        self.assertIsNone(cache.get('b'))
        self.assertEqual(cache.get('a'), payload)
        self.assertEqual(cache.get('c'), payload)
        self.assertEqual(cache.stats()['items'], 2)
        self.assertEqual(cache.stats()['capacity_evictions'], 1)

    def test_oversized_payload_is_not_retained(self):
        cache = TTLCache(ttl_seconds=60, max_items=10, max_bytes=64)
        cache.set('oversized', {'rows': ['x' * 4096]})

        self.assertIsNone(cache.get('oversized'))
        self.assertEqual(cache.stats()['items'], 0)

    def test_set_sweeps_all_expired_entries(self):
        cache = TTLCache(ttl_seconds=1, max_items=10)
        with patch('cache.time.monotonic', side_effect=[0.0, 2.0, 2.0]):
            cache.set('expired', {'value': 1})
            cache.set('fresh', {'value': 2})
            stats = cache.stats()

        self.assertEqual(stats['items'], 1)
        self.assertEqual(stats['expired_evictions'], 1)


class SectorCacheMemoryPolicyTests(unittest.TestCase):
    def test_sector_cache_is_lru_and_item_bounded(self):
        cache = SectorCacheService(max_items=2, max_bytes=1024 * 1024)
        cache.set_cache('a', [{'symbol': 'A'}], 60)
        cache.set_cache('b', [{'symbol': 'B'}], 60)
        self.assertIsNotNone(cache.get_cache('a'))
        cache.set_cache('c', [{'symbol': 'C'}], 60)

        self.assertIsNone(cache.get_cache('b'))
        self.assertIsNotNone(cache.get_cache('a'))
        self.assertIsNotNone(cache.get_cache('c'))
        self.assertEqual(cache.stats()['items'], 2)

    def test_sector_stock_cache_is_lru_and_item_bounded(self):
        cache = SectorStockCacheService(max_items=2, max_bytes=1024 * 1024)
        cache.set_memory_cache('a', table_name='A', sector_name='A', rows=[{'symbol': 'A'}], ttl_seconds=60)
        cache.set_memory_cache('b', table_name='B', sector_name='B', rows=[{'symbol': 'B'}], ttl_seconds=60)
        self.assertIsNotNone(cache.get_memory_cache('a'))
        cache.set_memory_cache('c', table_name='C', sector_name='C', rows=[{'symbol': 'C'}], ttl_seconds=60)

        self.assertIsNone(cache.get_memory_cache('b'))
        self.assertIsNotNone(cache.get_memory_cache('a'))
        self.assertIsNotNone(cache.get_memory_cache('c'))
        self.assertEqual(cache.memory_stats()['items'], 2)


class JobMemoryPolicyTests(unittest.TestCase):
    def test_pruning_keeps_active_jobs_and_newest_finished_jobs(self):
        jobs = {
            'active': {'finished_ts': 0.0},
            'expired': {'finished_ts': 10.0},
            'old': {'finished_ts': 80.0},
            'middle': {'finished_ts': 90.0},
            'new': {'finished_ts': 95.0},
        }

        removed = prune_finished_jobs(
            jobs,
            now_ts=100.0,
            ttl_seconds=60,
            max_finished_items=2,
        )

        self.assertEqual(set(removed), {('expired', 'ttl_expired'), ('old', 'retention_limit')})
        self.assertEqual(set(jobs), {'active', 'middle', 'new'})


if __name__ == '__main__':
    unittest.main()
