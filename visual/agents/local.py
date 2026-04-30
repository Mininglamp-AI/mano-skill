"""LocalAgent — on-device VLM agent using MLX + cider."""

import base64
import io
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from visual.agents.base import BaseAgent
from visual.config.visual_config import AUTOMATION_CONFIG

logger = logging.getLogger("mano.local")

LOCAL_AGENT_CONFIG = {
    "MAX_NEW_TOKENS": 2048,
    "TEMPERATURE": 0.0,
    "TOP_P": 1.0,
    "SCREENSHOT_WIDTH": 1280,
    "HISTORY_IMAGE_COUNT": 1,
}


class LocalAgent(BaseAgent):
    """On-device VLM agent using MLX (Qwen3-VL via cider)."""

    agent_type = "local"

    SYSTEM_PROMPT = "You are a helpful assistant."

    INSTRUCTION_TEMPLATE = """\
You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task.

## OS Platform
{platform}

## Output Format
<think>思考过程</think>
<action_desp>动作描述</action_desp>
<action>具体动作</action>

## Action Space

hover(start_box='<|box_start|>(x1,y1)<|box_end|>')
click(start_box='<|box_start|>(x1,y1)<|box_end|>')
triple_click(start_box='<|box_start|>(x1,y1)<|box_end|>') left click at the coordinate (x1,y1) three times
hotkey_click(start_box='<|box_start|>(x1,y1)<|box_end|>', key=''). press command key and click at the coordinate (x1,y1)
right_single(start_box='<|box_start|>(x1,y1)<|box_end|>').  right click at the coordinate (x1,y1)
type(content='') type the content.
doubleclick(start_box='<|box_start|>(x1,y1)<|box_end|>')
drag(start_box='<|box_start|>(x1,y1)<|box_end|>', end_box='<|box_start|>(x3,y3)<|box_end|>') # Drag an element from the start coordinate (x1,y1) to the end coordinate (x3,y3).
hotkey(key='') # Trigger a keyboard shortcut.
wait(duration='') # Sleep for specified duration (in seconds) and take a screenshot to check for any changes.
call_user() # Request human assistance
stop(reason='') # If the item can not found in the image, give the reason
scroll(start_box='<|box_start|>(x1,y1)<|box_end|>', direction='down or up or right or left', amount='scroll_amount') # Scroll on the specified direction at the coordinate (x1,y1) by the given amount
finish() # The task is completed.

## Note
- Use Chinese in `<think>` part.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `<action_desp>` part.
- Before using type(), always click the target input field first to ensure cursor focus is in the correct position.
- When the task requires opening an app that is not visible on screen, use Spotlight: hotkey(key='ctrl space'), then type(content='app name'), then hotkey(key='enter').
- To clear text in an input field, first click the field, then hotkey(key='ctrl a'), then hotkey(key='backspace').

## User Instruction:
{instruction}
"""

    def __init__(self, model_path: str):
        self._model_path = os.path.expanduser(model_path)
        self.model_name = os.path.basename(self._model_path)
        self.cfg = LOCAL_AGENT_CONFIG

        self.model = None
        self.processor = None
        self._custom_generate = None
        self._model_loaded = False

        self.prompt_history: list = []
        self.step_count = 0

    def _ensure_model_loaded(self):
        """Lazy-load model on first predict (must be called from worker thread)."""
        if self._model_loaded:
            return
        import mlx_vlm as pm
        from vlm_service import custom_generate

        logger.info(f"Loading local model from {self._model_path} ...")
        self.model, self.processor = pm.load(self._model_path)

        # W8A8 acceleration (config: auto/on/off, default auto)
        from visual.config.user_config import get_config
        w8a8_mode = get_config("w8a8") or "off"
        if w8a8_mode != "off":
            try:
                import mlx.core as mx
                from cider import convert_model, is_available
                if w8a8_mode == "auto" and not is_available():
                    logger.info("W8A8 not available on this hardware (requires M5+)")
                elif w8a8_mode == "on" or is_available():
                    try:
                        stats = convert_model(self.model.language_model)
                    except Exception:
                        stats = convert_model(self.model)
                    # Pre-warm: quantize all INT8 weights upfront
                    from cider.nn import CiderLinear
                    for module in self.model.language_model.modules():
                        if isinstance(module, CiderLinear):
                            module._ensure_w8()
                    mx.eval(self.model.parameters())
                    logger.info(f"W8A8 enabled: {stats}")
            except ImportError:
                if w8a8_mode == "on":
                    logger.warning("W8A8 requested but cider not installed")
            except Exception as e:
                logger.warning(f"W8A8 init failed: {e}")

        self._custom_generate = custom_generate
        self._model_loaded = True
        logger.info("Local model loaded successfully.")

    # ─── BaseAgent interface ──────────────────────────────────

    def predict(
        self,
        task_instruction: str,
        tool_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]], str, str]:
        self._ensure_model_loaded()
        _t0 = time.time()

        # 1. Extract screenshot
        screenshot_b64 = self._extract_screenshot(tool_results)
        if screenshot_b64 is None:
            screenshot_b64 = self._take_screenshot_b64()

        # 2. Build prompt
        user_text, images = self._build_prompt(task_instruction, screenshot_b64)

        # 3. Run inference
        response_text = self._infer(user_text, images)
        print(f"  [model output] {response_text}")

        # Save raw response to file
        self._save_raw_response(response_text)

        # 4. Parse response
        parsed = self._parse_response(response_text)
        think = parsed["think"]
        action_desp = parsed["action_desp"]
        parsed_actions = parsed["actions"]

        # 5. Record prompt history
        if screenshot_b64:
            self.prompt_history.append({
                "desc": action_desp or str(parsed_actions),
                "screenshot_b64": screenshot_b64,
            })

        # 6. Convert to Claude-compatible actions and determine status
        if not parsed_actions:
            actions = [{"action_type": "FAIL"}]
            status = "FAIL"
            action_str = "FAIL"
        else:
            actions = []
            for a in parsed_actions:
                actions.extend(self._convert_action(a))
            status = self._determine_status(actions)
            action_str = " → ".join(self._format_action_desc([a]) for a in actions)

        self.step_count += 1
        elapsed = time.time() - _t0
        print(f"  [step {self.step_count}] {elapsed:.1f}s — {action_str}")

        return think, actions, status, action_str

    def close(self, skip_eval: bool = False, close_reason: Optional[str] = None) -> Optional[dict]:
        # Local mode: no server session to close, no eval
        return None

    def _save_raw_response(self, text: str):
        import json
        log_path = os.path.expanduser("~/.mano/raw_responses.jsonl")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"step": self.step_count, "raw": text}, ensure_ascii=False) + "\n")

    def agree_to_continue(self) -> None:
        self.prompt_history.append({
            "desc": "用户已确认继续",
            "screenshot_b64": "",
        })

    # ─── Screenshot handling ──────────────────────────────────

    def _take_screenshot_b64(self) -> str:
        from visual.computer.computer_use_util import screenshot_to_bytes, b64_png
        raw_bytes = screenshot_to_bytes()
        raw_b64 = b64_png(raw_bytes)
        return self._resize_screenshot_b64(raw_b64)

    def _extract_screenshot(self, tool_results: Optional[List[Dict[str, Any]]]) -> Optional[str]:
        if not tool_results:
            return None
        for tr in reversed(tool_results):
            b64 = tr.get("screenshot_b64")
            if b64:
                return self._resize_screenshot_b64(b64)
        return None

    def _resize_screenshot_b64(self, b64: str) -> str:
        target_w = self.cfg["SCREENSHOT_WIDTH"]
        img_bytes = base64.b64decode(b64)
        img = Image.open(io.BytesIO(img_bytes))
        if img.width == target_w:
            return b64
        ratio = target_w / img.width
        new_h = int(img.height * ratio)
        img = img.resize((target_w, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    # ─── Prompt building ──────────────────────────────────────

    def _build_prompt(self, task: str, current_screenshot_b64: Optional[str]) -> Tuple[str, list]:
        import platform as _platform
        images: list = []
        history_count = self.cfg["HISTORY_IMAGE_COUNT"]
        recent = self.prompt_history[-(history_count + 1):]

        history_parts = []
        for i, h in enumerate(self.prompt_history):
            step_num = i + 1
            desc = h["desc"]
            if h in recent and h.get("screenshot_b64"):
                images.append(h["screenshot_b64"])
                history_parts.append(f"第{step_num}步：{desc}，对应的截图为<image>")
            else:
                history_parts.append(f"第{step_num}步：{desc}")

        history_text = "\n".join(history_parts) if history_parts else "无"

        instruction_parts = [f"### task: {task}"]
        instruction_parts.append(f"### action history: {history_text}")
        if current_screenshot_b64:
            images.append(current_screenshot_b64)
            instruction_parts.append("当前截图为<image>")

        text = self.INSTRUCTION_TEMPLATE.format(
            platform=_platform.system(),
            instruction="\n".join(instruction_parts),
        )
        return text, images

    # ─── Inference ────────────────────────────────────────────

    def _infer(self, user_text: str, images: list) -> str:
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]

        pil_images = []
        for b64 in images:
            img_bytes = base64.b64decode(b64)
            pil_images.append(Image.open(io.BytesIO(img_bytes)))

        prompt = self.processor.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        # Replace <image> placeholders with Qwen3-VL vision tokens
        org_placeholder = "<image>"
        new_placeholder = "<|vision_start|><|image_pad|><|vision_end|>"
        pi = len(pil_images)
        while pi > 0:
            pi -= 1
            pos = prompt.rfind(org_placeholder)
            if pos >= 0:
                prompt = prompt[:pos] + prompt[pos:].replace(org_placeholder, new_placeholder, 1)
            else:
                break

        result = self._custom_generate(
            self.model, self.processor, prompt,
            pil_images if pil_images else None,
            max_tokens=self.cfg["MAX_NEW_TOKENS"],
            temperature=self.cfg["TEMPERATURE"],
            top_p=self.cfg["TOP_P"],
            prefill_step_size=2048,
        )
        gen_tokens = getattr(result, "generation_tokens", 0)
        gen_tps = getattr(result, "generation_tps", 0)
        peak_mem = getattr(result, "peak_memory", 0)
        print(f"  [decode] {gen_tokens} tokens, {gen_tps:.1f} tok/s, peak_mem={peak_mem:.1f}GB")
        return result.text

    # ─── Response parsing ─────────────────────────────────────

    def _parse_response(self, text: str) -> dict:
        think = self._extract_tag(text, "think") or ""
        action_desp = self._extract_tag(text, "action_desp") or ""
        action_raw = self._extract_tag(text, "action") or ""
        actions = []
        if action_raw:
            # Match each action function call: name(...) allowing nested quotes/newlines
            for m in re.finditer(r"(\w+\(.*?\))(?=\s*\n\s*\w+\(|\s*$)", action_raw.strip(), re.DOTALL):
                parsed = self._parse_action(m.group(1).strip())
                if parsed:
                    actions.append(parsed)
        return {"think": think.strip(), "action_desp": action_desp.strip(), "actions": actions}

    def _extract_tag(self, text: str, tag: str) -> Optional[str]:
        m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
        return m.group(1) if m else None

    def _parse_box(self, box_str: str) -> list:
        m = re.search(r"\((\d+)\s*,\s*(\d+)\)", box_str)
        if not m:
            return [0, 0]
        return [int(m.group(1)), int(m.group(2))]

    def _parse_action(self, action_str: str) -> Optional[dict]:
        action_str = action_str.strip()
        m = re.match(r"(\w+)\((.*)\)$", action_str, re.DOTALL)
        if not m:
            return None

        func_name = m.group(1)
        args_str = m.group(2).strip()

        kwargs = {}
        for km in re.finditer(r"(\w+)\s*=\s*'(.*?)'", args_str, re.DOTALL):
            kwargs[km.group(1)] = km.group(2)

        if func_name in ("click", "doubleclick", "hover"):
            return {"action": func_name, "coords": self._parse_box(kwargs.get("start_box", ""))}
        if func_name == "triple_click":
            return {"action": "triple_click", "coords": self._parse_box(kwargs.get("start_box", ""))}
        if func_name == "right_single":
            return {"action": "right_click", "coords": self._parse_box(kwargs.get("start_box", ""))}
        if func_name == "hotkey_click":
            return {"action": "hotkey_click", "coords": self._parse_box(kwargs.get("start_box", "")), "key": kwargs.get("key", "")}
        if func_name == "type":
            return {"action": "type", "text": kwargs.get("content", "")}
        if func_name == "hotkey":
            return {"action": "hotkey", "key": kwargs.get("key", "")}
        if func_name == "scroll":
            amount = kwargs.get("amount", "3")
            try:
                amount = int(amount)
            except (ValueError, TypeError):
                amount = 3
            result = {"action": "scroll", "direction": kwargs.get("direction", "down"), "amount": amount}
            box = kwargs.get("start_box", "")
            if box:
                result["coords"] = self._parse_box(box)
            return result
        if func_name == "drag":
            return {
                "action": "drag",
                "start": self._parse_box(kwargs.get("start_box", "")),
                "end": self._parse_box(kwargs.get("end_box", "")),
            }
        if func_name == "wait":
            duration = kwargs.get("duration", "5")
            try:
                duration = float(duration)
            except (ValueError, TypeError):
                duration = 5.0
            return {"action": "wait", "duration": duration}
        if func_name == "finish":
            return {"action": "finish"}
        if func_name == "open_url":
            return {"action": "open_url", "url": kwargs.get("url", "")}
        if func_name == "stop":
            return {"action": "stop", "reason": kwargs.get("reason", "")}
        if func_name == "call_user":
            return {"action": "call_user"}
        return None

    # ─── Action conversion: Qwen3-VL → Claude format ─────────

    def _norm_coord(self, x: int, y: int) -> list:
        """Convert [0,1000] normalised coords to 1280x720 executor space.

        The executor then scales from 1280x720 to actual screen pixels.
        """
        return [int(x / 1000 * AUTOMATION_CONFIG["SCREEN_SCALE_WIDTH"]),
                int(y / 1000 * AUTOMATION_CONFIG["SCREEN_SCALE_HEIGHT"])]

    def _make_tool_action(self, input_dict: dict) -> dict:
        return {
            "name": "computer",
            "input": input_dict,
            "id": str(uuid.uuid4()),
            "action_type": "tool_use",
        }

    def _determine_status(self, actions: List[Dict[str, Any]]) -> str:
        for a in actions:
            at = (a.get("action_type") or "").upper()
            if at == "DONE":
                return "DONE"
            if at == "FAIL":
                return "FAIL"
            if at == "CALL_USER":
                return "CALL_USER"
        return "RUNNING"

    def _format_action_desc(self, actions: List[Dict[str, Any]]) -> str:
        """Format action list into human-readable string like 'left_click(432, 265)'."""
        if not actions:
            return ""
        a = actions[0]
        at = (a.get("action_type") or "").upper()
        if at in ("DONE", "FAIL", "CALL_USER"):
            return at
        inp = a.get("input", {})
        name = a.get("name", "")
        if name == "open_url":
            return f"open_url(\"{inp.get('url', '')}\")"
        action = inp.get("action", "unknown")
        coord = inp.get("coordinate")
        if coord:
            return f"{action}({coord[0]}, {coord[1]})"
        text = inp.get("text")
        if text:
            return f"{action}(\"{text[:30]}\")"
        direction = inp.get("scroll_direction")
        if direction:
            return f"{action} {direction}"
        return action

    def _convert_action(self, action: dict) -> List[Dict[str, Any]]:
        """Convert parsed Qwen3-VL action to Claude-compatible action list."""
        act = action["action"]

        if act == "finish":
            return [{"action_type": "DONE"}]
        if act == "open_url":
            return [{
                "name": "open_url",
                "input": {"url": action.get("url", "")},
                "id": str(uuid.uuid4()),
                "action_type": "tool_use",
            }]
        if act == "stop":
            return [{"action_type": "FAIL"}]
        if act == "call_user":
            return [{"action_type": "CALL_USER"}]

        if act == "click":
            coords = action.get("coords", [0, 0])
            return [self._make_tool_action({
                "action": "left_click",
                "coordinate": self._norm_coord(coords[0], coords[1]),
            })]

        if act == "doubleclick":
            coords = action.get("coords", [0, 0])
            return [self._make_tool_action({
                "action": "double_click",
                "coordinate": self._norm_coord(coords[0], coords[1]),
            })]

        if act == "triple_click":
            coords = action.get("coords", [0, 0])
            return [self._make_tool_action({
                "action": "triple_click",
                "coordinate": self._norm_coord(coords[0], coords[1]),
            })]

        if act == "right_click":
            coords = action.get("coords", [0, 0])
            return [self._make_tool_action({
                "action": "right_click",
                "coordinate": self._norm_coord(coords[0], coords[1]),
            })]

        if act == "hover":
            coords = action.get("coords", [0, 0])
            return [self._make_tool_action({
                "action": "mouse_move",
                "coordinate": self._norm_coord(coords[0], coords[1]),
            })]

        if act == "hotkey_click":
            coords = action.get("coords", [0, 0])
            return [self._make_tool_action({
                "action": "left_click",
                "coordinate": self._norm_coord(coords[0], coords[1]),
                "text": action.get("key", ""),
            })]

        if act == "type":
            return [self._make_tool_action({
                "action": "type",
                "text": action.get("text", ""),
            })]

        if act == "hotkey":
            return [self._make_tool_action({
                "action": "key",
                "text": action.get("key", ""),
            })]

        if act == "scroll":
            direction = action.get("direction", "down")
            amount = action.get("amount", 3)
            coords = action.get("coords")
            coordinate = self._norm_coord(coords[0], coords[1]) if coords else [640, 360]
            multiplier = AUTOMATION_CONFIG["SCROLL_MULTIPLIER"]
            return [self._make_tool_action({
                "action": "scroll",
                "scroll_direction": direction,
                "coordinate": coordinate,
                "scroll_amount": max(1, amount // multiplier),
            })]

        if act == "drag":
            start = action.get("start", [0, 0])
            end = action.get("end", [0, 0])
            return [self._make_tool_action({
                "action": "left_click_drag",
                "start_coordinate": self._norm_coord(start[0], start[1]),
                "coordinate": self._norm_coord(end[0], end[1]),
            })]

        if act == "wait":
            duration = action.get("duration", 5)
            return [self._make_tool_action({
                "action": "wait",
                "duration": duration,
            })]

        return [{"action_type": "FAIL"}]
