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
- Function 27, client health detail v2: implemented as a bounded 24-hour read, bound to a fresh site client inventory reference, and exposed over authenticated HTTP and MCP. The projection keeps documented numeric scores without assuming their scale, numeric series aggregates, and incident counts; it removes incident identifiers, MACs, free-text maps, and nested object details, and marks unknown or capped data partial. The source operation and response schema exist in Hardware Controller 6.3 and CBC 6.3 exports; the supplied ER7212PC export has no v2 operation. The focused projector, time-window, fixed-path, inventory-binding, HTTP/MCP, and registry tests passed; the required registry/matrix/evidence gate passed 235 tests. A synthetic serialized source response used 625 `o200k_base` tokens; the projected response used 457 (168 fewer, 26.88%) with js-tiktoken 1.0.21. This counts response JSON only, not the inventory read, schemas, prompts, framing, live data, or billed agent usage. No controller request or live agent-client check was made.


- Function 17, AP quality history: the exact PR head passed both hosted CI events (push run 44399281194 and pull-request run 44399357670). No controller read or scan was made.
- Function 18, site firmware summary: draft PR #8 is based on function 17; its exact-head push and pull-request CI runs passed. Local focused and required gates passed; no live firmware query or upgrade was made.
- Function 19, local offline demo: two focused tests and the 235-test registry/matrix/evidence gate passed. The demo uses synthetic data and makes no network request; no agent-client compatibility is inferred from it.
- Function 20, MCP setup protocol check: the guided check now validates initialize, paginated tools/list, the advertised read-only site tool, one site read and the standard unknown-tool error. Ten focused setup-check tests, 23 MCP tests and the 235-test registry/matrix/evidence gate passed. These are mocked/offline connector tests; this change did not run a live setup check or an agent client. Draft PR and hosted CI status are recorded with the next checkpoint.
- Function 23, PoE budget and schedule summary: implementation is in progress on a fresh branch from current public `main`. It joins a fresh switch inventory with fixed PoE capability, usage, current port, schedule and time-range reads; identities and names are omitted. Watt comparisons use only same-row values documented as watts in ER7212PC. Port measurements are reduced to counts by raw state; schedule timestamps are reduced to presence. The route, fixed-source dispatch, projection and required registry/API/evidence gate pass their current fixture checks; no live controller read or change was made.
- Full Python discovery ran 3,095 tests and found one error: the capability route index did not yet include this new route. That index is now updated and the formerly failing assertion passes in a focused rerun. Full discovery was not repeated after that correction.

- Function 23, PoE budget and schedule summary: draft PR #13 targets current public `main`; exact-head push and pull-request CI are still running. No live read or network change was made.
- Function 24, switch stack connections: source review found the stack list and stack-scoped LLDP reader in all three exports. Implementation is in progress on a fresh branch from current public `main`; members are joined only by unique inventory MACs, and undocumented LLDP neighbor identities are not turned into topology edges. No live stack read was made.

The DHCP pool workflow was checked against the range and lease schemas in all three supplied API exports. Focused projector and HTTP/MCP fixture tests pass. This confirms implementation behavior for the documented fields only; live support is unverified.

The DNS diagnosis is a local offline analysis; it does not issue lookups or controller reads. Imported checks are marked unverified, configuration is site-wide context, and available summaries do not link an imported device to a network. Focused fixture tests pass.

For the PoE overview, an eight-switch synthetic input with 192 port rows used 14,875 `o200k_base` tokens as source JSON; the compact result used 2,153 tokens (12,722 fewer; 85.52%). Counts use `js-tiktoken` 1.0.21. This compares serialized fixtures only and excludes tool schemas, prompts, framing, live data and billed agent usage.

Site switch-port anomaly summary is implemented as a read-only HTTP/MCP workflow. It joins the fresh inventory with the existing paginated port overview and counter feeds, caps coverage at 32 switches and emits nonzero error counters as review signals without treating them as diagnoses. Raw port status codes remain uninterpreted. The ER7212PC export documents the status and cumulative error fields; Hardware Controller and CBC Standard use a generic response schema for these feeds, so field-level compatibility there remains unverified. Drop counts are not present in the documented per-port counter schema; no trend is calculated. Eleven focused projection, client, HTTP and MCP checks passed, as did all six operation-evidence tests after regenerating the static references. The combined 553-test run initially found only the stale evidence reference; registry, API-matrix and all other tests in that run passed. A synthetic eight-switch/192-port comparison measured 39,858 source JSON tokens and 6,138 summary tokens (84.60% fewer; serialized fixture payloads only). No live read was made.

