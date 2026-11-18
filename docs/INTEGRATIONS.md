# HTTP and MCP integration

The connector exposes a fixed versioned HTTP API and a stateless MCP Streamable HTTP endpoint at `POST /mcp`. Both use the connector caller token as a Bearer credential. MCP advertises fixed reads and bounded diagnostic workflows; it does not accept arbitrary controller URLs or expose disabled scan starts.

Use the [read-only Compose example](../compose.read-only.example.yaml) for a local setup. It publishes the service on host loopback. An agent running on another host needs a separately secured private access path; do not expose the connector publicly by default.

The local [WLAN diagnostic CLI](../README.md#local-wlan-summary) and MCP workflows combine selected existing measurements and controller data. They do not start scans, speed tests, probes or network changes. Output remains operation-specific and may be partial when a controller response omits required data.

## Client evidence

| Client | Setup | End-to-end evidence |
| --- | --- | --- |
| Codex | MCP Streamable HTTP configuration is documented. | Passed on 2026-11-13: a real handshake and calls to `omada_sites`, `omada_devices` and `omada_clients`. |
| Claude Code | Setup example is documented. | Not tested end to end; the CLI was unavailable in the test environment. |
| Other MCP clients | Use the documented endpoint and authentication contract. | Not tested end to end. |

The Codex run used a temporary loopback-only tunnel to the connector. A separate verifier parsed the actual `tools/call` results and checked `isError=false`, valid connector JSON, the expected resource and matching item counts: one site, four devices and 31 clients. No names, references, addresses or raw rows were retained. Temporary client configuration, tunnel, container and credential files were removed. This proves those calls for that setup only.

The 18 MCP and 65 HTTP tests use a fake controller. They are protocol/connector fixture checks, not real agent-client or live-controller tests. See [MCP setup](MCP.md), [controller compatibility](CONTROLLER_COMPATIBILITY.md) and [current status](STATUS.md).
