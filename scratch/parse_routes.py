filepath = r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend\routes\sector_rotation.py"
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

for i, line in enumerate(content.splitlines()):
    if line.startswith('@bp.'):
        print(f"Line {i+1}: {line}")
        # print the next line which is the def statement
        print(f"  {content.splitlines()[i+1]}")
