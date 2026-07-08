import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { createServer, searchAgents } from "../bin/hvtracker-mcp.js";

test("registers the expected read-only tools", async () => {
  const server = createServer();
  const tools = server._registeredTools;
  assert.deepEqual(
    Object.keys(tools).sort(),
    ["check_agent_trust", "compare_agents", "search_agents", "verify_mcp_server"]
  );
  assert.equal(tools.verify_mcp_server.annotations.readOnlyHint, true);
});

test("search_agents handles upstream errors", async () => {
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
