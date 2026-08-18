"""Agents that propose changes; the harness gates every write behind approval."""

from ghl_toolkit.agents.harness import HarnessResult, Proposal, run_proposals

__all__ = ["HarnessResult", "Proposal", "run_proposals"]
