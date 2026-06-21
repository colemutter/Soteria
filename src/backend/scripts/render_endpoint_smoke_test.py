from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_RENDER_BACKEND_URL = "https://soteria-backend-7360.onrender.com"
DEFAULT_RENDER_FRONTEND_URL = "https://soteria-frontend-vcck.onrender.com"


@dataclass(frozen=True)
class EndpointCheck:
    name: str
    method: str
    path: str
    expected_statuses: frozenset[int]
    body: dict[str, Any] | None = None
    require_json_key: str | None = None


ENDPOINT_CHECKS = (
    EndpointCheck(
        name="health",
        method="GET",
        path="/healthz",
        expected_statuses=frozenset({200}),
        require_json_key="status",
    ),
    EndpointCheck(
        name="satellites-list",
        method="GET",
        path="/api/satellites?limit=1",
        expected_statuses=frozenset({200}),
        require_json_key="satellites",
    ),
    EndpointCheck(
        name="satellites-upsert-route",
        method="POST",
        path="/api/satellites",
        expected_statuses=frozenset({422}),
        body={},
    ),
    EndpointCheck(
        name="agent-reaction-route",
        method="POST",
        path="/agent/reactions",
        expected_statuses=frozenset({422}),
        body={},
    ),
    EndpointCheck(
        name="poller-report-route",
        method="POST",
        path="/api/poller/report",
        expected_statuses=frozenset({422}),
        body={},
    ),
    EndpointCheck(
        name="generated-runbook-route",
        method="POST",
        path="/api/runbooks/generated",
        expected_statuses=frozenset({422}),
        body={},
    ),
    EndpointCheck(
        name="upload-runbook-route",
        method="POST",
        path="/api/runbooks/upload",
        expected_statuses=frozenset({422}),
        body={},
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test deployed Render backend routes."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("SOTERIA_RENDER_BACKEND_URL", DEFAULT_RENDER_BACKEND_URL),
        help="Render backend base URL. Defaults to SOTERIA_RENDER_BACKEND_URL or production.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("RENDER_ENDPOINT_TIMEOUT_SECONDS", "30")),
        help="Per-request timeout in seconds.",
    )
    parser.add_argument(
        "--frontend-url",
        default=os.getenv("SOTERIA_RENDER_FRONTEND_URL", DEFAULT_RENDER_FRONTEND_URL),
        help="Render frontend URL to smoke-test after backend routes.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    failures: list[str] = []
    print(f"Checking Render backend endpoints at {base_url}")
    for check in ENDPOINT_CHECKS:
        try:
            status, payload, text = request_json(
                base_url,
                check.method,
                check.path,
                body=check.body,
                timeout=args.timeout,
            )
        except Exception as exc:
            failures.append(f"{check.name}: request failed: {exc}")
            print({"name": check.name, "ok": False, "error": str(exc)})
            continue

        ok = status in check.expected_statuses
        if status == 404:
            failures.append(f"{check.name}: route returned 404 for {check.path}")
        elif not ok:
            failures.append(
                f"{check.name}: expected {sorted(check.expected_statuses)}, got {status}"
            )

        if ok and check.require_json_key and check.require_json_key not in payload:
            failures.append(
                f"{check.name}: JSON body missing key {check.require_json_key!r}"
            )
            ok = False

        print(
            {
                "name": check.name,
                "method": check.method,
                "path": check.path,
                "status": status,
                "ok": ok,
                "body_preview": summarize_body(payload, text),
            }
        )

    if failures:
        print("Render endpoint smoke test failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    frontend_url = args.frontend_url.rstrip("/")
    frontend_status, _, frontend_text = request_json(
        frontend_url,
        "GET",
        "/",
        body=None,
        timeout=args.timeout,
    )
    frontend_ok = frontend_status == 200 and "html" in frontend_text[:200].lower()
    print(
        {
            "name": "frontend-root",
            "method": "GET",
            "url": frontend_url,
            "status": frontend_status,
            "ok": frontend_ok,
        }
    )
    if not frontend_ok:
        print(
            f"Render frontend smoke test failed: got HTTP {frontend_status}",
            file=sys.stderr,
        )
        return 1

    print("Render endpoint smoke test passed.")
    return 0


def request_json(
    base_url: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None,
    timeout: float,
) -> tuple[int, dict[str, Any], str]:
    data = None
    headers = {"accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"
    request = Request(
        f"{base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            return response.status, parse_json_object(text), text
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return exc.code, parse_json_object(text), text
    except URLError as exc:
        raise RuntimeError(f"{method} {path} failed: {exc}") from exc


def parse_json_object(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"non_json_body": text[:500]}
    return payload if isinstance(payload, dict) else {"non_object_body": payload}


def summarize_body(payload: dict[str, Any], text: str) -> dict[str, Any] | str:
    if payload:
        return {key: payload[key] for key in list(payload)[:5]}
    return text[:200]


if __name__ == "__main__":
    raise SystemExit(main())
