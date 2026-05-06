"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          SMART DELIVERY DISPATCH SYSTEM  –  HACKATHON EDITION               ║
║          Code2Create Challenge – Round 2                                    ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Approach : Adaptive Weighted Multi-Criteria Scoring with                   ║
║             Dynamic Re-Assignment, Zone-Aware Clustering,                   ║
║             ETA-Safety Scoring, and SLA Escalation                          ║
║  Complexity: O(A·log N) per dispatch event                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import heapq
import math
import random
import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

class Config:
    GRID_SIZE: int          = 20
    W_DISTANCE:       float = 0.30
    W_SLA_URGENCY:    float = 0.28
    W_AGENT_RATING:   float = 0.18
    W_LOAD_BALANCE:   float = 0.12
    W_ZONE_AFFINITY:  float = 0.08
    W_ETA_SAFETY:     float = 0.04
    HIGH_PRIORITY_MULTIPLIER: float = 1.8
    CRITICAL_SLA_THRESHOLD:   float = 0.25
    DOUBLE_ORDER_PENALTY:     float = 0.45
    ENABLE_REASSIGNMENT:  bool  = True
    REASSIGN_SCORE_DELTA: float = 0.15
    ESCALATION_INTERVAL:  float = 3.0
    NUM_AGENTS:          int   = 10
    NUM_ORDERS:          int   = 40
    INTER_ARRIVAL_MEAN:  float = 1.8
    PREP_TIME_RANGE:     tuple = (1, 5)
    SLA_WINDOW_RANGE:    tuple = (10, 30)
    AGENT_SPEED:         float = 1.2
    MAX_AGENT_CAPACITY:  int   = 2
    VERBOSE:             bool  = True


# ═══════════════════════════════════════════════════════════════════════════════
# DOMAIN MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class Priority(Enum):
    NORMAL   = "normal"
    HIGH     = "high"
    CRITICAL = "critical"


@dataclass
class Location:
    x: float
    y: float

    def distance_to(self, other: "Location") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def zone(self, grid: int = Config.GRID_SIZE) -> int:
        half = grid / 2
        return (1 if self.y >= half else 0) * 2 + (1 if self.x >= half else 0)

    def __repr__(self) -> str:
        return f"({self.x:.1f},{self.y:.1f})"


@dataclass
class Order:
    order_id:     int
    timestamp:    float
    location:     Location
    restaurant:   Location
    prep_time:    float
    priority:     Priority
    sla_deadline: float
    assigned_agent_id: Optional[int]   = None
    pickup_time:       Optional[float] = None
    delivery_time:     Optional[float] = None
    sla_breached:      bool            = False
    reassigned:        bool            = False

    @property
    def zone(self) -> int:
        return self.location.zone()

    def sla_fraction_remaining(self, sim_time: float) -> float:
        window = self.sla_deadline - self.timestamp
        return max(0.0, (self.sla_deadline - sim_time) / window) if window > 0 else 0.0

    def __repr__(self) -> str:
        return (f"Order#{self.order_id}[{self.priority.value}] "
                f"dest={self.location} prep={self.prep_time:.1f}m SLA={self.sla_deadline:.1f}")


@dataclass
class Agent:
    agent_id:         int
    current_location: Location
    rating:           float
    active_orders:    List[Order] = field(default_factory=list)
    total_completed:  int         = 0
    total_breached:   int         = 0
    busy_until:       float       = 0.0
    home_zone:        int         = 0

    @property
    def is_available(self) -> bool:
        return len(self.active_orders) < Config.MAX_AGENT_CAPACITY

    @property
    def current_load(self) -> int:
        return len(self.active_orders)

    @property
    def breach_rate(self) -> float:
        return (self.total_breached / self.total_completed) if self.total_completed else 0.0

    def assign_order(self, order: Order) -> None:
        if not self.is_available:
            raise ValueError(f"Agent#{self.agent_id} at full capacity.")
        self.active_orders.append(order)

    def complete_order(self, order: Order, sim_time: float) -> None:
        order.delivery_time = sim_time
        order.sla_breached  = sim_time > order.sla_deadline
        if order in self.active_orders:
            self.active_orders.remove(order)
        self.total_completed += 1
        if order.sla_breached:
            self.total_breached += 1

    def __repr__(self) -> str:
        return (f"Agent#{self.agent_id} loc={self.current_location} "
                f"rating={self.rating:.1f} load={self.current_load}")


