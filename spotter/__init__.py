"""spotter — a safety gate for agents training in Fleet's gyms.

Fleet scores whether an agent finished the task. spotter scores whether it
finished safely.
"""
from .core import Spotter, SpotterResult, Check, Severity, Verdict, Action, TaskContext, Finding
from .checks import DEFAULT_CHECKS

__all__ = [
    "Spotter", "SpotterResult", "Check", "Severity", "Verdict",
    "Action", "TaskContext", "Finding", "DEFAULT_CHECKS",
]
__version__ = "0.1.0"
