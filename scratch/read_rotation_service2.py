with open("backend/services/sector_rotation_service.py", "r", encoding="utf-8") as f:
    lines = f.readlines()
for i in range(100, 200):
    if i < len(lines):
        print(f"{i+1}: {lines[i]}", end="")
