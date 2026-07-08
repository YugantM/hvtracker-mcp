import asyncio

from hvtracker_mcp import server


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


def test_tools_have_read_only_annotations():
    tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}
    assert set(tools) == {"verify_mcp_server", "check_agent_trust", "search_agents", "compare_agents"}
    assert tools["verify_mcp_server"].annotations.readOnlyHint is True



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
