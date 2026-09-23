-- Safe rollback: disable only the additive Dairy records; preserve history.
UPDATE nse_symbol_sector_map SET is_active='N', updated_at=CURRENT_TIMESTAMP WHERE sector_code='DAIRY_MILK_PRODUCTS';
UPDATE nse_sector_master SET is_active='N', updated_at=CURRENT_TIMESTAMP WHERE sector_code='DAIRY_MILK_PRODUCTS';
COMMIT;

-- Optional reviewed cleanup of the additive staging object is intentionally not automatic.
