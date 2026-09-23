import sys
import re
from pathlib import Path
sys.path.insert(0, 'backend')
from db import get_oracle_connection

def run_sql_script(filepath):
    print(f"Reading SQL file: {filepath}")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by / that are on their own line
    # Match / at the start of line or following newline
    blocks = re.split(r'(?:^|\n)/\s*(?:\n|$)', content)
    
    conn = get_oracle_connection()
    cursor = conn.cursor()
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # Remove PROMPT lines
        lines = [line for line in block.split('\n') if not line.upper().startswith('PROMPT') and not line.upper().startswith('SET DEFINE OFF')]
        clean_block = '\n'.join(lines).strip()
        if not clean_block:
            continue
            
        try:
            print(f"Executing block starting with: {clean_block[:80]}")
            cursor.execute(clean_block)
            conn.commit()
            print("Success.")
        except Exception as e:
            print(f"Failed: {e}")
            conn.rollback()

if len(sys.argv) < 2:
    print("Usage: python scratch/run_script.py <sql_file_path>")
    sys.exit(1)

run_sql_script(sys.argv[1])
