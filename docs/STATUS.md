# Connector status and evidence

This page summarizes the connector's current capabilities and the evidence behind them. Catalog entries and offline tests alone do not establish live support; operation-specific limits are recorded in the [capability evidence](CAPABILITIES.md), [roadmap](ROADMAP.md), and [operation evidence index](OPERATION_EVIDENCE.json).

## Follow-on read workflows

The current local development branch also contains these read-only workflows:

- Setup check: separates configuration, controller TLS, authentication, site-inventory permission and MCP checks. MCP verifies initialization, paginated discovery, the read-only advertisement, one site-inventory call and the unknown-tool error path. Fixture tests pass; no live setup check was run.
- Diagnostic capability report: available over authenticated HTTP and MCP, reusing existing evidence without probing routes.
- Configuration snapshots: captures selected radio, SSID, LAN and DNS projection fields in versioned owner-only files; comparisons mark incomplete data as not comparable. No live snapshot was captured.
- WLAN network mapping: available over authenticated HTTP and MCP; checks up to 64 SSIDs, 32 matched networks and four gateway records. DNS-to-WLAN and gateway-to-network links remain unknown when the source does not expose them. No live controller workflow was run.
- Device measurement import: accepts a bounded v1 CSV/JSON format with timezone-qualified timestamps and field-specific declared source kinds. Identifiers and addresses are omitted. Fixture tests pass; no device export was provided or used.
- Device/Omada comparison: aligns imported observations with saved client timelines and passive WLAN sessions using an explicit window and tolerance. It reports freshness, coverage and disagreements without interpreting numeric event codes or inferring causes. Fixture tests pass; no controller or network was queried.
- Gateway WAN incident window: bundles current WAN status, same-window gateway health details and timeline, and saved speed-test counts into one HTTP/MCP report. Current and historical data are separate; health values are time-filtered; incident counts and speed-test time values are not assigned to the timeline without source definitions. Local fixture tests pass; no controller or live MCP request was made.
- Load-balancing status: remains open. The three source exports expose only a generic object for `getLoadBalanceWeightStatus`; the ER7212PC example is empty and no contract defines status, mode, or participating-line fields. The connector does not guess these labels or call this endpoint from the incident report.
- DHCP pool utilization: reads the documented pool ranges and available-address count for up to 64 networks, plus the complete paged site DHCP-user list. It returns capacity/availability and documented dynamic/static binding counts by opaque network reference; the source does not associate each lease with a configured range, so occupancy is not inferred. Fixture tests pass; no controller request was made.
- DNS incident diagnosis: an offline CLI combines imported, source-labeled device observations with optional redacted site DNS settings and WLAN/network summary files. It separates failures, missing data and cross-source disagreement while leaving cause and device-to-network mapping unknown. Fixture tests pass; no DNS probe or controller request was made.
- AP quality window: an HTTP/MCP read combines a common 24-hour health-score and retry/drop window with current per-band radio settings for up to 32 APs. A local CLI can line up a saved passive walk session by opaque AP reference. Missing rows, unspecified scales, the lack of retry/drop band mapping and the session file's missing site binding are explicit. Fixture tests pass; no live controller request or scan was made.
- Site firmware summary: an HTTP/MCP workflow groups the inventory and up to 64 existing current/latest firmware reads by device type, model and version. It reports exact matches, differences, missing versions, inventory disagreement and failed reads without inferring version ordering or upgrade availability. Eleven focused tests and the 235-test registry/matrix/evidence gate passed; no live firmware query or upgrade was made.
- Local offline demo: `python3 tools/demo_mode.py --workflow wifi-site` renders the existing WLAN text report from fixed synthetic data. It requires no credentials and uses an in-process requester; two tests verify deterministic output and block the connector's network request function. It demonstrates the report only, not a live integration.

The #7–10 baseline was checked with 302 offline tests and hosted CI. The #11–12 local gate ran 300 offline tests successfully. The #14 focused HTTP/MCP regression ran 289 tests successfully; the initial broader run exposed only missing TLS fixture pins and a generated evidence ledger that needed refreshing, both corrected before the passing focused run. This paragraph records launch-era validation for #11–14; later follow-on hosted checks are listed below. The synthetic four-SSID token comparison is recorded below.

## Recent follow-on validation

- Function 17, AP quality history: the exact PR head passed both hosted CI events (push run 44399281194 and pull-request run 44399357670). No controller read or scan was made.
- Function 18, site firmware summary: draft PR #8 is based on function 17; its exact-head push and pull-request CI runs passed. Local focused and required gates passed; no live firmware query or upgrade was made.
- Function 19, local offline demo: two focused tests and the 235-test registry/matrix/evidence gate passed. The demo uses synthetic data and makes no network request; no agent-client compatibility is inferred from it.
- Function 20, MCP setup protocol check: the guided check now validates initialize, paginated tools/list, the advertised read-only site tool, one site read and the standard unknown-tool error. Ten focused setup-check tests, 23 MCP tests and the 235-test registry/matrix/evidence gate passed. These are mocked/offline connector tests; this change did not run a live setup check or an agent client. Draft PR and hosted CI status are recorded with the next checkpoint.

The DHCP pool workflow was checked against the range and lease schemas in all three supplied API exports. Focused projector and HTTP/MCP fixture tests pass. This confirms implementation behavior for the documented fields only; live support is unverified.

The DNS diagnosis is a local offline analysis; it does not issue lookups or controller reads. Imported checks are marked unverified, configuration is site-wide context, and available summaries do not link an imported device to a network. Focused fixture tests pass.

Site switch-port anomaly summary is implemented as a read-only HTTP/MCP workflow. It joins the fresh inventory with the existing paginated port overview and counter feeds, caps coverage at 32 switches and emits nonzero error counters as review signals without treating them as diagnoses. Raw port status codes remain uninterpreted. The ER7212PC export documents the status and cumulative error fields; Hardware Controller and CBC Standard use a generic response schema for these feeds, so field-level compatibility there remains unverified. Drop counts are not present in the documented per-port counter schema; no trend is calculated. Eleven focused projection, client, HTTP and MCP checks passed, as did all six operation-evidence tests after regenerating the static references. The combined 553-test run initially found only the stale evidence reference; registry, API-matrix and all other tests in that run passed. A synthetic eight-switch/192-port comparison measured 39,858 source JSON tokens and 6,138 summary tokens (84.60% fewer; serialized fixture payloads only). No live read was made.

A synthetic 48-sample measurement file used 3,370 `o200k_base` tokens as JSON; the default aggregate diagnosis used 339 tokens (3,031 fewer, 89.94%). This measures the file and report payloads with `js-tiktoken` 1.0.21 and excludes prompts, command framing, optional context files and billed agent usage. Per-sample detail is available by an explicit flag and is larger.

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
