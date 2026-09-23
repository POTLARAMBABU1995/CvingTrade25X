from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _to_date(value: Any) -> Optional[dt.date]:
  if isinstance(value, dt.datetime):
    return value.date()
  if isinstance(value, dt.date):
    return value
  text = str(value or '').strip()
  if not text:
    return None
  normalized = text.replace('Z', '+00:00')
  for candidate in (normalized, normalized.split('T', 1)[0], normalized.split(' ', 1)[0], normalized[:10]):
    try:
      parsed = dt.datetime.fromisoformat(candidate)
      return parsed.date()
    except ValueError:
      pass
  for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d-%b-%Y', '%d-%b-%y', '%Y/%m/%d', '%d/%m/%Y'):
    try:
      return dt.datetime.strptime(text, fmt).date()
    except ValueError:
      continue
  return None


def _to_iso(value: Any) -> Any:
  if isinstance(value, dt.datetime):
    return value.isoformat()
  if isinstance(value, dt.date):
    return value.isoformat()
  return value


def _row_to_dict(cur: Any, row: Sequence[Any]) -> Dict[str, Any]:
  columns = [str(item[0]).lower() for item in (cur.description or [])]
  payload: Dict[str, Any] = {}
  for index, column in enumerate(columns):
    payload[column] = row[index] if index < len(row) else None
  return payload


def _count_value(row: Dict[str, Any], key: str) -> int:
  try:
    return max(0, int(row.get(key) or 0))
  except (TypeError, ValueError):
    return 0


def _iso_or_empty(value: Optional[dt.date]) -> str:
  return value.isoformat() if isinstance(value, dt.date) else ''


def _week_bounds(target_date: dt.date) -> Tuple[dt.date, dt.date]:
  week_start = target_date - dt.timedelta(days=target_date.weekday())
  return week_start, week_start + dt.timedelta(days=6)


def _month_label(first_trade_date: Optional[dt.date], fallback_year: int, fallback_month: int) -> str:
  if isinstance(first_trade_date, dt.date):
    return first_trade_date.strftime('%b %Y')
  return dt.date(fallback_year, max(1, fallback_month), 1).strftime('%b %Y')


def _build_year_rows(cur: Any, table_sql: str, selected_year: int) -> List[Dict[str, Any]]:
  cur.execute(
    f'''SELECT EXTRACT(YEAR FROM trade_date) bucket_year,
               COUNT(DISTINCT trade_date) trade_days,
               COUNT(*) records_count,
               COUNT(DISTINCT symbol) stocks_count,
               MAX(trade_date) latest_trade_date
          FROM {table_sql}
         GROUP BY EXTRACT(YEAR FROM trade_date)
         ORDER BY bucket_year DESC'''
  )
  rows = []
  for item in (cur.fetchall() or []):
    row = _row_to_dict(cur, item)
    bucket_year = _count_value(row, 'bucket_year')
    rows.append({
      'key': str(bucket_year),
      'label': str(bucket_year) if bucket_year else '-',
      'tradeDays': _count_value(row, 'trade_days'),
      'recordsCount': _count_value(row, 'records_count'),
      'stocksCount': _count_value(row, 'stocks_count'),
      'latestTradeDate': _to_iso(row.get('latest_trade_date')) or '',
      'isSelected': bucket_year == selected_year,
    })
  return rows


