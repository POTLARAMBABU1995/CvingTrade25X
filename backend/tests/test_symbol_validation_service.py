import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.symbol_validation_service import symbol_validation_service

def test_normalize_symbol():
    assert symbol_validation_service.normalize_symbol('NSE:ITC-EQ') == 'ITC'
    assert symbol_validation_service.normalize_symbol('BSE:500123') == '500123'
    assert symbol_validation_service.normalize_symbol('  TCS.NS  ') == 'TCS'
    assert symbol_validation_service.normalize_symbol('') == ''

def test_replace_old_symbol():
    assert symbol_validation_service.replace_old_symbol('AMARAJABAT') == 'ARE&M'
    assert symbol_validation_service.replace_old_symbol('APCOTEX') == 'APCOTEXIND'
    assert symbol_validation_service.replace_old_symbol('ITC') == 'ITC'

def test_classify_symbol():
    # Test known invalid/BSE
    assert symbol_validation_service.classify_symbol('SYMBOL') == 'INVALID'
    assert symbol_validation_service.classify_symbol('AGRITECH') == 'INVALID'
    assert symbol_validation_service.classify_symbol('MANDEEP') == 'BELOW_500CR'
    assert symbol_validation_service.classify_symbol('AMARAJABAT') == 'REPLACED'
