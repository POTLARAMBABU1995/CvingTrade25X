from contextlib import ExitStack
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = BACKEND_ROOT / 'app.py'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

spec = importlib.util.spec_from_file_location('legacy_backend_app_alias_routes', APP_FILE)
backend_app = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(backend_app)


class NseSymbolAliasRouteTests(unittest.TestCase):
    @staticmethod
    def _headers():
        return {'Authorization': 'Bearer test-token'}

    def _client(self):
        app = backend_app.create_app(enable_background_jobs=False, enable_warmup=False)
        return app.test_client()

    def test_nse_symbols_endpoint_returns_sorted_symbols(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(backend_app, 'init_registration_db', return_value=None))
            stack.enter_context(patch.object(backend_app, 'validate_session', return_value={'user_id': 'demo'}))
            stack.enter_context(
                patch.object(
                    backend_app.nse_existing_csv_symbol_svc,
                    'load_valid_symbols',
                    return_value={'RELIANCE', 'ITC', 'TCS'},
                )
            )
            stack.enter_context(
                patch.object(
                    backend_app.nse_existing_csv_symbol_svc,
                    'resolve_symbol_file_path',
                    return_value=Path(r'D:\fyers_api_integration\data\symbols_nifty500.csv'),
                )
            )
            client = self._client()

            response = client.get('/api/nse-symbols', headers=self._headers())

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload['status'], 'success')
            self.assertEqual(payload['count'], 3)
            self.assertEqual(payload['symbols'], ['ITC', 'RELIANCE', 'TCS'])

    def test_nse_symbols_post_endpoint_returns_sorted_symbols(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(backend_app, 'init_registration_db', return_value=None))
            stack.enter_context(patch.object(backend_app, 'validate_session', return_value={'user_id': 'demo'}))
            stack.enter_context(
                patch.object(
                    backend_app.nse_existing_csv_symbol_svc,
                    'load_valid_symbols',
                    return_value={'INFY', 'ITC'},
                )
            )
            stack.enter_context(
                patch.object(
                    backend_app.nse_existing_csv_symbol_svc,
                    'resolve_symbol_file_path',
                    return_value=Path(r'D:\fyers_api_integration\data\symbols_nifty500.csv'),
                )
            )
            client = self._client()

            response = client.post(
                '/api/nse-symbols',
                headers=self._headers(),
                json={'symbolFilePath': r'D:\fyers_api_integration\data\symbols_nifty500.csv'},
            )

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload['status'], 'success')
            self.assertEqual(payload['symbols'], ['INFY', 'ITC'])

    def test_nse_delivery_process_existing_csv_symbols_alias(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(backend_app, 'init_registration_db', return_value=None))
            stack.enter_context(patch.object(backend_app, 'validate_session', return_value={'user_id': 'demo'}))
            stack.enter_context(
                patch.object(
                    backend_app.nse_delivery_svc,
                    'process_existing_csv_for_symbols_api',
                    return_value={
                        'status': 'success',
                        'dataset_type': 'delivery_data',
                        'requested_count': 2,
                        'requested_symbols': ['ITC', 'RELIANCE'],
                        'valid_symbols': ['ITC', 'RELIANCE'],
                        'invalid_symbols': [],
                        'symbols_found_in_csv': ['ITC'],
                        'symbols_not_found_in_csv': ['RELIANCE'],
                        'records_inserted': 10,
                        'records_skipped_existing': 3,
                        'errors': [],
                    },
                )
            )
            client = self._client()

            response = client.post(
                '/api/nse-delivery/process-existing-csv-symbols',
                headers=self._headers(),
                json={'symbols': ['ITC', 'RELIANCE']},
            )

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload['dataset_type'], 'delivery_data')
            self.assertEqual(payload['requested_count'], 2)

    def test_nse_market_cap_process_existing_csv_symbols_alias(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(backend_app, 'init_registration_db', return_value=None))
            stack.enter_context(patch.object(backend_app, 'validate_session', return_value={'user_id': 'demo'}))
            stack.enter_context(
                patch.object(
                    backend_app.nse_mcap_svc,
                    'process_existing_csv_for_symbols_api',
                    return_value={
                        'status': 'success',
                        'dataset_type': 'market_cap',
                        'requested_count': 1,
                        'requested_symbols': ['ITC'],
                        'valid_symbols': ['ITC'],
                        'invalid_symbols': [],
                        'symbols_found_in_csv': ['ITC'],
                        'symbols_not_found_in_csv': [],
                        'records_inserted': 22,
                        'records_skipped_existing': 4,
                        'errors': [],
                    },
                )
            )
            client = self._client()

            response = client.post(
                '/api/nse-market-cap/process-existing-csv-symbols',
                headers=self._headers(),
                json={'symbols': ['ITC']},
            )

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload['dataset_type'], 'market_cap')
            self.assertEqual(payload['records_inserted'], 22)

    def test_nse_ffmc_process_existing_csv_symbols_alias(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(backend_app, 'init_registration_db', return_value=None))
            stack.enter_context(patch.object(backend_app, 'validate_session', return_value={'user_id': 'demo'}))
            stack.enter_context(
                patch.object(
                    backend_app.nse_ffmc_svc,
                    'process_existing_csv_for_symbols_api',
                    return_value={
                        'status': 'success',
                        'dataset_type': 'ffmc',
                        'requested_count': 1,
                        'requested_symbols': ['ITC'],
                        'valid_symbols': ['ITC'],
                        'invalid_symbols': [],
                        'symbols_found_in_csv': ['ITC'],
                        'symbols_not_found_in_csv': [],
                        'records_inserted': 8,
                        'records_skipped_existing': 2,
                        'errors': [],
                    },
                )
            )
            client = self._client()

            response = client.post(
                '/api/nse-ffmc/process-existing-csv-symbols',
                headers=self._headers(),
                json={'symbols': ['ITC']},
            )

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload['dataset_type'], 'ffmc')
            self.assertEqual(payload['records_skipped_existing'], 2)


if __name__ == '__main__':
    unittest.main()
