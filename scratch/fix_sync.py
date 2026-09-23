import sys

with open('backend/sql/create_sector_reference_sync_procedures.sql', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    "  append_stage_source('NSE_NIFTY_AUTO_STAGING', 'AUTO', 60);",
    "  append_stage_source('NSE_NIFTY_AUTO_STAGING', 'AUTO', 60);\n  append_stage_source('NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING', 'AUTO_COMPONENTS_EQUIPMENTS', 60);"
)

with open('backend/sql/create_sector_reference_sync_procedures.sql', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated create_sector_reference_sync_procedures.sql")
