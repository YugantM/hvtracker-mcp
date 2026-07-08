#!/usr/bin/env node

import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const VERSION = "0.2.0";
const DEFAULT_BASE_URL = "https://hvtracker.net";
const BASE_URL = (process.env.HVTRACKER_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, "");
const TIMEOUT_MS = Number(process.env.HVTRACKER_TIMEOUT_SECONDS || 20) * 1000;
const READ_ONLY = {
  readOnlyHint: true,
  destructiveHint: false,
  idempotentHint: true,
  openWorldHint: true
};

export async function apiGet(path, params = {}) {
  const url = new URL(path, BASE_URL);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && String(value) !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  const response = await fetch(url, {
    headers: { "user-agent": `hvtracker-mcp/${VERSION}` },
    signal: AbortSignal.timeout(TIMEOUT_MS)
  });
  if (!response.ok) {
    throw new Error(`HVTracker API returned ${response.status} for ${url.toString()}`);
  }
  const payload = await response.json();
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`Unexpected response shape from ${url.toString()}`);
  }
  return payload;
}

function asToolResult(value) {
  return {
    content: [{ type: "text", text: JSON.stringify(value, null, 2) }],
    structuredContent: value
  };
}

function agentProfile(agent) {
  const slug = agent.slug;
  return {
    tracked: true,
    name: agent.name,
    repo: agent.repo,
    trust_score: agent.trust_score,
    evidence_grade: agent.evidence_grade,
    rank: agent.rank,
    category: agent.category,
    has_provenance: agent.has_provenance,
    scorecard_score: agent.scorecard_score,
    mcp_server_support: agent.mcp_server_support?.status,
    profile_url: slug ? `${BASE_URL}/agents/${slug}/` : null
  };
}

export async function verifyMcpServer(server) {
  try {
    return await apiGet("/api/v1/mcp/verify", { server });
  } catch (error) {
    return {
      server,
      tracked: false,
      trusted: false,
      error: error instanceof Error ? error.message : String(error),
      reasons: ["HVTracker could not fetch a verdict right now."]
    };
  }
}

export async function checkAgentTrust(nameOrRepo) {
  const verdict = await verifyMcpServer(nameOrRepo);
  if (!verdict.tracked) {
    return {
      query: nameOrRepo,
      tracked: false,
      trusted: false,
      message: "Not in the HVTracker registry; treat as unverified.",
      submit_url: `${BASE_URL}/submit`,
      verdict
    };
  }

  const slug = verdict.slug;
  const result = {
    query: nameOrRepo,
    tracked: true,
    trusted: verdict.trusted,
    repo: verdict.resolved,
    slug,
    trust_score: verdict.trust_score,
    evidence_grade: verdict.grade,
    confidence: verdict.confidence,
    mcp_server_support: verdict.mcp_server_support,
    tool_permissions: verdict.tool_permissions || [],
    profile_url: slug ? `${BASE_URL}/agents/${slug}/` : null,
    credential_url: slug ? `${BASE_URL}/data/agents/${slug}.json` : null,
    reasons: verdict.reasons || []
  };
  if (slug) {
    try {
      const agent = await apiGet(`/data/agents/${slug}.json`);
      const ext = agent.external_service_dependencies || {};
      const tooling = agent.tool_plugin_surface || {};
      const drift = agent.package_provenance_drift || {};
      result.coverage_grade = agent.coverage_grade ?? null;
      result.capabilities = {
        mcp_status: (agent.mcp_server_support || {}).status || "none",
        provider_count: (ext.providers || []).length,
        requires_api_keys: Boolean(ext.requires_api_keys),
        plugin_system: tooling.plugin_system || "none",
        drift_status: drift.status || "not_applicable"
      };
    } catch {
      // enrichment is best-effort; the verdict stands alone
    }
  }
  return result;
}

