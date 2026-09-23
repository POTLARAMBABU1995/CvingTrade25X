import re

path = r'C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend\services\nse_delivery_service.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# First replace the whole _upsert_records down to insert_sql using a non-greedy regex
pattern = r"def _upsert_records\(records: List\[Dict\[str, Any\]\]\) -> Tuple\[int, int\]:.*?insert_sql = f\x22\x22\x22"

replacement = """def _upsert_records(records: List[Dict[str, Any]]) -> Tuple[int, int]:
  if not records:
    return 0, 0
  conn = mcap.pool.acquire()
  success_count = 0
  failure_count = 0
  update_sql = f\"\"\"
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
  \"\"\"
  insert_sql = f\"\"\""""

new_text = re.sub(pattern, replacement.replace('\\"', '"'), text, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_text)

print('Replaced:', text != new_text)
