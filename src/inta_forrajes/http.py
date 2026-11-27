from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class HTTPClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class JSONResponse:
    data: Any
    headers: dict[str, str]
    status: int


class HTTPClient:
    def __init__(self, timeout: int = 30, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries

    def request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> JSONResponse:
        if params:
            query = urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}{'&' if '?' in url else '?'}{query}"
        payload = None
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "inta-forrajes/0.1 (+prototipo-academico)",
            **(headers or {}),
        }
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                request = Request(url, data=payload, method=method.upper(), headers=request_headers)
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                    data = json.loads(raw) if raw.strip() else {}
                    return JSONResponse(
                        data=data,
                        headers={key.lower(): value for key, value in response.headers.items()},
                        status=response.status,
                    )
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.5 * (2**attempt))
        raise HTTPClientError(f"No se pudo consultar {url}: {last_error}") from last_error
