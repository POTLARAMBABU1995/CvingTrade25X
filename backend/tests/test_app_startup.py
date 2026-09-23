from contextlib import ExitStack
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = BACKEND_ROOT / 'app.py'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

spec = importlib.util.spec_from_file_location('legacy_backend_app', APP_FILE)
backend_app = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(backend_app)
from routes import automation_status as automation_status_route, chart_compat, marketdata as marketdata_route, react_spa


class CreateAppStartupTests(unittest.TestCase):
    def test_create_app_survives_registration_db_failure(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(backend_app, 'init_registration_db', side_effect=RuntimeError('oracle unavailable')))
            stack.enter_context(patch.object(backend_app, 'start_marketdata_auto_merge', return_value=None))
            stack.enter_context(patch.object(backend_app, 'start_asura_auto_insert', return_value=None))
            stack.enter_context(patch.object(backend_app, 'start_bhramhaputra_auto_insert', return_value=None))
            stack.enter_context(patch.object(backend_app, 'start_bhramhastra_auto_insert', return_value=None))
            stack.enter_context(patch.object(backend_app, 'start_yamuna_auto_ingest', return_value=None))
            stack.enter_context(patch.object(backend_app, 'start_manual_sr_image_auto_ingest_scheduler', return_value=None))
            stack.enter_context(patch.object(backend_app, 'start_strategy_agent_scheduler', return_value=None))
            stack.enter_context(patch.object(backend_app, 'warm_sector_rotation_cache', return_value=None))
            stack.enter_context(patch.object(backend_app, 'warm_in_background', return_value=None))
            stack.enter_context(patch.object(backend_app, 'oracledb', None))
            app = backend_app.create_app()
            client = app.test_client()
            response = client.get('/api/health')

            self.assertEqual(response.status_code, 200)

            payload = response.get_json()
            self.assertTrue(payload['ok'])
            self.assertEqual(payload['db'], 'down')
            self.assertEqual(payload['driver'], 'unavailable')
            self.assertTrue(payload['startupWarnings'])
            self.assertEqual(payload['startupWarnings'][0]['step'], 'registration-db-init')
            self.assertIn('oracle unavailable', payload['startupWarnings'][0]['error'])

    def test_create_app_can_skip_background_startup_steps(self):
        with ExitStack() as stack:
            marketdata = stack.enter_context(patch.object(backend_app, 'start_marketdata_auto_merge', return_value=None))
            asura = stack.enter_context(patch.object(backend_app, 'start_asura_auto_insert', return_value=None))
            bhramhaputra = stack.enter_context(patch.object(backend_app, 'start_bhramhaputra_auto_insert', return_value=None))
            bhramhastra = stack.enter_context(patch.object(backend_app, 'start_bhramhastra_auto_insert', return_value=None))
            yamuna = stack.enter_context(patch.object(backend_app, 'start_yamuna_auto_ingest', return_value=None))
            manual_sr = stack.enter_context(patch.object(backend_app, 'start_manual_sr_image_auto_ingest_scheduler', return_value=None))
            scheduler = stack.enter_context(patch.object(backend_app, 'start_strategy_agent_scheduler', return_value=None))
            nse_marketdata = stack.enter_context(patch.object(backend_app, 'start_nse_marketdata_auto_scheduler', return_value=None))
            sector_warm = stack.enter_context(patch.object(backend_app, 'warm_sector_rotation_cache', return_value=None))
            warmup = stack.enter_context(patch.object(backend_app, 'warm_in_background', return_value=None))

            app = backend_app.create_app(
                enable_background_jobs=False,
                enable_warmup=False,
                enable_marketdata_auto_merge=False,
            )

            self.assertIsNotNone(app)
            marketdata.assert_not_called()
            asura.assert_not_called()
            bhramhaputra.assert_not_called()
            bhramhastra.assert_not_called()
            yamuna.assert_not_called()
            manual_sr.assert_not_called()
            scheduler.assert_not_called()
            nse_marketdata.assert_not_called()
            sector_warm.assert_not_called()
            warmup.assert_not_called()

    def test_nse_database_page_apis_are_public_without_session_token(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(backend_app, 'init_registration_db', return_value=None))
            stack.enter_context(patch.object(marketdata_route.nse_mcap_svc, 'get_dashboard', return_value={'ok': True, 'page': 'mcap'}))
            stack.enter_context(patch.object(marketdata_route.nse_ffmc_svc, 'get_job', return_value={'ok': True, 'jobId': 'ffmc-job'}))
            stack.enter_context(patch.object(backend_app.nse_delivery_svc, 'get_trading_day_verification', return_value={'ok': True, 'page': 'delivery'}))
            stack.enter_context(patch.object(automation_status_route.status_svc, 'load_status', return_value={'current_status': 'IDLE'}))
            app = backend_app.create_app(
                enable_background_jobs=False,
                enable_warmup=False,
                enable_marketdata_auto_merge=False,
            )
            client = app.test_client()

            mcap_summary = client.get('/api/marketdata/nse-mcap/summary')
            ffmc_job = client.get('/api/marketdata/nse-ffmc/jobs/ffmc-job')
            delivery_verification = client.get('/api/market-calendar/trading-day-verification?page=DELIVERY&year=2026')
            automation_status = client.get('/api/automation/nse-marketdata/status')

            self.assertEqual(mcap_summary.status_code, 200)
            self.assertEqual(ffmc_job.status_code, 200)
            self.assertEqual(delivery_verification.status_code, 200)
            self.assertEqual(automation_status.status_code, 200)

    def test_create_app_can_start_manual_sr_ingest_without_all_background_jobs(self):
        with ExitStack() as stack:
            marketdata = stack.enter_context(patch.object(backend_app, 'start_marketdata_auto_merge', return_value=None))
            asura = stack.enter_context(patch.object(backend_app, 'start_asura_auto_insert', return_value=None))
            bhramhaputra = stack.enter_context(patch.object(backend_app, 'start_bhramhaputra_auto_insert', return_value=None))
            bhramhastra = stack.enter_context(patch.object(backend_app, 'start_bhramhastra_auto_insert', return_value=None))
            yamuna = stack.enter_context(patch.object(backend_app, 'start_yamuna_auto_ingest', return_value=None))
            manual_sr = stack.enter_context(patch.object(backend_app, 'start_manual_sr_image_auto_ingest_scheduler', return_value=None))
            scheduler = stack.enter_context(patch.object(backend_app, 'start_strategy_agent_scheduler', return_value=None))
            nse_marketdata = stack.enter_context(patch.object(backend_app, 'start_nse_marketdata_auto_scheduler', return_value=None))
            sector_warm = stack.enter_context(patch.object(backend_app, 'warm_sector_rotation_cache', return_value=None))
            warmup = stack.enter_context(patch.object(backend_app, 'warm_in_background', return_value=None))

            app = backend_app.create_app(
                enable_background_jobs=False,
                enable_warmup=False,
                enable_marketdata_auto_merge=False,
                enable_manual_sr_image_auto_ingest=True,
            )

            self.assertIsNotNone(app)
            marketdata.assert_not_called()
            asura.assert_not_called()
            bhramhaputra.assert_not_called()
            bhramhastra.assert_not_called()
            yamuna.assert_not_called()
            scheduler.assert_not_called()
            nse_marketdata.assert_not_called()
            sector_warm.assert_not_called()
            warmup.assert_not_called()
            manual_sr.assert_called_once()

    def test_create_app_can_explicitly_start_nse_marketdata_automation(self):
        with ExitStack() as stack:
            nse_marketdata = stack.enter_context(patch.object(backend_app, 'start_nse_marketdata_auto_scheduler', return_value=None))
            stack.enter_context(patch.object(backend_app, 'init_registration_db', return_value=None))
            stack.enter_context(patch.object(backend_app, 'start_marketdata_auto_merge', return_value=None))

            app = backend_app.create_app(
                enable_background_jobs=False,
                enable_warmup=False,
                enable_marketdata_auto_merge=False,
                enable_nse_marketdata_automation=True,
            )

            self.assertIsNotNone(app)
            nse_marketdata.assert_called_once()

    def test_create_app_registers_prudvi_strategy_api_route(self):
        with patch.object(backend_app, 'init_registration_db', return_value=None):
            app = backend_app.create_app(
                enable_background_jobs=False,
                enable_warmup=False,
                enable_marketdata_auto_merge=False,
                enable_nse_marketdata_automation=False,
            )

            self.assertTrue(any(str(rule) == '/api/strategy/prudvi' for rule in app.url_map.iter_rules()))

    def test_api_cors_allows_credentials_for_allowed_origin(self):
        app = backend_app.create_app(enable_background_jobs=False, enable_warmup=False)
        client = app.test_client()

        response = client.options(
            '/api/auth/login',
            headers={
                'Origin': 'http://127.0.0.1:8080',
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'content-type',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'http://127.0.0.1:8080')
        self.assertEqual(response.headers.get('Access-Control-Allow-Credentials'), 'true')

    def test_api_cors_rejects_credentials_for_untrusted_origin(self):
        app = backend_app.create_app(enable_background_jobs=False, enable_warmup=False)
        client = app.test_client()

        response = client.options(
            '/api/auth/login',
            headers={
                'Origin': 'https://evil.example',
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'content-type',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'null')
        self.assertEqual(response.headers.get('Access-Control-Allow-Credentials'), 'false')

    def test_single_port_frontend_serves_react_routes_only(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            dist = root / 'dist'
            for path in (dist / 'react-assets',):
                path.mkdir(parents=True, exist_ok=True)
            (dist / 'index.html').write_text('<div id="root">React shell</div>', encoding='utf-8')
            (dist / 'react-assets' / 'app.js').write_text('console.log("react")', encoding='utf-8')

            with ExitStack() as stack:
                stack.enter_context(patch.object(backend_app, 'init_registration_db', return_value=None))
                stack.enter_context(patch.object(react_spa, 'FRONTEND_DIST_DIR', dist))
                app = backend_app.create_app(
                    enable_background_jobs=False,
                    enable_warmup=False,
                    enable_nse_marketdata_automation=False,
                    enable_marketdata_auto_merge=False,
                )
                client = app.test_client()

                canonical_routes = [
                    '/',
                    '/app/home',
                    '/app/dashboard',
                    '/login',
                    '/register',
                    '/app/portfolio',
                    '/app/technical/ema',
                    '/app/technical/rsi50',
                    '/app/technical/support-resistance',
                    '/app/database/stock-history',
                    '/app/database/historical-data',
                    '/app/database/nse-ffmc',
                    '/app/fyers/automation',
                    '/app/fyers/failed-symbols',
                    '/app/sector/rotation',
                    '/app/sector/stocks/auto',
                    '/app/strategy',
                    '/app/strategy/asura',
                    '/app/strategy/asura-v3',
                    '/app/strategy/stock-chart',
                ]
                for route in canonical_routes:
                    self.assertIn(b'React shell', client.get(route).data, route)

                self.assertEqual(client.get('/dashboard.html').status_code, 404)
                self.assertEqual(client.get('/html/dashboard.html').status_code, 404)
                self.assertEqual(client.get('/assets/main.js').status_code, 404)
                self.assertEqual(client.get('/css/styles.css').status_code, 404)
                self.assertEqual(client.get('/images/Logo.png').status_code, 404)
                self.assertEqual(client.get('/json/market.json').status_code, 404)
                self.assertTrue(client.get('/api').is_json)

    def test_html_routes_stay_unavailable_when_react_build_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            dist = root / 'dist'
            for path in (dist / 'react-assets',):
                path.mkdir(parents=True, exist_ok=True)

            with ExitStack() as stack:
                stack.enter_context(patch.object(backend_app, 'init_registration_db', return_value=None))
                stack.enter_context(patch.object(react_spa, 'FRONTEND_DIST_DIR', dist))
                app = backend_app.create_app(
                    enable_background_jobs=False,
                    enable_warmup=False,
                    enable_nse_marketdata_automation=False,
                    enable_marketdata_auto_merge=False,
                )
                client = app.test_client()

                root_response = client.get('/')
                canonical_response = client.get('/app/dashboard')

                self.assertEqual(root_response.get_json()['frontend'], 'react_build_missing')
                self.assertEqual(canonical_response.status_code, 503)
                self.assertEqual(client.get('/dashboard.html').status_code, 404)
                self.assertEqual(client.get('/html/dashboard.html').status_code, 404)

    def test_chart_compat_bars_endpoint_uses_flask_api_shape(self):
        sample_payload = {
            'symbol': 'RELIANCE',
            'timeframe': 'daily',
            'candles': [
                {'time': '2026-05-08', 'open': 10, 'high': 11, 'low': 9, 'close': 10.5},
                {'time': '2026-05-11', 'open': 10.5, 'high': 12, 'low': 10, 'close': 11.5},
            ],
            'volume': [
                {'time': '2026-05-08', 'value': 1000},
                {'time': '2026-05-11', 'value': 1100},
            ],
        }
        with ExitStack() as stack:
            stack.enter_context(patch.object(backend_app, 'init_registration_db', return_value=None))
            stack.enter_context(patch.object(chart_compat.chart_svc, 'fetch_ohlcv_payload', return_value=sample_payload))
            app = backend_app.create_app(
                enable_background_jobs=False,
                enable_warmup=False,
                enable_nse_marketdata_automation=False,
                enable_marketdata_auto_merge=False,
            )
            response = app.test_client().get('/api/bars?symbol=RELIANCE&tf=1D&limit=1')

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['symbol'], 'RELIANCE')
        self.assertEqual(payload['tf'], '1D')
        self.assertEqual(len(payload['bars']), 1)
        self.assertEqual(payload['bars'][0]['c'], 11.5)


if __name__ == '__main__':
    unittest.main()

