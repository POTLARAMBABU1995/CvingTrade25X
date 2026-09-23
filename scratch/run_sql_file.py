import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND_ROOT = _HERE.parent / 'backend'
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from db import get_oracle_connection

def execute_sql_file(filepath):
    print(f"Connecting to Oracle DB to execute: {filepath}")
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            with open(filepath, 'r') as f:
                content = f.read()
            
            # Split by / that is on its own line
            blocks = []
            current_block = []
            for line in content.split('\n'):
                if line.strip() == '/':
                    if current_block:
                        blocks.append('\n'.join(current_block))
                        current_block = []
                elif not line.startswith('PROMPT ') and not line.startswith('SET DEFINE '):
                    current_block.append(line)
            
            if current_block:
                cleaned = '\n'.join(current_block).strip()
                if cleaned:
                    blocks.append(cleaned)
            
            for i, block in enumerate(blocks):
                block = block.strip()
                if not block:
                    continue
                print(f"Executing block {i+1}...")
                try:
                    cursor.execute(block)
                except Exception as e:
                    print(f"Error in block {i+1}:\n{block[:200]}...\n{e}")
                    raise
            
        conn.commit()
        print("Success!")
    except Exception as e:
        conn.rollback()
        print(f"Failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    execute_sql_file(sys.argv[1])
