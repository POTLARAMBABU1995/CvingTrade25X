filepath = r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend\app.py"
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

import re
matches = re.findall(r'\b\w+\s*=\s*Flask\b', content)
print("Flask instantiation:", matches)
for i, line in enumerate(content.splitlines()):
    if 'Flask' in line or 'app' in line.lower():
        if i < 50:
            print(f"Line {i+1}: {line.strip()}")
