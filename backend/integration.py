"""Bound optional agent calls, including imports, in disposable processes.

This is failure isolation, not a security boundary against hostile local code.
Agents receive only copied JSON decision-time observations, never fixtures.
"""
import asyncio
import importlib
import inspect
import json
import math
import multiprocessing
import os
import threading
import time
from copy import deepcopy

from pydantic import BaseModel, ValidationError

MAX_OUTPUT_BYTES = 65536
_SLOTS = threading.BoundedSemaphore(4)


class AgentFailure(Exception):
    """Safe, fixed-text cause suitable for fallback warnings."""


def _worker(connection, module_name: str, function_name: str, args: list):
    try:
        function = getattr(importlib.import_module(module_name), function_name)
        result = function(*args)
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        if isinstance(result, BaseModel):
            result = result.model_dump(mode="json")
        payload = json.dumps({"ok": True, "result": result}, allow_nan=False).encode("utf-8")
        if len(payload) > MAX_OUTPUT_BYTES:
            payload = b'{"ok":false}'
        connection.send_bytes(payload)
    except Exception:
        # Do not transmit exception strings, credentials, paths, or provider responses.
        connection.send_bytes(b'{"ok":false}')
    finally:
        connection.close()


class AgentRunner:
    def __init__(self, timeout_seconds: float | None = None):
        if timeout_seconds is None:
            try:
                timeout_seconds = float(os.environ.get("AGENT_TIMEOUT_SECONDS", "3"))
            except ValueError:
                timeout_seconds = 3.0
        self.timeout_seconds = min(10.0, max(0.1, timeout_seconds)) if math.isfinite(timeout_seconds) else 3.0

    def invoke(self, module_name, function_name, args, result_type, role=None, evidence_ids=None):
        if os.environ.get("AGENT_MODE", "auto") == "offline":
            raise AgentFailure("backend offline mode is enabled")
        started = time.monotonic()
        if not _SLOTS.acquire(timeout=self.timeout_seconds):
            raise AgentFailure("agent capacity limit reached")
        parent = child = process = None
        try:
            context = multiprocessing.get_context("spawn")
            parent, child = context.Pipe(duplex=False)
            process = context.Process(target=_worker, args=(child, module_name, function_name, deepcopy(args)), daemon=True)
            process.start()
            child.close()
            remaining = max(0, self.timeout_seconds - (time.monotonic() - started))
            if not parent.poll(remaining):
                raise AgentFailure("agent deadline exceeded")
            payload = json.loads(parent.recv_bytes(MAX_OUTPUT_BYTES))
            if not payload.get("ok"):
                raise AgentFailure("agent module unavailable or failed")
            return validate_agent_result(payload["result"], result_type, role, evidence_ids)
        except AgentFailure:
            raise
        except Exception:
            raise AgentFailure("agent module unavailable or invalid output") from None
        finally:
            if process is not None and process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=0.5)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=0.5)
                process.close()
            if parent is not None:
                parent.close()
            if child is not None:
                child.close()
            _SLOTS.release()


def validate_agent_result(raw, result_type, role=None, evidence_ids=None):
    try:
        if isinstance(raw, BaseModel):
            raw = raw.model_dump()
        result = result_type.model_validate(raw)
        if role is not None and result.specialist.role != role:
            raise ValueError("wrong specialist role")
        if evidence_ids is not None and hasattr(result, "specialist"):
            if not set(result.specialist.evidence_ids) <= set(evidence_ids):
                raise ValueError("unknown evidence reference")
        if hasattr(result, "headline_assessments"):
            ids = [item.headline_id for item in result.headline_assessments]
            if len(set(ids)) != len(ids) or (evidence_ids is not None and not set(ids) <= set(evidence_ids)):
                raise ValueError("invalid headline assessments")
        return result
    except (ValidationError, ValueError, TypeError, AttributeError):
        raise AgentFailure("agent output failed schema or evidence validation") from None
