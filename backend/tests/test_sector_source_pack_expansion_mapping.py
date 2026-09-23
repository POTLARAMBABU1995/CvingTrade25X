from pathlib import Path
import importlib
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sector_rotation = importlib.import_module('routes.sector_rotation')


EXPECTED_SOURCE_PACK_SECTORS = {
    'HOUSEHOLD_PERSONAL_PRODUCTS': 'NSE_NIFTY_HOUSEHOLD_PERSONAL_PRODUCTS_STAGING',
    'COMMODITIES_TRADING': 'NSE_NIFTY_COMMODITIES_TRADING_STAGING',
    'DEFENCE_AEROSPACE_DEFENSE': 'NSE_NIFTY_DEFENCE_AEROSPACE_DEFENSE_STAGING',
    'DIVERSIFIED': 'NSE_NIFTY_DIVERSIFIED_STAGING',
    'BIOTECHNOLOGY': 'NSE_NIFTY_BIOTECHNOLOGY_STAGING',
    'MEDICAL_EQUIPMENT_SUPPLIES': 'NSE_NIFTY_MEDICAL_EQUIPMENT_SUPPLIES_STAGING',
    'IT_ENABLED_SERVICES': 'NSE_NIFTY_IT_ENABLED_SERVICES_STAGING',
    'SOFTWARE_PRODUCTS_SERVICES': 'NSE_NIFTY_SOFTWARE_PRODUCTS_SERVICES_STAGING',
    'MEDIA_ENTERTAINMENT': 'NSE_NIFTY_MEDIA_ENTERTAINMENT_STAGING',
    'PRINT_MEDIA_PUBLISHING': 'NSE_NIFTY_PRINT_MEDIA_PUBLISHING_STAGING',
    'METALS_MINING': 'NSE_NIFTY_METALS_MINING_STAGING',
    'IRON_STEEL': 'NSE_NIFTY_IRON_STEEL_STAGING',
    'MINING': 'NSE_NIFTY_MINING_STAGING',
    'NON_FERROUS_METALS': 'NSE_NIFTY_NON_FERROUS_METALS_STAGING',
    'LPG_CNG_PNG_LNG_SUPPLIER': 'NSE_NIFTY_LPG_CNG_PNG_LNG_SUPPLIER_STAGING',
    'LUBRICANTS': 'NSE_NIFTY_LUBRICANTS_STAGING',
    'OIL_EQUIPMENT_SERVICES': 'NSE_NIFTY_OIL_EQUIPMENT_SERVICES_STAGING',
    'PETROLEUM_PRODUCTS_REFINERIES': 'NSE_NIFTY_PETROLEUM_PRODUCTS_REFINERIES_STAGING',
    'PAPER_PACKAGING': 'NSE_NIFTY_PAPER_PACKAGING_STAGING',
    'WASTE_WATER_MANAGEMENT': 'NSE_NIFTY_WASTE_WATER_MANAGEMENT_STAGING',
    'FOOTWEAR': 'NSE_NIFTY_FOOTWEAR_STAGING',
    'GEMS': 'NSE_NIFTY_GEMS_STAGING',
    'JEWELLERY_WATCHES': 'NSE_NIFTY_JEWELLERY_WATCHES_STAGING',
    'LEATHER_LEATHER_PRODUCTS': 'NSE_NIFTY_LEATHER_LEATHER_PRODUCTS_STAGING',
    'TEXTILES_APPARELS': 'NSE_NIFTY_TEXTILES_APPARELS_STAGING',
}


def test_source_pack_sector_tables_are_registered():
    for sector_code, staging_table in EXPECTED_SOURCE_PACK_SECTORS.items():
        assert sector_code in sector_rotation.SECTOR_CODE_ALIASES
        assert sector_rotation._STRICT_SECTOR_TABLE_MAP[sector_code] == staging_table
        assert sector_code in sector_rotation._SECTOR_DISPLAY_NAME_OVERRIDES


