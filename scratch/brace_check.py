def find_unmatched_before_3152(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    import re
    matches = [m.start() for m in re.finditer(r'"""', content)]
    
    before_3152 = []
    for pos in matches:
        line = content.count('\n', 0, pos) + 1
        if line < 3152:
            before_3152.append(line)
            
    print(f"Total before 3152: {len(before_3152)}")
    print("Lines:", before_3152)

find_unmatched_before_3152(r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend\services\marketdata_service.py")
