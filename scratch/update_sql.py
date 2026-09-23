import os

sql_path = r"backend/sql/sector_rotation_composite.sql"
with open(sql_path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace('\r\n', '\n')

old_mcap = (
    "    LEFT JOIN cving_nse_market_cap_hist t\n"
    "      ON UPPER(TRIM(t.symbol)) = u.symbol\n"
    "     AND t.trade_date <= (SELECT trade_date FROM anchor_date)\n"
    "     AND NVL(UPPER(t.fetch_status), 'SUCCESS') = 'SUCCESS'"
)

new_mcap = (
    "    LEFT JOIN cving_nse_market_cap_hist t\n"
    "      ON UPPER(TRIM(t.symbol)) = u.symbol\n"
    "     AND t.trade_date = (SELECT trade_date FROM anchor_date)\n"
    "     AND NVL(UPPER(t.fetch_status), 'SUCCESS') = 'SUCCESS'"
)

old_ffmc = (
    "    LEFT JOIN cving_nse_ffmc_hist t\n"
    "      ON UPPER(TRIM(t.symbol)) = u.symbol\n"
    "     AND t.trade_date <= (SELECT trade_date FROM anchor_date)\n"
    "     AND NVL(UPPER(t.fetch_status), 'SUCCESS') = 'SUCCESS'"
)

new_ffmc = (
    "    LEFT JOIN cving_nse_ffmc_hist t\n"
    "      ON UPPER(TRIM(t.symbol)) = u.symbol\n"
    "     AND t.trade_date = (SELECT trade_date FROM anchor_date)\n"
    "     AND NVL(UPPER(t.fetch_status), 'SUCCESS') = 'SUCCESS'"
)

old_delivery = (
    "delivery_stats AS (\n"
    "    SELECT\n"
    "        sector_code,\n"
    "        symbol,\n"
    "        MAX(CASE WHEN rn_desc = 1 THEN trade_date END) AS latest_delivery_date,\n"
    "        MAX(CASE WHEN rn_desc = 1 THEN delivery_qty END) AS latest_delivery_qty,\n"
    "        MAX(CASE WHEN rn_desc = 1 THEN delivery_pct END) AS latest_delivery_pct,\n"
    "        MAX(CASE WHEN rn_desc = 1 THEN total_traded_qty END) AS latest_traded_qty,\n"
    "        MAX(CASE WHEN rn_desc = 1 THEN no_of_trades END) AS latest_trade_count,\n"
    "        MAX(CASE WHEN rn_desc = 1 THEN turnover_lacs END) AS latest_turnover_lacs,"
)

new_delivery = (
    "delivery_stats AS (\n"
    "    SELECT\n"
    "        sector_code,\n"
    "        symbol,\n"
    "        MAX(CASE WHEN rn_desc = 1 AND trade_date = (SELECT trade_date FROM anchor_date) THEN trade_date END) AS latest_delivery_date,\n"
    "        MAX(CASE WHEN rn_desc = 1 AND trade_date = (SELECT trade_date FROM anchor_date) THEN delivery_qty END) AS latest_delivery_qty,\n"
    "        MAX(CASE WHEN rn_desc = 1 AND trade_date = (SELECT trade_date FROM anchor_date) THEN delivery_pct END) AS latest_delivery_pct,\n"
    "        MAX(CASE WHEN rn_desc = 1 AND trade_date = (SELECT trade_date FROM anchor_date) THEN total_traded_qty END) AS latest_traded_qty,\n"
    "        MAX(CASE WHEN rn_desc = 1 AND trade_date = (SELECT trade_date FROM anchor_date) THEN no_of_trades END) AS latest_trade_count,\n"
    "        MAX(CASE WHEN rn_desc = 1 AND trade_date = (SELECT trade_date FROM anchor_date) THEN turnover_lacs END) AS latest_turnover_lacs,"
)

if old_mcap in content:
    content = content.replace(old_mcap, new_mcap)
    print("Replaced MCAP join.")
else:
    print("Warning: old_mcap pattern not found!")

if old_ffmc in content:
    content = content.replace(old_ffmc, new_ffmc)
    print("Replaced FFMC join.")
else:
    print("Warning: old_ffmc pattern not found!")

if old_delivery in content:
    content = content.replace(old_delivery, new_delivery)
    print("Replaced Delivery stats.")
else:
    print("Warning: old_delivery pattern not found!")

with open(sql_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Finished writing file.")