def test_unique_sector_selector_collapses_duplicate_sector_aliases():
    unique_entries = sector_rotation._collapse_sector_entries_for_unique_ui([
        {
            'sectorCode': 'HEALTHCARE_INDEX',
            'sectorName': 'Healthcare Index',
            'tableName': 'NSE_NIFTY_HEALTHCARE_INDEX_STAGING',
            'stockCount': 71,
        },
        {
            'sectorCode': 'NIFTY500_HEALTHCARE',
            'sectorName': 'Nifty500 Healthcare',
            'tableName': 'NSE_NIFTY500_HEALTHCARE_STAGING',
            'stockCount': 50,
        },
        {
            'sectorCode': 'MIDSMALL_HEALTHCARE',
            'sectorName': 'Midsmall Healthcare',
            'tableName': 'NSE_NIFTY_MIDSMALL_HEALTHCARE_STAGING',
            'stockCount': 30,
        },
        {
            'sectorCode': 'CONS_DUR',
            'sectorName': 'Consumer Durables',
            'tableName': 'NSE_NIFTY_CONSUMER_DURABLES_STAGING',
            'stockCount': 35,
        },
        {
            'sectorCode': 'CONSUMER_DURABLES',
            'sectorName': 'Consumer Durables',
            'tableName': 'NSE_NIFTY_CONSUMER_DURABLES_STAGING',
            'stockCount': 34,
        },
        {
            'sectorCode': 'ELEC_HEAVY_EQUIP',
            'sectorName': 'Electricals Heavy Electrical Equipment',
            'tableName': 'NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING',
            'stockCount': 19,
        },
        {
            'sectorCode': 'ELECTRICALS_HEAVY_ELECTRICAL_EQUIPMENT',
            'sectorName': 'Electricals Heavy Electrical Equipment',
            'tableName': 'NSE_NIFTY_ELECTRICALS_HEAVY_ELECTRICAL_EQUIPMENT_STAGING',
            'stockCount': 19,
        },
    ])

    codes = [row['sectorCode'] for row in unique_entries]

    assert codes.count('HEALTHCARE') == 1
    assert 'HEALTHCARE_INDEX' not in codes
    assert 'NIFTY500_HEALTHCARE' not in codes
    assert 'MIDSMALL_HEALTHCARE' not in codes

    assert codes.count('CONSUMER_DURABLES') == 1
    assert 'CONS_DUR' not in codes

    assert codes.count('ELEC_HEAVY_EQUIPMENT') == 1
    assert 'ELEC_HEAVY_EQUIP' not in codes
    assert 'ELECTRICALS_HEAVY_ELECTRICAL_EQUIPMENT' not in codes

    healthcare = next(row for row in unique_entries if row['sectorCode'] == 'HEALTHCARE')
    assert healthcare['tableName'] == 'MERGED_HEALTHCARE_STAGING'
    assert sorted(healthcare['sourceTables']) == sorted([
        'NSE_NIFTY_HEALTHCARE_INDEX_STAGING',
        'NSE_NIFTY500_HEALTHCARE_STAGING',
        'NSE_NIFTY_MIDSMALL_HEALTHCARE_STAGING',
    ])

    consumer_durables = next(row for row in unique_entries if row['sectorCode'] == 'CONSUMER_DURABLES')
    assert consumer_durables['tableName'] == 'NSE_NIFTY_CONSUMER_DURABLES_STAGING'
    assert consumer_durables['stockCount'] == 35

    electricals = next(row for row in unique_entries if row['sectorCode'] == 'ELEC_HEAVY_EQUIPMENT')
    assert electricals['tableName'] == 'NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING'
    assert sorted(electricals['sourceTables']) == sorted([
        'NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING',
        'NSE_NIFTY_ELECTRICALS_HEAVY_ELECTRICAL_EQUIPMENT_STAGING',
    ])
