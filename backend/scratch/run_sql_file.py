import sys
import re
from pathlib import Path

_BACKEND_ROOT = Path(r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend")
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from db import get_oracle_connection

def run_sql_file(file_path: Path):
    print(f"Executing: {file_path}")
    content = file_path.read_text(encoding='utf-8')
    
    # Remove single line comments starting with --
    # and SQL*Plus commands (PROMPT, SET, EXIT, etc.)
    lines = content.split('\n')
    filtered_lines = []
    for line in lines:
        line_strip = line.strip()
        if line_strip.startswith('--') or line_strip.upper().startswith('PROMPT') or line_strip.upper().startswith('SET') or line_strip.upper().startswith('EXIT'):
            continue
        filtered_lines.append(line)
        
    content_clean = '\n'.join(filtered_lines)
    
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cur:
            # Split by '/' for PL/SQL block and other statements
            statements = content_clean.split('/')
            for stmt in statements:
                stmt_clean = stmt.strip()
                if not stmt_clean:
                    continue
                
                # Split by ';' if it's not a PL/SQL block
                if 'DECLARE' not in stmt_clean.upper() and 'BEGIN' not in stmt_clean.upper():
                    sub_stmts = stmt_clean.split(';')
                    for sub in sub_stmts:
                        sub_clean = sub.strip()
                        if not sub_clean or sub_clean.upper() in ('COMMIT', 'EXIT'):
                            continue
                        print(f"Running: {sub_clean[:100]}...")
                        cur.execute(sub_clean)
                else:
                    # Run PL/SQL block as is (remove trailing slash if any)
                    print(f"Running PL/SQL block: {stmt_clean[:100]}...")
                    cur.execute(stmt_clean)
            conn.commit()
            print("Successfully executed.")
    except Exception as e:
        conn.rollback()
        print(f"Error executing SQL: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python run_sql_file.py <path_to_sql_file>")
        sys.exit(1)
    run_sql_file(Path(sys.argv[1]))
