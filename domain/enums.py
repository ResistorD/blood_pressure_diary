from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    DEMO = "DEMO"
    DRY_RUN = "DRY_RUN"
    PAPER = "PAPER"
    LIVE = "LIVE"


class HealthStatus(str, Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DEGRADED = "DEGRADED"


class SignalKind(str, Enum):
    PAIR_ARB = "PAIR_ARB"
    MARKET_MAKING = "MARKET_MAKING"
    HEDGE = "HEDGE"
    IMPLICATION = "IMPLICATION"
    ANOMALY = "ANOMALY"
    QUALITY_ALERT = "QUALITY_ALERT"
    RISK_CONSTRAINT = "RISK_CONSTRAINT"


class DecisionType(str, Enum):
    ENTER = "ENTER"
    EXIT = "EXIT"
    SWITCH = "SWITCH"
    HOLD = "HOLD"
    PAUSE = "PAUSE"


class Severity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class OrderStatus(str, Enum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class PositionState(str, Enum):
    OPENING = "OPENING"
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
