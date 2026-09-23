with open("backend/routes/sector_rotation.py", "r", encoding="utf-8") as f:
    lines = f.readlines()
for i in range(400, 600):
    if i < len(lines):
        print(f"{i+1}: {lines[i]}", end="")
