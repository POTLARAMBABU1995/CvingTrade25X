with open("backend/services/sector_rotation_service.py", "r", encoding="utf-8") as f:
    content = f.read()

for term in ["STAGING", "STRICT", "_SECTOR", "master", "MASTER"]:
    if term in content:
        print(f"Term '{term}' found in sector_rotation_service.py")