For the stack summary, an eight-stack, 32-member, 96-neighbor synthetic source set used 8,239 `o200k_base` tokens; the redacted summary used 1,957 (6,282 fewer; 76.25%). Counts use `js-tiktoken` 1.0.21. This compares serialized fixtures only, not live data, tool schemas, prompts, framing or billed agent usage.

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
## Follow-up 26: backup inventory

A bounded backup metadata report now combines existing schedule/activity reads with the controller list and a one-site selected list. It exposes only counts, listed bytes, the highest returned timestamp and safe status/schedule fields. It never returns filenames, paths, URLs or credentials, and the site route does not enumerate all sites. Hardware Controller/CBC schemas are generic; detailed file metadata comes only from the ER7212PC export. A synthetic 12-file fixture measured 459 source JSON tokens and 103 summary tokens (77.56% fewer; js-tiktoken 1.0.21/o200k_base), excluding inventory, prompts and agent framing. Offline focused checks and hosted CI are pending.

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

## 2026-11-19 — Selected-site capability comparison

A bounded HTTP/MCP workflow compares documented site capability flags for 2–16
explicitly selected opaque site references after refreshing the site inventory.
It distinguishes permission-denied reads, stale/unknown references and missing
capability fields; no broad probes are run. Offline fixture tests pass. An
eight-site, 49-feature fixture measured 2,674 tokens across separate projected
source responses and 1,372 tokens for the aligned compact report (48.69% fewer;
js-tiktoken 1.0.21/o200k_base). This excludes tool schemas, prompts, framing,
inventory reads and billed agent usage. No live request was made.

## 2026-11-19 — Local change-journal summary

Added an authenticated HTTP and MCP read for counts of locally stored change-plan
states. It reads the connector's existing controller-bound journal object and
returns only total and per-state counts. Plan references, target references,
before/after values and event payloads are omitted. No caller path is accepted;
an unconfigured or unavailable journal is reported as unavailable. The integrity
marker refers to validation when the process opened the journal, not a disk
refresh. Unit and HTTP/MCP fixture checks pass. No controller call or journal
mutation was made. Reads now report an unavailable journal without creating or
opening one; the HTTP/MCP regression also confirms that an already-open journal
still returns its state counts. Token impact is not claimed because this endpoint returns
only a few fixed counters and has no repeated-source workflow to compare.

## Follow-up 31: overlapping WLAN client interruptions

The read-only HTTP and MCP summary accepts 2–16 explicitly selected clients and
one window of up to 24 hours. It counts only closed wireless disconnect-to-
reconnect intervals that overlap for different clients on the same AP reference
bound by the current site inventory. Missing AP mappings, open intervals,
partial reads and clients without samples remain visible; no cause is inferred.
All three supplied exports document event types `0` (wireless connect), `1`
(wireless disconnect), `2` (roaming) and `3` (blocked). The timeline reader now
uses those meanings; `association` remains a compatibility alias for type `1`.

Offline verification passed 39 focused diagnostics/transport checks, the full
3,116-test suite (457 seconds), the required 235-test registry/API-matrix/
operation-evidence gate, runtime smoke and Python compilation. A synthetic
eight-client fixture measured 3,164 `o200k_base` tokens across 16 timeline
responses and 244 tokens for the compact report (2,920 fewer; 92.29%), using
`js-tiktoken` 1.0.21. This measures serialized response data only; it excludes
inventory reads, tool schemas, prompts, framing, live data and billed agent use.
No controller read, network measurement or network change was made; live support
and real-client integration remain unverified.

Overlapping intervals are grouped and sorted by AP and client, then checked
with a two-pointer sweep for each distinct client pair. This keeps work bounded
by the selected clients and their interval counts while preserving one count
per client pair and AP. An unavailable client is counted once even when both
timeline sources fail; unavailable sources also contribute to partial coverage.

## Follow-up 32: reciprocal AP roaming sequences

