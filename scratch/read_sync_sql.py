with open("backend/sql/create_sector_reference_sync_procedures.sql", "r", encoding="utf-8") as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if "RUBBER" in line:
        print(f"{i+1}: {line.strip()}")
