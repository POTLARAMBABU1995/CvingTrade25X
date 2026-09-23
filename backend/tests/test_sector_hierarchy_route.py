from pathlib import Path
import sys

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import routes.sector_hierarchy as hierarchy_route


def _app_client():
    app = Flask(__name__)
    app.register_blueprint(hierarchy_route.bp)
    return app.test_client()


def test_parents_route_returns_success(monkeypatch):
    client = _app_client()
    monkeypatch.setattr(
        hierarchy_route.hierarchy_service,
        'get_parents',
        lambda refresh: {
            'data': [{'parentSector': 'Healthcare', 'stockCount': 56}],
            'metadata': {'cached': False, 'cacheKey': 'k', 'generatedAt': 'x', 'totalParents': 1},
        },
    )

    response = client.get('/api/sector-hierarchy/parents')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['data'][0]['parentSector'] == 'Healthcare'


def test_industries_route_requires_parent_sector():
    client = _app_client()
    response = client.get('/api/sector-hierarchy/industries')
    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['errorCode'] == 'SECTOR_HIERARCHY_VALIDATION_ERROR'


def test_sub_sectors_route_requires_industry_sector():
    client = _app_client()
    response = client.get('/api/sector-hierarchy/sub-sectors?parentSector=Healthcare')
    assert response.status_code == 400
    payload = response.get_json()
    assert payload['errorCode'] == 'SECTOR_HIERARCHY_VALIDATION_ERROR'


def test_summary_route_accepts_refresh(monkeypatch):
    client = _app_client()
    captured = {'refresh': None}

    def _fake_summary(parent_sector: str, refresh: bool):
        captured['refresh'] = refresh
        return {
            'data': {
                'parentSector': parent_sector,
                'totalStocks': 56,
                'industries': [],
            },
            'metadata': {'cached': False, 'cacheKey': 'k', 'generatedAt': 'x'},
        }

    monkeypatch.setattr(hierarchy_route.hierarchy_service, 'get_summary', _fake_summary)

    response = client.get('/api/sector-hierarchy/summary?parentSector=Healthcare&refresh=true')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert captured['refresh'] is True


def test_stocks_route_with_optional_filters(monkeypatch):
    client = _app_client()

    monkeypatch.setattr(
        hierarchy_route.hierarchy_service,
        'get_stocks',
        lambda parent_sector, industry_sector, sub_sector, refresh: {
            'data': {
                'parentSector': parent_sector,
                'industrySector': industry_sector,
                'subSector': sub_sector,
                'totalStocks': 1,
                'stocks': [{'symbol': 'SUNPHARMA', 'exchange': 'NSE'}],
            },
            'metadata': {'cached': False, 'cacheKey': 'k', 'generatedAt': 'x'},
        },
    )

    response = client.get('/api/sector-hierarchy/stocks?parentSector=Healthcare&industrySector=Pharmaceuticals')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['data']['totalStocks'] == 1


def test_tree_route_validation_error_when_missing_parent():
    client = _app_client()
    response = client.get('/api/sector-hierarchy/tree')
    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['errorCode'] == 'SECTOR_HIERARCHY_VALIDATION_ERROR'