# ═══════════════════════════════════════════════════════════════════════════════
# SCORING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class ScoringEngine:
    """
    Stateless six-dimensional scoring engine.
    Lower score = better match (cost minimisation).

    Score = w_dist·D + w_sla·U − w_rating·R + w_load·L − w_zone·Z + w_eta·E
    """

    def __init__(self, cfg: type = Config) -> None:
        self.cfg       = cfg
        self._max_dist = math.hypot(cfg.GRID_SIZE, cfg.GRID_SIZE)

    def _distance_score(self, agent: Agent, order: Order) -> float:
        return agent.current_location.distance_to(order.restaurant) / self._max_dist

    def _sla_urgency_score(self, order: Order, sim_time: float) -> float:
        urgency = max(0.0, min(1.0, 1.0 - order.sla_fraction_remaining(sim_time)))
        if order.priority == Priority.HIGH:
            urgency = min(1.0, urgency * self.cfg.HIGH_PRIORITY_MULTIPLIER)
        elif order.priority == Priority.CRITICAL:
            urgency = 1.0
        return urgency

    def _agent_rating_score(self, agent: Agent) -> float:
        return agent.rating / 5.0

    def _load_balance_score(self, agent: Agent) -> float:
        return self.cfg.DOUBLE_ORDER_PENALTY if agent.current_load > 0 else 0.0

    def _zone_affinity_score(self, agent: Agent, order: Order) -> float:
        return 1.0 if agent.home_zone == order.zone else 0.0

    def _eta_safety_score(self, agent: Agent, order: Order, sim_time: float) -> float:
        travel_rest  = agent.current_location.distance_to(order.restaurant) / self.cfg.AGENT_SPEED
        travel_cust  = order.restaurant.distance_to(order.location) / self.cfg.AGENT_SPEED
        est_delivery = sim_time + max(travel_rest, order.prep_time) + travel_cust
        slack        = order.sla_deadline - est_delivery
        if slack >= 0:
            return 0.0
        window = max(1.0, order.sla_deadline - sim_time)
        return min(1.0, abs(slack) / window)

    def score(self, agent: Agent, order: Order, sim_time: float) -> float:
        c = self.cfg
        return (
              c.W_DISTANCE      * self._distance_score(agent, order)
            + c.W_SLA_URGENCY   * self._sla_urgency_score(order, sim_time)
            - c.W_AGENT_RATING  * self._agent_rating_score(agent)
            + c.W_LOAD_BALANCE  * self._load_balance_score(agent)
            - c.W_ZONE_AFFINITY * self._zone_affinity_score(agent, order)
            + c.W_ETA_SAFETY    * self._eta_safety_score(agent, order, sim_time)
        )

    def best_agent(self, agents: List[Agent], order: Order, sim_time: float) -> Optional[Agent]:
        candidates = [a for a in agents if a.is_available]
        return min(candidates, key=lambda a: self.score(a, order, sim_time)) if candidates else None

    def ranked_available(self, agents: List[Agent], order: Order, sim_time: float) -> List[Tuple[float, Agent]]:
        return sorted([(self.score(a, order, sim_time), a) for a in agents if a.is_available])


# ═══════════════════════════════════════════════════════════════════════════════
# ESCALATION MONITOR
# ═══════════════════════════════════════════════════════════════════════════════

