"""
Smart Delivery Dispatch System - Dispatcher Module
"""

import heapq
import random
from typing import Dict, List, Optional, Tuple

from config import Config
from models import Agent, Location, Order, Priority
from scoring import ScoringEngine


class EscalationMonitor:
    """Monitors orders and performs reassignments when needed."""

    def __init__(self, scorer: ScoringEngine, cfg: type = Config) -> None:
        self.scorer = scorer
        self.cfg = cfg

    def check_and_escalate(
        self, all_agents: List[Agent], sim_time: float
    ) -> List[Tuple[Agent, Agent, Order]]:
        """Check for orders needing reassignment and return swap recommendations."""
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
                candidates = [a for a in all_agents
                             if a.agent_id != agent.agent_id and a.is_available]

                if not candidates:
                    continue

                ranked = self.scorer.ranked_available(candidates, order, sim_time)
                best_score, best_agent = ranked[0]

                if current_score - best_score >= self.cfg.REASSIGN_SCORE_DELTA:
                    swaps.append((agent, best_agent, order))
                    seen.add(order.order_id)

        return swaps


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
        agents: List[Agent],
        scorer: ScoringEngine,
        monitor: EscalationMonitor,
        cfg: type = Config,
    ) -> None:
        self.agents = agents
        self.scorer = scorer
        self.monitor = monitor
        self.cfg = cfg

        self.event_queue: List = []
        self.sim_time: float = 0.0
        self.all_orders: List[Order] = []
        self.unassigned_q: List[Order] = []
        self._counter: int = 0
        self._delivery_tokens: Dict[int, int] = {}

    # ── Heap helpers ──────────────────────────────────────────────────────────

    def _push(self, t: float, etype: str, payload) -> int:
        self._counter += 1
        heapq.heappush(self.event_queue, (t, self._counter, etype, payload))
        return self._counter

    def _pop(self):
        return heapq.heappop(self.event_queue)

    # ── Order factory ─────────────────────────────────────────────────────────

    def _create_order(self, oid: int, timestamp: float) -> Order:
        """Create a new random order."""
        dest = Location(random.uniform(0, self.cfg.GRID_SIZE),
                        random.uniform(0, self.cfg.GRID_SIZE))
        rest = Location(random.uniform(0, self.cfg.GRID_SIZE),
                        random.uniform(0, self.cfg.GRID_SIZE))
        prep = random.uniform(*self.cfg.PREP_TIME_RANGE)
        prio = random.choices([Priority.NORMAL, Priority.HIGH], weights=[70, 30])[0]
        sla_win = random.uniform(*self.cfg.SLA_WINDOW_RANGE)
        return Order(
            order_id=oid,
            timestamp=timestamp,
            location=dest,
            restaurant=rest,
            prep_time=prep,
            priority=prio,
            sla_deadline=timestamp + sla_win,
        )

    # ── Assignment helpers ────────────────────────────────────────────────────

    def _compute_delivery_time(self, agent: Agent, order: Order) -> float:
        """Compute estimated delivery time for an agent-order pair."""
        travel_rest = agent.current_location.distance_to(order.restaurant) / self.cfg.AGENT_SPEED
        pickup_t = self.sim_time + max(travel_rest, order.prep_time)
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
        """Try to assign an order to the best available agent."""
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
        agent.home_zone = order.zone
        agent.busy_until = delivery_time

        self._schedule_delivery(agent, order, delivery_time)

        if self.cfg.VERBOSE:
            sc = self.scorer.score(agent, order, self.sim_time)
            p = {"normal": "🟢 NORM", "high": "🔴 HIGH", "critical": "🚨 CRIT"}.get(order.priority.value, "❓")
            tag = "✅ ETA_OK" if delivery_time <= order.sla_deadline else "⚠️  ETA_RISK"
            print(f"  [t={self.sim_time:6.2f}] ASSIGNED  {p} Order#{order.order_id:03d}"
                  f" → Agent#{agent.agent_id} | score={sc:.4f}"
                  f" | ETA={delivery_time:.2f}m | SLA={order.sla_deadline:.2f}m | {tag}")
        return True

    # ── Re-assignment ─────────────────────────────────────────────────────────

    def _perform_reassignment(self, old: Agent, new: Agent, order: Order) -> None:
        """Perform reassignment of an order from one agent to another."""
        if order not in old.active_orders or not new.is_available:
            return
        old.active_orders.remove(order)
        order.reassigned = True
        order.assigned_agent_id = new.agent_id
        new.assign_order(order)
        delivery_time = self._compute_delivery_time(new, order)
        new.current_location = order.location
        new.home_zone = order.zone
        new.busy_until = delivery_time
        self._schedule_delivery(new, order, delivery_time)  # token rotated → old event stale
        if self.cfg.VERBOSE:
            print(f"  [t={self.sim_time:6.2f}] REASSIGN  🚨 Order#{order.order_id:03d}"
                  f" Agent#{old.agent_id}→Agent#{new.agent_id}"
                  f" | new_ETA={delivery_time:.2f}m SLA={order.sla_deadline:.2f}m")

    # ── Event handlers ────────────────────────────────────────────────────────

    def _handle_order_arrival(self, order: Order) -> None:
        """Handle a new order arrival."""
        self.all_orders.append(order)
        if self.cfg.VERBOSE:
            print(f"\n[t={self.sim_time:6.2f}] ARRIVED   Order#{order.order_id:03d} | {order}")
        if not self._try_assign(order):
            self.unassigned_q.append(order)
            if self.cfg.VERBOSE:
                print(f"  [t={self.sim_time:6.2f}] QUEUED    Order#{order.order_id:03d} — no free agent")

    def _handle_delivery_complete(self, agent: Agent, order: Order, token: int) -> None:
        """Handle order delivery completion."""
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
        """Handle periodic escalation check."""
        # Stop if all active orders are done
        active_orders = [o for a in self.agents for o in a.active_orders]
        if active_orders or self.unassigned_q:
            swaps = self.monitor.check_and_escalate(self.agents, self.sim_time)
            for old_agent, new_agent, order in swaps:
                self._perform_reassignment(old_agent, new_agent, order)
            self._push(self.sim_time + self.cfg.ESCALATION_INTERVAL, "ESCALATION_CHECK", None)

    # ── Main simulation ───────────────────────────────────────────────────────

    def run(self, num_orders: int) -> Dict:
        """Run the simulation and return results."""
        print("\n" + "═" * 72)
        print(f"{'SMART DELIVERY DISPATCH SYSTEM – SIMULATION START':^{72}}")
        print("═" * 72)

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

        return self._generate_summary()

    def _generate_summary(self) -> Dict:
        """Generate and return simulation summary statistics."""
        import statistics
        from utils import _percentile, _gini

        delivered = [o for o in self.all_orders if o.delivery_time is not None]
        undelivered = [o for o in self.all_orders if o.delivery_time is None]
        breached = [o for o in self.all_orders if o.sla_breached]
        reassigned = [o for o in self.all_orders if o.reassigned]

        dt_list = [o.delivery_time - o.timestamp for o in delivered]
        avg_dt = statistics.mean(dt_list) if dt_list else float("nan")
        med_dt = statistics.median(dt_list) if dt_list else float("nan")
        p95_dt = _percentile(dt_list, 95) if dt_list else float("nan")
        sla_rate = (len(breached) / len(self.all_orders) * 100) if self.all_orders else 0.0
        loads = [a.total_completed for a in self.agents]
        load_std = statistics.pstdev(loads)
        gini_coeff = _gini(loads)

        print("\n" + "═" * 72)
        print(f"{'SIMULATION SUMMARY':^{72}}")
        print("═" * 72)
        print(f"  Total orders          : {len(self.all_orders)}")
        print(f"  Delivered             : {len(delivered)}")
        print(f"  Undelivered           : {len(undelivered)}")
        print(f"  Re-assigned           : {len(reassigned)}")
        print()
        print("  ┌── Delivery Time Metrics ──────────────────────────")
        print(f"  │ Mean                : {avg_dt:.2f} min")
        print(f"  │ Median              : {med_dt:.2f} min")
        print(f"  │ 95th Percentile     : {p95_dt:.2f} min")
        print("  ├── SLA Compliance ─────────────────────────────────")
        print(f"  │ Breach Rate         : {sla_rate:.1f}%  ({len(breached)}/{len(self.all_orders)})")
        print("  ├── Load Fairness ──────────────────────────────────")
        print(f"  │ Std Deviation       : {load_std:.2f} orders/agent")
        print(f"  │ Gini Coefficient    : {gini_coeff:.3f}  (0=perfect equality)")
        print("  └────────────────────────────────────────────────────")
        print()
        print("     Agent | Rating |  Done | Breached | Breach% | Location")
        print("  ---------+--------+-------+----------+---------+-----------------")
        for a in sorted(self.agents, key=lambda x: x.agent_id):
            print(f"  Agent# {a.agent_id:>2}  | {a.rating:>5.1f}★ | "
                  f"{a.total_completed:>5} | {a.total_breached:>8} | "
                  f"{a.breach_rate*100:>6.0f}% | {a.current_location}")
        print("═" * 72)
        print(f"{'END':^{72}}")
        print("═" * 72)

        return {
            "total_orders": len(self.all_orders),
            "delivered": len(delivered),
            "undelivered": len(undelivered),
            "reassigned": len(reassigned),
            "breached": len(breached),
            "sla_rate": sla_rate,
            "avg_delivery_time": avg_dt,
            "med_delivery_time": med_dt,
            "p95_delivery_time": p95_dt,
            "load_std": load_std,
            "gini_coefficient": gini_coeff,
            "agents": [
                {
                    "id": a.agent_id,
                    "rating": a.rating,
                    "completed": a.total_completed,
                    "breached": a.total_breached,
                    "breach_rate": a.breach_rate,
                    "location": (a.current_location.x, a.current_location.y)
                }
                for a in sorted(self.agents, key=lambda x: x.agent_id)
            ]
        }</content>
<parameter name="filePath">c:\Users\91636\Documents\GitHub\ps2\data\dispatcher.py