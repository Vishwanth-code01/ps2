"""
Smart Delivery Dispatch System - Domain Models
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from config import Config


class Priority(Enum):
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Location:
    x: float
    y: float

    def distance_to(self, other: "Location") -> float:
        """Calculate Euclidean distance to another location."""
        return math.hypot(self.x - other.x, self.y - other.y)

    def zone(self, grid: int = Config.GRID_SIZE) -> int:
        """Determine the zone (0-3) based on grid quadrants."""
        half = grid / 2
        return (1 if self.y >= half else 0) * 2 + (1 if self.x >= half else 0)

    def __repr__(self) -> str:
        return f"({self.x:.1f},{self.y:.1f})"


@dataclass
class Order:
    order_id: int
    timestamp: float
    location: Location
    restaurant: Location
    prep_time: float
    priority: Priority
    sla_deadline: float
    assigned_agent_id: Optional[int] = None
    pickup_time: Optional[float] = None
    delivery_time: Optional[float] = None
    sla_breached: bool = False
    reassigned: bool = False

    @property
    def zone(self) -> int:
        """Get the zone of the delivery location."""
        return self.location.zone()

    def sla_fraction_remaining(self, sim_time: float) -> float:
        """Calculate fraction of SLA time remaining."""
        window = self.sla_deadline - self.timestamp
        return max(0.0, (self.sla_deadline - sim_time) / window) if window > 0 else 0.0

    def __repr__(self) -> str:
        return (f"Order#{self.order_id}[{self.priority.value}] "
                f"dest={self.location} prep={self.prep_time:.1f}m SLA={self.sla_deadline:.1f}")


@dataclass
class Agent:
    agent_id: int
    current_location: Location
    rating: float
    active_orders: List[Order] = field(default_factory=list)
    total_completed: int = 0
    total_breached: int = 0
    busy_until: float = 0.0
    home_zone: int = 0

    @property
    def is_available(self) -> bool:
        """Check if agent can accept more orders."""
        return len(self.active_orders) < Config.MAX_AGENT_CAPACITY

    @property
    def current_load(self) -> int:
        """Get current number of active orders."""
        return len(self.active_orders)

    @property
    def breach_rate(self) -> float:
        """Calculate breach rate for completed orders."""
        return (self.total_breached / self.total_completed) if self.total_completed else 0.0

    def assign_order(self, order: Order) -> None:
        """Assign an order to this agent."""
        if not self.is_available:
            raise ValueError(f"Agent#{self.agent_id} at full capacity.")
        self.active_orders.append(order)

    def complete_order(self, order: Order, sim_time: float) -> None:
        """Mark an order as completed and update statistics."""
        order.delivery_time = sim_time
        order.sla_breached = sim_time > order.sla_deadline
        if order in self.active_orders:
            self.active_orders.remove(order)
        self.total_completed += 1
        if order.sla_breached:
            self.total_breached += 1

    def __repr__(self) -> str:
        return (f"Agent#{self.agent_id} loc={self.current_location} "
                f"rating={self.rating:.1f} load={self.current_load}")</content>
<parameter name="filePath">c:\Users\91636\Documents\GitHub\ps2\data\models.py