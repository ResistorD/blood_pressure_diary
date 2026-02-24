"""Tests for utility functions."""
import pytest
from datetime import datetime, timezone

from utils.time import now_utc, parse_iso, to_iso, ensure_utc
from utils.pricing import (
    get_mid, calculate_spread, calculate_sum_mid,
    is_tradeable, calculate_edge
)
from utils.validation import (
    ValidationError,
    validate_market_id,
    validate_outcome,
    validate_price,
    validate_positive,
)


class TestTimeUtils:
    """Tests for time utilities."""
    
    def test_now_utc(self):
        """Test now_utc returns datetime with UTC timezone."""
        dt = now_utc()
        assert isinstance(dt, datetime)
        assert dt.tzinfo is not None
        assert dt.tzinfo == timezone.utc
    
    def test_parse_iso_with_z(self):
        """Test parsing ISO timestamp with Z suffix."""
        ts = "2024-01-01T12:00:00Z"
        dt = parse_iso(ts)
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 1
        assert dt.hour == 12
        assert dt.tzinfo is not None
    
    def test_parse_iso_with_offset(self):
        """Test parsing ISO timestamp with timezone offset."""
        ts = "2024-01-01T12:00:00+00:00"
        dt = parse_iso(ts)
        assert dt.year == 2024
        assert dt.tzinfo is not None
    
    def test_parse_iso_with_datetime(self):
        """Test parse_iso with datetime input."""
        dt_in = datetime.now(timezone.utc)
        dt_out = parse_iso(dt_in)
        assert dt_in == dt_out
    
    def test_to_iso(self):
        """Test converting datetime to ISO string."""
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        iso = to_iso(dt)
        assert iso == "2024-01-01T12:00:00+00:00"
    
    def test_ensure_utc_naive(self):
        """Test ensure_utc with naive datetime."""
        dt_naive = datetime(2024, 1, 1, 12, 0, 0)
        dt_utc = ensure_utc(dt_naive)
        assert dt_utc.tzinfo == timezone.utc
        assert dt_utc.year == 2024
    
    def test_ensure_utc_with_tz(self):
        """Test ensure_utc with timezone-aware datetime."""
        dt_utc = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = ensure_utc(dt_utc)
        assert result.tzinfo == timezone.utc


class TestPricingUtils:
    """Tests for pricing utilities."""
    
    def test_get_mid_success(self, sample_snapshots):
        """Test getting mid price."""
        mid = get_mid(sample_snapshots, "YES")
        assert mid == 0.625
    
    def test_get_mid_missing_outcome(self, sample_snapshots):
        """Test get_mid with missing outcome."""
        mid = get_mid(sample_snapshots, "INVALID")
        assert mid is None
    
    def test_get_mid_missing_field(self):
        """Test get_mid with missing mid field."""
        snaps = {"YES": {"bid": 0.5}}
        mid = get_mid(snaps, "YES")
        assert mid is None
    
    def test_calculate_spread(self):
        """Test spread calculation."""
        spread = calculate_spread(0.60, 0.65)
        assert spread == 0.05
    
    def test_calculate_spread_missing(self):
        """Test spread calculation with missing values."""
        assert calculate_spread(None, 0.65) is None
        assert calculate_spread(0.60, None) is None
    
    def test_calculate_sum_mid(self, sample_snapshots):
        """Test YES + NO sum calculation."""
        sum_mid = calculate_sum_mid(sample_snapshots)
        assert sum_mid == 1.0
    
    def test_calculate_sum_mid_missing(self):
        """Test sum_mid with missing data."""
        snaps = {"YES": {"mid": 0.6}}
        assert calculate_sum_mid(snaps) is None
    
    def test_is_tradeable_yes(self):
        """Test tradeability check - positive case."""
        assert is_tradeable(0.03, 100.0, 0.05, 50.0) is True
    
    def test_is_tradeable_high_spread(self):
        """Test tradeability check - spread too high."""
        assert is_tradeable(0.10, 100.0, 0.05, 50.0) is False
    
    def test_is_tradeable_low_liquidity(self):
        """Test tradeability check - liquidity too low."""
        assert is_tradeable(0.03, 30.0, 0.05, 50.0) is False
    
    def test_is_tradeable_missing(self):
        """Test tradeability check with missing values."""
        assert is_tradeable(None, 100.0, 0.05, 50.0) is False
        assert is_tradeable(0.03, None, 0.05, 50.0) is False
    
    def test_calculate_edge_buy(self):
        """Test edge calculation for buy."""
        edge = calculate_edge(0.70, 0.60, "BUY")
        assert edge == 0.10
    
    def test_calculate_edge_sell(self):
        """Test edge calculation for sell."""
        edge = calculate_edge(0.60, 0.70, "SELL")
        assert edge == 0.10


class TestValidationUtils:
    """Tests for validation utilities."""
    
    def test_validate_market_id_success(self):
        """Test valid market ID."""
        validate_market_id("market-123")  # Should not raise
    
    def test_validate_market_id_empty(self):
        """Test empty market ID."""
        with pytest.raises(ValidationError):
            validate_market_id("")
    
    def test_validate_market_id_none(self):
        """Test None market ID."""
        with pytest.raises(ValidationError):
            validate_market_id(None)
    
    def test_validate_outcome_yes(self):
        """Test valid YES outcome."""
        validate_outcome("YES")  # Should not raise
    
    def test_validate_outcome_no(self):
        """Test valid NO outcome."""
        validate_outcome("NO")  # Should not raise
    
    def test_validate_outcome_invalid(self):
        """Test invalid outcome."""
        with pytest.raises(ValidationError):
            validate_outcome("MAYBE")
    
    def test_validate_price_valid(self):
        """Test valid price."""
        validate_price(0.5)  # Should not raise
        validate_price(0.0)  # Should not raise
        validate_price(1.0)  # Should not raise
    
    def test_validate_price_out_of_range(self):
        """Test price out of range."""
        with pytest.raises(ValidationError):
            validate_price(-0.1)
        with pytest.raises(ValidationError):
            validate_price(1.5)
    
    def test_validate_price_non_numeric(self):
        """Test non-numeric price."""
        with pytest.raises(ValidationError):
            validate_price("0.5")
    
    def test_validate_positive(self):
        """Test positive validation."""
        validate_positive(1.0)  # Should not raise
        validate_positive(0.1)  # Should not raise
    
    def test_validate_positive_zero(self):
        """Test zero is not positive."""
        with pytest.raises(ValidationError):
            validate_positive(0.0)
    
    def test_validate_positive_negative(self):
        """Test negative value."""
        with pytest.raises(ValidationError):
            validate_positive(-1.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
