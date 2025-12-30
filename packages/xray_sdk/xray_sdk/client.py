# packages/xray_sdk/xray_sdk/client.py
import time
import uuid
import requests
import os
import json
from pathlib import Path
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List


def _now_ms() -> int:
    return int(time.time() * 1000)



REDACT_KEYS = {"password", "token", "api_key", "secret", "authorization"}


def redact(obj):
    """
    Recursively redacts sensitive keys in dict/list structures.
    Leaves primitive values untouched unless they are under a sensitive key.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in REDACT_KEYS:
                out[k] = "***REDACTED***"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


@dataclass
class StepRecord:
    name: str
    execution_id: str
    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at_ms: int = field(default_factory=_now_ms)
    ended_at_ms: Optional[int] = None
    status: str = "SUCCESS"

    # Core data
    input: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    artifacts: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None

    # New: tags for filtering
    tags: List[str] = field(default_factory=list)

    def end(self):
        self.ended_at_ms = _now_ms()

    @property
    def duration_ms(self) -> Optional[int]:
        return None if self.ended_at_ms is None else self.ended_at_ms - self.started_at_ms

class XRayClient:
    """
    Minimal SDK:
    - start_execution() creates an execution record in API
    - step() captures a decision step and emits it

    Production-quality features:
    - redaction of secrets
    - tags for filtering
    - fail-open behavior
    - local buffering when API is down
    """

    def __init__(
        self,
        base_url: str,
        app: str = "app",
        timeout_s: float = 3.0,
        fail_open: bool = True,
        queue_path: Optional[str] = None,
        max_queue_bytes: int = 5_000_000,
        default_tags: Optional[List[str]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.app = app
        self.timeout_s = timeout_s
        self.fail_open = fail_open
        self.default_tags = default_tags or []

        if queue_path is None:
            queue_path = str(Path.home() / ".xray_queue.jsonl")

        self.queue_path = queue_path
        self.max_queue_bytes = max_queue_bytes

    # -------------------------
    # Execution lifecycle
    # -------------------------
    def start_execution(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        execution_id = str(uuid.uuid4())
        payload = {
            "execution_id": execution_id,
            "name": name,
            "app": self.app,
            "created_at_ms": _now_ms(),
            "metadata": redact(metadata or {}),
            "tags": list(dict.fromkeys((tags or []) + self.default_tags)),
        }
        self._post("/executions", payload)
        return execution_id

    @contextmanager
    def step(
        self,
        execution_id: str,
        name: str,
        input: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ):
        rec = StepRecord(
            name=name,
            execution_id=execution_id,
            input=input or {},
            tags=list(dict.fromkeys(tags or [])),
        )
        helper = StepHelper(rec)

        try:
            yield helper
            rec.status = "SUCCESS"
        except Exception as e:
            rec.status = "ERROR"
            rec.error = {"type": type(e).__name__, "message": str(e)}
            raise
        finally:
            rec.end()

            payload = {
                "step_id": rec.step_id,
                "execution_id": rec.execution_id,
                "name": rec.name,
                "status": rec.status,
                "started_at_ms": rec.started_at_ms,
                "ended_at_ms": rec.ended_at_ms,
                "duration_ms": rec.duration_ms,
                "tags": rec.tags,
                "input": redact(rec.input),
                "output": redact(rec.output),
                "reasoning": rec.reasoning,
                "artifacts": redact(rec.artifacts),
                "error": redact(rec.error) if rec.error else None,
            }

            self._post(f"/executions/{execution_id}/steps", payload)

    # -------------------------
    # Buffering + delivery
    # -------------------------
    def _enqueue(self, path: str, payload: Dict[str, Any]) -> None:
        try:
            p = Path(self.queue_path)
            p.parent.mkdir(parents=True, exist_ok=True)

            # crude size cap
            if p.exists() and p.stat().st_size > self.max_queue_bytes:
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                keep = lines[len(lines) // 2 :]
                p.write_text("\n".join(keep) + "\n", encoding="utf-8")

            record = {
                "path": path,
                "payload": payload,
                "queued_at_ms": _now_ms(),
            }

            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            # never crash caller
            return

    def flush(self, limit: int = 50) -> None:
        p = Path(self.queue_path)
        if not p.exists():
            return

        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            if not lines:
                return

            remaining = []
            sent = 0

            for line in lines:
                if sent >= limit:
                    remaining.append(line)
                    continue

                try:
                    rec = json.loads(line)
                    self._post_raw(rec["path"], rec["payload"])
                    sent += 1
                except Exception:
                    remaining.append(line)

            if remaining:
                p.write_text("\n".join(remaining) + "\n", encoding="utf-8")
            else:
                p.unlink(missing_ok=True)

        except Exception:
            return

    def _post_raw(self, path: str, payload: Dict[str, Any]) -> None:
        r = requests.post(self.base_url + path, json=payload, timeout=self.timeout_s)
        r.raise_for_status()

    def _post(self, path: str, payload: Dict[str, Any]) -> None:
        try:
            # best-effort flush before new send
            self.flush(limit=25)

            r = requests.post(self.base_url + path, json=payload, timeout=self.timeout_s)
            r.raise_for_status()
        except Exception:
            self._enqueue(path, payload)
            if not self.fail_open:
                raise


class StepHelper:
    def __init__(self, rec: StepRecord):
        self._rec = rec

    def output(self, data: Dict[str, Any]) -> None:
        self._rec.output = data

    def reason(self, text: str) -> None:
        self._rec.reasoning = text

    def artifact(self, key: str, value: Any) -> None:
        self._rec.artifacts[key] = value

    def tag(self, *tags: str) -> None:
        """
        Add tags to this step.
        Example: helper.tag("retrieval", "cache_hit")
        """
        for t in tags:
            if t and t not in self._rec.tags:
                self._rec.tags.append(t)
