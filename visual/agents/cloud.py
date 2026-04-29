"""CloudAgent — wraps existing server HTTP calls."""

import uuid
from typing import Any, Dict, List, Optional, Tuple

import requests

from visual.agents.base import BaseAgent
from visual.config.visual_config import AUTOMATION_CONFIG, API_HEADERS


class CloudAgent(BaseAgent):
    """Agent that delegates inference to the mano cloud server."""

    agent_type = "cloud"

    def __init__(self, server_url: str, session_id: str, device_id: str):
        self.server_url = server_url
        self.session_id = session_id
        self.device_id = device_id

    def predict(
        self,
        task_instruction: str,
        tool_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]], str, str]:
        payload = {
            "request_id": str(uuid.uuid4()),
            "tool_results": tool_results or [],
        }

        resp = requests.post(
            f"{self.server_url}/v1/sessions/{self.session_id}/step",
            json=payload,
            timeout=AUTOMATION_CONFIG["STEP_TIMEOUT"],
        )
        resp.raise_for_status()
        data = resp.json()

        reasoning = data.get("reasoning", "")
        actions = data.get("actions", [])
        status = (data.get("status") or "RUNNING").upper()
        action_desc = data.get("action_desc", "")

        return reasoning, actions, status, action_desc

    def close(self, skip_eval: bool = False, close_reason: Optional[str] = None) -> Optional[dict]:
        if not self.session_id:
            return None
        try:
            params = f"skip_eval={str(skip_eval).lower()}"
            if close_reason:
                params += f"&close_reason={close_reason}"
            resp = requests.post(
                f"{self.server_url}/v1/sessions/{self.session_id}/close?{params}",
                json={},
                timeout=AUTOMATION_CONFIG["CLOSE_SESSION_TIMEOUT"],
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("eval_result")
        except Exception as e:
            print(f"Failed to close session: {e}")
            return None

    def stop(self) -> None:
        try:
            requests.post(
                f"{self.server_url}/v1/devices/{self.device_id}/stop",
                json={},
                timeout=5,
            )
        except Exception:
            pass

    def agree_to_continue(self) -> None:
        requests.post(
            f"{self.server_url}/v1/sessions/{self.session_id}/go_no",
            timeout=AUTOMATION_CONFIG["SESSION_TIMEOUT"],
            headers={"Content-Type": "application/json"},
        )
