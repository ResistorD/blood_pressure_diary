"""Validation utilities for data integrity checks."""
from __future__ import annotations

from typing import Any, Dict, List


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


def validate_market_id(market_id: str) -> None:
    """Validate market ID format.
    
    Args:
        market_id: Market identifier to validate
        
    Raises:
        ValidationError: If market_id is invalid
        
    Example:
        >>> validate_market_id("market_123")
        >>> validate_market_id("")  # doctest: +SKIP
        Traceback: ValidationError
    """
    if not market_id or not isinstance(market_id, str):
        raise ValidationError(f"Invalid market_id: {market_id!r}")
    if len(market_id) == 0:
        raise ValidationError("market_id cannot be empty")


def validate_outcome(outcome: str) -> None:
    """Validate outcome value.
    
    Args:
        outcome: Outcome to validate (should be "YES" or "NO")
        
    Raises:
        ValidationError: If outcome is invalid
    """
    if outcome not in ("YES", "NO"):
        raise ValidationError(f"Invalid outcome: {outcome!r}, must be YES or NO")


def validate_snapshot(snap: Dict[str, Any]) -> None:
    """Validate snapshot data structure.
    
    Args:
        snap: Snapshot dictionary to validate
        
    Raises:
        ValidationError: If snapshot is malformed
        
    Example:
        >>> validate_snapshot({"market_id": "m1", "outcome": "YES", "ts": "2024-01-01"})
    """
    required = ["market_id", "outcome", "ts"]
    for field in required:
        if field not in snap:
            raise ValidationError(f"Missing required field: {field}")
    
    # Validate market_id
    validate_market_id(snap["market_id"])
    
    # Validate outcome
    validate_outcome(snap["outcome"])
    
    # Validate numeric fields if present
    numeric_fields = ["bid", "ask", "mid", "spread", "liquidity", "volume"]
    for field in numeric_fields:
        val = snap.get(field)
        if val is not None:
            try:
                float(val)
            except (TypeError, ValueError):
                raise ValidationError(f"Invalid {field}: {val!r}, must be numeric")


def validate_signal_features(features: Dict[str, float]) -> None:
    """Validate signal features are numeric.
    
    Args:
        features: Dictionary of feature name -> value
        
    Raises:
        ValidationError: If any feature is non-numeric
    """
    for k, v in features.items():
        if not isinstance(v, (int, float)):
            raise ValidationError(f"Feature {k!r} must be numeric, got {type(v).__name__}")


def validate_price(price: float, field_name: str = "price") -> None:
    """Validate price is in valid range [0, 1] for prediction markets.
    
    Args:
        price: Price value to validate
        field_name: Name of field for error messages
        
    Raises:
        ValidationError: If price is out of range
    """
    if not isinstance(price, (int, float)):
        raise ValidationError(f"{field_name} must be numeric, got {type(price).__name__}")
    if not (0.0 <= price <= 1.0):
        raise ValidationError(f"{field_name} must be between 0 and 1, got {price}")


def validate_positive(value: float, field_name: str = "value") -> None:
    """Validate value is positive.
    
    Args:
        value: Value to validate
        field_name: Name of field for error messages
        
    Raises:
        ValidationError: If value is not positive
    """
    if not isinstance(value, (int, float)):
        raise ValidationError(f"{field_name} must be numeric, got {type(value).__name__}")
    if value <= 0:
        raise ValidationError(f"{field_name} must be positive, got {value}")


def validate_non_negative(value: float, field_name: str = "value") -> None:
    """Validate value is non-negative.
    
    Args:
        value: Value to validate
        field_name: Name of field for error messages
        
    Raises:
        ValidationError: If value is negative
    """
    if not isinstance(value, (int, float)):
        raise ValidationError(f"{field_name} must be numeric, got {type(value).__name__}")
    if value < 0:
        raise ValidationError(f"{field_name} must be non-negative, got {value}")


def validate_run_id(run_id: str) -> None:
    """Validate run ID format.
    
    Args:
        run_id: Run identifier to validate
        
    Raises:
        ValidationError: If run_id is invalid
    """
    if not run_id or not isinstance(run_id, str):
        raise ValidationError(f"Invalid run_id: {run_id!r}")


def validate_config_value(value: Any, min_val: float = None, max_val: float = None) -> None:
    """Validate configuration value is within bounds.
    
    Args:
        value: Value to validate
        min_val: Minimum allowed value (inclusive)
        max_val: Maximum allowed value (inclusive)
        
    Raises:
        ValidationError: If value is out of bounds
    """
    if not isinstance(value, (int, float)):
        raise ValidationError(f"Config value must be numeric, got {type(value).__name__}")
    
    if min_val is not None and value < min_val:
        raise ValidationError(f"Value {value} is below minimum {min_val}")
    
    if max_val is not None and value > max_val:
        raise ValidationError(f"Value {value} exceeds maximum {max_val}")
