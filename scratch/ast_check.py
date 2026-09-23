import ast
import traceback

try:
    with open("backend/services/marketdata_service.py", "r", encoding="utf-8") as f:
        content = f.read()
    ast.parse(content)
    print("No AST syntax errors found!")
except SyntaxError as exc:
    print(f"SyntaxError: {exc.msg}")
    print(f"Line: {exc.lineno}, Col: {exc.offset}")
    print(f"Text: {exc.text}")
except Exception as exc:
    traceback.print_exc()