def _build_month_rows(cur: Any, table_sql: str, selected_year: int, selected_month: int) -> List[Dict[str, Any]]:
  cur.execute(
    f'''SELECT EXTRACT(MONTH FROM trade_date) bucket_month,
               MIN(trade_date) first_trade_date,
               COUNT(DISTINCT trade_date) trade_days,
               COUNT(*) records_count,
               COUNT(DISTINCT symbol) stocks_count,
               MAX(trade_date) latest_trade_date
          FROM {table_sql}
         WHERE EXTRACT(YEAR FROM trade_date) = :selected_year
         GROUP BY EXTRACT(MONTH FROM trade_date)
         ORDER BY bucket_month DESC''',
    {'selected_year': selected_year}
  )
  rows = []
  for item in (cur.fetchall() or []):
    row = _row_to_dict(cur, item)
    bucket_month = _count_value(row, 'bucket_month')
    first_trade_date = _to_date(row.get('first_trade_date'))
    rows.append({
      'key': f'{selected_year:04d}-{bucket_month:02d}',
      'label': _month_label(first_trade_date, selected_year, bucket_month),
      'tradeDays': _count_value(row, 'trade_days'),
      'recordsCount': _count_value(row, 'records_count'),
      'stocksCount': _count_value(row, 'stocks_count'),
      'latestTradeDate': _to_iso(row.get('latest_trade_date')) or '',
      'isSelected': bucket_month == selected_month,
    })
  return rows


def _build_week_rows(cur: Any, table_sql: str, selected_year: int, selected_month: int, selected_date: dt.date) -> List[Dict[str, Any]]:
  selected_week_start, _selected_week_end = _week_bounds(selected_date)
  cur.execute(
    f'''SELECT TRUNC(trade_date, 'IW') week_start,
               MIN(trade_date) first_trade_date,
               MAX(trade_date) latest_trade_date,
               COUNT(DISTINCT trade_date) trade_days,
               COUNT(*) records_count,
               COUNT(DISTINCT symbol) stocks_count
          FROM {table_sql}
         WHERE EXTRACT(YEAR FROM trade_date) = :selected_year
           AND EXTRACT(MONTH FROM trade_date) = :selected_month
         GROUP BY TRUNC(trade_date, 'IW')
         ORDER BY week_start DESC''',
    {'selected_year': selected_year, 'selected_month': selected_month}
  )
  rows = []
  for item in (cur.fetchall() or []):
    row = _row_to_dict(cur, item)
    week_start = _to_date(row.get('week_start'))
    latest_trade_date = _to_date(row.get('latest_trade_date'))
    label = '-'
    if isinstance(week_start, dt.date) and isinstance(latest_trade_date, dt.date):
      label = f'{week_start.strftime("%d %b")} - {latest_trade_date.strftime("%d %b")}'
    rows.append({
      'key': _to_iso(row.get('week_start')) or '',
      'label': label,
      'weekStart': _to_iso(row.get('week_start')) or '',
      'weekEnd': _to_iso(row.get('latest_trade_date')) or '',
      'tradeDays': _count_value(row, 'trade_days'),
      'recordsCount': _count_value(row, 'records_count'),
      'stocksCount': _count_value(row, 'stocks_count'),
      'isSelected': week_start == selected_week_start,
    })
  return rows


def _build_day_rows(cur: Any, table_sql: str, selected_date: dt.date) -> List[Dict[str, Any]]:
  week_start, week_end = _week_bounds(selected_date)
  cur.execute(
    f'''SELECT trade_date,
               COUNT(*) records_count,
               COUNT(DISTINCT symbol) stocks_count
          FROM {table_sql}
         WHERE trade_date BETWEEN :week_start AND :week_end
         GROUP BY trade_date
         ORDER BY trade_date DESC''',
    {'week_start': week_start, 'week_end': week_end}
  )
  rows = []
  for item in (cur.fetchall() or []):
    row = _row_to_dict(cur, item)
    trade_date = _to_date(row.get('trade_date'))
    rows.append({
      'key': _to_iso(row.get('trade_date')) or '',
      'label': trade_date.strftime('%d %b %Y') if isinstance(trade_date, dt.date) else '-',
      'tradeDate': _to_iso(row.get('trade_date')) or '',
      'recordsCount': _count_value(row, 'records_count'),
      'stocksCount': _count_value(row, 'stocks_count'),
      'isSelected': trade_date == selected_date,
    })
  return rows


