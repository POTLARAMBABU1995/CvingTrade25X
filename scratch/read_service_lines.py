with open("backend/services/sector_rotation_service.py", "r", encoding="utf-8") as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if any(t in line for t in ["_SECTOR", "MASTER"]):
        print(f"{i+1}: {line.strip()}")
