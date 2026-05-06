"""
Smart Delivery Dispatch System - Scoring Engine
"""

import math
from typing import List, Optional, Tuple

from config import Config
from models import Agent, Order, Priority


class ScoringEngine:
    """
    Stateless six-dimensional scoring engine.
    Lower score = better match (cost minimisation).

    Score = w_dist·D + w_sla·U − w_rating·R + w_load·L − w_zone·Z + w_eta·E
    """

    def __init__(self, cfg: type = Config) -> None:
        self.cfg = cfg
        self._max_dist = math.hypot(cfg.GRID_SIZE, cfg.GRID_SIZE)

    def _distance_score(self, agent: Agent, order: Order) -> float:
        """Calculate distance-based score component."""
        return agent.current_location.distance_to(order.restaurant) / self._max_dist

    def _sla_urgency_score(self, order: Order, sim_time: float) -> float:
        """Calculate SLA urgency score component."""
        urgency = max(0.0, min(1.0, 1.0 - order.sla_fraction_remaining(sim_time)))
        if order.priority == Priority.HIGH:
            urgency = min(1.0, urgency * self.cfg.HIGH_PRIORITY_MULTIPLIER)
        elif order.priority == Priority.CRITICAL:
            urgency = 1.0
        return urgency

    def _agent_rating_score(self, agent: Agent) -> float:
        """Calculate agent rating score component."""
        return agent.rating / 5.0

    def _load_balance_score(self, agent: Agent) -> float:
        """Calculate load balancing score component."""
        return self.cfg.DOUBLE_ORDER_PENALTY if agent.current_load > 0 else 0.0

    def _zone_affinity_score(self, agent: Agent, order: Order) -> float:
        """Calculate zone affinity score component."""
        return 1.0 if agent.home_zone == order.zone else 0.0

    def _eta_safety_score(self, agent: Agent, order: Order, sim_time: float) -> float:
        """Calculate ETA safety score component."""
        travel_rest = agent.current_location.distance_to(order.restaurant) / self.cfg.AGENT_SPEED
        travel_cust = order.restaurant.distance_to(order.location) / self.cfg.AGENT_SPEED
        est_delivery = sim_time + max(travel_rest, order.prep_time) + travel_cust
        slack = order.sla_deadline - est_delivery
        if slack >= 0:
            return 0.0
        window = max(1.0, order.sla_deadline - sim_time)
        return min(1.0, abs(slack) / window)

    def score(self, agent: Agent, order: Order, sim_time: float) -> float:
        """Calculate the overall score for agent-order assignment."""
        c = self.cfg
        return (
            c.W_DISTANCE * self._distance_score(agent, order)
            + c.W_SLA_URGENCY * self._sla_urgency_score(order, sim_time)
            - c.W_AGENT_RATING * self._agent_rating_score(agent)
            + c.W_LOAD_BALANCE * self._load_balance_score(agent)
            - c.W_ZONE_AFFINITY * self._zone_affinity_score(agent, order)
            + c.W_ETA_SAFETY * self._eta_safety_score(agent, order, sim_time)
        )

    def best_agent(self, agents: List[Agent], order: Order, sim_time: float) -> Optional[Agent]:
        """Find the best agent for an order."""
        candidates = [a for a in agents if a.is_available]
        return min(candidates, key=lambda a: self.score(a, order, sim_time)) if candidates else None

    def ranked_available(self, agents: List[Agent], order: Order, sim_time: float) -> List[Tuple[float, Agent]]:
        """Get ranked list of available agents with their scores."""
        return sorted([(self.score(a, order, sim_time), a) for a in agents if a.is_available])</content>
<parameter name="filePath">c:\Users\91636\Documents\GitHub\ps2\data\scoring.py