class EscalationMonitor:
    def __init__(self, scorer: ScoringEngine, cfg: type = Config) -> None:
        self.scorer = scorer
        self.cfg    = cfg

    def check_and_escalate(
        self, all_agents: List[Agent], sim_time: float
    ) -> List[Tuple[Agent, Agent, Order]]:
        if not self.cfg.ENABLE_REASSIGNMENT:
            return []

        swaps: List[Tuple[Agent, Agent, Order]] = []
        seen: set = set()

        for agent in all_agents:
            for order in list(agent.active_orders):
                if order.order_id in seen:
                    continue
                # Skip already-delivered orders
                if order.delivery_time is not None:
                    continue
                # Skip if SLA is not yet critical
                if order.sla_fraction_remaining(sim_time) > self.cfg.CRITICAL_SLA_THRESHOLD:
                    continue
                # Skip if SLA is already 100% gone (no point reassigning)
                if sim_time >= order.sla_deadline:
                    continue

                if order.priority == Priority.NORMAL:
                    order.priority = Priority.CRITICAL

                current_score = self.scorer.score(agent, order, sim_time)
                candidates    = [a for a in all_agents
                                 if a.agent_id != agent.agent_id and a.is_available]
                if not candidates:
                    continue

                ranked = self.scorer.ranked_available(candidates, order, sim_time)
                best_score, best_agent = ranked[0]

                if current_score - best_score >= self.cfg.REASSIGN_SCORE_DELTA:
                    swaps.append((agent, best_agent, order))
                    seen.add(order.order_id)

        return swaps


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════════