export async function compareAgents(a, b) {
  const [ra, rb] = [await checkAgentTrust(a), await checkAgentTrust(b)];
  if (!ra.tracked || !rb.tracked) {
    const missing = [[a, ra], [b, rb]].filter(([, r]) => !r.tracked).map(([q]) => q);
    return {
      a: ra,
      b: rb,
      verdict: `No verdict: ${missing.join(", ")} not in the registry — no independent trust evidence to compare.`,
      compare_url: null
    };
  }
  const sa = ra.trust_score || 0;
  const sb = rb.trust_score || 0;
  let verdict;
  if (sa === sb) {
    verdict = `${ra.repo} and ${rb.repo} tie at HVTrust ${sa} (grades ${ra.evidence_grade}/${rb.evidence_grade}).`;
  } else {
    const [hi, lo] = sa > sb ? [ra, rb] : [rb, ra];
    verdict = `${hi.repo} scores higher on verifiable trust: HVTrust ${hi.trust_score} (grade ${hi.evidence_grade}) vs ${lo.repo} at ${lo.trust_score} (grade ${lo.evidence_grade}).`;
  }
  let compareUrl = null;
  if (ra.slug && rb.slug) {
    const [first, second] = [ra.slug, rb.slug].sort();
    const candidate = `${BASE_URL}/compare/${first}-vs-${second}/`;
    try {
      const probe = await fetch(candidate, {
        method: "HEAD",
        headers: { "user-agent": `hvtracker-mcp/${VERSION}` },
        signal: AbortSignal.timeout(TIMEOUT_MS)
      });
      if (probe.ok) {
        compareUrl = candidate;
      }
    } catch {
      // no published compare page (or unreachable) — omit the link
    }
  }
  return { a: ra, b: rb, verdict, compare_url: compareUrl };
}

export async function searchAgents(query = "", category = "", limit = 10) {
  try {
    const data = await apiGet("/api/v1/agents");
    const ql = String(query || "").trim().toLowerCase();
    const cl = String(category || "").trim().toLowerCase();
    const matches = [];

    for (const agent of data.agents || []) {
      const haystack = ["name", "repo", "description", "slug"]
        .map((key) => String(agent[key] || ""))
        .join(" ")
        .toLowerCase();
      if (ql && !haystack.includes(ql)) {
        continue;
      }
      if (cl && String(agent.category || "").toLowerCase() !== cl) {
        continue;
      }
      matches.push(agentProfile(agent));
    }

    matches.sort((a, b) => {
      if (a.trust_score == null && b.trust_score != null) return 1;
      if (a.trust_score != null && b.trust_score == null) return -1;
      return (b.trust_score || 0) - (a.trust_score || 0);
    });

    const safeLimit = Math.max(1, Math.min(Number.parseInt(limit, 10) || 10, 50));
    return { count: matches.length, results: matches.slice(0, safeLimit) };
  } catch (error) {
    return {
      count: 0,
      results: [],
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

export function createServer() {
  const server = new McpServer({
    name: "hvtracker",
    version: VERSION,
    instructions: "Check trust signals for AI agents and MCP servers."
  });

  server.registerTool(
    "verify_mcp_server",
    {
      title: "Verify MCP Server",
      description: "Pre-connect trust verdict for an MCP server or AI agent.",
      inputSchema: {
        server: z.string().describe("GitHub repo, package, display name, slug, or MCP URL.")
      },
      annotations: READ_ONLY
    },
    async ({ server }) => asToolResult(await verifyMcpServer(server))
  );

  server.registerTool(
    "check_agent_trust",
    {
      title: "Check Agent Trust",
      description: "Get the HVTracker trust profile for a tracked AI agent or framework.",
      inputSchema: {
        name_or_repo: z.string().describe("Agent name, slug, GitHub repo, package, or MCP URL.")
      },
      annotations: READ_ONLY
    },
    async ({ name_or_repo }) => asToolResult(await checkAgentTrust(name_or_repo))
  );

  server.registerTool(
    "compare_agents",
    {
      title: "Compare Agents",
      description: "Compare two tracked AI agents side by side: trust scores, grades, runtime capabilities, and an evidence-based verdict.",
      inputSchema: {
        a: z.string().describe("First agent — name, slug, GitHub repo/URL, or package."),
        b: z.string().describe("Second agent — name, slug, GitHub repo/URL, or package.")
      },
      annotations: READ_ONLY
    },
    async ({ a, b }) => asToolResult(await compareAgents(a, b))
  );

  server.registerTool(
    "search_agents",
    {
      title: "Search Agents",
      description: "Search tracked AI agents and frameworks by name, repo, or description.",
      inputSchema: {
        query: z.string().optional().default(""),
        category: z.string().optional().default(""),
        limit: z.number().int().min(1).max(50).optional().default(10)
      },
      annotations: READ_ONLY
    },
    async ({ query = "", category = "", limit = 10 }) =>
      asToolResult(await searchAgents(query, category, limit))
  );

  return server;
}

export async function runStdio() {
  const server = createServer();
  await server.connect(new StdioServerTransport());
}

function isEntrypoint() {
  if (!process.argv[1]) {
    return false;
  }
  try {
    return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return process.argv[1] === fileURLToPath(import.meta.url);
  }
}

if (isEntrypoint()) {
  runStdio().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
