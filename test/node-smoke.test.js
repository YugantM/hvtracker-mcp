import test from "node:test";
import assert from "node:assert/strict";

import { createServer, searchAgents } from "../bin/hvtracker-mcp.js";

test("registers the expected read-only tools", async () => {
  const server = createServer();
  const tools = server._registeredTools;
  assert.deepEqual(
    Object.keys(tools).sort(),
    ["check_agent_trust", "search_agents", "verify_mcp_server"]
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
