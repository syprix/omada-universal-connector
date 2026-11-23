# Connector status and evidence

This page summarizes the connector's current capabilities and the evidence behind them. Catalog entries and offline tests alone do not establish live support; operation-specific limits are recorded in the [capability evidence](CAPABILITIES.md), [roadmap](ROADMAP.md), and [operation evidence index](OPERATION_EVIDENCE.json).

## Follow-on read workflows

- #59 controller-wide event and alert windows: fixed, paginated HTTP/MCP reads use bounded time filters and omit row text and identifiers. Source contracts include the global log read permission in all three exports. A synthetic 20-row fixture measured 850→82 serialized tokens (90.35% fewer); live support remains unknown.
- #60 WAN-port availability by function: HTTP/MCP read validates the documented function codes 0–15 and returns redacted counts. Hardware/CBC document the source operation; ER7212PC does not. Physical link state is not inferred. A synthetic eight-port fixture measured 554→98 serialized tokens (82.31% fewer); live support remains unknown.

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

## Selected AP channel reuse summary

`GET /v1/sites/{site_ref}/channel-reuse?device_refs=...` and
`omada_site_channel_reuse_summary` compare current radio-detail channel and
bandwidth fields with matching rows from existing per-AP channel-load results
for 1–16 selected AP references. Equal reported channels are grouped by band.
The source schemas do not define occupied channel ranges or channel-load units,
so the report does not estimate adjacent-channel overlap or interpret load as
interference. If AP radio detail or load data is unavailable, coverage remains
partial. No scan or live network test was made. ER7212PC has the nested response
fields; Hardware Controller and CBC 6.3 have generic response schemas.
On a synthetic eight-AP fixture with inventory, eight radio-detail responses
and eight existing channel-load responses, `js-tiktoken` 1.0.21 (`o200k_base`)
counted 9,324 source JSON tokens and 2,046 report tokens (7,278 fewer; 78.06%).
This fixture included 608 channel-load rows and detailed radio counters; it
excludes tool schemas, prompts, transport framing and billed agent usage.
Integer and digit-string channel values are normalized before applying the
same 1–1000 validity range; zero and out-of-range values remain unknown. The
54 focused channel-reuse/integration/registry tests and the 235-test evidence
gate passed after this correction. The checks are offline only.
Draft PR #21 now points to `bb06757faebd7ad0f0f062b9f363bd8796db7eba`, with
exact remote tree `d064a3c45c724fa1cc7e895546fdc7e190a877ed`. Hosted checks for
the corrected exact head are running (push `44480805936`, pull request
`44480811773`); it remains a draft and unmerged.

## Bounded audit-log window summary

Added site and controller reads at
`GET /v1/sites/{site_ref}/audit-logs/window` and
`GET /v1/controller/audit-logs/window`, with MCP tools for each. Both require
explicit UTC epoch-millisecond bounds or an explicit local-time range and IANA
time zone; windows are limited to 24 hours. The connector sends the documented
`filters.times` range, sorts ascending, reads at most ten pages and 1,000 rows,
and marks a truncated result partial. It returns only timestamp, recognized
audit category, level and result. Unknown strings become `other`; operator,
source IP, resource, free-text content, labels and before/after setting values
are omitted. This avoids exposing the fields that can identify a person or
reveal configuration values.

All three supplied exports contain both upstream operations. ER7212PC 6.2.14
provides the operation response schema; Hardware Controller and CBC 6.3 use a
generic response schema, so their exact runtime row compatibility remains
unconfirmed. Individual projection, site/controller fixed-path and query,
bounded pagination, HTTP and MCP tests passed offline. No live controller
request was made. A synthetic 240-entry fixture measured 23,654 tokens for the
source JSON and 5,533 for the compact endpoint result (18,121 fewer; 76.61%) with
`js-tiktoken` 1.0.21 and `o200k_base`. The source fixture included synthetic
identity, text and setting fields that the result drops. Counts cover JSON only,
not schemas, prompts, transport framing or billed agent use.
Fifty-nine focused offline tests and the 235-test registry, API-matrix and
evidence gate passed. The corrected commit passed both exact-head GitHub CI
runs (push `44482564502`, pull request `44482572662`). The full local Python
suite then passed all 3,197 tests. No live controller request was made.

## Virtual WAN inventory summary

Added read-only `GET /v1/sites/{site_ref}/virtual-wan-summary` and the matching
MCP tool. It reads at most 1,000 documented virtual WAN grid rows and the
bounded available-virtual-WAN list. In all three exports, the grid `id` and
availability `virtualWanId` are both described as the virtual WAN ID. The
projection joins only unique values and reports matched, unmatched, ambiguous
and unkeyed counts while omitting identifiers, names and nested settings. The
exports do not define a crosswalk from the virtual rows to physical port
configuration or current WAN status; those facts remain separate, so physical
reconciliation is still open. Fixtures cover both fixed site reads, projection,
HTTP and MCP. Live support remains unknown. A synthetic 200-row grid and
180-row availability list used 36,469 `o200k_base` tokens as source JSON and
179 tokens for the compact result (36,290 fewer; 99.51%) with
`js-tiktoken` 1.0.21. This comparison excludes schemas, prompts, transport
framing and billed agent use. The complete local Python suite passed 3,204
tests; exact-head push and pull-request CI both passed (runs `44491276891` and
`44491284328`). No live controller request was made.

