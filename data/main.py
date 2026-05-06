"""
Smart Delivery Dispatch System - Main Entry Point
"""

import random
from typing import List

from config import Config
from dispatcher import Dispatcher, EscalationMonitor
from models import Agent, Location
from scoring import ScoringEngine


def build_agents(cfg: type = Config) -> List[Agent]:
    """Create a list of agents with random initial positions and ratings."""
    random.seed(42)
    agents = []
    for i in range(cfg.NUM_AGENTS):
        loc = Location(random.uniform(0, cfg.GRID_SIZE),
                       random.uniform(0, cfg.GRID_SIZE))
        agents.append(Agent(
            agent_id=i + 1,
            current_location=loc,
            rating=round(random.uniform(3.0, 5.0), 1),
            home_zone=loc.zone(),
        ))
    return agents


def main() -> None:
    """Main simulation entry point."""
    # Validate configuration
    Config.validate()

    # Set random seeds for reproducibility
    random.seed(0)

    # Initialize components
    agents = build_agents(Config)
    scorer = ScoringEngine(Config)
    monitor = EscalationMonitor(scorer, Config)
    dispatcher = Dispatcher(agents, scorer, monitor, Config)

    # Run simulation
    results = dispatcher.run(Config.NUM_ORDERS)

    # Results are already printed by dispatcher.run()
    # Return results dict for potential further processing
    return results


if __name__ == "__main__":
    main()</content>
<parameter name="filePath">c:\Users\91636\Documents\GitHub\ps2\data\main.py