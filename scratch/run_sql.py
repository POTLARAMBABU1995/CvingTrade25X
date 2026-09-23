import os
import subprocess
import tempfile
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X")
load_dotenv(root_dir / '.env')

user = os.getenv("ORACLE_USER", "CVING_APP").strip()
password = os.getenv("ORACLE_PASSWORD", "").strip()
host = os.getenv("ORACLE_HOST", "127.0.0.1").strip()
port = os.getenv("ORACLE_PORT", "1521").strip()
service_name = (os.getenv("ORACLE_SERVICE_NAME") or os.getenv("ORACLE_SERVICE") or "cvingpdb.local").strip()

sqlplus_connect = f'{user}/"{password}"@//{host}:{port}/{service_name}'
sqlplus_exe = r"E:\SOFTWARES\WINDOWS.X64_193000_db_home\bin\sqlplus.exe"

def run_sql_file(script_path):
    script_path = Path(script_path).resolve()
    print(f"Executing: {script_path}")
    
    # Create wrapper file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
        f.write(f"CONNECT {sqlplus_connect}\n")
        f.write(f"@{script_path.as_posix()}\n")
        f.write("EXIT;\n")
        wrapper_path = f.name
        
    try:
        res = subprocess.run(
            [sqlplus_exe, "-S", "/nolog", f"@{wrapper_path}"],
            capture_output=True,
            text=True,
            check=True
        )
        print("Output:\n", res.stdout)
        if res.stderr:
            print("Error:\n", res.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Execution failed with exit code: {e.returncode}")
        print("Output:\n", e.stdout)
        print("Error:\n", e.stderr)
        raise
    finally:
        if os.path.exists(wrapper_path):
            os.remove(wrapper_path)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python run_sql.py <sql_file_path>")
        sys.exit(1)
    run_sql_file(sys.argv[1])
