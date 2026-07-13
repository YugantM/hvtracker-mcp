"""Standalone HVTracker MCP server.

The hosted production endpoint is https://hvtracker.net/mcp. This package is
the local stdio distribution path: it exposes the same user-facing tools and
delegates verdicts/searches to HVTracker's public HTTPS API.
"""

from __future__ import annotations

import argparse
import os
import time
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import __version__

DEFAULT_BASE_URL = "https://hvtracker.net"
BASE_URL = os.environ.get("HVTRACKER_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
TIMEOUT_SECONDS = float(os.environ.get("HVTRACKER_TIMEOUT_SECONDS", "20"))
# The full leaderboard is ~1MB and the API serves it with Cache-Control
# max-age=900; re-pulling it per search_agents call is wasted origin load.
BOARD_TTL_SECONDS = float(os.environ.get("HVTRACKER_BOARD_TTL_SECONDS", "900"))

mcp = FastMCP("hvtracker", instructions="Check trust signals for AI agents and MCP servers.")
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


def _api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    response = requests.get(
        url,
        params=params,
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": f"hvtracker-mcp/{__version__}"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected response shape from {url}")
    return payload


_board_cache: dict[str, Any] = {"at": 0.0, "data": None}


def _get_board() -> dict[str, Any]:
    """Return /api/v1/agents, cached for BOARD_TTL_SECONDS. Failures are not
    cached — the next call retries."""
    now = time.monotonic()
    if _board_cache["data"] is not None and now - _board_cache["at"] < BOARD_TTL_SECONDS:
        return _board_cache["data"]
    data = _api_get("/api/v1/agents")
    _board_cache["data"] = data
    _board_cache["at"] = now
    return data


def _api_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    response = requests.post(
        url,
        json=body,
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": f"hvtracker-mcp/{__version__}"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected response shape from {url}")
    return payload


def _agent_profile(agent: dict[str, Any]) -> dict[str, Any]:
    slug = agent.get("slug")
    return {
        "tracked": True,
        "name": agent.get("name"),
        "repo": agent.get("repo"),
        "trust_score": agent.get("trust_score"),
        "evidence_grade": agent.get("evidence_grade"),
        "rank": agent.get("rank"),
        "category": agent.get("category"),
        "has_provenance": agent.get("has_provenance"),
        "scorecard_score": agent.get("scorecard_score"),
        "mcp_server_support": (agent.get("mcp_server_support") or {}).get("status"),
        "profile_url": f"{BASE_URL}/agents/{slug}/" if slug else None,
    }


@mcp.tool(title="Verify MCP Server", annotations=READ_ONLY)
def verify_mcp_server(server: str) -> dict[str, Any]:
    """Pre-connect trust verdict for an MCP server or AI agent.

    Pass a GitHub owner/repo, GitHub URL, npm/PyPI package, display name, slug,
    or MCP server URL. Unknown servers return trusted=false because HVTracker has
    no independent evidence, not because harm is proven.
    """
    try:
        return _api_get("/api/v1/mcp/verify", {"server": server})
    except Exception as exc:
        return {
            "server": server,
            "tracked": False,
            "trusted": False,
            "error": str(exc),
            "reasons": ["HVTracker could not fetch a verdict right now."],
        }


@mcp.tool(title="Check Agent Trust", annotations=READ_ONLY)
def check_agent_trust(name_or_repo: str) -> dict[str, Any]:
    """Get the HVTracker trust profile for a tracked AI agent or framework,
    including its runtime capability surface and the URL of its Ed25519-signed
    trust credential (verifiable offline)."""
    verdict = verify_mcp_server(name_or_repo)
    if not verdict.get("tracked"):
        return {
            "query": name_or_repo,
            "tracked": False,
            "trusted": False,
            "message": "Not in the HVTracker registry; treat as unverified.",
            "submit_url": f"{BASE_URL}/submit",
            "verdict": verdict,
        }
    slug = verdict.get("slug")
    result = {
        "query": name_or_repo,
        "tracked": True,
        "trusted": verdict.get("trusted"),
        "repo": verdict.get("resolved"),
        "slug": slug,
        "trust_score": verdict.get("trust_score"),
        "evidence_grade": verdict.get("grade"),
        "confidence": verdict.get("confidence"),
        "mcp_server_support": verdict.get("mcp_server_support"),
        "tool_permissions": verdict.get("tool_permissions") or [],
        "profile_url": f"{BASE_URL}/agents/{slug}/" if slug else None,
        "credential_url": f"{BASE_URL}/data/agents/{slug}.json" if slug else None,
        "reasons": verdict.get("reasons") or [],
    }
    if slug:
        try:
            agent = _api_get(f"/data/agents/{slug}.json")
            ext = agent.get("external_service_dependencies") or {}
            tooling = agent.get("tool_plugin_surface") or {}
            drift = agent.get("package_provenance_drift") or {}
            result["coverage_grade"] = agent.get("coverage_grade")
            result["capabilities"] = {
                "mcp_status": (agent.get("mcp_server_support") or {}).get("status") or "none",
                "provider_count": len(ext.get("providers") or []),
                "requires_api_keys": bool(ext.get("requires_api_keys")),
                "plugin_system": tooling.get("plugin_system") or "none",
                "drift_status": drift.get("status") or "not_applicable",
            }
        except Exception:  # enrichment is best-effort; the verdict stands alone
            pass
    return result


@mcp.tool(title="Compare Agents", annotations=READ_ONLY)
def compare_agents(a: str, b: str) -> dict[str, Any]:
    """Compare two tracked AI agents side by side: both trust profiles, an
    evidence-based one-line verdict, and the HVTracker compare-page URL when
    one is published."""
    ra, rb = check_agent_trust(a), check_agent_trust(b)
    if not ra.get("tracked") or not rb.get("tracked"):
        missing = [q for q, r in ((a, ra), (b, rb)) if not r.get("tracked")]
        verdict = (
            f"No verdict: {', '.join(missing)} not in the registry — "
            "no independent trust evidence to compare."
        )
        return {"a": ra, "b": rb, "verdict": verdict, "compare_url": None}

    sa, sb = ra.get("trust_score") or 0, rb.get("trust_score") or 0
    na, nb = ra.get("repo") or a, rb.get("repo") or b
    if sa == sb:
        verdict = (
            f"{na} and {nb} tie at HVTrust {sa} "
            f"(grades {ra.get('evidence_grade')}/{rb.get('evidence_grade')})."
        )
    else:
        hi, lo = (ra, rb) if sa > sb else (rb, ra)
        verdict = (
            f"{hi.get('repo')} scores higher on verifiable trust: HVTrust "
            f"{hi.get('trust_score')} (grade {hi.get('evidence_grade')}) vs "
            f"{lo.get('repo')} at {lo.get('trust_score')} (grade {lo.get('evidence_grade')})."
        )

    compare_url = None
    if ra.get("slug") and rb.get("slug"):
        first, second = sorted([ra["slug"], rb["slug"]])
        candidate = f"{BASE_URL}/compare/{first}-vs-{second}/"
        try:
            probe = requests.head(
                candidate,
                timeout=TIMEOUT_SECONDS,
                headers={"User-Agent": f"hvtracker-mcp/{__version__}"},
                allow_redirects=True,
            )
            if probe.status_code == 200:
                compare_url = candidate
        except Exception:
            pass
    return {"a": ra, "b": rb, "verdict": verdict, "compare_url": compare_url}


@mcp.tool(title="Search Agents", annotations=READ_ONLY)
def search_agents(query: str = "", category: str = "", limit: int = 10) -> dict[str, Any]:
    """Search tracked AI agents and frameworks by name, repo, or description."""
    try:
        data = _get_board()
    except Exception as exc:
        return {"count": 0, "results": [], "error": str(exc)}

    ql = (query or "").strip().lower()
    cl = (category or "").strip().lower()
    matches = []
    for agent in data.get("agents", []):
        haystack = " ".join(
            str(agent.get(key) or "") for key in ("name", "repo", "description", "slug")
        ).lower()
        if ql and ql not in haystack:
            continue
        if cl and (agent.get("category") or "").lower() != cl:
            continue
        matches.append(_agent_profile(agent))

    matches.sort(key=lambda row: (row["trust_score"] is None, -(row["trust_score"] or 0)))
    limit = max(1, min(int(limit or 10), 50))
    return {"count": len(matches), "results": matches[:limit]}


@mcp.tool(title="Scan Stack", annotations=READ_ONLY)
def scan_stack(input: str) -> dict[str, Any]:
    """Bulk pre-connect trust check for a whole dependency set. Paste a
    requirements.txt, package.json, MCP client config, or a newline/comma list;
    each item is returned with a trust verdict plus a stack summary."""
    try:
        return _api_post("/api/v1/scan", {"input": (input or "")[:20000]})
    except Exception as exc:
        return {"summary": {"total": 0}, "results": [], "error": str(exc)}


@mcp.tool(title="List Categories", annotations=READ_ONLY)
def list_categories() -> dict[str, Any]:
    """List HVTracker categories with agent counts (most-populated first), so you
    can then pull a category's leaderboard."""
    try:
        data = _get_board()
    except Exception as exc:
        return {"count": 0, "categories": [], "error": str(exc)}
    counts: dict[str, int] = {}
    for agent in data.get("agents", []):
        cat = agent.get("category")
        if cat:
            counts[cat] = counts.get(cat, 0) + 1
    cats = [
        {"category": c, "count": n, "leaderboard_hint": f'get_leaderboard(category="{c}")'}
        for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {"count": len(cats), "categories": cats}


@mcp.tool(title="Get Leaderboard", annotations=READ_ONLY)
def get_leaderboard(category: str = "", limit: int = 10) -> dict[str, Any]:
    """Top tracked AI agents and MCP servers by HVTrust score, optionally scoped
    to one category (exact name from list_categories)."""
    try:
        data = _get_board()
    except Exception as exc:
        return {"category": category or None, "count": 0, "results": [], "error": str(exc)}
    cl = (category or "").strip().lower()
    rows = [
        _agent_profile(agent)
        for agent in data.get("agents", [])
        if not cl or (agent.get("category") or "").lower() == cl
    ]
    rows.sort(key=lambda row: (row["trust_score"] is None, -(row["trust_score"] or 0)))
    limit = max(1, min(int(limit or 10), 50))
    return {"category": category or None, "count": len(rows), "results": rows[:limit]}


@mcp.tool(title="Get Agent History", annotations=READ_ONLY)
def get_agent_history(name_or_repo: str) -> dict[str, Any]:
    """90-day trust-score, grade, and rank history for one tracked agent — is it
    improving or declining? Accepts the same identifiers as check_agent_trust."""
    verdict = verify_mcp_server(name_or_repo)
    slug = verdict.get("slug")
    if not verdict.get("tracked") or not slug:
        return {"tracked": False, "query": name_or_repo,
                "message": "Not in the HVTracker registry; no history to show."}
    try:
        hist = _api_get(f"/api/v1/agents/{slug}/history")
    except Exception as exc:
        return {"tracked": True, "slug": slug, "history": [], "error": str(exc)}
    hist["tracked"] = True
    return hist


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the HVTracker MCP server.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=os.environ.get("HVTRACKER_MCP_TRANSPORT", "stdio"),
        help="Transport to run. Use stdio for local MCP clients.",
    )
    args = parser.parse_args(argv)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()

