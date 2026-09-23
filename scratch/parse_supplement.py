filepath = r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend\routes\sector_rotation.py"
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.splitlines()

def print_function(func_name, count=100):
    for i, line in enumerate(lines):
        if f'def {func_name}' in line:
            print(f"=== {func_name} (Line {i+1}) ===")
            for j in range(i, min(i+count, len(lines))):
                print(lines[j])
            print("\n")
            return
    print(f"Function {func_name} not found")

print_function('_load_strict_sector_symbols', 50)
