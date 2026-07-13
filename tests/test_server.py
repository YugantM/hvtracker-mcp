import asyncio

import pytest

from hvtracker_mcp import server


@pytest.fixture(autouse=True)
def _fresh_board_cache():
    server._board_cache.update({"at": 0.0, "data": None})


def test_verify_mcp_server_delegates_to_api(monkeypatch):
    def fake_get(path, params=None):
        assert path == "/api/v1/mcp/verify"
        assert params == {"server": "langchain-ai/langgraph"}
        return {"tracked": True, "trusted": True, "resolved": "langchain-ai/langgraph"}

    monkeypatch.setattr(server, "_api_get", fake_get)
    assert server.verify_mcp_server("langchain-ai/langgraph")["trusted"] is True


def test_check_agent_trust_maps_verdict(monkeypatch):
    monkeypatch.setattr(
        server,
        "verify_mcp_server",
        lambda query: {
            "tracked": True,
            "trusted": True,
            "resolved": "langchain-ai/langgraph",
            "slug": "langgraph",
            "trust_score": 92.8,
            "grade": "A",
            "confidence": 1.0,
            "mcp_server_support": "none",
            "tool_permissions": ["code"],
            "reasons": ["Build provenance present."],
        },
    )
    result = server.check_agent_trust("LangGraph")
    assert result["repo"] == "langchain-ai/langgraph"
    assert result["profile_url"].endswith("/agents/langgraph/")


def test_search_agents_filters_and_sorts(monkeypatch):
    monkeypatch.setattr(
        server,
        "_api_get",
        lambda path: {
            "agents": [
                {
                    "name": "Lower",
                    "repo": "example/lower",
                    "slug": "lower",
                    "trust_score": 40,
                    "evidence_grade": "C",
                    "category": "Coding Agents",
                    "description": "agent",
                },
                {
                    "name": "Higher",
                    "repo": "example/higher",
                    "slug": "higher",
                    "trust_score": 90,
                    "evidence_grade": "A",
                    "category": "Coding Agents",
                    "description": "agent",
                },
            ]
        },
    )
    result = server.search_agents(query="example", category="Coding Agents")
    assert result["count"] == 2
    assert [row["name"] for row in result["results"]] == ["Higher", "Lower"]


def test_search_agents_caches_the_board(monkeypatch):
    calls = {"n": 0}

    def fake_get(path):
        calls["n"] += 1
        return {"agents": [{"name": "A", "repo": "x/a", "slug": "a",
                            "trust_score": 50, "category": "Coding Agents"}]}

    monkeypatch.setattr(server, "_api_get", fake_get)
    server.search_agents(query="a")
    server.search_agents(query="a")
    assert calls["n"] == 1

    server._board_cache["at"] -= server.BOARD_TTL_SECONDS + 1
    server.search_agents(query="a")
    assert calls["n"] == 2


def test_search_agents_does_not_cache_failures(monkeypatch):
    state = {"fail": True}

    def fake_get(path):
        if state["fail"]:
            raise RuntimeError("upstream down")
        return {"agents": []}

    monkeypatch.setattr(server, "_api_get", fake_get)
    assert "error" in server.search_agents(query="a")
    state["fail"] = False
    assert "error" not in server.search_agents(query="a")


def test_tools_have_read_only_annotations():
    tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}
    assert set(tools) == {
        "verify_mcp_server", "check_agent_trust", "search_agents", "compare_agents",
        "scan_stack", "list_categories", "get_leaderboard", "get_agent_history",
    }
    for tool in tools.values():
        assert tool.annotations.readOnlyHint is True


def test_scan_stack_delegates_to_scan_api(monkeypatch):
    seen = {}

    def fake_post(path, body):
        seen["path"], seen["body"] = path, body
        return {"summary": {"total": 2, "tracked": 1}, "results": []}

    monkeypatch.setattr(server, "_api_post", fake_post)
    out = server.scan_stack("langgraph\nunknown-pkg")
    assert seen["path"] == "/api/v1/scan"
    assert seen["body"]["input"].startswith("langgraph")
    assert out["summary"]["total"] == 2


def test_list_categories_counts(monkeypatch):
    monkeypatch.setattr(server, "_api_get", lambda path: {"agents": [
        {"category": "Coding Agents"}, {"category": "Coding Agents"},
        {"category": "MCP Servers"},
    ]})
    out = server.list_categories()
    cats = {c["category"]: c["count"] for c in out["categories"]}
    assert cats == {"Coding Agents": 2, "MCP Servers": 1}
    assert out["categories"][0]["category"] == "Coding Agents"  # most first


def test_get_leaderboard_filters_and_sorts(monkeypatch):
    monkeypatch.setattr(server, "_api_get", lambda path: {"agents": [
        {"name": "Lo", "repo": "x/lo", "slug": "lo", "trust_score": 40, "category": "Coding Agents"},
        {"name": "Hi", "repo": "x/hi", "slug": "hi", "trust_score": 90, "category": "Coding Agents"},
        {"name": "Other", "repo": "x/o", "slug": "o", "trust_score": 99, "category": "MCP Servers"},
    ]})
    out = server.get_leaderboard(category="Coding Agents")
    assert out["category"] == "Coding Agents"
    assert [r["name"] for r in out["results"]] == ["Hi", "Lo"]


def test_get_agent_history_delegates(monkeypatch):
    monkeypatch.setattr(server, "verify_mcp_server",
                        lambda q: {"tracked": True, "slug": "langgraph"})
    monkeypatch.setattr(server, "_api_get",
                        lambda path: {"count": 3, "history": [{"date": "2026-07-13"}]})
    out = server.get_agent_history("LangGraph")
    assert out["tracked"] is True
    assert out["count"] == 3


def test_get_agent_history_untracked_is_graceful(monkeypatch):
    monkeypatch.setattr(server, "verify_mcp_server", lambda q: {"tracked": False})
    out = server.get_agent_history("ghost")
    assert out["tracked"] is False
    assert "message" in out



def test_compare_agents_verdict(monkeypatch):
    profiles = {
        "LangGraph": {"tracked": True, "repo": "langchain-ai/langgraph",
                      "slug": "langgraph", "trust_score": 92.8, "evidence_grade": "A"},
        "AIPass": {"tracked": True, "repo": "AIOSAI/AIPass",
                   "slug": "aipass", "trust_score": 70.0, "evidence_grade": "C"},
    }
    monkeypatch.setattr(server, "check_agent_trust", lambda q: dict(profiles[q]))

    class _Probe:
        status_code = 404

    monkeypatch.setattr(server.requests, "head", lambda *a, **k: _Probe())
    result = server.compare_agents("LangGraph", "AIPass")
    assert "langchain-ai/langgraph scores higher" in result["verdict"]
    assert result["compare_url"] is None


def test_compare_agents_untracked_is_graceful(monkeypatch):
    monkeypatch.setattr(
        server, "check_agent_trust",
        lambda q: {"tracked": q == "LangGraph", "repo": q, "slug": q.lower(),
                   "trust_score": 90.0, "evidence_grade": "A"},
    )
    result = server.compare_agents("LangGraph", "ghost-agent")
    assert result["verdict"].startswith("No verdict")
    assert result["compare_url"] is None
