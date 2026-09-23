import os
import sys

root_dir = r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X"
sys.path.append(os.path.join(root_dir, 'backend'))

import importlib.machinery
import importlib.util

loader = importlib.machinery.SourceFileLoader('app_module', os.path.join(root_dir, 'backend', 'app.py'))
spec = importlib.util.spec_from_loader('app_module', loader)
app_module = importlib.util.module_from_spec(spec)
loader.exec_module(app_module)

print("Variables in app_module:")
for k, v in vars(app_module).items():
    if not k.startswith('__'):
        print(f"  {k}: {type(v)}")
