import os
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Any, Tuple

from flask import Flask, jsonify, request
from flask_cors import CORS

try:
    import oracledb  # python-oracledb (thin mode by default)
except Exception:  # pragma: no cover
    oracledb = None


def ema(values: List[float], period: int) -> float:
    if not values:
        return None
    k = 2 / (period + 1)
    prev = values[0]
    for v in values[1:]:
        prev = v * k + prev * (1 - k)
    return float(prev)


def _fmt_ddmmyyyy(dt: datetime) -> str:
    try:
        return dt.strftime('%d-%m-%Y')
    except Exception:
        return ''


def _pct_change(latest: float, past: float) -> float | None:
    try:
        if past is None or past == 0 or latest is None:
            return None
        return (latest - past) / past * 100.0
    except Exception:
        return None


def build_rows(series_by_symbol: Dict[str, List[Tuple[datetime, float]]]) -> List[Dict[str, Any]]:
    rows = []
    for symbol, series in series_by_symbol.items():
        if not series:
            continue
        # Ensure sorted by date ascending
        series_sorted = sorted(series, key=lambda x: x[0])
        closes = [float(v) for (_d, v) in series_sorted if v is not None]
        dates = [d for (d, _v) in series_sorted]
        if not closes:
            continue
        price = float(closes[-1])
        last_date = dates[-1] if dates else None
        e20 = ema(closes, 20)
        e50 = ema(closes, 50)
        e100 = ema(closes, 100)
        e200 = ema(closes, 200)

        def flag(p):
            e = ema(closes, p)
            return 'Y' if (e is not None and price > e) else 'N'

        # Percent moves over trading-day windows
        windows = {
            'd5': 5, 'd10': 10, 'd15': 15, 'd22': 22,
            'd44': 44, 'd66': 66, 'd132': 132, 'd188': 188,
            'y1': 252, 'y2': 504, 'y3': 756, 'y4': 1008, 'y5': 1260,
        }
        pct_fields: Dict[str, Any] = {}
        for key, n in windows.items():
            if len(closes) > n:
                past = closes[-(n + 1)]
                pct = _pct_change(price, past)
            else:
                pct = None
            # Provide both display and numeric sort value
            pct_fields[key + 'Sort'] = float(pct) if (pct is not None) else None
            pct_fields[key] = (f"{pct:.2f}%" if pct is not None else '-')

        row = {
            'symbol': symbol,
            'stock': symbol,
            'price': price,
            'priceSort': price,
            # Last traded/close date for convenience in UI
            'ltcDate': _fmt_ddmmyyyy(last_date) if last_date else '',
            # Retain EMA coverage flags for categorization elsewhere if needed
            'd5Flag': flag(5), 'd10Flag': flag(10), 'd15Flag': flag(15), 'd22Flag': flag(22),
            'd44Flag': flag(44), 'd66Flag': flag(66), 'd132Flag': flag(132), 'd188Flag': flag(188),
            'y1Flag': flag(252), 'y2Flag': flag(504), 'y3Flag': flag(756), 'y4Flag': flag(1008), 'y5Flag': flag(1260),
            '_e20': e20, '_e50': e50, '_e100': e100, '_e200': e200,
        }
        # Merge percentage fields
        row.update(pct_fields)
        rows.append(row)
    return rows


def categorize(rows: List[Dict[str, Any]]):
    c1, c2, c3, c4 = [], [], [], []
    for r in rows:
        price = r['price']
        e20, e50, e100, e200 = r.get('_e20'), r.get('_e50'), r.get('_e100'), r.get('_e200')
        if e200 is not None and price > e200:
            c1.append(r)
            if e100 is not None and price > e100:
                c2.append(r)
                if e50 is not None and price > e50:
                    c3.append(r)
                    if e20 is not None and price > e20:
                        c4.append(r)
    # strip internal EMA fields
    def strip(arr):
        out = []
        for i, item in enumerate(arr, 1):
            d = {k: v for k, v in item.items() if not k.startswith('_')}
            d['sNo'] = i
            out.append(d)
        return out
    return strip(c1), strip(c2), strip(c3), strip(c4)


def _build_dsn():
    """Build DSN using either SID or SERVICE_NAME based on env."""
    user = os.getenv('ORACLE_USER', 'system')
    password = os.getenv('ORACLE_PASSWORD', '')
    host = os.getenv('ORACLE_HOST', '127.0.0.1')
    port = int(os.getenv('ORACLE_PORT', '1521'))
    sid = os.getenv('ORACLE_SID')
    service_name = os.getenv('ORACLE_SERVICE_NAME')
    if sid:
        dsn = oracledb.makedsn(host, port, sid=sid)
    else:
        # Default to service_name if provided or 'orcl' if none specified
        dsn = oracledb.makedsn(host, port, service_name=(service_name or 'cvingpdb.local'))
    return user, password, dsn