Added a read-only HTTP and MCP workflow for 1–16 explicitly selected current
clients and one time window of up to 24 hours. It compares type-2 roaming with
type-1 disconnect and type-0 connect timelines. Consecutive reciprocal AP
roams (`A → B → A`) count as returns only when no disconnect is observed
between them. A disconnect and any observed reconnect after that separation
are counted separately; incomplete sources remain event gaps. Return counts
use opaque AP references bound to current site inventory. Unknown mappings,
unavailable sources and clients without samples remain visible; client
references are omitted and no cause is inferred. All three supplied API
exports document the source timeline and event types. Fixture-based offline
checks passed; no controller was queried, so live support remains unverified.

The focused #31/#32 transport and projection checks passed (54 tests), the full
offline suite passed (3,170 tests in 468 seconds), the required registry/API-
matrix/operation-evidence gate passed (235 tests), and runtime smoke, Python
compilation and diff checks passed. A synthetic eight-client fixture measured
2,386 `o200k_base` tokens across 24 serialized timeline endpoint responses
(roaming, disconnect and connect for eight clients) and 210 for the compact
report (2,176 fewer; 91.20%), using `js-tiktoken` 1.0.21. This counts
serialized endpoint response JSON only; it excludes inventory calls, schemas,
prompts, framing and billed agent use. No active WLAN measurement or network
change was made.

## Combined #31/#32 review update

After review, the #31 overlap check now sorts intervals once per AP and client
and uses a linear two-pointer scan for each distinct client pair. A client with
both timeline reads unavailable is counted once in the unavailable-client
coverage and once in partial-client coverage; it is not also called a
no-sample client. Regression fixtures cover the repeated-source failure and
400 intervals per client, preserving one count per client pair.

The final combined offline suite passed 3,171 tests in 467.282 seconds; 55
focused #31/#32 projection and transport checks, the 235-test registry/API-
matrix/operation-evidence gate, runtime smoke, Python compilation and diff
checks passed. The exact-head push run initially failed in the IPTV redaction test because
its random opaque reference happened to contain `123`, matching the old
substring search for a raw VLAN value. The regression fixture now uses a fixed
opaque reference containing that sequence, checks it separately, and asserts
the exact projected fields while preserving string-redaction checks. The fix
was included in PR #19 and is now on main at
`c60394ab1d47f7599012b912c75e8d37451e8c81`; both exact-head CI runs passed.
Live controller behavior remains unverified.

## Follow-up 33: selected AP uplink and mesh path

Added `GET /v1/sites/{site_ref}/ap-uplink-paths?device_ref=...` and MCP tool
`omada_site_ap_uplink_path_summary` for 1–16 explicitly selected current APs.
The workflow refreshes the selected site's device inventory, then reads each
AP's existing wired-uplink and mesh-statistics endpoints. It resolves peer
MACs only to unique same-site opaque device/AP references. The result reports
one evidenced next hop; the continuation is marked unexamined. A positive
documented wired rate can establish that hop even if the mesh read is
unavailable. Successful partial sources remain distinct from unavailable
sources. Unknown segments, missing peers and inventory status signals remain
visible; counters are review signals without cause or rate interpretation. No
scan or network change is initiated.

The three supplied API exports document the upstream reads and inventory.
ER7212PC 6.2.14 provides detailed response fields/examples; Hardware Controller
6.3 and CBC 6.3 include the schemas but do not provide the same detailed
operation response fields. RSSI/SNR thresholds and wired link-status/speed
meanings remain undocumented, and live compatibility is unverified.

Forty-eight focused local projection, inventory binding, HTTP/MCP and related
regression checks passed. A synthetic eight-AP comparison measured 2,485
`o200k_base` tokens for the inventory plus 16 separate connector endpoint
responses, versus 1,513 for the bundled report: 972 fewer (39.11%), using
`js-tiktoken` 1.0.21. This compares serialized connector JSON only; it excludes
tool schemas, prompts, framing, live data and billed agent use. The full offline suite passed 3,181 tests in 468.724 seconds. The required
registry/API-matrix/operation-evidence gate passed 235 tests, focused projection
and HTTP/MCP checks passed 48 tests, and runtime smoke, Python compilation and
diff checks passed. These are offline checks only; no controller was contacted.
