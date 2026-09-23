import re

with open('backend/services/nse_delivery_service.py', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if '_get_dashboard_all' in line:
            print(f"{i}: {line.rstrip()}")
