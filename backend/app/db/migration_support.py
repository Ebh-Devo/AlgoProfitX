SYNTHETIC_STRATEGY_VERSION_BACKFILL_SQL = """
UPDATE strategy_versions AS version
SET instrument_id = instrument.id
FROM instruments AS instrument
WHERE instrument.canonical_symbol = 'TRADEEBH_TEST_EQ'
  AND version.configuration ->> 'instrument' = 'TRADEEBH_TEST_EQ'
"""
