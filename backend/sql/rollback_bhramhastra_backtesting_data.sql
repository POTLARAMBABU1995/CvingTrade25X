-- Rollback for Bhramhastra backtesting storage.

DROP INDEX IDX_BHRAMHASTRA_BT_STATUS;
DROP INDEX IDX_BHRAMHASTRA_BT_LTC_DATE;
DROP TABLE Bhramhastra_BackTesting_Data PURGE;
