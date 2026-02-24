def test_import_decision_engine():
    from decision.engine import DecisionEngineV0  # noqa
    assert DecisionEngineV0 is not None