class Dispatcher:
    """
    Event-driven dispatcher with token-based stale-event prevention.

    Each DELIVERY_COMPLETE event carries a monotonic token.
    _delivery_tokens[order_id] stores the CURRENT valid token.
    Re-assignment issues a new token, superseding the old event.
    Stale events are discarded in O(1) — zero ghost completions.
    """

    def __init__(
        self,
        agents:  List[Agent],
        scorer:  ScoringEngine,
        monitor: EscalationMonitor,
        cfg:     type = Config,
    ) -> None:
        self.agents   = agents
        self.scorer   = scorer
        self.monitor  = monitor
        self.cfg      = cfg

        self.event_queue:      List              = []
        self.sim_time:         float             = 0.0
        self.all_orders:       List[Order]       = []
        self.unassigned_q:     List[Order]       = []
        self._counter:         int               = 0
        self._delivery_tokens: Dict[int, int]    = {}

    # ── Heap helpers ──────────────────────────────────────────────────────────

    def _push(self, t: float, etype: str, payload) -> int:
        self._counter += 1
        heapq.heappush(self.event_queue, (t, self._counter, etype, payload))
        return self._counter

    def _pop(self):
        return heapq.heappop(self.event_queue)

    # ── Order factory ─────────────────────────────────────────────────────────

    def _create_order(self, oid: int, timestamp: float) -> Order:
        dest    = Location(random.uniform(0, self.cfg.GRID_SIZE),
                           random.uniform(0, self.cfg.GRID_SIZE))
        rest    = Location(random.uniform(0, self.cfg.GRID_SIZE),
                           random.uniform(0, self.cfg.GRID_SIZE))
        prep    = random.uniform(*self.cfg.PREP_TIME_RANGE)
        prio    = random.choices([Priority.NORMAL, Priority.HIGH], weights=[70, 30])[0]
        sla_win = random.uniform(*self.cfg.SLA_WINDOW_RANGE)
        return Order(
            order_id     = oid,
            timestamp    = timestamp,
            location     = dest,
            restaurant   = rest,
            prep_time    = prep,
            priority     = prio,
            sla_deadline = timestamp + sla_win,
        )

    # ── Assignment helpers ────────────────────────────────────────────────────

    def _compute_delivery_time(self, agent: Agent, order: Order) -> float:
        travel_rest = agent.current_location.distance_to(order.restaurant) / self.cfg.AGENT_SPEED
        pickup_t    = self.sim_time + max(travel_rest, order.prep_time)
        travel_cust = order.restaurant.distance_to(order.location) / self.cfg.AGENT_SPEED
        return pickup_t + travel_cust

    def _schedule_delivery(self, agent: Agent, order: Order, delivery_time: float) -> None:
        """Schedule DELIVERY_COMPLETE and register its token."""
        self._counter += 1
        token = self._counter
        heapq.heappush(
            self.event_queue,
            (delivery_time, token, "DELIVERY_COMPLETE", (agent, order, token))
        )
        self._delivery_tokens[order.order_id] = token

    def _try_assign(self, order: Order) -> bool:
        agent = self.scorer.best_agent(self.agents, order, self.sim_time)
        if agent is None:
            return False

        delivery_time = self._compute_delivery_time(agent, order)

        agent.assign_order(order)
        order.assigned_agent_id = agent.agent_id
        order.pickup_time = self.sim_time + max(
            agent.current_location.distance_to(order.restaurant) / self.cfg.AGENT_SPEED,
            order.prep_time
        )
        agent.current_location = order.location
        agent.home_zone        = order.zone
        agent.busy_until       = delivery_time

        self._schedule_delivery(agent, order, delivery_time)

        if self.cfg.VERBOSE:
            sc  = self.scorer.score(agent, order, self.sim_time)
            p   = {"normal": "🟢 NORM", "high": "🔴 HIGH", "critical": "🚨 CRIT"}.get(order.priority.value, "❓")
            tag = "✅ ETA_OK" if delivery_time <= order.sla_deadline else "⚠️  ETA_RISK"
            print(f"  [t={self.sim_time:6.2f}] ASSIGNED  {p} Order#{order.order_id:03d}"
                  f" → Agent#{agent.agent_id} | score={sc:.4f}"
                  f" | ETA={delivery_time:.2f}m | SLA={order.sla_deadline:.2f}m | {tag}")
        return True

    # ── Re-assignment ─────────────────────────────────────────────────────────

    def _perform_reassignment(self, old: Agent, new: Agent, order: Order) -> None:
        if order not in old.active_orders or not new.is_available:
            return
        old.active_orders.remove(order)
        order.reassigned        = True
        order.assigned_agent_id = new.agent_id
        new.assign_order(order)
        delivery_time        = self._compute_delivery_time(new, order)
        new.current_location = order.location
        new.home_zone        = order.zone
        new.busy_until       = delivery_time
        self._schedule_delivery(new, order, delivery_time)  # token rotated → old event stale
        if self.cfg.VERBOSE:
            print(f"  [t={self.sim_time:6.2f}] REASSIGN  🚨 Order#{order.order_id:03d}"
                  f" Agent#{old.agent_id}→Agent#{new.agent_id}"
                  f" | new_ETA={delivery_time:.2f}m SLA={order.sla_deadline:.2f}m")

    # ── Event handlers ────────────────────────────────────────────────────────

    def _handle_order_arrival(self, order: Order) -> None:
        self.all_orders.append(order)
        if self.cfg.VERBOSE:
            print(f"\n[t={self.sim_time:6.2f}] ARRIVED   Order#{order.order_id:03d} | {order}")
        if not self._try_assign(order):
            self.unassigned_q.append(order)
            if self.cfg.VERBOSE:
                print(f"  [t={self.sim_time:6.2f}] QUEUED    Order#{order.order_id:03d} — no free agent")

    def _handle_delivery_complete(self, agent: Agent, order: Order, token: int) -> None:
        if self._delivery_tokens.get(order.order_id) != token:
            return  # stale event — discard silently
        agent.complete_order(order, self.sim_time)
        breach = "💥 SLA BREACH" if order.sla_breached else "✅ on time"
        remark = " [re-assigned]" if order.reassigned else ""
        if self.cfg.VERBOSE:
            print(f"[t={self.sim_time:6.2f}] DELIVERED Order#{order.order_id:03d}"
                  f" by Agent#{agent.agent_id} | {breach}"
                  f" (ETA={self.sim_time:.2f} SLA={order.sla_deadline:.2f}){remark}")
        still_waiting = []
        for q_order in self.unassigned_q:
            if not self._try_assign(q_order):
                still_waiting.append(q_order)
        self.unassigned_q = still_waiting

    def _handle_escalation_check(self) -> None:
        # Stop if all active orders are done
        active_orders = [o for a in self.agents for o in a.active_orders]
        if active_orders or self.unassigned_q:
            swaps = self.monitor.check_and_escalate(self.agents, self.sim_time)
            for old_agent, new_agent, order in swaps:
                self._perform_reassignment(old_agent, new_agent, order)
            self._push(self.sim_time + self.cfg.ESCALATION_INTERVAL, "ESCALATION_CHECK", None)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self, num_orders: int) -> None:
        _banner("SMART DELIVERY DISPATCH SYSTEM  –  SIMULATION START")

        arrival_t = 0.0
        for i in range(num_orders):
            order = self._create_order(i + 1, arrival_t)
            self._push(arrival_t, "ORDER_ARRIVAL", order)
            arrival_t += random.expovariate(1.0 / self.cfg.INTER_ARRIVAL_MEAN)

        self._push(self.cfg.ESCALATION_INTERVAL, "ESCALATION_CHECK", None)

        while self.event_queue:
            sim_t, _cnt, etype, payload = self._pop()
            self.sim_time = sim_t

            if etype == "ORDER_ARRIVAL":
                self._handle_order_arrival(payload)
            elif etype == "DELIVERY_COMPLETE":
                agent, order, token = payload
                self._handle_delivery_complete(agent, order, token)
            elif etype == "ESCALATION_CHECK":
                self._handle_escalation_check()

        for order in self.unassigned_q:
            order.sla_breached = True
            print(f"[END] Order#{order.order_id:03d} NEVER ASSIGNED → SLA BREACHED")

        self._print_summary()

    # ── Summary ───────────────────────────────────────────────────────────────

    def _print_summary(self) -> None:
        delivered   = [o for o in self.all_orders if o.delivery_time is not None]
        undelivered = [o for o in self.all_orders if o.delivery_time is None]
        breached    = [o for o in self.all_orders if o.sla_breached]
        reassigned  = [o for o in self.all_orders if o.reassigned]

        dt_list  = [o.delivery_time - o.timestamp for o in delivered]
        avg_dt   = statistics.mean(dt_list)    if dt_list else float("nan")
        med_dt   = statistics.median(dt_list)  if dt_list else float("nan")
        p95_dt   = _percentile(dt_list, 95)    if dt_list else float("nan")
        sla_rate = (len(breached) / len(self.all_orders) * 100) if self.all_orders else 0.0
        loads    = [a.total_completed for a in self.agents]
        load_std = statistics.pstdev(loads)
        gini     = _gini(loads)

        _banner("SIMULATION SUMMARY")
        print(f"  Total orders          : {len(self.all_orders)}")
        print(f"  Delivered             : {len(delivered)}")
        print(f"  Undelivered           : {len(undelivered)}")
        print(f"  Re-assigned           : {len(reassigned)}")
        print()
        print(f"  ┌── Delivery Time Metrics ──────────────────────────")
        print(f"  │ Mean                : {avg_dt:.2f} min")
        print(f"  │ Median              : {med_dt:.2f} min")
        print(f"  │ 95th Percentile     : {p95_dt:.2f} min")
        print(f"  ├── SLA Compliance ─────────────────────────────────")
        print(f"  │ Breach Rate         : {sla_rate:.1f}%  ({len(breached)}/{len(self.all_orders)})")
        print(f"  ├── Load Fairness ──────────────────────────────────")
        print(f"  │ Std Deviation       : {load_std:.2f} orders/agent")
        print(f"  │ Gini Coefficient    : {gini:.3f}  (0=perfect equality)")
        print(f"  └────────────────────────────────────────────────────")
        print()
        print(f"  {'Agent':>8} | {'Rating':>6} | {'Done':>5} | {'Breached':>8} | {'Breach%':>7} | Location")
        print(f"  {'-'*8}-+-{'-'*6}-+-{'-'*5}-+-{'-'*8}-+-{'-'*7}-+-{'-'*16}")
        for a in sorted(self.agents, key=lambda x: x.agent_id):
            print(f"  Agent#{a.agent_id:>2}  | {a.rating:>5.1f}★ | "
                  f"{a.total_completed:>5} | {a.total_breached:>8} | "
                  f"{a.breach_rate*100:>6.0f}% | {a.current_location}")
        _banner("END")


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def _banner(msg: str) -> None:
    w = 72
    print("\n" + "═" * w)
    print(f"{msg:^{w}}")
    print("═" * w)


