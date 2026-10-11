"""
obs.py - Structured run log (JSONL) for tracing what the pipeline did and why.

One file per run: logs/run_<run_id>.jsonl. Every line is one event:

    ts, run_id, site, stage, event (start|success|fail|skip), duration_ms,
    error_type, error_message, context

error_type is one of ERROR_TYPES (or null). Field events carry
context.kind == "field" plus the field name, value, source and the exact rule
that produced it, so a wrong value in a report can be traced back to the
selector / JSON-LD / regex / AI call / default that set it.

Nothing here changes pipeline behaviour: until init_run() is called every
function is a no-op, and a failure to write the log never propagates.
"""

import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

ERROR_TYPES = ("input_invalid", "http", "blocked", "parse", "timeout", "external_api", "unknown")
EVENTS = ("start", "success", "fail", "skip")

# Where a field value came from. The first five are the categories asked for;
# "json" covers embedded/API JSON that is not JSON-LD and "derived" covers
# values computed from other logged values (detail names the inputs).
SOURCES = ("selector", "json_ld", "regex", "ai", "default", "json", "derived")

_state: Dict[str, Any] = {
    "run_id": None,
    "path": None,
    "fh": None,
    "site": None,
    "stage": None,
    "provenance": {},
    "page": None,
    "write_failed": False,
}


def init_run(log_dir: Optional[str] = None, run_id: Optional[str] = None) -> str:
    """Open logs/run_<run_id>.jsonl. ECI_LOG_DIR / ECI_RUN_ID override the defaults."""
    close_run()
    log_dir = log_dir or os.environ.get("ECI_LOG_DIR") or "logs"
    run_id = run_id or os.environ.get("ECI_RUN_ID") or (
        datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    )
    path = Path(log_dir) / f"run_{run_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _state.update(run_id=run_id, path=path, fh=open(path, "a", encoding="utf-8"),
                  site=None, stage=None, provenance={}, page=None, write_failed=False)
    return run_id


def close_run() -> None:
    fh = _state.get("fh")
    if fh:
        try:
            fh.close()
        except Exception:  # pragma: no cover - closing a log must never break a run
            pass
    _state.update(run_id=None, path=None, fh=None, site=None, stage=None, provenance={}, page=None)


def active() -> bool:
    return _state["fh"] is not None


def run_id() -> Optional[str]:
    return _state["run_id"]


def log_path() -> Optional[Path]:
    return _state["path"]


def set_site(site: Optional[str]) -> None:
    """Attach later events to this site and reset field provenance."""
    _state["site"] = site
    _state["provenance"] = {}
    _state["page"] = None


def current_stage() -> Optional[str]:
    return _state["stage"]


def _default_stage() -> str:
    """Stage for events emitted outside begin()/end(): "site" inside a site, else "run"."""
    return _state["stage"] or ("site" if _state["site"] else "run")


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "value") and value.__class__.__name__ == "Platform":
        return value.value
    return str(value)


def event(
    stage: str,
    event: str,
    *,
    duration_ms: Optional[float] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    site: Optional[str] = None,
    **context: Any,
) -> None:
    """Write one event line. Never raises."""
    if not active():
        return
    if event not in EVENTS:
        context["bad_event"] = event
        event = "fail"
    if error_type is not None and error_type not in ERROR_TYPES:
        context["bad_error_type"] = error_type
        error_type = "unknown"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "run_id": _state["run_id"],
        "site": site if site is not None else _state["site"],
        "stage": stage,
        "event": event,
        "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
        "error_type": error_type,
        "error_message": (str(error_message)[:500] if error_message is not None else None),
        "context": _jsonable(context),
    }
    try:
        _state["fh"].write(json.dumps(record, ensure_ascii=False) + "\n")
        _state["fh"].flush()
    except Exception as exc:  # the log is best effort; report once on stderr
        if not _state["write_failed"]:
            _state["write_failed"] = True
            print(f"[obs] could not write run log: {exc}", file=sys.stderr)


