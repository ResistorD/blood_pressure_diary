"""Tests for configuration system."""
import pytest
from pydantic import ValidationError as PydanticValidationError

from app.config import (
    AgentConfig,
    DecisionConfig,
    RiskConfig,
    DispatcherConfig,
    DatabaseConfig,
    AppConfig,
)
from domain.enums import Mode


class TestAgentConfig:
    """Tests for AgentConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = AgentConfig()
        assert config.min_liquidity == 50.0
        assert config.max_spread == 0.10
        assert config.logic_min_delta == 0.08
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = AgentConfig(
            min_liquidity=100.0,
            max_spread=0.05,
        )
        assert config.min_liquidity == 100.0
        assert config.max_spread == 0.05
    
    def test_spread_validation(self):
        """Test spread must be between 0 and 1."""
        with pytest.raises(PydanticValidationError):
            AgentConfig(max_spread=1.5)
        
        with pytest.raises(PydanticValidationError):
            AgentConfig(max_spread=-0.1)
    
    def test_negative_liquidity(self):
        """Test negative liquidity is rejected."""
        with pytest.raises(PydanticValidationError):
            AgentConfig(min_liquidity=-10.0)


class TestDecisionConfig:
    """Tests for DecisionConfig."""
    
    def test_default_values(self):
        """Test default values."""
        config = DecisionConfig()
        assert config.arb_buy_threshold == 0.99
        assert config.arb_close_threshold == 1.00
        assert config.min_emit_interval_sec == 120
    
    def test_threshold_validation(self):
        """Test close threshold must be > buy threshold."""
        with pytest.raises(PydanticValidationError):
            DecisionConfig(
                arb_buy_threshold=1.00,
                arb_close_threshold=0.99,
            )
    
    def test_threshold_equal(self):
        """Test thresholds cannot be equal."""
        with pytest.raises(PydanticValidationError):
            DecisionConfig(
                arb_buy_threshold=1.00,
                arb_close_threshold=1.00,
            )
    
    def test_valid_thresholds(self):
        """Test valid threshold configuration."""
        config = DecisionConfig(
            arb_buy_threshold=0.98,
            arb_close_threshold=1.02,
        )
        assert config.arb_buy_threshold == 0.98
        assert config.arb_close_threshold == 1.02


class TestRiskConfig:
    """Tests for RiskConfig."""
    
    def test_default_values(self):
        """Test default risk limits."""
        config = RiskConfig()
        assert config.max_notional_total == 500.0
        assert config.max_notional_per_group == 250.0
        assert config.max_notional_per_market == 150.0
    
    def test_hierarchy_validation(self):
        """Test group limit cannot exceed total limit."""
        with pytest.raises(PydanticValidationError):
            RiskConfig(
                max_notional_total=500.0,
                max_notional_per_group=600.0,
            )
    
    def test_market_vs_group(self):
        """Test market limit cannot exceed group limit."""
        with pytest.raises(PydanticValidationError):
            RiskConfig(
                max_notional_per_group=250.0,
                max_notional_per_market=300.0,
            )
    
    def test_valid_hierarchy(self):
        """Test valid limit hierarchy."""
        config = RiskConfig(
            max_notional_total=1000.0,
            max_notional_per_group=500.0,
            max_notional_per_market=250.0,
        )
        assert config.max_notional_total == 1000.0
        assert config.max_notional_per_group == 500.0
        assert config.max_notional_per_market == 250.0


class TestDispatcherConfig:
    """Tests for DispatcherConfig."""
    
    def test_default_values(self):
        """Test default dispatcher settings."""
        config = DispatcherConfig()
        assert config.poll_interval_sec == 20
        assert config.reconcile_interval_sec == 60
        assert config.event_batch_size == 500
    
    def test_minimum_values(self):
        """Test minimum value constraints."""
        with pytest.raises(PydanticValidationError):
            DispatcherConfig(poll_interval_sec=0)
        
        with pytest.raises(PydanticValidationError):
            DispatcherConfig(sleep_sec=0.0)


class TestDatabaseConfig:
    """Tests for DatabaseConfig."""
    
    def test_default_values(self):
        """Test default database settings."""
        config = DatabaseConfig()
        assert config.path == "polysyndicate.db"
        assert config.wal_mode is True
        assert config.cache_enabled is True
    
    def test_custom_path(self):
        """Test custom database path."""
        config = DatabaseConfig(path="/tmp/test.db")
        assert config.path == "/tmp/test.db"


class TestAppConfig:
    """Tests for AppConfig."""
    
    def test_default_values(self):
        """Test default application configuration."""
        config = AppConfig()
        assert config.mode == Mode.DRY_RUN
        assert config.api_host == "127.0.0.1"
        assert config.api_port == 8000
        assert config.enable_ingest is True
        assert config.enable_agents is True
    
    def test_nested_configs(self):
        """Test nested configuration objects."""
        config = AppConfig()
        assert isinstance(config.agent, AgentConfig)
        assert isinstance(config.decision, DecisionConfig)
        assert isinstance(config.risk, RiskConfig)
        assert isinstance(config.dispatcher, DispatcherConfig)
        assert isinstance(config.database, DatabaseConfig)
    
    def test_config_hash(self):
        """Test configuration hashing."""
        config1 = AppConfig()
        config2 = AppConfig()
        
        # Same config should have same hash
        assert config1.config_hash() == config2.config_hash()
        
        # Different config should have different hash
        config3 = AppConfig(mode=Mode.LIVE)
        assert config1.config_hash() != config3.config_hash()
    
    def test_custom_mode(self):
        """Test different modes."""
        config_dry = AppConfig(mode=Mode.DRY_RUN)
        assert config_dry.mode == Mode.DRY_RUN
        
        config_paper = AppConfig(mode=Mode.PAPER)
        assert config_paper.mode == Mode.PAPER
        
        config_live = AppConfig(mode=Mode.LIVE)
        assert config_live.mode == Mode.LIVE
    
    def test_port_validation(self):
        """Test port number validation."""
        with pytest.raises(PydanticValidationError):
            AppConfig(api_port=80)  # Below 1024
        
        with pytest.raises(PydanticValidationError):
            AppConfig(api_port=70000)  # Above 65535
        
        # Valid ports
        config = AppConfig(api_port=8080)
        assert config.api_port == 8080


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
