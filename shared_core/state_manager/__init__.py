"""shared_core.state_manager - live WorldState + World-State History Ledger (Phase B).

Architecture:
  Current State    = WorldState (live machine snapshot)
  Historical Ledger = HistoryLedger (chronological sequence of prior states)
                      backed by LedgerStore (rolling local persistence under data/).
"""
from __future__ import annotations

from .continuity import ContinuityManager
from .ledger import HistoryLedger, LEDGER_FIELDS
from .ledger_store import LedgerStore
from .manager import StateManager
from .os_sampler import OSSampler
from .world_state import WorldState


def build_state_manager(bus, *, persist: bool = True, ring_len: int = 5000,
                        store_cap: int = 50000):
    """Construct a fully-wired StateManager (manager + ledger + rolling store).

    persist=False keeps everything in-memory (used by tests / ephemeral runs).
    """
    store = LedgerStore(cap=store_cap) if persist else None
    ledger = HistoryLedger(store=store, maxlen=ring_len)
    return StateManager(bus, ledger=ledger)


__all__ = [
    "StateManager",
    "WorldState",
    "HistoryLedger",
    "LedgerStore",
    "OSSampler",
    "ContinuityManager",
    "LEDGER_FIELDS",
    "build_state_manager",
]
