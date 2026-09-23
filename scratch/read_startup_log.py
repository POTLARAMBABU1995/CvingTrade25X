from pathlib import Path

path = Path("logs/cvingtrade25x_startup_events.log")
if path.exists():
    print(path.read_text(encoding='utf-8', errors='ignore'))
else:
    print("Log file does not exist")
