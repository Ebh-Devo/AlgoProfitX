SYNTHETIC_STRATEGY_VERSION_BACKFILL_SQL = """
UPDATE strategy_versions AS version
SET instrument_id = instrument.id
FROM instruments AS instrument
WHERE instrument.id = '20000000-0000-4000-8000-000000000001'
  AND version.configuration ->> 'instrument' = 'TRADEEBH_TEST_EQ'
"""