@contextmanager
def stage(name: str, **context: Any) -> Iterator[Dict[str, Any]]:
    """Emit start, then success (or fail on an escaping exception, which is re-raised).

    The yielded dict is merged into the closing event's context.
    """
    previous = _state["stage"]
    _state["stage"] = name
    extra: Dict[str, Any] = {}
    started = time.perf_counter()
    event(name, "start", **context)
    try:
        yield extra
    except BaseException as exc:
        event(name, "fail", duration_ms=(time.perf_counter() - started) * 1000,
              error_type=classify_exception(exc), error_message=f"{type(exc).__name__}: {exc}",
              **{**context, **extra})
        raise
    else:
        event(name, "success", duration_ms=(time.perf_counter() - started) * 1000,
              **{**context, **extra})
    finally:
        _state["stage"] = previous


def classify_exception(exc: BaseException) -> str:
    """Map an exception to an error_type by its class name and module."""
    name = type(exc).__name__
    module = type(exc).__module__ or ""
    text = str(exc)
    if "Timeout" in name or "timed out" in text.lower():
        return "timeout"
    if "Cloudflare" in name or "Captcha" in name:
        return "blocked"
    if name in ("JSONDecodeError", "ParseError", "XMLSyntaxError") or "Decode" in name:
        return "parse"
    if module.startswith(("requests", "urllib3", "http", "ssl", "socket", "playwright", "patchright")) \
            or name in ("ConnectionError", "SSLError", "HTTPError"):
        return "http"
    if module.startswith(("ollama", "httpx")):
        return "external_api"
    if name in ("FileNotFoundError", "IsADirectoryError", "UnicodeDecodeError"):
        return "input_invalid"
    if name in ("ValueError", "KeyError", "TypeError", "IndexError", "AttributeError"):
        return "parse"
    return "unknown"


def classify_fetch(status: int, error: Optional[str]) -> Optional[str]:
    """error_type for an HttpClient result tuple (status, error string)."""
    if not error:
        return None
    text = error.lower()
    if status in (403, 429) or "cloudflare" in text or "challenge" in text or "captcha" in text:
        return "blocked"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "parsing error" in text:
        return "parse"
    if status and status >= 400:
        return "http"
    if any(k in text for k in ("connection error", "ssl error", "request error", "empty response",
                               "net::err", "playwright error", "cloudscraper error")):
        return "http"
    return "unknown"


def swallowed(where: str, error_type: Optional[str] = None, fallback: str = "",
              stage: Optional[str] = None, exc: Optional[BaseException] = None, **context: Any) -> None:
    """Record an exception that was caught and not re-raised.

    Call it from inside the except block; the active exception is used when
    exc is not given. where is "file.py:function".
    """
    if not active():
        return
    if exc is None:
        exc = sys.exc_info()[1]
    etype = error_type or (classify_exception(exc) if exc is not None else "unknown")
    message = f"{type(exc).__name__}: {exc}" if exc is not None else None
    event(stage or _default_stage(), "fail", error_type=etype, error_message=message,
          swallowed=True, where=where, fallback=fallback, **context)


def degraded(where: str, error_type: str, reason: str, fallback: str = "",
             stage: Optional[str] = None, event_name: str = "skip", **context: Any) -> None:
    """Record a silent fallback that did not involve an exception."""
    if not active():
        return
    event(stage or _default_stage(), event_name, error_type=error_type,
          error_message=reason, degraded=True, where=where, fallback=fallback, **context)


def note(field: str, value: Any, source: str, detail: str = "", url: Optional[str] = None,
         stage: Optional[str] = None, applied: bool = False, **context: Any) -> None:
    """Record a candidate value for a field and remember its provenance.

    url defaults to the page set with set_page(). applied=True marks the
    candidate the pipeline actually assigned (see apply()).
    """
    if not active():
        return
    if source not in SOURCES:
        context["bad_source"] = source
    url = url if url is not None else _state["page"]
    _state["provenance"].setdefault(field, []).append(
        {"source": source, "detail": detail, "url": url, "value": _jsonable(value), "applied": applied})
    event(stage or _default_stage(), "success", kind="candidate", field=field,
          value=value, source=source, detail=detail, url=url, applied=applied, **context)


