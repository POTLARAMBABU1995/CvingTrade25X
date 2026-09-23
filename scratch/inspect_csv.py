import csv
import os

path = r"G:\SECTOR\CAPITAL GOODS, ENGINEERING & INDUSTRIALS\Capital Goods, Engineering & Industrials.csv"
if os.path.exists(path):
    print("File exists")
    with open(path, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        print("Header:", header)
        for i in range(5):
            try:
                print(next(reader))
            except StopIteration:
                break
else:
    print("File does not exist")