def _where_clause(start_date: Optional[dt.date], end_date: Optional[dt.date]) -> Tuple[str, Dict[str, Any]]:
  if start_date and end_date:
    return ' WHERE trade_date BETWEEN :start_date AND :end_date', {'start_date': start_date, 'end_date': end_date}
  if start_date:
    return ' WHERE trade_date >= :start_date', {'start_date': start_date}
  if end_date:
    return ' WHERE trade_date <= :end_date', {'end_date': end_date}
  return '', {}


def build_overview(conn: Any, table_sql: str, selected_trade_date: Optional[dt.date], start_date: Optional[dt.date] = None, end_date: Optional[dt.date] = None) -> Dict[str, Any]:
  selected_trade_date = _to_date(selected_trade_date)
  start_date = _to_date(start_date)
  end_date = _to_date(end_date)
  where_sql, where_binds = _where_clause(start_date, end_date)
  with conn.cursor() as cur:
    cur.execute(
      f'''SELECT COUNT(*) total_records,
                 COUNT(DISTINCT symbol) total_symbols,
                 COUNT(DISTINCT trade_date) total_trade_dates,
                 MIN(trade_date) earliest_trade_date,
                 MAX(trade_date) latest_trade_date,
                 MAX(fetch_ts) latest_fetch_ts
            FROM {table_sql}'''
    )
    table_totals_row = _row_to_dict(cur, cur.fetchone() or [])
    table_latest_trade_date = _to_date(table_totals_row.get('latest_trade_date'))
    if where_sql:
      cur.execute(
        f'''SELECT COUNT(*) total_records,
                   COUNT(DISTINCT symbol) total_symbols,
                   COUNT(DISTINCT trade_date) total_trade_dates,
                   MIN(trade_date) earliest_trade_date,
                   MAX(trade_date) latest_trade_date,
                   MAX(fetch_ts) latest_fetch_ts
              FROM {table_sql}{where_sql}''',
        where_binds
      )
      totals_row = _row_to_dict(cur, cur.fetchone() or [])
    else:
      totals_row = dict(table_totals_row)

    latest_trade_date = _to_date(totals_row.get('latest_trade_date'))
    resolved_trade_date = selected_trade_date or latest_trade_date or end_date or start_date or table_latest_trade_date
    if resolved_trade_date and start_date and resolved_trade_date < start_date:
      resolved_trade_date = latest_trade_date or end_date or start_date
    if resolved_trade_date and end_date and resolved_trade_date > end_date:
      resolved_trade_date = latest_trade_date or end_date or start_date
    if table_latest_trade_date is None:
      return {
        'stocksCount': 0,
        'recordsCount': 0,
        'earliestTradeDate': '',
        'latestTradeDate': '',
        'latestFetchTs': '',
        'tableStocksCount': 0,
        'tableRecordsCount': 0,
        'tableTradeDatesCount': 0,
        'tableFromDate': '',
        'tableToDate': '',
        'tableLatestFetchTs': '',
        'selectedTradeDate': _iso_or_empty(selected_trade_date),
        'selectedYear': 0,
        'selectedMonth': 0,
        'selectedWeekStart': '',
        'selectedWeekEnd': '',
        'dailyData': 0,
        'dailyStocksCount': 0,
        'weeklyData': 0,
        'monthlyData': 0,
        'yearlyData': 0,
        'years': [],
        'months': [],
        'weeks': [],
        'days': [],
        'selectedDateHasData': False,
      }

    assert resolved_trade_date is not None
    selected_year = resolved_trade_date.year
    selected_month = resolved_trade_date.month
    selected_week_start, selected_week_end = _week_bounds(resolved_trade_date)

    cur.execute(
      f'''SELECT COUNT(*) daily_records,
                 COUNT(DISTINCT symbol) daily_stocks
            FROM {table_sql}
           WHERE trade_date = :selected_trade_date''',
      {'selected_trade_date': resolved_trade_date}
    )
    daily_row = _row_to_dict(cur, cur.fetchone() or [])

    if start_date or end_date:
      cur.execute(
        f'''SELECT EXTRACT(YEAR FROM trade_date) bucket_year,
                   COUNT(DISTINCT trade_date) trade_days,
                   COUNT(*) records_count,
                   COUNT(DISTINCT symbol) stocks_count,
                   MAX(trade_date) latest_trade_date
              FROM {table_sql}
             WHERE trade_date BETWEEN :start_date AND :end_date
             GROUP BY EXTRACT(YEAR FROM trade_date)
             ORDER BY bucket_year DESC''',
        {'start_date': start_date or resolved_trade_date, 'end_date': end_date or resolved_trade_date}
      )
      year_rows = []
      for item in (cur.fetchall() or []):
        row = _row_to_dict(cur, item)
        bucket_year = _count_value(row, 'bucket_year')
        year_rows.append({
          'key': str(bucket_year),
          'label': str(bucket_year) if bucket_year else '-',
          'tradeDays': _count_value(row, 'trade_days'),
          'recordsCount': _count_value(row, 'records_count'),
          'stocksCount': _count_value(row, 'stocks_count'),
          'latestTradeDate': _to_iso(row.get('latest_trade_date')) or '',
          'isSelected': bucket_year == selected_year,
        })

      cur.execute(
        f'''SELECT EXTRACT(MONTH FROM trade_date) bucket_month,
                   MIN(trade_date) first_trade_date,
                   COUNT(DISTINCT trade_date) trade_days,
                   COUNT(*) records_count,
                   COUNT(DISTINCT symbol) stocks_count,
                   MAX(trade_date) latest_trade_date
              FROM {table_sql}
             WHERE trade_date BETWEEN :start_date AND :end_date
               AND EXTRACT(YEAR FROM trade_date) = :selected_year
             GROUP BY EXTRACT(MONTH FROM trade_date)
             ORDER BY bucket_month DESC''',
        {'start_date': start_date or resolved_trade_date, 'end_date': end_date or resolved_trade_date, 'selected_year': selected_year}
      )
      month_rows = []
      for item in (cur.fetchall() or []):
        row = _row_to_dict(cur, item)
        bucket_month = _count_value(row, 'bucket_month')
        first_trade_date = _to_date(row.get('first_trade_date'))
        month_rows.append({
          'key': f'{selected_year:04d}-{bucket_month:02d}',
          'label': _month_label(first_trade_date, selected_year, bucket_month),
          'tradeDays': _count_value(row, 'trade_days'),
          'recordsCount': _count_value(row, 'records_count'),
          'stocksCount': _count_value(row, 'stocks_count'),
          'latestTradeDate': _to_iso(row.get('latest_trade_date')) or '',
          'isSelected': bucket_month == selected_month,
        })

      cur.execute(
        f'''SELECT TRUNC(trade_date, 'IW') week_start,
                   MIN(trade_date) first_trade_date,
                   MAX(trade_date) latest_trade_date,
                   COUNT(DISTINCT trade_date) trade_days,
                   COUNT(*) records_count,
                   COUNT(DISTINCT symbol) stocks_count
              FROM {table_sql}
             WHERE trade_date BETWEEN :start_date AND :end_date
               AND EXTRACT(YEAR FROM trade_date) = :selected_year
               AND EXTRACT(MONTH FROM trade_date) = :selected_month
             GROUP BY TRUNC(trade_date, 'IW')
             ORDER BY week_start DESC''',
        {'start_date': start_date or resolved_trade_date, 'end_date': end_date or resolved_trade_date, 'selected_year': selected_year, 'selected_month': selected_month}
      )
      week_rows = []
      for item in (cur.fetchall() or []):
        row = _row_to_dict(cur, item)
        week_start = _to_date(row.get('week_start'))
        latest_trade_date = _to_date(row.get('latest_trade_date'))
        label = '-'
        if isinstance(week_start, dt.date) and isinstance(latest_trade_date, dt.date):
          label = f'{week_start.strftime("%d %b")} - {latest_trade_date.strftime("%d %b")}'
        week_rows.append({
          'key': _to_iso(row.get('week_start')) or '',
          'label': label,
          'weekStart': _to_iso(row.get('week_start')) or '',
          'weekEnd': _to_iso(row.get('latest_trade_date')) or '',
          'tradeDays': _count_value(row, 'trade_days'),
          'recordsCount': _count_value(row, 'records_count'),
          'stocksCount': _count_value(row, 'stocks_count'),
          'isSelected': week_start == selected_week_start,
        })

      cur.execute(
        f'''SELECT trade_date,
                   COUNT(*) records_count,
                   COUNT(DISTINCT symbol) stocks_count
              FROM {table_sql}
             WHERE trade_date BETWEEN :start_date AND :end_date
               AND trade_date BETWEEN :week_start AND :week_end
             GROUP BY trade_date
             ORDER BY trade_date DESC''',
        {
          'start_date': start_date or resolved_trade_date,
          'end_date': end_date or resolved_trade_date,
          'week_start': selected_week_start,
          'week_end': selected_week_end,
        }
      )
      day_rows = []
      for item in (cur.fetchall() or []):
        row = _row_to_dict(cur, item)
        trade_date = _to_date(row.get('trade_date'))
        day_rows.append({
          'key': _to_iso(row.get('trade_date')) or '',
          'label': trade_date.strftime('%d %b %Y') if isinstance(trade_date, dt.date) else '-',
          'tradeDate': _to_iso(row.get('trade_date')) or '',
          'recordsCount': _count_value(row, 'records_count'),
          'stocksCount': _count_value(row, 'stocks_count'),
          'isSelected': trade_date == resolved_trade_date,
        })
    else:
      year_rows = _build_year_rows(cur, table_sql, selected_year)
      month_rows = _build_month_rows(cur, table_sql, selected_year, selected_month)
      week_rows = _build_week_rows(cur, table_sql, selected_year, selected_month, resolved_trade_date)
      day_rows = _build_day_rows(cur, table_sql, resolved_trade_date)

    daily_records = _count_value(daily_row, 'daily_records')
    daily_stocks = _count_value(daily_row, 'daily_stocks')

    return {
      'stocksCount': _count_value(totals_row, 'total_symbols'),
      'recordsCount': _count_value(totals_row, 'total_records'),
      'totalTradeDates': _count_value(totals_row, 'total_trade_dates'),
      'earliestTradeDate': _to_iso(totals_row.get('earliest_trade_date')) or '',
      'latestTradeDate': _to_iso(totals_row.get('latest_trade_date')) or '',
      'latestFetchTs': _to_iso(totals_row.get('latest_fetch_ts')) or '',
      'tableStocksCount': _count_value(table_totals_row, 'total_symbols'),
      'tableRecordsCount': _count_value(table_totals_row, 'total_records'),
      'tableTradeDatesCount': _count_value(table_totals_row, 'total_trade_dates'),
      'tableFromDate': _to_iso(table_totals_row.get('earliest_trade_date')) or '',
      'tableToDate': _to_iso(table_totals_row.get('latest_trade_date')) or '',
      'tableLatestFetchTs': _to_iso(table_totals_row.get('latest_fetch_ts')) or '',
      'selectedTradeDate': resolved_trade_date.isoformat(),
      'selectedYear': selected_year,
      'selectedMonth': selected_month,
      'selectedWeekStart': selected_week_start.isoformat(),
      'selectedWeekEnd': selected_week_end.isoformat(),
      'dailyData': daily_records,
      'dailyStocksCount': daily_stocks,
      'weeklyData': len(week_rows),
      'monthlyData': len(month_rows),
      'yearlyData': len(year_rows),
      'years': year_rows,
      'months': month_rows,
      'weeks': week_rows,
      'days': day_rows,
      'selectedDateHasData': daily_records > 0,
    }
