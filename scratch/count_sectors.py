import csv
import os
from collections import Counter

path = r"G:\SECTOR\CAPITAL GOODS, ENGINEERING & INDUSTRIALS\Capital Goods, Engineering & Industrials.csv"
if os.path.exists(path):
    with open(path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        sectors = [row['SECTOR'] for row in reader]
        print(Counter(sectors))
