"""
Smart Delivery Dispatch System - Configuration Module
"""

from typing import Tuple


class Config:
    """Configuration parameters for the delivery dispatch system."""

    # Grid and simulation parameters
    GRID_SIZE: int = 20
    NUM_AGENTS: int = 10
    NUM_ORDERS: int = 40
    INTER_ARRIVAL_MEAN: float = 1.8

    # Agent parameters
    AGENT_SPEED: float = 1.2
    MAX_AGENT_CAPACITY: int = 2

    # Order parameters
    PREP_TIME_RANGE: Tuple[float, float] = (1, 5)
    SLA_WINDOW_RANGE: Tuple[float, float] = (10, 30)

    # Scoring weights
    W_DISTANCE: float = 0.30
    W_SLA_URGENCY: float = 0.28
    W_AGENT_RATING: float = 0.18
    W_LOAD_BALANCE: float = 0.12
    W_ZONE_AFFINITY: float = 0.08
    W_ETA_SAFETY: float = 0.04

    # Priority multipliers
    HIGH_PRIORITY_MULTIPLIER: float = 1.8
    CRITICAL_SLA_THRESHOLD: float = 0.25

    # Reassignment parameters
    ENABLE_REASSIGNMENT: bool = True
    REASSIGN_SCORE_DELTA: float = 0.15
    ESCALATION_INTERVAL: float = 3.0

    # Penalties
    DOUBLE_ORDER_PENALTY: float = 0.45

    # Output control
    VERBOSE: bool = True

    @classmethod
    def validate(cls) -> None:
        """Validate configuration parameters."""
        assert cls.GRID_SIZE > 0, "GRID_SIZE must be positive"
        assert cls.NUM_AGENTS > 0, "NUM_AGENTS must be positive"
        assert cls.NUM_ORDERS > 0, "NUM_ORDERS must be positive"
        assert cls.INTER_ARRIVAL_MEAN > 0, "INTER_ARRIVAL_MEAN must be positive"
        assert cls.AGENT_SPEED > 0, "AGENT_SPEED must be positive"
        assert cls.MAX_AGENT_CAPACITY > 0, "MAX_AGENT_CAPACITY must be positive"
        assert all(w >= 0 for w in [cls.W_DISTANCE, cls.W_SLA_URGENCY, cls.W_AGENT_RATING,
                                   cls.W_LOAD_BALANCE, cls.W_ZONE_AFFINITY, cls.W_ETA_SAFETY]), \
               "All weights must be non-negative"
        assert abs(sum([cls.W_DISTANCE, cls.W_SLA_URGENCY, cls.W_AGENT_RATING,
                       cls.W_LOAD_BALANCE, cls.W_ZONE_AFFINITY, cls.W_ETA_SAFETY]) - 1.0) < 1e-6, \
               "Weights must sum to 1.0"
        assert cls.HIGH_PRIORITY_MULTIPLIER >= 1.0, "HIGH_PRIORITY_MULTIPLIER must be >= 1.0"
        assert 0 < cls.CRITICAL_SLA_THRESHOLD < 1, "CRITICAL_SLA_THRESHOLD must be between 0 and 1"
        assert cls.REASSIGN_SCORE_DELTA > 0, "REASSIGN_SCORE_DELTA must be positive"
        assert cls.ESCALATION_INTERVAL > 0, "ESCALATION_INTERVAL must be positive"
        assert cls.DOUBLE_ORDER_PENALTY >= 0, "DOUBLE_ORDER_PENALTY must be non-negative"</content>
<parameter name="filePath">c:\Users\91636\Documents\GitHub\ps2\data\config.py