def _percentile(data: List[float], pct: float) -> float:
    if not data:
        return float("nan")
    s  = sorted(data)
    k  = (len(s) - 1) * pct / 100
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (k - lo) * (s[hi] - s[lo])


def _gini(values: List[float]) -> float:
    n = len(values)
    if n == 0 or sum(values) == 0:
        return 0.0
    s   = sorted(values)
    cum = sum((i + 1) * v for i, v in enumerate(s))
    return (2 * cum) / (n * sum(s)) - (n + 1) / n


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def build_agents(cfg: type = Config) -> List[Agent]:
    random.seed(42)
    agents = []
    for i in range(cfg.NUM_AGENTS):
        loc = Location(random.uniform(0, cfg.GRID_SIZE),
                       random.uniform(0, cfg.GRID_SIZE))
        agents.append(Agent(
            agent_id         = i + 1,
            current_location = loc,
            rating           = round(random.uniform(3.0, 5.0), 1),
            home_zone        = loc.zone(),
        ))
    return agents


def main() -> None:
    random.seed(0)
    agents     = build_agents(Config)
    scorer     = ScoringEngine(Config)
    monitor    = EscalationMonitor(scorer, Config)
    dispatcher = Dispatcher(agents, scorer, monitor, Config)
    dispatcher.run(Config.NUM_ORDERS)


