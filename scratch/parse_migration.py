filepath = r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\db\migration\restore_cving_app.py"
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.splitlines()
for j in range(99, 125):
    print(f"Line {j+1}: {lines[j]}")
