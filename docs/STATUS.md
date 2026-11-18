# Connector status and evidence

This page summarizes the connector's current capabilities and the evidence behind them. Catalog entries and offline tests alone do not establish live support; operation-specific limits are recorded in the [capability evidence](CAPABILITIES.md), [roadmap](ROADMAP.md), and [operation evidence index](OPERATION_EVIDENCE.json).

## Follow-on read workflows

The current local development branch also contains these read-only workflows:

- Setup check: separates configuration, controller TLS, authentication, site-inventory permission and MCP initialization checks. Fixture tests pass; no live setup check was run.
- Diagnostic capability report: available over authenticated HTTP and MCP, reusing existing evidence without probing routes.
- Configuration snapshots: captures selected radio, SSID, LAN and DNS projection fields in versioned owner-only files; comparisons mark incomplete data as not comparable. No live snapshot was captured.
- WLAN network mapping: available over authenticated HTTP and MCP; checks up to 64 SSIDs, 32 matched networks and four gateway records. DNS-to-WLAN and gateway-to-network links remain unknown when the source does not expose them. No live controller workflow was run.
- Device measurement import: accepts a bounded v1 CSV/JSON format with timezone-qualified timestamps and field-specific declared source kinds. Identifiers and addresses are omitted. Fixture tests pass; no device export was provided or used.
- Device/Omada comparison: aligns imported observations with saved client timelines and passive WLAN sessions using an explicit window and tolerance. It reports freshness, coverage and disagreements without interpreting numeric event codes or inferring causes. Fixture tests pass; no controller or network was queried.
- Gateway WAN incident window: bundles current WAN status, same-window gateway health details and timeline, and saved speed-test counts into one HTTP/MCP report. Current and historical data are separate; health values are time-filtered; incident counts and speed-test time values are not assigned to the timeline without source definitions. Local fixture tests pass; no controller or live MCP request was made.
- Load-balancing status: remains open. The three source exports expose only a generic object for `getLoadBalanceWeightStatus`; the ER7212PC example is empty and no contract defines status, mode, or participating-line fields. The connector does not guess these labels or call this endpoint from the incident report.
- DHCP pool utilization: reads the documented pool ranges and available-address count for up to 64 networks, plus the complete paged site DHCP-user list. It returns capacity/availability and documented dynamic/static binding counts by opaque network reference; the source does not associate each lease with a configured range, so occupancy is not inferred. Fixture tests pass; no controller request was made.

The #7–10 baseline was checked with 302 offline tests and hosted CI. The #11–12 local gate ran 300 offline tests successfully. The #14 focused HTTP/MCP regression ran 289 tests successfully; the initial broader run exposed only missing TLS fixture pins and a generated evidence ledger that needed refreshing, both corrected before the passing focused run. The operation-registry and full API-matrix checks in the broader run completed; the evidence check passed after regeneration. No hosted CI result is available yet for the updated branch, and no live controller check was run for #11–14. The synthetic four-SSID token comparison is recorded below.

The DHCP pool workflow was checked against the range and lease schemas in all three supplied API exports. Focused projector and HTTP/MCP fixture tests pass. This confirms implementation behavior for the documented fields only; live support is unverified.

For #14, four synthetic existing-read request/response pairs serialized to 625 `o200k_base` tokens. One bundled MCP request and its compact report serialized to 590 tokens: 35 fewer (5.60%). This fixture comparison excludes tool schemas, inventory reads, prompts, framing and billed agent context; it is not a live-agent token measurement.

For DHCP utilization, eight synthetic network summaries and 80 lease rows serialized to 3,050 `o200k_base` tokens across separate existing reads. One bundled report serialized to 1,252 tokens: 1,798 fewer (58.95%). This compares fixture JSON payloads only and excludes tool schemas, prompts, framing, live inventories and billed agent context; it is not a live-agent token measurement.

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
