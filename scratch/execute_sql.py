import sys
import re
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND_ROOT = _HERE.parent / 'backend'
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from db import get_oracle_connection

def execute_sql_file(filepath):
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            with open(filepath, 'r', encoding='utf-8') as f:
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
                
                # Strip single-line comments for detection
                cleaned_block = re.sub(r'--.*$', '', block, flags=re.MULTILINE).strip()
                
                is_plsql = (
                    cleaned_block.upper().startswith('DECLARE') or 
                    cleaned_block.upper().startswith('BEGIN') or
                    cleaned_block.upper().startswith('CREATE')
                )
                if is_plsql:
                    print(f"Executing PL/SQL or CREATE block {i+1}...")
                    if block.endswith('/'):
                        block = block[:-1].strip()
                    cursor.execute(block)
                    if cleaned_block.upper().startswith('SELECT'):
                        rows = cursor.fetchall()
                        if cursor.description:
                            headers = [col[0] for col in cursor.description]
                            print(" | ".join(headers))
                        for row in rows:
                            print(" | ".join(str(val) for val in row))
                else:
                    # Split SQL block by semicolon
                    statements = block.split(';')
                    for stmt in statements:
                        stmt = stmt.strip()
                        if not stmt:
                            continue
                        print(f"\nExecuting SQL statement: {stmt[:150]}...")
                        cursor.execute(stmt)
                        if stmt.strip().upper().startswith('SELECT'):
                            rows = cursor.fetchall()
                            if cursor.description:
                                headers = [col[0] for col in cursor.description]
                                print(" | ".join(headers))
                            for row in rows:
                                print(" | ".join(str(val) for val in row))
            
        conn.commit()
        print("\nSQL File executed successfully!")
    except Exception as e:
        conn.rollback()
        print(f"Execution failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    execute_sql_file(sys.argv[1])
