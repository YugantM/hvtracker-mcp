"""Standalone HVTracker MCP server.

The hosted production endpoint is https://hvtracker.net/mcp. This package is
the local stdio distribution path: it exposes the same user-facing tools and
delegates verdicts/searches to HVTracker's public HTTPS API.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import __version__

DEFAULT_BASE_URL = "https://hvtracker.net"
BASE_URL = os.environ.get("HVTRACKER_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
TIMEOUT_SECONDS = float(os.environ.get("HVTRACKER_TIMEOUT_SECONDS", "20"))

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
    """Get the HVTracker trust profile for a tracked AI agent or framework."""
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
    return {
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
        "reasons": verdict.get("reasons") or [],
    }


@mcp.tool(title="Search Agents", annotations=READ_ONLY)
def search_agents(query: str = "", category: str = "", limit: int = 10) -> dict[str, Any]:
    """Search tracked AI agents and frameworks by name, repo, or description."""
    try:
        data = _api_get("/api/v1/agents")
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

