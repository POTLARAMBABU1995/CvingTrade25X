import sys
from pathlib import Path

path = Path("backend_run.log")
if path.exists():
    try:
        content = path.read_bytes()
        # Decode using utf-16 (handles both BE/LE if BOM exists)
        decoded = content.decode('utf-16', errors='ignore')
        lines = decoded.splitlines()
        print("Log content (last 50 lines):")
        for line in lines[-50:]:
            print(line)
    except Exception as e:
        print("Error reading:", e)
else:
    print("Log file does not exist")
