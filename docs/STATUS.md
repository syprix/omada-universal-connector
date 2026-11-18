# Connector status and evidence

This page summarizes the connector's current capabilities and the evidence behind them. Catalog entries and offline tests alone do not establish live support; operation-specific limits are recorded in the [capability evidence](CAPABILITIES.md), [roadmap](ROADMAP.md), and [operation evidence index](OPERATION_EVIDENCE.json).

## Follow-on read workflows

The current local development branch also contains these read-only workflows:

- Setup check: separates configuration, controller TLS, authentication, site-inventory permission and MCP initialization checks. Fixture tests pass; no live setup check was run.
- Diagnostic capability report: available over authenticated HTTP and MCP, reusing existing evidence without probing routes.
- Configuration snapshots: captures selected radio, SSID, LAN and DNS projection fields in versioned owner-only files; comparisons mark incomplete data as not comparable. No live snapshot was captured.
- WLAN network mapping: available over authenticated HTTP and MCP; checks up to 64 SSIDs, 32 matched networks and four gateway records. DNS-to-WLAN and gateway-to-network links remain unknown when the source does not expose them. No live controller workflow was run.

The final local check for this code and its API-contract evidence ran 302 offline tests successfully. The synthetic four-SSID token comparison is recorded below. There is no hosted CI result or live controller evidence for these follow-on workflows.

## Core functions

Fourteen of the fifteen agreed core functions meet their documented acceptance scope. The remaining function covers active diagnostics.

- A single-port switch cable-test workflow has a bounded, journaled and separately approved implementation with offline tests. A compatible switch was not available for its hardware check.
- Other active scan and measurement starts remain disabled where the available API contract does not document reliable termination, bounded duration, or result freshness and correlation.
- Site-wide WLAN optimization is excluded from the active-test path because it can deploy radio changes without a target-bound preview or run identifier.

## Live evidence

The recorded end-to-end controller evidence comes from one OC200 running Omada Controller 6.3.0.45. Selected read operations and a Codex MCP client flow were exercised there. This does not establish compatibility with other controller families, releases, device models, or firmware; operation-specific unknowns remain in the capability evidence.

One supported 5 GHz delivery setting on one access point was changed from `true` to `false` through the guarded HTTP preview and approval flow, then restored through a separate approved plan. Both applies returned verified readback. Independent controller, HTTP, and MCP reads confirmed the original supported state after restoration. This verifies that path only.

## Agent integrations

| Client | Evidence |
| --- | --- |
| Codex | MCP handshake and calls to `omada_sites`, `omada_devices`, and `omada_clients` passed in a temporary loopback-only setup. |
| Claude Code | Setup notes exist; end-to-end client integration has not been tested. |
| Other MCP clients | Not tested end to end. |

See [integration details](INTEGRATIONS.md) for the scope and limits of the Codex check.

## Token measurements

A live MCP network-overview workflow serialized to 1,630 `o200k_base` tokens. Twelve separate live MCP reads for the same sections serialized to 6,416 tokens, a reduction of 4,786 tokens (74.59%). This excludes the shared site lookup and tool schemas. It measures serialized calls, not a model's full context or billed usage.

## Verification

The application, tests, and tooling prepared for the 2026-11-18 launch are byte-identical to the source that passed 2,980 offline tests and the runtime smoke check. Documentation updates do not alter that tested code. These are offline checks, not live-controller evidence.

The exact source built with Docker 29.8.2 using `docker build --network=none`. A read-only container with networking disabled and no controller credentials reached healthy status; the temporary container, image, and source directory were removed.

The Compose configuration was checked with Docker Compose 5.8.0. The base configuration confirmed loopback-only binding, read-only secret mounts, disabled writes, and no Docker socket. An isolated smoke configuration built and ran with networking disabled and no published ports; its read-only container reached healthy status using dummy secrets and a synthetic controller address. Temporary containers, images, files, and the CLI were removed. No controller request was made.

A GitHub account restriction prevented hosted CI from starting; no hosted test result is available. The offline checks above do not represent a hosted CI result.

## Compatibility

The three supplied OpenAPI exports are reference material and are not redistributed. Compatibility depends on controller release, API permissions, device model, and firmware.
