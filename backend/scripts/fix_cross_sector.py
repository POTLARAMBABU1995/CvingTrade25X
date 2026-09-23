import glob
import textwrap

code_to_add = '''
            if conflicts:
                for conflict in conflicts:
                    cursor.execute(f"DELETE FROM {conflict['tableName']} WHERE SYMBOL = :1", [conflict['symbol']])
                conn.commit()
                conflicts = _find_cross_sector_conflicts(cursor, symbols)
'''
for f in glob.glob('backend/scripts/load_*_sector_file.py'):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # We replace the bad indent block using regex or direct replacement
    # Actually, I'll just restore the original string then replace properly.
    if "if conflicts:\n                  for conflict in conflicts:" in content:
        # It's badly indented. Let's fix it by replacing the bad block.
        bad_block = '''
              if conflicts:
                  for conflict in conflicts:
                      cursor.execute(f"DELETE FROM {conflict['tableName']} WHERE SYMBOL = :1", [conflict['symbol']])
                  conn.commit()
                  conflicts = _find_cross_sector_conflicts(cursor, symbols)

              summary['crossSectorConflicts'] = conflicts'''
        good_block = '''
            if conflicts:
                for conflict in conflicts:
                    cursor.execute(f"DELETE FROM {conflict['tableName']} WHERE SYMBOL = :1", [conflict['symbol']])
                conn.commit()
                conflicts = _find_cross_sector_conflicts(cursor, symbols)
            summary['crossSectorConflicts'] = conflicts'''
        content = content.replace(bad_block, good_block)
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
