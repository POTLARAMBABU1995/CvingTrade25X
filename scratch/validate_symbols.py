import os
from dotenv import load_dotenv

root_dir = r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X"
load_dotenv(os.path.join(root_dir, '.env'))

import sys
sys.path.append(os.path.join(root_dir, 'backend'))
from db import get_oracle_connection

conn = get_oracle_connection()
try:
    with conn.cursor() as cursor:
        auto_anc_csv = ['ACGL', 'ALICON', 'APOLLOTYRE', 'ARE&M', 'ASAHIINDIA', 'ASAL', 'ASKAUTOLTD', 'AUTOAXLES', 'BALKRISIND', 'BANCOINDIA', 'BHARATFORG', 'BOSCHLTD', 'CEATLTD', 'CIEINDIA', 'CRAFTSMAN', 'ENDURANCE', 'EXIDEIND', 'FIEMIND', 'GABRIEL', 'GNA', 'HBLENGINE', 'JAMNAAUTO', 'JBMA', 'JKTYRE', 'JTEKTINDIA', 'KROSS', 'LGBROSLTD', 'LUMAXIND', 'LUMAXTECH', 'MENONBE', 'MINDACORP', 'MMFORG', 'MOTHERSON', 'MRF', 'MSUMI', 'MUNJALAU', 'MUNJALSHOW', 'NDRAUTO', 'PRICOLLTD', 'RACLGEAR', 'RANEMADRAS', 'RICOAUTO', 'RKFORGE', 'ROLEXRINGS', 'SANDHAR', 'SCHAEFFLER', 'SHANTHIGEA', 'SONACOMS', 'SSWL', 'SUBROS', 'SUNCLAY', 'SUNDRMFAST', 'SUPRAJIT', 'TALBROAUTO', 'TIINDIA', 'UNOMINDA', 'VARROC', 'ZFCVINDIA']
        
        valid_symbols = []
        invalid_symbols = []
        
        for s in auto_anc_csv:
            # Check if exists in DIM_SYMBOLS or raw data
            cursor.execute("SELECT COUNT(*) FROM DIM_SYMBOLS WHERE UPPER(TRIM(symbol)) = :sym", {'sym': s})
            in_dim = cursor.fetchone()[0] > 0
            
            cursor.execute("SELECT COUNT(*) FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV WHERE UPPER(TRIM(symbol)) = :sym", {'sym': s})
            in_raw = cursor.fetchone()[0] > 0
            
            if in_dim or in_raw:
                valid_symbols.append(s)
            else:
                invalid_symbols.append(s)
                
        print("Valid symbols in DB:", len(valid_symbols))
        print(valid_symbols)
        print("\nInvalid symbols in DB:", len(invalid_symbols))
        print(invalid_symbols)
finally:
    conn.close()
