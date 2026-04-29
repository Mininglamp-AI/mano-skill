"""Base agent ABC for task prediction."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class BaseAgent(ABC):
    """Abstract base for task prediction agents."""

    agent_type: str = "unknown"

    @abstractmethod
    def predict(
        self,
        task_instruction: str,
        tool_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]], str, str]:
        """Run one prediction step.

        Returns:
            (reasoning, actions, status, action_desc)
            - reasoning: model thinking text
            - actions: list of action dicts (Claude format)
            - status: RUNNING / DONE / FAIL / CALL_USER / MAX_STEP_REACHED / STOP
            - action_desc: human-readable action description
        """
        ...

    @abstractmethod
    def close(self, skip_eval: bool = False, close_reason: Optional[str] = None) -> Optional[dict]:
        """Close session. Returns eval_result if available."""
        ...

    def stop(self) -> None:
        """Stop the running session. Default: no-op."""
        pass

    def agree_to_continue(self) -> None:
        """Signal user approved continuation after CALL_USER. Default: no-op."""
        pass
