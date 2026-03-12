from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import quote_plus
from urllib import request as urlrequest
from urllib.error import HTTPError


@dataclass
class VikiClient:
    base_url: str = "http://127.0.0.1:8787"
    timeout: int = 1800

    def _call(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(self.base_url.rstrip("/") + path, data=data, headers=headers, method=method)
        try:
            with urlrequest.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            try:
                payload = json.loads(body) if body else {}
            except Exception:
                payload = {"raw": body}
            raise RuntimeError(json.dumps({"status": exc.code, "body": payload})) from exc

    def protocol(self) -> Dict[str, Any]:
        return self._call("GET", "/protocol")

    def run(self, prompt: str, mode: str = "standard", workspace: str | None = None) -> Dict[str, Any]:
        return self._call("POST", "/runs", {"prompt": prompt, "mode": mode, "workspace": workspace})

    def get_run(self, session_id: str) -> Dict[str, Any]:
        return self._call("GET", f"/runs/{session_id}")

    def list_runs(self, limit: int = 20) -> Dict[str, Any]:
        return self._call("GET", f"/runs?limit={limit}")

    def run_events(self, session_id: str) -> Dict[str, Any]:
        return self._call("GET", f"/runs/{session_id}/events")

    def repo_profile(self) -> Dict[str, Any]:
        return self._call("GET", "/repo/profile")

    def repo_search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        return self._call("GET", f"/repo/search?q={quote_plus(query)}&limit={limit}")

    def repo_context(self, query: str = "repo overview", limit: int = 12) -> Dict[str, Any]:
        return self._call("GET", f"/repo/context?q={quote_plus(query)}&limit={limit}")

    def repo_symbols(self, query: str = "", limit: int = 20) -> Dict[str, Any]:
        return self._call("GET", f"/repo/symbols?q={quote_plus(query)}&limit={limit}")

    def repo_impact(self, *paths: str, limit: int = 20) -> Dict[str, Any]:
        suffix = "&".join(f"path={quote_plus(path)}" for path in paths)
        route = f"/repo/impact?limit={limit}"
        if suffix:
            route += "&" + suffix
        return self._call("GET", route)

    def list_approvals(self, status: str = "pending") -> Dict[str, Any]:
        return self._call("GET", f"/approvals?status={status}")

    def decide_approval(self, approval_id: int, decision: str, reviewer: str = "sdk-user") -> Dict[str, Any]:
        return self._call("POST", f"/approvals/{approval_id}", {"decision": decision, "reviewer": reviewer})
