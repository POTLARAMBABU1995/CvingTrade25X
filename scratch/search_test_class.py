import os

for root, dirs, files in os.walk('.'):
    # Exclude common large/non-source directories
    if any(x in root for x in ['.venv', 'venv', '.git', '.agents', '.codex', '__pycache__', 'node_modules']):
        continue
    for file in files:
        if file.endswith('.py'):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f, 1):
                        if 'TestNseDeliveryService' in line:
                            print(f"{path}:{i}: {line.strip()}")
            except Exception:
                pass