## WAN maximum-speed configuration

The initial draft omitted the source-required `wanId` query and is superseded
by a port-bound read at
`GET /v1/sites/{site_ref}/wan-ports/{wan_port_ref}/max-speed-summary`. The
three exports resolve `WanMaxSpeedOpenApiVO` to optional upstream/downstream
int32 values without a unit. The WAN-port inventory provides opaque port
references; each read resolves one reference against a fresh fixed inventory
response and sends its unique documented `portId` as `wanId`.

Focused client, port inventory, registry, matrix and HTTP/MCP tests passed (64
tests). They cover query encoding and rejection of missing, duplicate,
wrong-controller and extra query values. The mandatory registry/matrix/evidence
gate passed 253 tests. The full Python suite passed 3,214 tests in 472.535
seconds, and the runtime smoke check exited successfully. The source catalog
check passed; corrected exact-head push and pull-request CI both passed (runs 44502474666 and 44502481656). No live controller request
was made.

A synthetic two-request comparison measured 206 source JSON tokens and 260
connector-result tokens (+54) with `js-tiktoken` 1.0.21 / `o200k_base`. The
sample includes a two-port WAN configuration inventory and one selected-port
response; it excludes schemas, prompts, transport framing and billed agent use,
and does not save tokens at this size.


## AP SSID override audit read

Implemented as a bounded, redacted HTTP/MCP read for an AP reference refreshed from the selected site inventory. The connector requests a fixed page of at most 100 audit rows using the source default trailing seven-day window and returns aggregate modification-flag counts plus partial-data indicators. SSID/VLAN values and controller messages are omitted. The documented row schema has no timestamp or actor, so chronological ordering and attribution are not provided. This operation is documented in Hardware Controller 6.3.0 and CBC Standard 6.3.0, and absent from ER7212PC 6.2.14. The projector, request guard, route, HTTP/MCP tests and 240-test registry/matrix/evidence gate passed. Full offline discovery on the combined current branch passed 3,223 tests; runtime smoke, catalog check, compilation and diff checks passed. Controller support and actual third-party agent-client use remain unverified.

A synthetic two-row fixture measured 133 source JSON tokens versus 35 projected tokens (98 fewer, 73.7%) using js-tiktoken 1.0.21 with `o200k_base`. This covers serialized payloads only and is not a measurement of end-to-end agent billing.
## Function 40 — saved incident report comparison

Implemented a shared local-only comparator for existing redacted site-outage report schema version 1. It is available as `tools/compare_site_outage_reports.py`, authenticated HTTP `POST /v1/incident-reports/compare`, and MCP `omada_compare_incident_reports`. It accepts 2–8 reports with a 60 KiB data cap and never queries the controller. Event/alert totals compare only for identical windows and complete reports; reachability compares only when observation timestamps match exactly. Other schema versions are marked unsupported. It surfaces overlap, missing times/sections, unknown fields and pagination limits without returning report text or identifiers. Focused tests cover the existing report exporter, file permissions, schema gaps, HTTP/MCP dispatch and no-live-read behavior. Controller support is not applicable because this function consumes existing reports. Token measurement on two compact synthetic reports found 688 input JSON tokens versus 783 result tokens (95 more; js-tiktoken 1.0.21/o200k_base), so this sample does not save tokens.

## Function 41 — gateway information summary

Added `GET /v1/sites/{site_ref}/gateways/{device_ref}/info-summary` and the
`omada_gateway_info_summary` MCP tool. The selected gateway must come from the
current site inventory. Across all three supplied exports, `GatewayInfo`
documents a model string, firmware-version string, and `lastSeen` int64. The
projection returns only those values, reports missing/invalid/unknown fields,
and omits MAC/IP/IPv6 values and port details. The source gives no unit or epoch
for `lastSeen`, so no online/offline status is inferred. The read permission is
Site Device Manager View Only; live support remains unknown.

The 9 focused projector, inventory-binding, HTTP, MCP, and source-matrix tests
passed. The required registry/matrix/evidence gate passed 242 tests, full
offline discovery passed 3,246 tests in 476.156 seconds, and the runtime
smoke, compilation and diff checks passed. An offline matrix run confirmed the
common gateway detail route in Hardware Controller 6.3.0, CBC Standard 6.3.0
and ER7212PC 6.2.14.

A synthetic full-response comparison measured 119 source JSON tokens and 79
connector-result tokens (40 fewer) with js-tiktoken 1.0.21 / `o200k_base`.
This includes the source response wrapper and connector envelope but excludes
inventory, tool schemas, prompts, transport framing and billed agent usage.
No controller request or external agent-client test was made. The exact-head
push and pull-request CI runs for this implementation commit passed (44522696991,
44522719023); later commits require their own checks.

## Function 42 — VLAN port support summary

