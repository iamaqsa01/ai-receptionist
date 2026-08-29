import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging_context import bind_request_id, new_request_id

logger = logging.getLogger("app.request")

_REQUEST_ID_HEADER = "X-Request-ID"

# Every payload this API legitimately accepts (registration, notes fields,
# telephony webhook form posts) is well under this — generous headroom
# without leaving the door open to an unbounded body tying up memory/CPU
# before Pydantic validation even runs. Checked against Content-Length only
# (a request that lies about its length via chunked transfer-encoding isn't
# caught here — full protection needs a streaming byte-count limit at the
# ASGI server/proxy layer, out of scope for application middleware alone).
MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024  # 2 MB


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_REQUEST_BODY_BYTES:
                    return JSONResponse(status_code=413, content={"detail": "Request body too large"})
            except ValueError:
                pass  # malformed header — let normal request handling reject it
        return await call_next(request)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Every HTTP request gets a request ID — reused from an inbound
    `X-Request-ID` header when the caller (or a load balancer / API
    gateway) already set one, otherwise a fresh one is generated. It's
    bound for the lifetime of the request (so every log line emitted while
    handling it is correlated automatically — see logging_context.py),
    echoed back on the response so a client can report "what request ID
    got this error", and the request's method/path/status/duration is
    logged as one structured line per request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or new_request_id()
        start = time.monotonic()

        with bind_request_id(request_id):
            try:
                response = await call_next(request)
            except Exception:
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                logger.exception(
                    "request failed: %s %s", request.method, request.url.path,
                    extra={"http_method": request.method, "path": request.url.path, "duration_ms": duration_ms},
                )
                raise
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.info(
                "%s %s -> %s (%sms)", request.method, request.url.path, response.status_code, duration_ms,
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            response.headers[_REQUEST_ID_HEADER] = request_id
            return response
