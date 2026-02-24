def test_allocator_pass_through():
    from decision.allocator import Allocator, Allocation
    a = Allocator()
    desired = [Allocation(market_id="m1", action="HOLD", size_usd=0, reason="test")]
    out = a.allocate(desired, bankroll_usd=1000)
    assert out == desired
