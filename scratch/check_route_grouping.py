filepath = r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend\routes\sector_rotation.py"
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()
    
print("UI_SECTOR_GROUPS in sector_rotation.py:", "UI_SECTOR_GROUPS" in content)
print("UI_SECTOR_GROUPS in sector_rotation.py line matches:")
for i, line in enumerate(content.splitlines()):
    if 'UI_SECTOR_GROUPS' in line:
        print(f"  Line {i+1}: {line.strip()}")
