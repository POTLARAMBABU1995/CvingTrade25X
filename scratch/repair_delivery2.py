import sys

path = r'C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend\services\nse_delivery_service.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

correct_content = r'''def _record(symbol: str, trade_date: dt.date, **kwargs: Any) -> Dict[str, Any]:
  return {
    'id': kwargs.get('id'),
    'trade_date': trade_date,
    'symbol': str(symbol).strip().upper(),
    'source_name': _FILE_SOURCE,
    'series': (kwargs.get('series') or None),
    'security_name': (kwargs.get('security_name') or None),
    'prev_close': mcap._parse_decimal(kwargs.get('prev_close')),
    'close_price': mcap._parse_decimal(kwargs.get('close_price')),
    'total_traded_qty': mcap._parse_decimal(kwargs.get('total_traded_qty')),
    'turnover_lacs': mcap._parse_decimal(kwargs.get('turnover_lacs')),
    'no_of_trades': mcap._parse_decimal(kwargs.get('no_of_trades')),
    'delivery_qty': mcap._parse_decimal(kwargs.get('delivery_qty')),
    'delivery_pct': mcap._parse_decimal(kwargs.get('delivery_pct')),
    'response_payload': kwargs.get('response_payload'),
    'fetch_status': str(kwargs.get('fetch_status') or 'SUCCESS').upper(),
    'error_message': (str(kwargs.get('error_message') or '')[:2000] or None),
    'created_by': kwargs.get('created_by') or _CREATED_BY,
  }


def _merge_sql() -> str:
  return f"""
    SELECT CAST(:trade_date AS DATE) trade_date,
           CAST(:symbol AS VARCHAR2(50)) symbol,
           CAST(:source_name AS VARCHAR2(50)) source_name,
           CAST(:series AS VARCHAR2(10)) series,
           CAST(:security_name AS VARCHAR2(300)) security_name,
           CAST(:prev_close AS NUMBER(24,6)) prev_close,
           CAST(:close_price AS NUMBER(24,6)) close_price,
           CAST(:total_traded_qty AS NUMBER(24,6)) total_traded_qty,
           CAST(:turnover_lacs AS NUMBER(24,6)) turnover_lacs,
           CAST(:no_of_trades AS NUMBER(24,6)) no_of_trades,
           CAST(:delivery_qty AS NUMBER(24,6)) delivery_qty,
           CAST(:delivery_pct AS NUMBER(12,6)) delivery_pct,
           TO_CLOB(:response_payload) response_payload,
           CAST(:fetch_status AS VARCHAR2(30)) fetch_status,
           CAST(:error_message AS VARCHAR2(2000)) error_message,
           CAST(:created_by AS VARCHAR2(128)) created_by
    FROM dual
  """


def _upsert_records(records: List[Dict[str, Any]]) -> Tuple[int, int]:
  if not records:
    return 0, 0
  conn = mcap.pool.acquire()
  success_count = 0
  failure_count = 0
  update_sql = f"""
    UPDATE {_TABLE_SQL}
       SET series = CASE WHEN :series IS NOT NULL THEN :series ELSE series END,
           security_name = CASE WHEN :security_name IS NOT NULL THEN :security_name ELSE security_name END,
           prev_close = CASE WHEN :prev_close IS NOT NULL THEN :prev_close ELSE prev_close END,
           close_price = CASE WHEN :close_price IS NOT NULL THEN :close_price ELSE close_price END,
           total_traded_qty = CASE WHEN :total_traded_qty IS NOT NULL THEN :total_traded_qty ELSE total_traded_qty END,
           turnover_lacs = CASE WHEN :turnover_lacs IS NOT NULL THEN :turnover_lacs ELSE turnover_lacs END,
           no_of_trades = CASE WHEN :no_of_trades IS NOT NULL THEN :no_of_trades ELSE no_of_trades END,
           delivery_qty = CASE WHEN :delivery_qty IS NOT NULL THEN :delivery_qty ELSE delivery_qty END,
           delivery_pct = CASE WHEN :delivery_pct IS NOT NULL THEN :delivery_pct ELSE delivery_pct END,
           response_payload = CASE WHEN :response_payload IS NOT NULL THEN TO_CLOB(:response_payload) ELSE response_payload END,
           fetch_status = :fetch_status,
           error_message = CASE
             WHEN :fetch_status = 'SUCCESS' THEN NULL
             WHEN :error_message IS NOT NULL THEN :error_message
             ELSE error_message
           END,
           fetch_ts = :trade_date,
           updated_ts = SYSTIMESTAMP,
           created_by = CASE WHEN :created_by IS NOT NULL THEN :created_by ELSE created_by END
     WHERE trade_date = :trade_date
       AND symbol = :symbol
       AND source_name = :source_name
  """
  insert_sql = f"""
    INSERT INTO {_TABLE_SQL} (
      id, trade_date, symbol, source_name, series, security_name, prev_close, close_price,
      total_traded_qty, turnover_lacs, no_of_trades, delivery_qty, delivery_pct,
      response_payload, fetch_status, error_message, fetch_ts, created_by, updated_ts
    ) VALUES (
      :id, :trade_date, :symbol, :source_name, :series, :security_name, :prev_close, :close_price,
      :total_traded_qty, :turnover_lacs, :no_of_trades, :delivery_qty, :delivery_pct,
      TO_CLOB(:response_payload), :fetch_status, :error_message, :trade_date, :created_by, SYSTIMESTAMP
    )
  """
'''

start_idx = text.find('def _record(symbol: str, trade_date: dt.date, **kwargs: Any) -> Dict[str, Any]:')
end_idx = text.find('  try:\n    ensure_runtime(conn)')
if start_idx == -1 or end_idx == -1:
    print('Failed to find markers')
    sys.exit(1)

new_text = text[:start_idx] + correct_content + text[end_idx:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_text)
print('Fixed successfully')
