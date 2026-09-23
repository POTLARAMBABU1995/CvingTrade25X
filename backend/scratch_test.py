import importlib.util
spec = importlib.util.spec_from_file_location("myapp", "app.py")
myapp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(myapp)
app = myapp.create_app()

from routes.sector_rotation import _build_strict_symbol_fallback_rows

with app.app_context():
    rows = _build_strict_symbol_fallback_rows(['BSHSL', 'GODREJAGRO', 'KSCL', 'VENKEYS', 'VSTTILLERS'])
    print("FALLBACK ROWS LEN:", len(rows))
    print("FALLBACK ROWS:", rows)