Added the read-only `site_vlan_port_support_summary` HTTP route and
`omada_site_vlan_port_support_summary` MCP tool. It checks that the selected
network is a VLAN network and that its inventory VLAN matches the requested
VLAN before reading the documented device-support-port endpoint. The result
contains only returned device/port counts by documented device type and
support boolean, with MAC, port, stack, LAG and MLAG identifiers omitted.
Unknown support booleans, missing port lists, invalid fields, and the
ER7212PC single-object schema shape are surfaced as partial data. The source
contract has no total-coverage field, so this is not a fleet-completeness
claim. Live controller compatibility remains unknown.

The source route and operation ID were confirmed in all three supplied API
exports. The projector, network/VLAN binding, path allowlist, registry, HTTP
and MCP dispatch have focused offline fixtures. A source-shaped synthetic
example with 8 devices and 192 ports measured 4,912 source JSON tokens versus
194 projected tokens (4,718 fewer; 96.05%) using js-tiktoken 1.0.21 and
`o200k_base`; a three-port example was larger after projection, so the saving
applies to larger result payloads. This measurement excludes inventory,
prompts, schemas, transport framing and billed agent usage. No live request or
network change was made. The required registry/matrix/evidence gate passed 242 tests. Full offline
discovery passed 3,255 tests in 475.857 seconds; runtime smoke, compilation,
JSON parsing, source-matrix confirmation and diff checks passed.

## Function 43 — static gateway-route summary

Added a read-only HTTP and MCP summary of the selected site's paginated static
route list. All three source exports document the same GET path and required
`page`/`pageSize` parameters. The projection counts route types, boolean status,
and occurrences of interface, VPN-client and virtual-WAN references; route IDs,
names, destination and next-hop addresses, metrics and descriptions are omitted.
ER7212PC omits one optional feature-description field, which is not projected.
The request uses the existing configured page bound and rejects a response that
cannot be read completely within it. Live support remains unknown.

The five projector/client checks, HTTP/MCP dispatch, registry, and source-matrix
checks passed (8 focused tests). The required registry/matrix/evidence gate
passed 244 tests. Source catalog consistency, runtime smoke, compilation and
diff checks passed. No controller request was made. A synthetic 20-route
comparison measured 1,571 source JSON tokens and 83 projected-result tokens
(1,488 fewer; 94.72%) with js-tiktoken 1.0.21 / `o200k_base`; it excludes
schemas, prompts, framing, and billed agent usage. Exact-head hosted CI is not
yet available because this change has not been uploaded.

Policy-routing summary is implemented for the documented read contract and exposed through HTTP and MCP. Live controller support has not been checked.


The IPsec security-association summary is implemented as a read-only HTTP and MCP operation. Live controller support and actual tunnel state remain unverified.

VPN server status codes are summarized per selected protocol through a read-only HTTP/MCP operation. The source exports do not define status code meanings; live support is unverified.

WAN QoS configuration is summarized with explicit unmatched/duplicate-reference coverage. Bandwidth values are omitted because the exports do not specify their units. No live-read was performed.

The UPnP site/template comparison is implemented using the existing redacted reads. The template source endpoint is documented only for CBC Standard 6.3.0; other controller variants remain unsupported by the supplied contract evidence.

Bridge inventory is summarized from adopted/pending list reads with identity fields discarded. No adoption or live controller test was performed.

The per-switch DHCP-snooping and ARP-detection capability endpoints have no documented row schema in any supplied export; the ER7212PC example is an empty result object. Safe inventory binding and missing-device accounting therefore cannot be established. No output fields or capability classifications have been guessed; #48 remains open pending a usable response contract.