def apply(field: str, value: Any, how: str, source: str = "default", stage: Optional[str] = None) -> None:
    """Mark that the pipeline assigned value to field, reusing the latest equal candidate's provenance.

    Several extractors can propose the same value; this records which assignment
    actually happened so field() does not credit a candidate that was ignored.
    """
    if not active():
        return
    target = _comparable(_jsonable(value))
    match = next((c for c in reversed(provenance(field)) if _comparable(c["value"]) == target), None)
    if match is not None:
        note(field, value, match["source"], f"{how}; {match['detail']}", url=match["url"],
             stage=stage, applied=True)
    else:
        note(field, value, source, how, stage=stage, applied=True)


def provenance(field: str) -> List[Dict[str, Any]]:
    """Every candidate noted for a field on the current site, oldest first."""
    return list(_state["provenance"].get(field, []))


def field(stage: str, name: str, value: Any, source: Optional[str] = None, detail: str = "",
          url: Optional[str] = None, **context: Any) -> None:
    """Record the value a field ends up with and where it came from.

    Without an explicit source, the most recent note() for the field whose
    value equals the final value is used; if none matches, the value is
    attributed to "default" and the detail lists what was seen instead.
    """
    if not active():
        return
    candidates = provenance(name)
    if source is None:
        final = _comparable(_jsonable(value))
        equal = [c for c in reversed(candidates) if _comparable(c["value"]) == final]
        match = next((c for c in equal if c.get("applied")), equal[0] if equal else None)
        if match is not None:
            source, detail, url = match["source"], match["detail"], match["url"]
        elif candidates:
            source = "default"
            seen = "; ".join(f"{c['value']!r} via {c['source']} ({c['detail']})" for c in candidates[-3:])
            detail = detail or f"no candidate equals the final value; last candidates: {seen}"
        else:
            source = "default"
            detail = detail or "no extractor produced a value"
    event(stage, "success", kind="field", field=name, value=value, source=source,
          detail=detail, url=url, candidates=len(candidates), **context)


def _comparable(value: Any) -> Any:
    """Lists are compared as sorted lists (several extractors return list(set(...)))."""
    if isinstance(value, list):
        return sorted(str(v) for v in value)
    return value


def snippet(text: Optional[str], needle: str, width: int = 40) -> Optional[str]:
    """The text around the first case-insensitive occurrence of needle, for context."""
    if not text or not needle:
        return None
    i = text.lower().find(needle.lower())
    if i < 0:
        return None
    start, stop = max(0, i - width), min(len(text), i + len(needle) + width)
    return " ".join(text[start:stop].split())


def set_page(url: Optional[str]) -> None:
    """The page later note() calls are about (None = not page specific)."""
    _state["page"] = url


def begin(stage_name: str, **context: Any) -> "Timer":
    """Emit a start event, make stage_name current, return a Timer for end()."""
    _state["stage"] = stage_name
    event(stage_name, "start", **context)
    return Timer()


def end(stage_name: str, timer: "Timer", **context: Any) -> None:
    """Emit the success event that closes begin()."""
    event(stage_name, "success", duration_ms=timer.ms(), **context)
    _state["stage"] = None


def skip(stage_name: str, reason: str, error_type: Optional[str] = None, **context: Any) -> None:
    """A stage that did not run at all, and why."""
    event(stage_name, "skip", error_type=error_type, error_message=reason, **context)


class Timer:
    """Small helper: Timer().ms() is the elapsed time in milliseconds."""

    def __init__(self) -> None:
        self.started = time.perf_counter()

    def ms(self) -> float:
        return (time.perf_counter() - self.started) * 1000
