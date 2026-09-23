import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND_ROOT = _HERE.parent / 'backend'
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from db import get_oracle_connection

def run_validation(filepath):
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            with open(filepath, 'r') as f:
                content = f.read()
            
            # Clean up content: handle PROMPT lines
            cleaned_statements = []
            current_stmt = []
            
            for line in content.split('\n'):
                line_str = line.strip()
                if line_str.startswith('PROMPT'):
                    # Output prompt immediately
                    print(f"\n=== {line_str[7:].strip()} ===")
                elif line_str.startswith('SET DEFINE'):
                    continue
                else:
                    current_stmt.append(line)
                    if ';' in line:
                        stmt_text = '\n'.join(current_stmt).replace(';', '').strip()
                        if stmt_text:
                            cleaned_statements.append(stmt_text)
                        current_stmt = []
            
            if current_stmt:
                stmt_text = '\n'.join(current_stmt).replace(';', '').strip()
                if stmt_text:
                    cleaned_statements.append(stmt_text)
            
            for stmt in cleaned_statements:
                print(f"Executing Query:\n{stmt}")
                try:
                    cursor.execute(stmt)
                    if cursor.description:
                        cols = [c[0] for c in cursor.description]
                        print(" | ".join(cols))
                        print("-" * 50)
                        rows = cursor.fetchall()
                        for row in rows:
                            print(" | ".join(str(val) for val in row))
                    else:
                        print("Done.")
                except Exception as e:
                    print(f"Error executing statement:\n{stmt}\nError: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    run_validation(sys.argv[1])