The recent-client summary (#51) uses the documented `getGridKnownClients` time filters and one bounded page. It returns only the controller-reported total and sampled row count. `lastSeen` is an integer with no documented unit, so it is not interpreted; missing clients are not treated as outages. The route and projector passed focused HTTP, MCP, client, and contract checks. Live support remains unknown.

The VLAN affected-port summary (#53) uses `getGridVlanNetworkAffectedDevicePorts`, explicitly bound to a selected site, network, and VLAN. It reports device-class and port/LAG membership counts for one page, with identities and downstream client data omitted. Hardware Controller/CBC use integer port arrays while ER7212PC uses strings; the projection counts each documented representation separately and does not claim unique physical ports. Live support remains unknown.

The required registry, source-matrix, and evidence gate passed 262 tests with #51; focused tests for #53 also pass. No live controller read or network change was made. Synthetic token impact measurements are recorded in the capability notes; they measure serialized fixtures, not billed agent usage.

The SSID client-list operation (#52) remains open. Hardware Controller and CBC document it, but the ER7212PC export has no matching route. Its required `queryDataVO` object parameter also lacks an explicit serialization style, so the connector does not guess its wire encoding.

The port-schedule summary (#54) reads a bounded schedule page and the same-site supported-port list. It counts documented enabled state and time-reference/next-execution field presence, then compares schedule port memberships only when the documented MAC reference is unique. Device MACs, schedule IDs/names, time-range IDs, and port IDs are omitted. The `nextExecute` unit is unspecified; no execution or effect is inferred. Focused client, projector, registry, and HTTP/MCP checks pass. Live support remains unknown.

The routing-table summary (#55) accepts only the documented `gateway` or `switch` scope and one bounded page. It returns route totals and coverage plus counts of uninterpreted row type values; the exports do not enumerate those values. Destinations, hops, VRFs, interfaces and device identity fields are omitted. No route settings are changed, and live support remains unknown.


The VPN client status summary is implemented as an authenticated HTTP/MCP read, bound to one selected site and a documented protocol filter. Status values remain uninterpreted because no code mapping exists in the source exports. Live controller behavior is unconfirmed.

The selected-SSID client count read is implemented for the two source exports that document `getGridSsidClients`. It sends only the OpenAPI 3.0.1 default flat `page` and `pageSize` query fields, binds the SSID to its selected site inventory, and reports page coverage. The endpoint is absent from the ER7212PC export; live behavior remains unconfirmed.

The Site-to-Site VPN status summary (#61) filters by documented IPsec or WireGuard protocol and counts raw documented integer status codes over bounded pages. None of the three exports assigns meanings to those codes; the summary does not assert tunnel connectivity. This read is separate from #45's IPsec security-association list and does not close its missing status semantics. The ER7212PC example has inconsistent page totals and row data; it is not accepted as valid evidence. Live behavior remains unconfirmed.

The selected-SSID topology device summary (#62) binds a fresh selected SSID to its site, reads the same site's device inventory and joins inventory classes against the documented topology MAC list. It omits MACs and names, reports unmatched or ambiguous coverage, and makes no RF coverage claim. The v3 endpoint appears in Hardware Controller and CBC exports but is absent from ER7212PC. Live behavior remains unconfirmed.

Synthetic payload measurements with `js-tiktoken` 1.0.21 (`o200k_base`) were 1,743 → 90 tokens for twenty source-shaped VPN rows (#61; 94.84% fewer), and 241 → 87 for twenty topology MACs (#62; 63.90% fewer). These are serialized-payload fixtures, not live responses or billed-agent usage.

The AP topology-client summary (#63) resolves an opaque AP reference from a freshly refreshed site inventory and then uses `getTopologyClients`. It counts documented wireless/guest fields plus whether the unenumerated client-type field is present, while omitting all client values and identifiers. The endpoint provides no source timestamp and no roaming history; no current connected-state claim is made. It is documented in Hardware Controller and CBC, not ER7212PC. Live behavior remains unknown.

The selected LAN network delivery summary (#64) refreshes the site's network inventory and reads `getDeliveringProcessWithoutConfig` only for that network. It reports documented state and counts from success/failure/delivering lists without device IDs. Completion does not imply device reachability. The operation is documented in all three exports; live support is unknown. A synthetic fixture with 20 device/stack entries measured 120 → 96 tokens (20% fewer), serialized payload only.

The site LAN port profile summary (#65) reads `getOswLanProfileList` from all three exports. It counts documented profile/source enum values and safe feature toggles over bounded pagination while redacting names, IDs, VLANs and network references. No device assignment is inferred. Live behavior remains unknown.

A synthetic 20-profile fixture measured 2,543 → 475 tokens (81.32% fewer) using `js-tiktoken` 1.0.21 (`o200k_base`); serialized payload only.

The controller firmware plan summary (#66) reads `getGridUpgradePlans` from all three exports with a bounded ten-page limit. It counts documented site associations, current-version entries, schedule/model/version field presence and rollback origin; it does not reveal versions, model/site names, operators, identifiers or dates. The source has no execution-state field, so planned upgrades remain distinct from #58 execution records. Live behavior is unknown.

A synthetic 20-plan fixture measured 2,002 → 166 tokens (91.71% fewer) using `js-tiktoken` 1.0.21 (`o200k_base`); serialized payload only.

Site remote logging is exposed as a redacted HTTP/MCP read. Destination values and delivery claims are excluded; only documented enablement, category and target presence are summarized. Live behavior is unconfirmed.

The controller-wide firmware upgrade-log read is bounded to a 100-row page and reports only documented aggregate state and coverage. It redacts identities, versions, model details and raw timestamps; no update action is exposed. Live behavior is unconfirmed.

The LAN multicast settings summary (#67) reads `getGridLanMulticasts` from all three exports over bounded pagination. It reports documented protocol and unknown-multicast rule counts, selected enablement flags, and field coverage while omitting names, addresses, device/network identifiers, and nested configuration. The ER7212PC example's page metadata conflicts with its row data, so it is not treated as valid response evidence. The result describes settings, not actual multicast traffic. Live behavior is unknown.

A synthetic 20-entry fixture measured 5,398 → 237 serialized tokens (95.61% fewer); this is not billed agent usage.

The bandwidth policy summary (#68) reads `getGridBandwidthCtrlRule` from all three exports over bounded pagination. It counts active state, documented source/mode categories, units by direction, and field coverage; names, identifiers, target lists, and numeric rate limits are omitted. It is separate from WAN QoS settings and actual traffic measurements. The ER7212PC example has contradictory page metadata and is not treated as valid response evidence. Live behavior is unknown.

A synthetic 20-rule payload measured 1,620 → 236 serialized tokens (85.43% fewer); this is not billed agent usage.

The log notification summary (#69) reads `getLogSettingForSiteV2` from all three exports for a selected site. It counts notification categories and documented alert/event/email/webhook switch states, plus top-level email and webhook enablement. Category keys, message text, webhook IDs and numeric delay values are omitted. The response contains no delivery result; configured switches do not prove delivery. Live behavior is unknown.

A synthetic 20-category fixture measured 787 → 187 serialized tokens (76.24% fewer); this is not billed agent usage.

The LAN network interface summary (#70) reads `getInterfaceLanNetworkV2` from all three exports for a selected site. It counts documented purpose, interface VLAN type and application scope, plus interface-reference and subnet presence. Its optional type filter accepts only `0` (single interfaces) or may be omitted. Names, IDs, VLAN values and subnet addresses are redacted; no router/VLAN mapping is inferred from interface IDs. Live behavior is unknown.

A synthetic 20-network fixture measured 2,104 → 159 serialized tokens (92.44% fewer); this is not billed agent usage.

The LAN client inventory summary (#71) reads the common `networks/client` route (`getGridAllClients_1` in Hardware/CBC and `getGridAllClients` in ER7212PC). Fixed 100-row pagination is capped at ten pages. The result reports total inventory, returned coverage and device-type field presence; MACs, names and raw device types are omitted. It does not claim current connectivity. Live behavior is unknown.

A synthetic 20-client source response and connector result measured 516 → 76 serialized tokens (85.27% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; this is not billed agent usage.

The topology root-candidate summary (#72) reads `getTopologyNodes`, documented by Hardware Controller and CBC 6.3.0 but absent from ER7212PC. It counts candidate node types, documented root/stack flags, and MLAG/VRRP codes; names, addresses, model and subtype text are omitted. The endpoint returns no edges, and its documented empty response case with a gateway is not interpreted as missing topology. Live behavior is unknown.

A synthetic 20-node source response and connector result measured 1,498 → 175 serialized tokens (88.32% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; this is not billed agent usage.

The isolated/preconfigured device summary (#73) reads the two documented topology categories separately from Hardware Controller and CBC 6.3.0; ER7212PC does not document this endpoint. It checks the returned counts against the documented total and reports only category, type/health/IPPT field coverage. It does not claim adoption state or infer isolation cause. Live support is unknown.

A synthetic 20-device source response and connector result measured 944 → 208 serialized tokens (77.97% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; this is not billed agent usage.

The VLAN topology summary (#74) reads `getFilterDevicesOfVlan` from Hardware Controller and CBC 6.3.0; ER7212PC does not document it. It requires a current same-site network/VLAN match, then classifies returned topology MACs only through that site's device inventory. It returns class and coverage counts, not topology links. Live support is unknown.

A synthetic 20-MAC source response and connector result measured 241 → 114 serialized tokens (52.70% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; this is not billed agent usage.

The ES-switch network overview (#75) reads `getESNetworkOverview` only after a same-site inventory-bound lookup in `getOswDetailInfoListForPortsView` returns exactly one matching MAC with the documented `es: true` Agile-Series flag. Missing, duplicate, and non-Agile matches are rejected before the overview call. It counts network rows and native, untagged and tagged port assignments while omitting network details, VLAN values and port numbers. Live hardware support remains unknown.

A synthetic 20-network source response and connector result measured 851 → 160 serialized tokens (81.20% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; this is not billed agent usage.

The schedule-capable port summary (#76) reads `getPortSchedulePorts` from all three exports. It is distinct from `getPortScheduleList`, which backs the existing configured schedule summary. The result counts device and port totals by documented fields; it does not report configuration or execution of an actual schedule. Device and port details are redacted, and raw status values are not interpreted. Live support is unknown.

A synthetic 20-device source response and connector result measured 1,798 → 128 serialized tokens (92.88% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; this is not billed agent usage.


The controller-wide notification summary (#78) reads `getLogSettingForGlobalV2`, separate from site rules. It counts only the documented alert, event, email and webhook switches, and omits category keys, messages, webhook IDs and delay values. It does not report delivery. Live support is unknown.

The port-forwarding status read (#77) remains open: all three exports describe the required `type` path value only as `User/UPnP`, without an enum or request example. Accepted literals and casing are not confirmed; no experimental call or guessed value is used.

The firmware-plan model summary (#79) reads the documented paginated `getGridPlanUpgradeModelList` from all three exports. It counts model type metadata and the documented good/critical and up-to-date/new-version status codes, while omitting model names and firmware versions. The read is capped at 1,000 rows; excess source rows are reported as truncation. It does not trigger an upgrade or infer compatibility. Live support is unknown.

The selected site-to-site VPN peer summary (#80) adds an opaque reference inventory from `getSiteToSiteVpnList` and uses it to bind `getGridVpnS2SPeersStatus` to one current VPN at the selected site. It counts the documented status filter meanings (0 disconnected, 1 connected) and keeps other/missing codes unknown. VPN/peer IDs, names, endpoint addresses, ports and traffic counters are omitted; the inventory Boolean is not presented as tunnel connectivity. Live support is unknown.

The static-route interface-options summary (#81) reads `getStaticRoutingInterfaceList` from all three exports. It aggregates the documented WAN, LAN, L2TP, PPTP and virtual-WAN type codes, `needNextHop` values and optional WAN-enabled flag, while omitting names and IDs. This describes choices in the route editor, not configured or active routes. Live support is unknown.

The available-SSID topology read (#82) remains blocked. Hardware Controller and CBC require `page`, `pageSize`, and a string `searchKey`; its description leaves the supported search fields blank, and there is no request example or documented no-filter value. ER7212PC does not document this operation. No guessed empty search value or live request is used.

The selected WLAN configuration summary (#83) refreshes the site WLAN-group and SSID inventories, confirms one unique membership match, then reads the documented group-scoped `getSsidDetail` operation. It returns only the documented enable flag, band coverage bits and EAP/gateway applicability bits. Names, identifiers, VLAN values and credentials are omitted. Missing fields remain unknown. Live support is unknown.

Synthetic serialized JSON token counts for #81 and #83 use `js-tiktoken` 1.0.21 / `o200k_base`: 533→128 (75.98%) for 20 route-interface rows and 134→92 (31.34%) for a selected-SSID inventory, membership and detail flow. These are fixture payloads, not live measurements or billed agent usage.

The LTE WAN configuration summary (#84) reads `getLteWanPortsConfig` from all three exports. It counts documented mobile-data/roaming flags, network and band modes, dial-up modes, failover-setting presence, and the documented modem and SIM-card state codes. Settings and reported modem status are separate, and no Internet reachability is inferred. SIM/port IDs, names, provider values, APNs and raw band strings are omitted; the list is bounded to 1,000 rows. Live support is unknown.

The synthetic 20-row LTE settings payload measured 4,328→458 serialized JSON tokens (89.42% fewer) using `js-tiktoken` 1.0.21 / `o200k_base`; this is not a live measurement or billed agent usage.

The NAT exception summary (#85) reads `getDisableNatGrid_1` from the Hardware
Controller and CBC exports. It counts documented enabled/disabled states, LAN
list coverage and entries, and WAN-interface coverage while omitting names,
IDs, descriptions and raw LAN/WAN values. This represents stored configuration;
effective enforcement and traffic behavior remain unknown. ER7212PC does not
document the operation, and live support is unknown.

The v2 site-to-site VPN summary (#86) reads `getGridVpnS2SV2` from all three
exports. It aggregates documented VPN/site-VPN type codes, the API's boolean
status field, network-selection and WAN coverage, failover-object coverage,
and four S2S support flags. The existing v1 endpoint remains the source for
opaque VPN references. Names, IDs, addresses, raw network/WAN values,
custom-subnet values, peers and user/client counts are omitted. The boolean
status does not establish tunnel connectivity. Live support is unknown.

The synthetic 20-row v2 VPN fixture measured 2,999→328 serialized JSON tokens
(89.06% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; this is not a live
measurement or billed agent usage.


The selected stack network summary (#87) reads `getStackNetworkList` from all three exports after binding the opaque reference to a unique, fresh stack row in the selected site. It counts DHCP modes and documented status/management/IPv6 fields, while omitting VLAN/network identifiers, names, member details, addresses, DHCP values and VRF identifiers. The scan is capped at 1,000 rows. Fixture tests cover the projection and binding; the required stack hardware was not available for live testing.

A synthetic 20-row stack-network response measured 2,526→138 serialized JSON tokens (94.54% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`. This fixture comparison excludes prompts, schemas, transport framing and billed agent use.
The controller-wide SD-WAN group summary reads `getGridSdWanGroupBrief` from
Hardware Controller and CBC Standard only; ER7212PC does not document it. It
counts groups, hub type/model/version field coverage and the sum of per-group
device counts, without returning IDs, names or hub values. The sum is group
membership, not a count of unique devices. The contract has no status or enabled
field. Live support remains unknown.

A synthetic 20-group fixture measured 902→55 serialized JSON tokens (93.90% fewer) with `js-tiktoken` 1.0.21 and `o200k_base`. The fixture and summary exclude HTTP/MCP framing, live payloads and billed agent usage.

The configured client-to-site VPN server summary (#90) reads `getGridVpnServerV2`
from all three exports. It counts documented protocol codes and the source
boolean VPN status flag, and omits IDs, names, WAN/network values and user/client
counts. This flag does not establish tunnel connectivity and remains separate
from the existing operational-status read. Live support is unknown.

A synthetic 20-server fixture measured 882→128 serialized JSON tokens (85.49%
fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; it is not a live measurement
or billed agent usage.

The remote-access tunnel status summary reads `getTunnelsStatus` from all three
exports. It counts the documented connection codes (0 disconnected, 1
connected, 2 opening, -1 heartbeat missed, -2 expired) separately from the
open/closed flag. Tunnel IDs and names are omitted; the source list is capped
at 1,024 rows. Live support is unknown.

A synthetic 20-tunnel fixture measured 450→110 serialized JSON tokens (75.56%
fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; this is not a live measurement
or billed agent usage.

The site IDS/IPS configuration summary reads `getIpsConfig` from all three
exports. It counts the documented enable and geo flags, mode and detection
level codes, and custom category count. Schedule identifiers and raw category
values are omitted; configuration is not presented as attack detection or
successful enforcement. Live support remains unknown.

A synthetic one-site IDS/IPS fixture measured 65→46 serialized JSON tokens
(29.23% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; this is not a live
payload or billed agent measurement.
The gateway webfilter summary reads `getGridGatewayRule` from all three
exports. It is bounded to 1,000 rows and reports the documented gateway/AP rule
types, enabled state, optional feature flags and source support flags. URLs,
keywords, category values, names, IDs, source IDs and schedule values are
omitted. No effective filtering behavior is inferred; live support is unknown.

A synthetic 20-rule gateway webfilter page measured 2,005→225 serialized JSON
tokens (88.78% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`. The fixture
comparison excludes tool schemas, prompts, transport framing and billed agent
usage.

The gateway QoS class summary reads `getClassRuleGrid` from all three exports.
It is bounded to 1,000 rules and reports enable state, documented IPv4/IPv6
codes and class codes. Address-group values, service IDs, rule IDs and DSCP
values are omitted; no traffic or throughput is inferred. Live support remains
unknown.

A synthetic 20-rule gateway QoS class page measured 1,109→113 serialized JSON
tokens (89.81% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; this excludes
prompts, tool schemas, transport framing and billed agent usage.

A synthetic 20-rule webfilter page measured 2,005→225 serialized JSON tokens
(88.78% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; this excludes prompts,
tool schemas, transport framing and billed agent usage.

## 2026-11-23 — WAN limitation entry summary

Added a site-bound HTTP/MCP read for `obtainWanUnsupportedFunction`. The
connector sends only the documented fixed `filter=1`, counts typed string
entries, and discards all labels. Empty, missing, invalid and truncated data
are distinct. The output describes source-reported list entries only; it does
not make a claim about current device capability or WAN state. All three
exports document the operation. Live support has not been checked.

A synthetic 20-entry response measured 331 source tokens and 40 summary tokens
(87.92% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; transport framing and
model usage are excluded.

## 2026-11-23 — Bonjour profile summary

Added a site-bound HTTP/MCP read for `listMdnsProfile`, separate from the
existing mDNS rule list. It counts profile defaults and zero-to-three service
entries, omits IDs, names and service strings, and caps the list at 1,000
profiles. Missing/invalid fields and truncation are visible in the summary. All
three exports document the read; live support has not been checked.

A synthetic 20-profile response measured 722 source tokens and 103 summary
tokens (85.73% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; framing and
model usage are excluded.

## 2026-11-23 — Switch OUI VLAN and stack DHCP summaries

Added two site-bound HTTP/MCP reads. The OUI VLAN summary counts documented
enable flags and port-scope modes only; it omits rule/device identities, OUI
values and VLAN values, and makes no enforcement claim. The ER7212PC export
explicitly marks the endpoint Omada Pro-only and documents `-44119` for non-Pro
controllers; ER7212PC is not claimed as supported. The stack DHCP summary
refreshes same-site stack inventory and requires one unique match before
reading; it counts documented device/client types and dynamic/static binding
states while omitting addresses, names and binding rows. It makes no current
lease or wired-client claim.

Both operations are present in all three supplied API exports. Synthetic
20-row JSON measurements with `tiktoken` 0.9.0 / `o200k_base` were 1,793→110
tokens for the OUI-rule response (93.87% fewer) and 2,359→92 for the stack DHCP
user response (96.10% fewer). They exclude prompts, tool schemas, transport
framing and billed agent usage. Projection, binding, HTTP/MCP, registry,
matrix/evidence and full HTTP-module tests passed. Live controller support was
not tested. These changes are prepared for review and are not represented as
merged or released.

## 2026-11-23 — AP webfilter and global filter summaries

Added site-bound HTTP and MCP reads for AP URL-filter rules and global URL
filter settings. The AP summary counts documented AP rule type, URL/category
mode, reported status and feature-flag coverage, while omitting rule text,
URLs, keywords, categories, schedules, names and source identities. The global
summary reports only SafeSearch and block-page flags; it omits the optional
block-page message. Both report controller configuration only, not effective
filtering. Offline contract checks found both operations in all three supplied
API exports; live controller support is unknown.

Synthetic JSON projections were tokenized with `tiktoken` 0.9.0 and
`o200k_base`: a 20-rule AP page measured 2,076 source tokens and 276 summary
tokens (86.71% fewer); a global settings response with a repeated block-page
message measured 296 and 46 tokens (84.46% fewer). These figures cover only
serialized JSON and exclude prompts, tool schemas, transport framing and billed
agent usage. Focused projection and adapter tests passed, the full HTTP module
passed (367 tests), and the registry/matrix/evidence gate passed (302 tests).
Exact push and pull-request CI passed for public head
`b64f0b1057fb834bb28e03d41bb0ecbfd1434db2`. The two reads were merged in
`132c67646b16b91aefef208d9455d0bfaec43a8b` and included in release `v0.18.0`.
Live controller support was not tested.

## 2026-11-23 — LAN isolation and OSPF interface summaries

Added two site-bound reads. LAN isolation uses the documented unfiltered GET
and counts only reported true, false, missing and invalid flags. All three
exports document the path; ER7212PC uses the operation ID without `_1`. The
OSPF summary is bounded to 1,000 rows,
counts documented interface/network types and valid link costs, and reports
optional field coverage. It omits names, addresses, VLAN values and
authentication keys. Neither summary claims real network separation or OSPF
neighbor state. Offline contract checks passed for all three exports, including
the ER7212PC operation-ID variant. Focused projection and adapter tests and the
full HTTP module (370 tests) passed; the registry/matrix/evidence gate passed
(303 tests). Synthetic JSON measurements with `tiktoken`
0.9.0 / `o200k_base`: LAN isolation 605→79 tokens (86.94% fewer); OSPF 2,806→283
(89.91% fewer). Exact push and pull-request checks for head
`9631aad1208fc5d16ea7bb795007b3cb4ec71502` passed. Both reads were merged in
`7df8b60a4b77bd0d99e148de7d89fe24a5b51a5d`, tree
`6e732a371d9090c6045aa2624aacacd996da4f3d`. Live support was not tested.

## 2026-11-23 — Switch QoS rules and optical DDM flags

Added a bounded switch QoS rule summary and a switch-bound optical DDM summary.
The QoS read sends only documented pagination and summarizes status, type and
queue. DDM refreshes the selected site's inventory, requires one unique switch
match and summarizes only data-valid, transmit-fault and signal-loss flags.
Names, identifiers, addresses, ports and numeric optical readings are omitted.
The ER7212PC QoS response is generic and its DDM response has no effective row
contract; unsupported shapes are rejected and live support remains unknown.
The full HTTP/MCP module passed (471 tests), and the registry/matrix/evidence
gate passed (304 tests) after refreshing the generated evidence ledger. Offline
matrix and contract checks found both operations in the three supplied exports,
with the documented ER7212PC limitations above. The ledger now records 460
fixed GET routes, 1,960 unmapped operations and 25 manual-only entries. Synthetic
JSON measures used `tiktoken` 0.9.0 /
`o200k_base`: QoS 2,346→163 tokens (93.05% fewer); DDM 1,855→124 (93.32% fewer).
Live controller behavior was not tested.

## 2026-11-23 — Stack VLAN interfaces and SNMP incompatibility counts

Added a selected-stack VLAN-interface summary that binds `stack_ref` through a
complete, fresh same-site inventory. It reports interface-row counts,
duplicate/missing/invalid IDs and documented field coverage without exposing
names, IDs or VLAN numbers. Hardware/CBC provide the typed list contract; the
ER7212PC export does not declare this operation.

Added a bounded count-only read for controller-reported SNMP-incompatible
device rows. Hardware/CBC define a narrow `DeviceVO` while ER7212PC defines a
broader inventory row; the output avoids equating their fields and omits all
device data. Both operations have individual projection, binding, route and
HTTP/MCP tests. The full HTTP/MCP module passed (378 tests), as did the
registry/matrix/evidence gate (305 tests). Offline contract and matrix checks
passed across all three exports. No controller read was made.

Synthetic serialized JSON measured with `js-tiktoken` 1.0.21 /
`o200k_base`: stack VLAN interfaces 562→102 tokens; SNMP counts 4,448→69 for
Hardware/CBC-shaped rows and 8,929→69 for ER7212PC-shaped rows. These figures
measure serialized JSON payloads only. Exact push and pull-request CI passed
for `9ee72e6efc9b560d69f157bad642a5b5400f605a`; the changes were merged as
`43e87898a9869e491a8b659c326f4ddb8d3da5cc` with tree
`da604325900c2067a62bd44d51f19d2abbec9a22`.

## 2026-11-23 — Gateway and switch general settings

Added site-bound HTTP and MCP reads for documented gateway and switch general
settings. Each refreshes the selected site's inventory and requires exactly
one matching gateway or switch before making the GET. The gateway summary
reports the documented LED mode and whether the optional `rememberDevice` and
SNMP objects are present; it does not assign undocumented meaning to the
remember-device integer. The switch summary reports LED mode, Jumbo setting
scope/range validity, LAG hash setting scope/mode and SDM object presence.
Hardware/CBC declare both switch site-follow fields; ER7212PC omits them, and
the summary marks them missing. No names, tags, locations, SNMP values or raw
Jumbo values are returned, and no packet-forwarding behavior is inferred.

The two operations were found in all three local exports. Offline contract and
full API matrix checks passed for Hardware 6.3.0, CBC 6.3.0 and ER7212PC
6.2.14. The complete HTTP/MCP module passed (380 tests), and the registry,
matrix and generated-evidence gate passed (307 tests). Focused projection and
binding tests passed (10 tests); compile and whitespace checks passed. No
controller read was made. Synthetic serialized JSON measured with
`js-tiktoken` 1.0.21 / `o200k_base`: gateway settings 77→36 tokens, switch
settings 78→43 and ER7212PC-shaped switch settings 63→39. These measurements
cover serialized payloads only and do not represent billed agent usage. The
changes are locally verified and await GitHub CI; they are not represented as
merged or released.
