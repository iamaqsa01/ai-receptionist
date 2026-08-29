"""Request-scoped correlation IDs, propagated through structured logs via
`contextvars` (safe across concurrent asyncio tasks — each request/websocket
connection gets its own copy) and injected into every LogRecord by
`ContextLogFilter` (see logging_config.py).

Three IDs, three different lifetimes:
  - request_id: one HTTP request/response cycle (RequestContextMiddleware)
  - workspace_id: bound for the duration of any workspace-scoped request
    (app.api.deps.get_tenant_context) or telephony call
  - call_id: bound for the duration of one telephony call
    (app.telephony.session.CallSession)
"""

import contextvars
import uuid
from contextlib import contextmanager
from typing import Iterator

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_workspace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("workspace_id", default=None)
_call_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("call_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str | None:
    return _request_id.get()


def get_workspace_id() -> str | None:
    return _workspace_id.get()


def get_call_id() -> str | None:
    return _call_id.get()


@contextmanager
def bind_request_id(request_id: str) -> Iterator[None]:
    # Restores the *previous value* via a plain .set() rather than
    # Token-based .reset(): FastAPI runs sync generator dependencies (see
    # get_tenant_context below) via anyio's threadpool, where __enter__ and
    # __exit__ can end up executing against different `contextvars.Context`
    # snapshots — a Token minted in one Context raises ValueError if
    # .reset() is called against another. `.set()` has no such restriction.
    previous = _request_id.get()
    _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.set(previous)


@contextmanager
def bind_workspace_id(workspace_id) -> Iterator[None]:
    previous = _workspace_id.get()
    _workspace_id.set(str(workspace_id) if workspace_id is not None else None)
    try:
        yield
    finally:
        _workspace_id.set(previous)


@contextmanager
def bind_call_id(call_id: str | None) -> Iterator[None]:
    previous = _call_id.get()
    _call_id.set(call_id)
    try:
        yield
    finally:
        _call_id.set(previous)


class ContextLogFilter:
    """logging.Filter (duck-typed — only needs .filter()) that stamps every
    LogRecord with whichever correlation IDs are currently bound, so the
    JSON formatter (and the plain-text one, for local dev) can include them
    without every call site passing them explicitly."""

    def filter(self, record) -> bool:
        record.request_id = _request_id.get()
        record.workspace_id = _workspace_id.get()
        record.call_id = _call_id.get()
        return True
