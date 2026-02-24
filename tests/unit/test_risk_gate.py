from __future__ import annotations

from app.config import RiskConfig
from app.risk_gate import RiskGate
from domain.models import Market


class _Settings:
    def __init__(self, risk: RiskConfig):
        self.risk = risk
        self.risk_window_minutes = 60
        self.quality_window_minutes = 180


def _seed_market(repo, market_id: str, group_key: str = "g1") -> None:
    repo.insert_market(Market(market_id=market_id, slug=market_id, title=market_id, group_key=group_key))


def test_risk_gate_blocks_max_open_positions(repo):
    _seed_market(repo, "m1", "g1")
    _seed_market(repo, "m2", "g1")
    repo.paper_buy(run_id="r", market_id="m1", outcome="YES", qty=1.0, price=10.0)

    settings = _Settings(RiskConfig(max_open_positions=1, auto_kill_on_limit_breach=False))
    gate = RiskGate(repo, settings)
    v = gate.check_market("m2")
    assert v.allow is False
    assert v.code == "LIMIT"


def test_risk_gate_blocks_capital_usage_pct(repo):
    _seed_market(repo, "m1", "g1")
    _seed_market(repo, "m2", "g1")
    repo.paper_buy(run_id="r", market_id="m1", outcome="YES", qty=1.0, price=60.0)

    settings = _Settings(
        RiskConfig(
            max_open_positions=10,
            max_notional_total=100.0,
            max_notional_per_group=100.0,
            max_notional_per_market=100.0,
            max_capital_usage_pct=0.5,  # 50%
            auto_kill_on_limit_breach=False,
        )
    )
    gate = RiskGate(repo, settings)
    v = gate.check_market("m2")
    assert v.allow is False
    assert v.code == "LIMIT"
    assert "capital usage" in v.reason


def test_risk_gate_blocks_exposure_per_cluster(repo):
    _seed_market(repo, "m1", "g-alpha")
    _seed_market(repo, "m2", "g-alpha")
    repo.paper_buy(run_id="r", market_id="m1", outcome="YES", qty=1.0, price=80.0)

    settings = _Settings(
        RiskConfig(
            max_open_positions=10,
            max_notional_total=1000.0,
            max_notional_per_group=50.0,
            max_notional_per_market=50.0,
            auto_kill_on_limit_breach=False,
        )
    )
    gate = RiskGate(repo, settings)
    v = gate.check_market("m2")
    assert v.allow is False
    assert v.code == "LIMIT"


def test_risk_gate_auto_kill_switch(repo):
    _seed_market(repo, "m1", "g1")
    _seed_market(repo, "m2", "g1")
    repo.paper_buy(run_id="r", market_id="m1", outcome="YES", qty=1.0, price=10.0)

    settings = _Settings(RiskConfig(max_open_positions=1, auto_kill_on_limit_breach=True))
    gate = RiskGate(repo, settings)
    v = gate.check_market("m2")
    assert v.allow is False
    assert v.code == "KILL"
    assert repo.get_bool_setting("kill_switch", default=False) is True
