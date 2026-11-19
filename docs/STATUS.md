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
- Site switch health history: an HTTP/MCP read uses the documented batch timeline for up to 64 switches from a freshly loaded site inventory. It returns only documented timestamp/score pairs keyed by opaque switch references, with the 24-hour bounds, source, missing rows and device-limit omissions shown. Score scale and live support remain unknown; no live request was made.

The combined operation-registry, full API-matrix and operation-evidence gate plus the switch-health projection, client, route-allowlist, HTTP and MCP checks passed (553 tests) after integration with main. All three local API exports document the batch path, required MAC/time query fields and timeline score schema; the ER7212PC export also includes a matching example. No live controller read was made.
- Site firmware summary: an HTTP/MCP workflow groups the inventory and up to 64 existing current/latest firmware reads by device type, model and version. It reports exact matches, differences, missing versions, inventory disagreement and failed reads without inferring version ordering or upgrade availability. Eleven focused tests and the 235-test registry/matrix/evidence gate passed; no live firmware query or upgrade was made.
- Local offline demo: `python3 tools/demo_mode.py --workflow wifi-site` renders the existing WLAN text report from fixed synthetic data. It requires no credentials and uses an in-process requester; two tests verify deterministic output and block the connector's network request function. It demonstrates the report only, not a live integration.

The #7–10 baseline was checked with 302 offline tests and hosted CI. The #11–12 local gate ran 300 offline tests successfully. The #14 focused HTTP/MCP regression ran 289 tests successfully; the initial broader run exposed only missing TLS fixture pins and a generated evidence ledger that needed refreshing, both corrected before the passing focused run. This paragraph records launch-era validation for #11–14; later follow-on hosted checks are listed below. The synthetic four-SSID token comparison is recorded below.

## Recent follow-on validation

- Function 17, AP quality history: the exact PR head passed both hosted CI events (push run 44399281194 and pull-request run 44399357670). No controller read or scan was made.
- Function 18, site firmware summary: draft PR #8 is based on function 17; its exact-head push and pull-request CI runs passed. Local focused and required gates passed; no live firmware query or upgrade was made.
- Function 19, local offline demo: two focused tests and the 235-test registry/matrix/evidence gate passed. The demo uses synthetic data and makes no network request; no agent-client compatibility is inferred from it.
- Function 20, MCP setup protocol check: the guided check now validates initialize, paginated tools/list, the advertised read-only site tool, one site read and the standard unknown-tool error. Ten focused setup-check tests, 23 MCP tests and the 235-test registry/matrix/evidence gate passed. These are mocked/offline connector tests; this change did not run a live setup check or an agent client. Draft PR and hosted CI status are recorded with the next checkpoint.
- Function 23, PoE budget and schedule summary: implementation is in progress on a fresh branch from current public `main`. It joins a fresh switch inventory with fixed PoE capability, usage, current port, schedule and time-range reads; identities and names are omitted. Watt comparisons use only same-row values documented as watts in ER7212PC. Port measurements are reduced to counts by raw state; schedule timestamps are reduced to presence. The route, fixed-source dispatch, projection and required registry/API/evidence gate pass their current fixture checks; no live controller read or change was made.
- Full Python discovery ran 3,095 tests and found one error: the capability route index did not yet include this new route. That index is now updated and the formerly failing assertion passes in a focused rerun. Full discovery was not repeated after that correction.

The DHCP pool workflow was checked against the range and lease schemas in all three supplied API exports. Focused projector and HTTP/MCP fixture tests pass. This confirms implementation behavior for the documented fields only; live support is unverified.

The DNS diagnosis is a local offline analysis; it does not issue lookups or controller reads. Imported checks are marked unverified, configuration is site-wide context, and available summaries do not link an imported device to a network. Focused fixture tests pass.

For the PoE overview, an eight-switch synthetic input with 192 port rows used 14,875 `o200k_base` tokens as source JSON; the compact result used 2,153 tokens (12,722 fewer; 85.52%). Counts use `js-tiktoken` 1.0.21. This compares serialized fixtures only and excludes tool schemas, prompts, framing, live data and billed agent usage.

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


## Follow-up 24: stack connections

The bounded stack and LLDP summary is available in draft PR #14. It links stack members only through unique current switch-inventory MAC matches. Remote LLDP identity fields remain redacted because the source contract does not define a reliable inventory join. The summary is included in topology output and is available over HTTP and MCP. Offline verification passed 3,104 tests, including the 235-test required registry, API-matrix, and operation-evidence gate. A synthetic 8-stack fixture measured 8,239 source tokens and 1,957 compact-summary tokens (76.25% fewer, o200k_base, js-tiktoken 1.0.21). Stack hardware has not been live-tested.

## Follow-up 25: scheduled restarts

A bounded, read-only reboot-schedule summary is implemented on the isolated work branch. The source exports share the GET path; detailed response fields are available only in the ER7212PC export, while the Hardware Controller and CBC response schemas are generic. The implementation preserves timezone uncertainty and reports schedule configuration without claiming an actual reboot. A synthetic 12-schedule payload measured 796 source JSON tokens and 464 projected tokens (41.71% fewer; js-tiktoken 1.0.21/o200k_base), excluding inventory, prompts and agent framing. Offline focused checks pass; hosted CI is pending.
## 2026-11-19 — Client outage history coverage

The existing HTTP/MCP client outage-timeline read now reports earliest/latest
observed client and client-health timestamps, site event/alert totals and
pagination limits, documented controller/client history settings, and health
timelines for up to eight currently inventoried APs referenced by observed
client events. Empty sources and retention settings do not establish actual
retained-history coverage; overall completeness remains unknown. Offline
fixture tests pass. A synthetic source-response fixture serialized to 9,288
o200k_base tokens across separate client, health, AP, event, alert and retention
payloads; the bundled redacted timeline serialized to 3,546 tokens (61.82%
fewer) with js-tiktoken 1.0.21. This excludes tool schemas, prompts, framing,
inventory reads, live data and billed agent usage. No controller request or
network operation was made.