def fetch_series_from_oracle() -> Dict[str, List[Tuple[datetime, float]]]:
    if oracledb is None:
        raise RuntimeError('python-oracledb is not installed. Run: pip install oracledb')

    user, password, dsn = _build_dsn()
    conn = oracledb.connect(user=user, password=password, dsn=dsn)
    try:
        cur = conn.cursor()
        min_date = datetime.utcnow() - timedelta(days=1500)
        # Fetch last ~1500 days for all symbols, ordered by symbol/date
        schema = os.getenv('ORACLE_SCHEMA', '')
        table = os.getenv('ORACLE_TABLE', 'NSE_NIFTY500_DAILY_RAW_DATA_DEV')
        qualified = f"{schema}.{table}" if schema else table
        sql = (
            f'SELECT SYMBOL, TRADING_DATE, LTP '
            f'FROM {qualified} '
            f'WHERE SYMBOL IS NOT NULL AND TRADING_DATE >= :min_date '
            f'ORDER BY SYMBOL, TRADING_DATE'
        )
        cur.execute(sql, min_date=min_date)
        series_by_symbol: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
        for symbol, trading_date, ltp in cur:
            try:
                # Ensure trading_date is datetime and ltp numeric
                dt = trading_date if isinstance(trading_date, datetime) else None
                cl = float(ltp)
                if dt is not None:
                    series_by_symbol[symbol].append((dt, cl))
            except (TypeError, ValueError):
                # skip malformed rows
                continue
        return series_by_symbol
    finally:
        conn.close()


_CACHE: Dict[str, Any] = {"data": None, "ts": None}
_CACHE_TTL_SECONDS = int(os.getenv('TREND_CACHE_TTL', '300'))  # 5 minutes default


def create_app():
    app = Flask(__name__)
    CORS(app)

    @app.get('/')
    def root():
        return jsonify({
            'name': 'SwingTrade25X API',
            'status': 'online',
            'endpoints': ['/api/health', '/api/config', '/api/trend']
        })

    @app.get('/api')
    def api_index():
        return jsonify({'ok': True, 'endpoints': ['/api/health', '/api/config', '/api/trend']})

    @app.get('/api/health')
    def health():
        db_ok = False
        err = None
        try:
            # Attempt lightweight DB check
            if oracledb is not None:
                user, password, dsn = _build_dsn()
                with oracledb.connect(user=user, password=password, dsn=dsn) as conn:
                    with conn.cursor() as cur:
                        cur.execute('SELECT 1 FROM DUAL')
                        cur.fetchone()
                db_ok = True
        except Exception as e:  # pragma: no cover
            err = str(e)
            db_ok = False
        info = {
            'ok': True,
            'driver': ('python-oracledb' if oracledb is not None else 'unavailable'),
            'db': 'up' if db_ok else 'down',
            'error': err,
        }
        return jsonify(info)

    @app.get('/api/trend')
    def api_trend():
        force_refresh = request.args.get('refresh') in ('1', 'true', 'yes')
        now = datetime.utcnow()
        if (not force_refresh) and _CACHE["data"] and _CACHE["ts"] and (now - _CACHE["ts"]).total_seconds() < _CACHE_TTL_SECONDS:
            return jsonify(_CACHE["data"])
        try:
            series = fetch_series_from_oracle()
            rows = build_rows(series)
            ema200, ema200100, ema20010050, ema2001005020 = categorize(rows)
            payload = {
                'ema200': ema200,
                'ema200100': ema200100,
                'ema20010050': ema20010050,
                'ema2001005020': ema2001005020,
                'cachedAt': now.isoformat() + 'Z'
            }
            _CACHE["data"] = payload
            _CACHE["ts"] = now
            return jsonify(payload)
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @app.get('/api/config')
    def api_config():  # minimal debug info (no secrets)
        schema = os.getenv('ORACLE_SCHEMA', '')
        table = os.getenv('ORACLE_TABLE', 'NSE_NIFTY500_DAILY_RAW_DATA_DEV')
        qualified = f"{schema}.{table}" if schema else table
        return jsonify({
            'host': os.getenv('ORACLE_HOST', 'localhost'),
            'port': int(os.getenv('ORACLE_PORT', '1521')),
            'sid': os.getenv('ORACLE_SID'),
            'service_name': os.getenv('ORACLE_SERVICE_NAME'),
            'user_set': bool(os.getenv('ORACLE_USER')),
            'schema': schema,
            'table': table,
            'qualified_table': qualified,
        })

    return app


if __name__ == '__main__':
    port = int(os.getenv('PORT', '5055'))
    app = create_app()
    app.run(host='0.0.0.0', port=port, debug=True)
