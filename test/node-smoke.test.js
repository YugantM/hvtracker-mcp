import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { createServer, resetBoardCache, searchAgents } from "../bin/hvtracker-mcp.js";

test("registers the expected read-only tools", async () => {
  const server = createServer();
  const tools = server._registeredTools;
  assert.deepEqual(
    Object.keys(tools).sort(),
    [
      "check_agent_trust", "compare_agents", "get_agent_history", "get_leaderboard",
      "list_categories", "scan_stack", "search_agents", "verify_mcp_server"
    ]
  );
  for (const tool of Object.values(tools)) {
    assert.equal(tool.annotations.readOnlyHint, true);
  }
});

test("search_agents handles upstream errors", async () => {
  resetBoardCache();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 503 });
  try {
    const result = await searchAgents("example");
    assert.equal(result.count, 0);
    assert.match(result.error, /503/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("search_agents caches the board and retries after failures", async () => {
  resetBoardCache();
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return {
      ok: true,
      json: async () => ({
        agents: [{ name: "A", repo: "x/a", slug: "a", trust_score: 50, category: "Coding Agents" }]
      })
    };
  };
  try {
    await searchAgents("a");
    await searchAgents("a");
    assert.equal(calls, 1);

    // A failed fetch must not be cached: the next call retries.
    resetBoardCache();
    globalThis.fetch = async () => ({ ok: false, status: 503 });
    const failed = await searchAgents("a");
    assert.match(failed.error, /503/);
    globalThis.fetch = async () => ({ ok: true, json: async () => ({ agents: [] }) });
    const recovered = await searchAgents("a");
    assert.equal(recovered.error, undefined);
  } finally {
    globalThis.fetch = originalFetch;
    resetBoardCache();
  }
});

test("stdio server starts when launched through an npm-style symlink", async () => {
  const tempDir = await mkdtemp(join(tmpdir(), "hvtracker-mcp-bin-"));
  const linkPath = join(tempDir, "hvtracker-mcp");
  await symlink(new URL("../bin/hvtracker-mcp.js", import.meta.url), linkPath);

  const client = new Client({ name: "hvtracker-bin-test", version: "0.0.0" });
  await client.connect(
    new StdioClientTransport({
      command: linkPath,
      stderr: "pipe"
    })
  );
  try {
    const tools = await client.listTools();
    assert.equal(tools.tools.some((tool) => tool.name === "verify_mcp_server"), true);
  } finally {
    await client.close();
  }
});
