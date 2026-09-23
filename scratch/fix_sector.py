import sys

with open('backend/routes/sector_rotation.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    "'AUTO': ['AUTO'],",
    "'AUTO': ['AUTO'],\n    'AUTO_COMPONENTS_EQUIPMENTS': ['AUTO_COMPONENTS_EQUIPMENTS', 'AUTO_COMP_EQUIP'],"
)
content = content.replace(
    "'AUTO_ANCILLARIES': 'NSE_NIFTY_AUTO_ANCILLARIES_STAGING',",
    "'AUTO_ANCILLARIES': 'NSE_NIFTY_AUTO_ANCILLARIES_STAGING',\n    'AUTO_COMPONENTS_EQUIPMENTS': 'NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING',"
)
content = content.replace(
    "'AUTO_ANCILLARIES': 'Auto Ancillaries',",
    "'AUTO_ANCILLARIES': 'Auto Ancillaries',\n    'AUTO_COMPONENTS_EQUIPMENTS': 'Auto Components & Equipments',"
)

with open('backend/routes/sector_rotation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated sector_rotation.py")
