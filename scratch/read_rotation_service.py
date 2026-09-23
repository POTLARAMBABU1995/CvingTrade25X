with open("backend/services/sector_rotation_service.py", "r", encoding="utf-8") as f:
    lines = f.readlines()
for i in range(1, 100):
    if i < len(lines):
        print(f"{i}: {lines[i-1]}", end="")
