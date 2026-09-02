from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class WorkingMemory:
    """Ephemeral task state. Never the canonical source of scientific truth."""
    goal: str = ""
    active_collection: str = ""
    active_paper: str = ""
    recent_actions: List[str] = field(default_factory=list)
    notes: Dict[str, str] = field(default_factory=dict)

    def add_action(self, text: str, max_actions: int = 12):
        self.recent_actions.append(text)
        if len(self.recent_actions) > max_actions:
            self.recent_actions = self.recent_actions[-max_actions:]
