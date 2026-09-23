import sys
from pathlib import Path

path = Path("logs/cvingtrade25x_flask.log")
if path.exists():
    content = path.read_bytes()
    try:
        decoded = content.decode('utf-8', errors='ignore')
    except Exception:
        decoded = content.decode('utf-16', errors='ignore')
    
    # Write directly to stdout as bytes encoded in utf-8 to prevent cp1252 issues
    lines = decoded.splitlines()[-50:]
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode('utf-8'))
else:
    print("Log file does not exist")
