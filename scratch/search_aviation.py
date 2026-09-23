import os

search_term = "AVIATION"
found = []
for root, dirs, files in os.walk("backend"):
    for file in files:
        if file.endswith((".py", ".sql")):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if search_term in content:
                        found.append(path)
            except Exception as e:
                pass

print("Found in:")
for p in found:
    print(p)