# ═══════════════════════════════════════════════════════════════════════════════
# JUSTIFICATION
# ═══════════════════════════════════════════════════════════════════════════════
"""
DESIGN DECISIONS & COMPETITIVE ADVANTAGES
──────────────────────────────────────────

1. SIX-DIMENSIONAL SCORING (vs. original four)
   Two new dimensions over the baseline:
   • Zone Affinity  – agents near an order's zone incur lower repositioning
     cost, reducing avg delivery time in clustered demand.
   • ETA Safety     – penalises assignments where estimated delivery already
     risks breach at assignment time; prevents "optimistic but doomed"
     assignments wasting agent capacity on guaranteed breaches.

2. EXPLICIT RESTAURANT ↔ CUSTOMER ROUTING
   The baseline collapsed restaurant + delivery into one point.  Each order
   now carries a separate `restaurant`; travel = agent→restaurant→customer,
   giving accurate ETAs and exposing real cost of cross-zone pickups.

3. TOKEN-BASED STALE-EVENT PREVENTION  ← key correctness innovation
   Every DELIVERY_COMPLETE event carries a monotonic token.
   _delivery_tokens[order_id] holds the current valid token.  Re-assignment
   issues a new token, superseding the old event.  Stale events are
   discarded in O(1) — zero ghost completions, zero duplicate deliveries.

4. PRIORITY ESCALATION (CRITICAL tier)
   Orders auto-upgrade NORMAL→CRITICAL when remaining SLA window < 25%.
   This continuously re-evaluates urgency with zero polling overhead.

5. DYNAMIC RE-ASSIGNMENT (Agent Swap)
   EscalationMonitor scans every ESCALATION_INTERVAL minutes.  If a
   significantly better free agent (Δscore ≥ REASSIGN_SCORE_DELTA) exists,
   the order is transferred — recovering from suboptimal initial assignments.

6. GINI COEFFICIENT for load fairness
   Gini = 0 → perfectly equal; Gini = 1 → one agent did everything.
   Standard economic inequality metric repurposed for agent load — far more
   informative than std dev alone.

7. ENRICHED TELEMETRY
   P50 / Mean / P95 delivery time; per-order ETA safety tag at assignment;
   per-agent breach rate to surface reliability variance across the fleet.

8. COMPLEXITY: O(A·log N) per event — unchanged from baseline.
   ScoringEngine stateless, Dispatcher owns all mutable state,
   EscalationMonitor injected → every layer independently unit-testable.
"""

if __name__ == "__main__":
    main()