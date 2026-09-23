import sys
from datetime import datetime

with open('CHANGELOG.md', 'r', encoding='utf-8') as f:
    content = f.read()

now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')

changelog_entry = f"""## v37-auto-components-equipments-sector - {now_str}

### Summary

Added the new sector "Auto Components & Equipments" using the staging-table-driven architecture, registered it in the canonical reference sync view, and verified its successful synchronization and loading.

### Files Changed

- `backend/sql/create_sector_reference_sync_procedures.sql`
- `backend/routes/sector_rotation.py`
- `backend/sql/create_auto_components_equipments_sector_tables.sql`
- `backend/sql/validate_auto_components_equipments_sector_tables.sql`
- `backend/sql/rollback_auto_components_equipments_sector_tables.sql`
- `CHANGELOG.md`

### Before Logic

The database lacked the `NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING` staging table, and its master/reference sync metadata was missing.

### After Logic

Staging table was created and populated with valid 108 unique symbols from the source CSV files. Duplicate ownership validation guards were put in place. The new sector was registered in the `VW_NSE_CANONICAL_SECTOR_STAGE` view and backend maps.

### Validation

- Run `backend/sql/create_auto_components_equipments_sector_tables.sql`
- Run `backend/sql/validate_auto_components_equipments_sector_tables.sql`

### Rollback

Run rollback script `backend/sql/rollback_auto_components_equipments_sector_tables.sql` to clean staging table and metadata.
"""

content = content.replace("# Changelog\n", f"# Changelog\n\n{changelog_entry}")

with open('CHANGELOG.md', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated CHANGELOG.md")
