# Capability evidence

`GET /v1/sites/{site_ref}/static-route-summary` and MCP tool
`omada_site_policy_route_summary` provides a bounded, read-only summary of documented policy-routing rows for one selected site. It counts source, destination and interface types, enabled state and opaque reference occurrences; it marks unknown values and index quality. It does not disclose IDs or names, infer precedence, or claim that a route is carrying traffic.

`omada_site_static_route_summary` provide a bounded read-only overview of the
selected site's static gateway routes. The response counts documented route
types, status values and occurrences of interface, VPN-client and virtual-WAN
references. It does not return route identifiers, names, destination or
next-hop addresses, metrics or descriptions. Live controller support is
unknown until verified against a controller.

## Dynamic Wireless IDS blacklist summary

`GET /v1/sites/{site_ref}/wifi/wids-blacklist-summary` and MCP tool
`omada_site_wids_blacklist_summary` expose `getGridWipsBlackList` through the
fixed site GET
`/openapi/v1/{omadacId}/sites/{siteId}/insight/wids/blacklist?page=1&pageSize=1000`.
All three exports document the same required page arguments and row fields,
plus `Site Insight Manager View Only` or `Network Config Page View Only`.
The connector returns the page count and quality counters only; station/AP
MAC addresses and event timestamps are discarded. More rows than returned,
malformed values or unknown fields mark the result partial. The fixed read is
included in the site WLAN diagnostic. Fixture coverage only; live support is
unknown.

On the checked-in empty-event fixture, `js-tiktoken` 1.0.21 / `o200k_base`
counted twelve separate GET path/response objects at 1,594 tokens and the
bundled CLI request/report at 1,337 (257 fewer; 16.12%). Without the
blacklist read, the same fixture measured 1,516 versus 1,280. The blacklist
added 78 tokens to separate calls and 57 to the bundle. This serialization
excludes live data, MCP framing and billed usage.

## Stored Wireless IDS summary

`GET /v1/sites/{site_ref}/wifi/wids-summary` and MCP tool
`omada_site_wids_summary` expose `getGridWidsData` through the fixed site GET
`/openapi/v1/{omadacId}/sites/{siteId}/insight/wids?page=1&pageSize=1000`.
All three API exports document the same required page parameters and row
fields, plus `Site Insight Manager View Only` or `Network Config Page View
Only`. The connector reads one page, aggregates documented severity and band
codes, raw event type codes and channels, and discards MAC addresses and
detection times. More rows than returned, malformed fields or unknown fields
mark the projection partial. The WLAN site diagnostic includes this fixed
read; it never starts an IDS scan. Fixture coverage only; live support remains
unknown.

On the checked-in empty-event diagnostic fixture, `js-tiktoken` 1.0.21 with
`o200k_base` measured eleven separate GET path/response objects at 1,516 tokens
and the bundled CLI request/report at 1,280 tokens (236 fewer; 15.57%). The
same fixture without the WIDS endpoint measured 1,407 and 1,192 tokens
respectively. Thus this empty WIDS result added 109 tokens to separate calls
and 88 to the bundle; bundling reduced its serialized cost by another 21
tokens. This is fixture serialization only, not live responses, MCP framing,
agent runtime behavior or billed token use.

## Controller scenario list

`controller_scenarios` provides `GET /v1/controller/scenarios` through HTTP
and MCP. It validates and returns at most 100 source strings; invalid entries
are omitted and make the result partial. The three original API exports
document the same `ListString` response and no query or body parameters. The
operation docs do not specify a permission. Fixture coverage only; live support
is unknown.

## Longest client uptime dashboard read

`GET /v1/sites/{site_ref}/dashboard/longest-client-uptime-summary` and MCP
tool `omada_site_longest_client_uptime_summary` expose
`getLongestClientUptime` from the fixed site dashboard endpoint. All three
exports define a response with `total`, `wiredClient` and `wirelessClient`
int32 fields, no query/body, and the Site Dashboard Manager View Only
permission. The schemas do not describe their meanings or units, so the
connector preserves the source field names and does not interpret them. Fixture
coverage only; live support remains unknown.

## Site LAN network inventory

`GET /v1/sites/{site_ref}/lan-networks/inventory` and MCP tool
`omada_site_lan_network_inventory` expose `getAllLanNetworks` through the
fixed `/openapi/v1/{omadacId}/sites/{siteId}/lan-networks/all` route. All three
exports describe a result list with no query or body; the operation names the
Site Settings Manager View Only or Network Config Page View Only permission.
The connector processes at most 500 rows and returns purpose, DHCP and
documented feature counts. Names, identifiers, addresses, subnet values and
nested configuration are omitted. Invalid, unknown or truncated data marks the
result partial. Live support remains unknown.

## Site LAN network detail

`GET /v1/sites/{site_ref}/lan-networks/{network_ref}/summary` and MCP tool
`omada_site_lan_network_detail_summary` expose `getLanNetwork` through the
fixed detail GET. The reference is resolved from the selected site's current
LAN-network inventory, so the request stays bound to that site. The projection
keeps documented purpose, VLAN and device-type codes, an IPv4 gateway subnet,
DHCP enabled/pool counts and selected feature flags. Names, IDs, MAC addresses,
DNS values, DHCP ranges and unrelated configuration are omitted. The three
source exports document the route and either Site Settings Manager View Only
or Network Config Page View Only permission. ER7212PC's schema has different
required fields; the projection treats only common required fields as missing.
Fixture tests cover projection, reference binding, HTTP and MCP. Live support
remains unknown.

## Site-bound threat windows

`site_threat_window_summary` exposes `getGlobalThreatList` through
`GET /v1/sites/{site_ref}/threats/window` and MCP. A current opaque site
reference binds the request to one site; caller-selected URLs and site IDs are
not accepted. The UTC window is limited to 24 hours, records are paginated in
pages of 1000 with a 10-page cap, and only severity counts and bounded time
metadata are returned. Threat IDs, descriptions, signatures, addresses and
location data are omitted. Truncation is reported as `partial=true`. The three
provided exports document the operation; the operation docs do not specify a
permission. Fixture coverage only; live support is unknown.

### Controller system port settings

Three fixed, controller-bound GET operations now expose the documented
upgrade, portal and management port settings through HTTP and MCP:

- `GET /v1/controller/settings/upgrade-port`
- `GET /v1/controller/settings/portal-port`
- `GET /v1/controller/settings/controller-port`

All three original exports (Hardware Controller 6.3.0, CBC Standard 6.3.0 and
ER7212PC 6.2.14) document the same upstream paths, path parameter and
`Global Other Setting View Only` permission. Each has the required `omadacId`
path parameter and no query or body parameters. Their response fields are the
same: the upgrade HTTPS port; portal HTTP/HTTPS ports, host, auto-IP and HTTPS
redirect flags; and management HTTP/HTTPS ports, hostname and auto-refresh
flag. The described port ranges allow the documented HTTP/HTTPS defaults and
otherwise 1024–65535. Hardware Controller and CBC use `*/*` response media;
ER7212PC specifies `application/json`. ER7212PC's `portalHost` has no pattern
constraint, while the other two exports describe a domain/IP pattern. The
connector never returns either raw host value; it reports only whether one
was configured. Ports and booleans are type/range checked, and missing,
invalid or unknown fields make a result partial. The routes are fixed to the
configured controller ID and take no caller-supplied path, query or host.
Fixture tests cover projection, HTTP and MCP dispatch; live support remains
unknown.

`controller_scenario_differences` exposes the `getScenarioListDifference`
read through HTTP and MCP. The result validates and returns at most 100
documented `{name, isDefault}` rows, with an invalid/truncated marker; IDs and
other fields are omitted. All three source exports document the same fields,
with no operation-specific permission. Fixture coverage only; live support is
unknown.

Three additional fixed reads cover controller status, logging levels and the
active certificate at `/v1/controller/status`,
`/v1/controller/settings/logging` and
`/v1/controller/settings/certificate`. All three source exports document the
paths with `Global Other Setting View Only`; Hardware Controller and CBC use
`*/*` response media types while ER7212PC uses `application/json`. Status
returns bounded version, uptime and capacity fields, with names, MAC, serial,
timezone, area and inform URL reduced to presence flags. Logging returns only
the documented categorical levels. Certificate IDs, names, key IDs and
passwords are reduced to presence flags; only the strict enabled flag is
returned as a value. Missing, malformed or unknown fields mark results partial.
Fixture tests cover projection, exact GET paths, controller binding and
HTTP/MCP dispatch. No live response has been observed; support remains unknown.

`controller_radius_proxy` and `controller_radius_server` are fixed, fixture-
tested HTTP/MCP reads. The supplied Hardware Controller 6.3.0 and ER7212PC
6.2.14 specifications document both GETs; the CBC specification documents
neither controller-wide GET. RADIUS secrets, failure text, certificate
identities/password and custom address are not projected. Live support remains
unknown.

`site_radius_user_summary` is a fixed, paginated read of the built-in RADIUS
user inventory. It returns aggregate counts only; user IDs, usernames,
passwords, descriptions and assigned VLAN values are discarded. The Hardware
Controller 6.3.0 and ER7212PC 6.2.14 exports document the operation. The CBC
description explicitly says the built-in RADIUS function cannot be called
through that API. Fixture tests do not establish live support.

`controller_radius_proxy` also has a controlled PATCH plan. Its source schema
is documented in Hardware Controller 6.3.0 and ER7212PC 6.2.14 only; CBC's
similarly named route is MSP-scoped and is not treated as the same operation.
The PATCH is fixture-tested and remains unverified on live hardware.

`GET /v1/capabilities` requires the same caller bearer token as the inventory
routes. It lists the implemented operations and observations collected by
this running process. Reading this endpoint does not contact the controller
or start a diagnostic operation.

The response identifies its catalog with
`catalog_scope: instrumented_openapi_operations` and `catalog_complete: false`. It is a partial
catalog of instrumented OpenAPI operations, not a complete list of every
connector route or every route that is not implemented. Its entries do not
infer fixture coverage or documentation presence; those facts are not part of
this runtime catalog. Controller-export comparisons remain a separate,
documentation-only source.

`GET /v1/diagnostic-capabilities` and the MCP tool
`omada_diagnostic_capability_summary` group those same in-process records into
the complete WLAN, client, AP, gateway, switch and site-network read workflows.
Each required operation is labelled `documented`, `observed`, `unknown` or
`failed`. `observed` requires a successful controller response and a supported
projected shape; a fixture is not live evidence. A workflow with any recorded
required-read failure is labelled `failed` and also reports per-operation
counts. The report reuses the current catalog and makes zero network requests.

Documented-source counts refer to the three checked-in API exports. They do
not identify the controller connected to this process, and a route documented
for an export is not evidence of permission or live support on the user's
controller. Unknown or mixed evidence stays unknown; the workflow report never
probes missing operations.

The bounded WLAN/network mapping workflow is available through
`GET /v1/sites/{site_ref}/ssid-network-summary` and
`omada_ssid_network_summary`. It reconciles up to 64 SSID bindings, then checks
VLAN/LAN detail and DHCP pool counts for at most 32 matched networks, site DNS
settings, and internet metadata for at most four known gateways. It returns
only aggregate counts and redacted settings. A site DNS setting is not proof
of an SSID-specific resolver path, and gateway inventory is not proof of a
network-to-gateway attachment; both relationships remain unknown. Partial
inventories and unavailable reads remain visible in the result.

### Controller threat severity counts

`GET /v1/controller/threat-severity-summary?start_ms=...&end_ms=...` and
`omada_controller_threat_severity_summary` read the controller's documented
critical, major, moderate, minor and low threat counts for a caller-selected
window capped at 24 hours. The connector returns only those five counts;
missing source fields are `null` and set `partial=true`.
It does not return threat records or identifiers. All three source exports
document `getThreatCount` at the same upstream GET route. The source describes
the bounds as int64 timestamps without stating their unit; the public connector
currently interprets them as UTC epoch milliseconds. HTTP, MCP and fixture
checks pass. A synthetic five-field payload used 31 source tokens and 41
connector-result tokens (10 more; 32.26%) with `js-tiktoken` 1.0.21 and
`o200k_base`; HTTP/MCP framing and agent billing are excluded. This direct
summary is compact but does not reduce tokens relative to the already-aggregated
upstream response. Live support and timestamp-unit compatibility on hardware
remain unknown.

A fresh process starts with unknown support. Permission evidence and support
evidence are separate: an HTTP/operation success can establish permission for
that call, while support becomes verified only when that operation's response
passes its completeness checks. Permission is denied only after an explicit
permission error; otherwise it remains unknown. Partial or incomplete
responses, and an empty `data` object, leave support unknown. A valid empty
inventory is not treated as unsupported. Generic errors, missing fields or
absent scan results never establish hardware or firmware non-support. Numeric
upstream error codes are retained without raw messages or payloads. Evidence
for one AP does not certify another AP. Hardware and firmware support remain
unknown because no unambiguous explicit hardware/firmware signal is evaluated.
Evidence is bounded and process-local; restart clears it. Site and device
references change on restart unless a persistent reference key is configured;
client snapshot references remain short-lived in either mode.

The five client event timeline routes (`connect`, `disconnect`, `roaming`,
`blocked`, and the compatibility alias `association`) have separate runtime capability entries. Each uses a known
client reference and a type-specific controller GET capped at 24 hours. The
routes select documented event types: connect `0`, wireless disconnect `1`,
roaming `2`, and blocked `3`; `association` remains an alias for type `1`.
The projection retains timestamps, documented numeric `event_type` codes, and
opaque same-site AP references when known; it omits raw text, attributes and
MAC addresses. A session is included only
when it has a valid MAC matching the selected client. Sessions with missing,
invalid or mismatching MACs are omitted and mark the response partial; no
session data is implicitly attributed. All three supplied exports document
the operation; fixture coverage is not live
support evidence, and no universal support is claimed.

The site client-roaming backtrack summary is a separate read-only workflow. It
compares documented roaming, disconnect and connect events for explicitly
selected current clients. Consecutive reciprocal roaming events (`A` to `B`,
then `B` to `A`) count as a return only when no disconnect is observed between
them; a disconnect, reconnect after separation and incomplete event source are
reported separately. Both AP references must bind to the current site
inventory. Counts are grouped by AP pair and affected-client count; client
references are omitted. Unknown mappings and timeline gaps remain visible. It
does not infer why roaming occurred, and it has no live-controller evidence.

The selected-AP uplink-path summary joins current device inventory with the
documented wired-uplink and mesh-statistics reads. A next hop is reported only
when its source MAC maps uniquely to a current same-site device reference; an
AP mesh parent is bound only through the AP inventory. A known one-hop link
does not claim the unqueried continuation. Nonzero drop/error counters and
documented inventory states are review signals, not causes or rates; raw
addresses and names remain omitted. Unknown segments and unavailable reads are
explicit, and no scan is initiated.

The separate client-health timeline is a read-only operation bound to a fresh
site-bound client reference. It requests a fixed 24-hour window in
milliseconds and projects only timestamps and raw int32 scores without a
scale. Missing, invalid or out-of-window values mark partial. All three
supplied exports document the GET; it has fixture coverage only and no live
support evidence.

Controller device-access settings are exposed as a fixed read. The projection
accepts only the three documented Boolean switches and reports missing,
invalid or newly added fields as partial; it never exposes the associated
PATCH operation. The GET appears in all three supplied exports with
Global Other Setting View Only permission. Fixture coverage does not establish
live support.

Controller remote logging is exposed as a fixed read. Its projection returns
the required enabled Boolean plus validated presence flags for the optional
host and port; it omits both network values. Unknown fields mark the response
partial. The GET appears in all three supplied exports with Global Other
Setting View Only permission. Its PATCH and separate `syslog/tip` operation
remain distinct: PATCH is not exposed, while `syslog/tip` has its own fixed
read route and MCP tool using the same redacted projection. Live support is
unknown.

Client history is a separate paginated read bound to a fresh client reference
from the selected site's inventory. Each returned row is internally checked
against the requested client MAC; raw identity and private fields are never
projected. The output is limited to validated raw int64 `download`, `upload`,
`duration`, `lastSeen`, `associated`, int32 `port`, `vid`, `reasonType`,
`associationTime`, and boolean `guest`, with no inferred units, enum meanings
or causes. Missing, invalid or unknown fields and omitted/unmatched rows mark
partial. Paging stops with an error at configured `max_pages`, never a
silently truncated result. All three offline exports document the operation;
fixture evidence is not live verification. The controller has no documented
snapshot token, so page contents may shift during concurrent updates and an
atomic complete history is not guaranteed.

The site-wide Wi-Fi channel overview is a read-only projection of the
documented dashboard response. It reports aggregate AP/client counts and the
documented mean channel utilization in percent for each returned band/channel.
Absent band arrays are partial, while a null utilization value means no data.
The operation appears in all three supplied exports; the ER7212PC export has
an unresolved schema reference for the utilization type. There is no live
verification or guarantee of support across controller families or versions.

The catalog lists implemented radio, DNS-cache, SSID, gateway IPv6
IP-passthrough, single-port PoE, switch-port-status, site band-steering,
RRM mode, site LED, AP AFC, site LLDP-setting, AP channel-limit and gateway
tag-outbound-QoS change-preview routes.
Their presence establishes neither write permission nor controller support.
A preview alone does not establish that a write succeeded. Every corresponding
apply route also requires `OMADA_ENABLE_WRITES=true`, a ready durable journal,
a persistent reference key, and a separate valid short-lived approval
envelope in the request body.

Switch-port status also has a read route. Its preview flag
`disruption_confirmed: true` is an acknowledgement field, not evidence of
separate user approval. `tools/approve_plan.py` displays the exact preview and
requires the interactive response `FREIGEBEN` before signing its digest.
Port status uses `0` for off and `1` for on;
turning a port off can disconnect an uplink, access point or management path.
The route appears in the three supplied controller exports, has no live write
test, and provides no universal support guarantee.

The approval uses HMAC with a separate private 32-byte operator key. The server
holds that same symmetric key, so a compromised server can forge approvals;
the opaque operator ID does not authenticate a natural person. Nonce use is
process-local and the journal is not a durable personal approval audit.

Band-steering has a redacted GET, preview and journal-bound apply route. Its
three documented modes are `0` off, `1` prefer 5/6 GHz and `2` balance. The
current-state response is rejected when fields are missing or unknown. A mode
change may interrupt clients, and the preview acknowledgement does not replace
personal approval. The GET/PATCH contract is present in all three supplied
exports, but no live write verification or universal support is claimed.

The site optimization/RRM read checks the four core fields `mode`,
`timeRangeEnable`, `resource`, and `timeRangeAction`; when optional
`timeRangeId` is present, its type is checked before the value is redacted.
This is a response-shape check, not a hardware or firmware support signal. The
narrow RRM mode preview/apply flow additionally requires all five fields,
`timeRangeEnable=false`, and the read `timeRangeId` to be empty. Unknown,
incomplete or additional state blocks the plan; only `mode` changes and the
other fields are sent and read back unchanged. The API does not define the
empty ID's meaning, and effects on time ranges are unverified. The route is in
all three supplied exports but has no live write verification. RF optimization
may change WLAN parameters and interrupt clients; preview acknowledgement does
not replace personal approval.

The site roaming view is read-only. It projects five documented booleans;
missing or unknown fields mark the response partial. Some supplied exports
mark two options deprecated. No site-roaming write route is implemented, and
these schema facts do not prove controller, hardware or firmware support.

The site LED route has a strict boolean `enable` GET/PUT contract and a
journal-backed preview/apply flow with approval and readback. The API does not
specify which devices are affected. It appears in all three supplied exports,
but has no live write verification or universal support guarantee.

The site-level LLDP setting has a redacted GET and a journal-backed
bool-only preview/apply flow using the documented nested
`{"lldp":{"enable":bool}}` body. It is distinct from the switch
LLDP-neighbor read. The API does not specify affected devices, and no network
effect is inferred. It is documented in all three exports, with no live write
verification or universal support guarantee. Its apply still requires a
separate personal approval; HMAC does not identify a person.

The site-level channel-limit setting is deprecated and read-only. AP
channel-limit preview is available only when the full AP response has
`supportChannelLimit=true`, an integer `channelLimitType` in 0–2, and both
boolean default fields. One AP's `channelLimitType` is changed per plan and the
complete prior state is bound into approval. Documented values are `0` default,
`1` false and `2` true; no further technical or regulatory effect is inferred.
This feature has no live write verification or universal support claim.

AP OFDMA has a documented redacted GET plus a separate, default-off preview
and apply for one supported band enable field. A plan requires the full eight
booleans in both before and target state, exactly one changed enable field,
and its corresponding reported support flag true. Journal intent, stale-state
checking, separate HMAC approval, full eight-field readback and no-replay are
required. All three supplied exports document GET/PATCH, but no write or live
compatibility has been verified. Partial PATCH behavior and effects on other
settings or clients are unknown; readback detects changes after dispatch but
cannot prevent them. A change may interrupt clients and requires personal
approval. Runtime capability evidence remains separate from support; no
hardware or firmware support is inferred.

AP Advanced QoS has a read-only GET for eight optional booleans: `support2g`,
`support5g`, `support5g2`, `support6g`, `deliveryEnable2g`,
`deliveryEnable5g`, `deliveryEnable5g2` and `deliveryEnable6g`. Missing,
invalid or unknown fields mark the read projection partial. The `support*`
values describe band-related support, not support for the QoS function. The
GET and PATCH are documented in all three exports. The PATCH has a journaled,
operator-approved preview/apply path. It requires the four support flags and
only the delivery values for supported bands; any unknown support or missing
required value blocks the plan. The 5-GHz split mapping is source-backed and
covered offline. One live GET omitted the 5-GHz-2 and 6-GHz delivery values,
but the saved acceptance record does not include the corresponding support
flags. No live QoS write has been verified.

AP LAG is a read-only GET of `supportTrunkSetting`, `enable` and `mode`.
Missing, invalid or unknown fields mark partial; mode is returned unchanged as
documented integer 0, 1 or 2. The support flag does not establish a hardware
or firmware cause. All three supplied exports document the GET; it has
fixture coverage only and no live support evidence. There is no write route:
LAG depends on uplink, VLAN, PoE-Out and port states that are not safely bound
by this operation, and changing it can disrupt connectivity. This does not
assert controller/device non-support.

The site client-signal distribution is a separate aggregated GET. Its five
documented categories are `poorSignal`, `weakSignal`, `averageSignal`,
`stableSignal` and `strongSignal`; each has five optional int32 fields:
`totalClients`, `clientsPercent`, `clients2g`, `clients5g` and `clients6g`.
The projection assigns no unit or scale to `clientsPercent` and no RSSI
thresholds to category names. Missing, invalid or unknown fields mark partial;
client names and MAC addresses are omitted. All three supplied exports
document this route. It has fixture coverage only, so runtime support remains
unknown and there is no universal compatibility claim.

AP AFC reads only the documented boolean `supportAfc` and `enable` fields. A
successful GET establishes read-endpoint success; `supportAfc: false` is a
reported device value, not a hardware or firmware diagnosis, and blocks the
preview. Apply is limited to the documented boolean `enable` field, with a
journal, stale-state check, readback and separate approval. The three supplied
exports document this contract; no live write or compatibility verification
exists. The documentation makes no claim about effects beyond AFC support
indication and enabling AFC.

The AFC operating-status read is a separate resource from configuration:
`GET /v1/sites/{site_ref}/aps/{device_ref}/afc/status` maps to the documented
`/sites/{siteId}/aps/{apMac}/afc` GET. Its nine optional boolean/integer values
are projected with raw second values and raw error codes; no calendar
conversion or error interpretation is applied. Missing, invalid or unexpected
values mark the result partial and leave support unknown. This read is in all
three supplied exports, has no live verification and makes no controller
change.

Site overview and AP RF responses now have operation-specific completeness
checks before a successful response can establish support. AP RF scan checks
distinguish an absent band field from a present band with an empty list: absent
fields mark the projection partial and keep support unknown, while a returned
empty list is treated as an actual empty result. Neither case claims hardware
or firmware non-support. Other operations
without their own completeness contracts can report successful execution, but
that is limited evidence and does not claim complete API feature detection.
Hardware and firmware support remain unknown unless a separate explicit signal
is actually evaluated.

The site RRM incompatibility view is a paginated read. It uses only inventoried
AP references, preserves documented status values without interpretation, and
omits names and MACs. Unknown or ambiguous AP mapping marks the response
partial. The schema does not give the reason for an incompatibility. It is
fixture-tested only and has no live support evidence.

The catalog also lists the site Wi-Fi health timeline, switch LLDP-neighbor
summary and switch health detail as implemented read routes. The supplied
Hardware Controller 6.3.0, ER7212PC 6.2.14 and CBC Standard 6.3.0 exports
document all three routes. They have fixture tests but no live verification;
their support remains unknown until a successful operation is observed for
the relevant target. The health views use a fixed 24-hour window. LLDP output
contains local port numbers and counts of returned neighbor rows only.

The site switch-health history report also uses the documented batch timeline
GET from all three exports. It refreshes the site's switch inventory, requests
at most 64 unique switch MACs in one fixed 24-hour window, and maps documented
timeline rows back to opaque references. Missing, ambiguous and excess devices
remain visible as partial data. The source gives integer scores but no scale;
the report does not rank switches or infer severity. This is fixture-tested;
live support remains unknown.

The site switch-port anomaly summary is a bounded HTTP/MCP workflow over the
fresh device inventory and the existing switch port overview and counter
feeds. It reports raw port status codes and nonzero cumulative error counters
as review signals without decoding controller-specific status codes. The
documented per-port counter response contains error totals but no drop
counters; one snapshot cannot provide rates or trends. No live read has
been performed for this workflow.

The AP health-score timeline is a separate, read-only AP route. All three
supplied exports document its endpoint. The connector fixes the window at 24
hours and projects redacted timestamps and int32 score values without
inventing a score scale. Missing or invalid values and out-of-window samples
mark the response partial. It has fixture coverage only and no live support
evidence.

The separate `CONTRACT_MATRIX.json` records a selected set of reviewed
operations and their presence in the three supplied API exports; its live
support values remain unknown. The reduced route catalog and
`OPERATION_EVIDENCE.json` cover the full union of documented method/path
entries, but that ledger records only static route and test-file hints. Neither
document proves behavior, remote support or app privileges. The original API
exports remain outside the repository.

Hardware Controller 6.3.0, ER7212PC 6.2.14 and CBC Standard 6.3.0 all document
the selected operations. Other controller families/releases require an
appropriate export and runtime evidence. Cloud/system-CA behavior has fixture
tests but no live cloud test in this project.


AP load-balance is a read-only GET projecting four documented bands: `2g`,
`5g`, `5g2` and `6g`. Each has boolean `maxClientsEnable` and `rssiEnable`,
plus integer `maxClients` (1–512) and `threshold` (-95–0). Missing, invalid
or unknown fields mark the result partial. The projection does not invent
`5g1`. The GET appears in all three supplied exports and has fixture coverage
only; live support remains unknown. No PATCH is implemented because the PATCH
schemas include `5g1` fields absent from GET and partial-update preservation semantics are unclear. This
is not a claim of non-support.


AP antenna settings are available through a read-only GET. The projection
includes global `antMode` (0–3) and `omniAntState` (0–2), and four per-band
`antSetting*` objects for `2g`, `5g`, `5g2` and `6g`. Nested fields are
validated as int32; only `antPattern` has the documented 0/1 bound. No other
gain range or effect is inferred. Missing, invalid or unknown fields mark
partial. All three supplied exports document the GET; it has fixture coverage
only and no live verification. No write route is implemented because update
semantics and dependencies are unclear. This does not mean the feature is
unsupported.


AP antenna gain has a separate read-only GET. Its `anteGainList` contains
`radioId` integers 0–3 and `anteGain` integers 0–30, as documented; no unit
or regulatory meaning is inferred. Missing, invalid, unknown or duplicate
entries mark partial. All three supplied exports document the route; it has
fixture coverage only and no live verification. No PATCH is implemented while
list-level partial/full semantics and effects on other radio settings remain
unknown. This does not imply the feature is unsupported.


The site Wi-Fi sub-health detail route reads the documented timeline endpoint
for a fixed 24-hour window in milliseconds. It projects only whitelisted raw
score, support, interference and onboarding values without assigning scales,
causes or units. Incident records are excluded, including IDs, MAC addresses
and free text. Missing, invalid, unknown or out-of-window values mark partial.
All three supplied exports document the route; it has fixture coverage only
and no live support verification. The ER7212PC 6.2.14 export omits the
onboarding dimension and extended interference-average schema, leaving those
values unknown/partial when unavailable.


AP power-saving is a read-only GET. The projection accepts `mode` 0–3, three
documented booleans (`timeEnable`, `bandEnable`, `supportPowerSaving`), band
entries 0–3, and documented hour/minute bounds. `idleDuration` is kept as
int32 without an inferred unit or extra range. Missing, invalid or unknown
fields mark partial; `supportPowerSaving` is not used to infer a cause. All
three supplied exports document the GET, but ER7212PC 6.2.14 does not document
`mode`, so that field remains missing/unknown. No PUT is implemented given
the schema difference, unclear partial/full semantics and unverified supported
bands. This establishes neither live compatibility nor non-support.


The AP VLAN route is a read-only V2 GET. It projects `mvlanSetting` and
`voipVlanSetting` with mode values 0/1, optional bridge VLAN fields as int32,
and VoIP `ipType` 0/1. Raw `lanNetworkId`, IP, mask, gateway and DNS values
are fully omitted. Missing, invalid or unknown fields mark partial. The V2
route is documented in all three supplied exports and has fixture coverage
only; live support remains unknown. No PUT is implemented because management
VLAN/IP changes could affect the uplink and full/partial update semantics are
unclear. This is not a finding of non-support.


AP wired-uplink is a read-only, redacted GET. It projects documented duplex,
port type, rate, byte/packet/drop/error counters, activity and link values
with schema types; it does not add interpretations beyond the source. Optional
`poeState` and `voipState` appear in the Hardware Controller and CBC 6.3
exports, not ER7212PC 6.2.14. Names, MAC/IP addresses, stack/port IDs and
model data are omitted. Missing core, invalid or unknown fields mark partial;
optional readings may be absent. ER sensor schemas have unresolved numeric references. All
three exports document the route; fixture coverage exists, but no live support
verification. No write function is implemented.

AP LAN traffic is a separate read-only GET for a known AP reference bound to
the selected site. It projects eight optional nonnegative int64 counters:
`rxPkts`, `txPkts`, `rx`, `tx`, `rxDropPkts`, `txDropPkts`, `rxErrPkts` and
`txErrPkts`. The source documents `rx`/`tx` as byte totals and the rest as
packet counts. No rate, time window, reset or health inference is made.
Missing, invalid or unknown fields mark partial. All three offline exports
document the route; fixture coverage is not live verification, and the read
route makes no changes.


Switch-port counters are exposed through a read-only paginated site-level GET,
then filtered to rows uniquely matching the inventoried target switch. The
projection contains current cumulative counters, not rates or time series.
Sensitive names, MAC/IP addresses, stack details and port labels are omitted.
The route appears in all three supplied specifications; tests are simulated
fixtures only, with no live support claim.


Switch-port PoE information is a read-only paginated site-wide GET filtered to
rows uniquely associated with the inventoried switch. The projection omits
sensitive names and identifiers and accepts only finite numeric measurements;
it does not infer units or PoE support from these values. Port numbers have a
conservative connector bound of 0–4096. The ER7212PC schema has ambiguous PoE
measurement types. Test coverage uses simulated fixtures only, with no live
verification or support conclusion.

`site_poe_schedule_summary` reads a fresh switch inventory, PoE-port inventory,
documented per-switch usage/capacity, current port PoE fields, schedule targets
and time-range profile IDs. It joins MAC addresses only inside the projection
and returns opaque switch references. Same-row usage and capacity values are
reported as watts only when the ER7212PC contract documents both fields.
Current port readings are reduced to counts by raw status code and measurement
presence; numeric measurements and port identities are omitted. Schedule names,
profile names, IDs and timestamps are omitted; the
next-execution field is reduced to presence because its unit is undocumented.
The other two exports have generic response schemas. Fixtures cover the
projection and route, but no controller or live support was tested.

`site_stack_connections_summary` reads the documented site stack list and a
bounded LLDP page for each stack. Stack member MACs are joined internally to
unique references from a fresh switch inventory. Output keeps opaque stack and
switch references, documented status codes, and local stack-port neighbor
counts; names and LLDP neighbor identities are omitted. Because `deviceId` is
not contractually tied to inventory MACs, these counts are not topology edges.
The export schemas are detailed only in ER7212PC; hardware support remains
unknown and no live controller read was made. The existing site topology
response includes the same stack section and marks the combined report partial
when stack coverage is incomplete.


Gateway health timeline is a redacted read using an opaque inventoried
`gateway_ref` and a fixed 24-hour interval. It returns millisecond timestamps
and raw int32 scores without an invented scale. Missing, invalid or
out-of-window values mark partial; unknown fields are omitted. All three
supplied specifications document the route. It has simulated-fixture tests
only, with no live support claim.

Gateway WAN speed-test results use the fixed read-only
`GET /v1/sites/{site_ref}/gateways/{device_ref}/speed-test-results`, bound to
an inventoried gateway. The projection keeps numeric status, port and WAN
entry identifiers, timestamps, latency, transfer counters and progress. Port
names, ISP and server/location text are removed; malformed and unknown values
mark the response partial. The gateway diagnostic reads only stored results
and never starts a test. All three supplied specifications document the
upstream route; fixture-backed tests cover the projection, fixed path,
inventory binding, HTTP/MCP dispatch and bundle inclusion. Live support is
unknown.


Switch-port name changes use
`POST /v1/sites/{site_ref}/switches/{switch_ref}/ports/{port}/name-preview`
and `POST /v1/switch-port-name-plans/{plan_id}/apply` for one uniquely
identified inventoried port. Approval binds the exact prior and target names;
an absent or
invalid prior name blocks preview, while an empty prior name is valid. Apply
performs a stale-state check, one PUT and a readback. Uncertain outcomes stay
in-doubt and are not automatically retried. Journal entries contain only a
fixed name-redaction marker, never the name or a name hash. Writes default off
and each change requires explicit operator approval of that exact plan. The
operation appears in all three supplied exports and has simulated-fixture
tests only, with no live support verification.


Site DPI/traffic logging has a complete GET/PUT contract over exactly two
booleans, `dpi` and `loggingTraffic`. The protected preview changes exactly
one value while carrying the other unchanged; approval binds full before and
target state. Stale checking, journal intent, one-use apply and complete
readback are required. Unknown outcomes stay in-doubt without automatic retry.
Writes default off and require explicit operator approval of each exact
plan. Enabling traffic logging can record usage data; DPI side effects are
unknown. All three supplied specifications document GET/PUT; there is no live
verification.


Gateway VoIP prioritization exposes a complete GET/PUT state with `enable` and
`sipUdpPort`. Preview changes only `enable` and preserves the port in the full
request and requires `disruption_confirmed: true`, which is not user approval. Because the
export marks the port optional, the connector conservatively requires it and
validates 0–65535 even when disabled; missing or invalid state fails closed.
Apply requires stale checking, journal, one-use HMAC approval and readback;
uncertain outcomes are not replayed. The setting may affect VoIP traffic and
success is not guaranteed. Writes default off and each actual change requires
explicit operator approval. All three offline specs document GET/PUT, without
live verification.


Gateway tag-outbound QoS exposes a site-level GET and guarded preview/apply.
The state must contain four ordered rows with exactly `classType`, `enable`
and `dscp`; classes 0–3 must each occur once, and the DSCP value must be one
of 20 explicitly allowed strings. Empty, unknown or malformed values fail
closed. Preview changes only one class's `enable`, preserving order and all
DSCP values in the full target. Apply requires write opt-in, journal, expiry
and full before-state recheck, a separate one-use approval, a single PUT and
complete readback; uncertain outcomes are not retried. The ER7212PC example is
contradictory, site-wide QoS side effects are unknown, and there is no live
verification. Writes default off and each actual change requires explicit operator approval. All three supplied exports document GET/PUT.


The AP speed-test result (`GET /speed-test-result`) is a read-only, site-bound route documented in all three exports. It returns existing link-speed state and results; no speed test is started. The ER7212PC export describes the result as a referenced object while its example and the other two exports describe a map of result objects. The bounded projection accepts either documented shape, removes controller error messages and AP MAC addresses, and maps known APs to opaque references. It has fixture and MCP/HTTP dispatch tests; live support is unknown.


Gateway DHCP lease classification uses the paged `GET /v1/sites/{site_ref}/gateways/{gateway_ref}/dhcp/leases` route for a gateway already present in that site's device inventory. The matching MCP tool requires `gateway_ref`. The projection returns only opaque lease references and the documented device/client and dynamic/static binding classifications, with aggregate counts. IP and MAC addresses, host/network names, network IDs and remaining lease times are discarded. Pagination uses the response's total and current-page metadata and fails rather than returning a silently truncated list. The same route, pagination fields and row schema appear in all three supplied exports. Fixture tests cover pagination, fixed path and query, gateway binding, redaction and HTTP/MCP dispatch; live support remains unknown.


Gateway internet metadata uses the fixed `GET /v1/sites/{site_ref}/gateways/{device_ref}/internet-info` route. It returns the documented WAN support booleans, selected non-identifying setting codes and counts grouped by raw `onlineDetection` code. It does not assign online/offline meanings to undocumented codes. Gateway/port/VLAN identifiers, WAN settings, network labels and address-bearing configuration are omitted. The same schema and permission choices are present in all three supplied exports; fixture tests cover the projection, fixed request, inventory binding, HTTP/MCP route and gateway diagnostic. Live support remains unknown.

Virtual WAN inventory is available at `GET /v1/sites/{site_ref}/virtual-wan-summary`. It reads the virtual WAN grid and available-virtual-WAN list. Their `id` and `virtualWanId` fields are both explicitly described as the virtual WAN ID, so the projection reports matches only for unique values and separately counts unmatched and ambiguous rows. It omits names and identifiers. The exports do not define how `physicalWanId` or `physicalWanPortId` maps to physical port configuration or current WAN status; those remain separate facts. Live support is unknown.

Site switch-family support is available through the read-only
`GET /v1/sites/{site_ref}/switch-support` route and MCP tool
`omada_site_switch_support`. The request is bound to a known site. The
projection returns strict booleans for `support_es` and `support_l2`, which
the three supplied exports describe as support for Agile and non-Agile Series
Switch adoption. Missing, invalid or additional response fields mark the
result partial; unrelated fields and labels are omitted. The route and schema
are identical across the three exports. Local tests cover each flag, exact
upstream route, site binding, HTTP and MCP dispatch. Live support remains
unknown.


Incident notification settings are available at
`GET /v1/sites/{site_ref}/incidents/notification` and through
`omada_site_incident_notification`. The projection accepts the documented
Hardware/CBC `email` object and ER7212PC `Email Alerts` variant, including the
ER example's single event-category key. It returns only allowlisted event
flags, alert-delay settings, the resource code and recipient count. Recipient
addresses and all unrecognized values are discarded. The exports name
`Incidents Page View Only` for Hardware/CBC and
`Site Health & Incident Manager View Only` for ER7212PC. The ER7212PC route
description is explicitly Omada Pro only; support on the controller family
used for other products is unknown. Offline tests cover projection variants,
redaction, validation, site binding and HTTP/MCP dispatch. No live request was
made.

Site anomaly event settings are available at
`GET /v1/sites/{site_ref}/incidents/settings` and through
`omada_site_anomaly_event_settings`. The fixed upstream request reads page 1
with a page size of 100 and accepts no caller-supplied filters. It returns
bounded event codes, category/level/enable flags, recognized object types,
optional fixed statistics and an explicit `has_more`/omitted-row count. The
free-form parameter names and values are omitted and counted. Hardware/CBC
category codes use 11–19, while ER7212PC documents 0–9; codes remain numeric
because the exports use different category schemes. All three exports require
`Incidents Page View Only` or, for ER7212PC, `Site Health & Incident Manager
View Only`. ER7212PC marks the operation Omada Pro only. Offline tests cover
the projection, page cap, exact query, site binding, and HTTP/MCP dispatch;
live support is unknown.

Incident influence summaries are available through
`omada_site_incident_influencing_clients` and
`omada_site_incident_influencing_devices`. Each request requires a fresh
opaque `incident_ref` from a device/client health-incident read. The connector
keeps the corresponding MAC and anomaly code in memory, so callers cannot
provide arbitrary identifiers, search text, filters or sort fields. Requests
read one fixed page of at most 100 rows. The result can include site-bound
opaque entity references plus documented connection, status and health codes;
MAC addresses, IP addresses, display names and model labels are discarded.
Unknown identities and later pages are counted and mark the result partial.
Hardware Controller and CBC Standard document both routes with
`Incidents Page View Only`; ER7212PC does not document them. Offline tests
cover snapshot binding, redaction, exact requests and HTTP/MCP dispatch. Live
support remains unknown.

WLAN group capacity is available at `GET /v1/sites/{site_ref}/wlan-group-capacity`
through `omada_site_wlan_group_capacity`. It returns only the WLAN-group count
and limit flag. The source marks this legacy GET for future deprecation in
favor of the AP-group count route. The newer
`GET /v1/sites/{site_ref}/ap-group-capacity` and
`omada_site_ap_group_capacity` return an AP-group count and a limit flag. The
documented count is controller-wide, despite the site-scoped request. Both
exports require `Site Settings Manager View Only` or
`Network Config Page View Only`. All three API exports document the legacy
route; Hardware Controller and CBC document the newer route, while ER7212PC
does not. Offline tests cover strict values, site binding, exact upstream
routes and HTTP/MCP dispatch. Live support remains unknown.

The paginated AP-group inventory is available at
`GET /v1/sites/{site_ref}/ap-groups` through
`omada_site_ap_group_summary`. It returns group and AP counts, bounded
remaining-SSID-binding totals, and documented per-band SSID limits. Group IDs,
group names and SSID labels are discarded. Hardware Controller and CBC
Standard document `getApGroupList` with `Site Settings Manager View Only` or
`Network Config Page View Only`; ER7212PC does not document this route. The
fixed reader fetches bounded pages and accepts no caller filters. Offline
projection, paging, HTTP and MCP tests cover the implementation; live support
remains unknown.

A synthetic 12-group response was serialized and counted with js-tiktoken
1.0.21 using `o200k_base`: the raw JSON used 712 tokens and the projected
summary used 163, saving 549 tokens (77.11%) for the result payload. This
fixture comparison excludes HTTP framing, MCP schemas, prompts and host
overhead; it is not a live controller or agent-billing measurement.

AP OUI-based VLAN rules are summarized at
`GET /v1/sites/{site_ref}/ap-oui-rules/summary` through
`omada_site_ap_oui_vlan_rules_summary`. The reader follows the documented
paginated `getGridApOuiBasedVlan` route and returns only rule-state, SSID-binding,
VLAN-assignment and priority counts. It omits rule and profile IDs, all names,
SSID labels, and VLAN values. Hardware Controller, CBC Standard and ER7212PC
document the same response fields. The operation does not specify a permission
in the supplied contracts. Fixed paging, bounded projection, HTTP and MCP
dispatch are fixture-tested; live support remains unknown.

A synthetic 12-rule response with nested SSID and VLAN assignments used 1,507
tokens as raw JSON and 123 tokens after projection using js-tiktoken 1.0.21 /
`o200k_base`, saving 1,384 tokens (91.84%) for the result payload. This counts
serialized JSON only, excluding transport, schemas, prompts and billed agent
usage; it is not live evidence.

Per-network DHCP server capabilities are exposed at
`GET /v1/sites/{site_ref}/networks/{network_ref}/dhcp-server/capabilities`.
The network reference must come from that site's network inventory. The
projection accepts only the two documented booleans for reading the DHCP
client table and server information; missing, invalid and extra fields are
reported without exposing raw response data. The supplied API descriptions
require `Site Settings Manager View Only` or `Network Config Page View Only`.
Fixture tests verify the request binding and projection. No live controller
response was observed, so support and permission remain unverified.


The per-network DHCP pool reader is exposed at
`GET /v1/sites/{site_ref}/networks/{network_ref}/dhcp-server/info`. It returns
a bounded count of the documented pool ranges and the sum of valid available-IP
counts. Range start/end addresses are never returned. Missing, malformed,
unknown, and omitted range data marks the response partial. All three supplied
API descriptions state `Site Settings Manager View Only` or `Network Config Page
View Only`. Projection, reference binding, HTTP/MCP dispatch, and the fixed GET
are covered by fixtures; no live response has been observed.


Controller client-recognition status is available at
`GET /v1/controller/settings/client-recognition`. All three API exports
document the same `enable` Boolean and `Global Other Setting View Only`
permission. The projection emits only that strict Boolean and counts missing,
invalid or additional fields; it does not change the setting. Fixture tests cover
projection, exact controller-bound GET, HTTP/MCP dispatch and path rejection.
No live controller response has been observed.


Controller device statistics are available at
`GET /v1/controller/devices/statistics`. The projection returns only the 14
documented int32 inventory, activation and device-health counters. Nested
switch/EAP/gateway health objects are omitted because their response schemas
are inconsistent across the supplied exports; their presence marks the response
partial. All three descriptions list `Site Device Manager View Only` or `MSP
Device Manager View Only`. Fixture tests cover each scalar mapping, malformed
values, exact GET, response redaction, HTTP/MCP dispatch and controller binding.
No live controller response has been observed.


Controller client active-timeout is exposed at
`GET /v1/controller/settings/client-active-timeout`. All three exports
document the int32 field `clientActiveTimeoutMin` and the permission `Global
Other Setting View Only`. Their description says 3–10 minutes but the ER7212PC
example uses `0`; the connector preserves the valid int32 without enforcing
that contradictory range. Projection, exact GET, redaction, HTTP/MCP dispatch
and controller binding have fixture coverage. No live response has been
observed.


Controller client-history retention is exposed at
`GET /v1/controller/settings/client-history`. All three API exports document
the `clientsDataEnable` and `clientStatEnable` Boolean flags and the
`Global Other Setting View Only` permission. Focused projection and route tests
and HTTP/MCP dispatch tests pass; live support remains unknown.


Global audit-log notification settings are exposed at
`GET /v1/controller/settings/audit-notification`. All three exports document
the route and `Global Log & Audit Log Manager View Only` permission. The
projection returns only webhook enablement, identifier presence and aggregate
category counts; webhook IDs, category keys and labels are omitted. Focused
projection, route, redaction and HTTP/MCP dispatch tests pass; live support
remains unknown.


Controller UI interface preferences are exposed at
`GET /v1/controller/settings/ui-interface`. All three API exports document the
same fields and `Global Other Setting View Only` permission. Time-zone,
refresh-rate and MAC-format values remain raw documented numeric codes; no
meaning is inferred for the MAC-format code. The private-label URL, file ID and
filename are never returned; the projection exposes only whether each bounded
string is present. Fixture tests cover field validation, redaction, exact GET,
HTTP/MCP dispatch and controller binding. No live response has been observed.


Controller data-retention settings are exposed at
`GET /v1/controller/settings/retention`. The bounded projection retains only
the documented enable flags, int32 retention values and bounded lists of
available retention-day values. It does not modify retention or infer support
from a missing optional field. The route and field schema are present in all
three API exports; the permission is `Global Other Setting View Only`.
Projection, shape limits, exact GET, HTTP/MCP dispatch and controller binding
have fixture coverage. No live response has been observed.

Controller daylight-saving status is available at
`GET /v1/controller/dst-info`. The projection validates mode, offset, timestamps,
month/week/day/hour/minute fields and the bounded time-zone string. It preserves
documented numeric codes and milliseconds without converting timestamps to local
time. A sparse response with DST disabled is valid; otherwise omitted fields,
malformed values or unknown properties mark the result partial. All three exports
document the same response; they state no specific permission. Fixture tests cover
the exact GET, controller binding, validation and HTTP/MCP dispatch. No live
response has been observed.


Controller experience-improvement participation is available at
`GET /v1/controller/settings/experience-improvement`. The route returns only
the documented strict Boolean `expImprove`, requires `Global Other Setting View
Only`, and does not change the preference. All three supplied API exports
document the same field. Projection, exact GET, controller binding and HTTP/MCP
dispatch have fixture coverage; no live response has been observed.


Controller client-detail data settings are available at
`GET /v1/controller/client-detail-information`. The projection returns only the
five documented strict Boolean flags for client recognition, health, history,
data trends and following MSP settings. It does not read client records or
change the settings. All three exports document the route and
`Global Other Setting View Only` permission. Fixture coverage includes field
validation, controller binding and HTTP/MCP dispatch; live support is unknown.


Controller general settings are exposed at `GET /v1/controller/settings/general`.
The projection returns the bounded controller name, time-zone and region strings,
and reuses the validated DST projection when that object is present. It limits
the name to 32 printable ASCII characters, preserves locale strings as
documented, and omits unknown fields. All three exports document the route and
`Global Other Setting View Only` permission. Fixture tests cover nested DST,
validation, controller binding and HTTP/MCP dispatch; live support remains
unknown.

The site incident overview is exposed at
`GET /v1/sites/{site_ref}/incidents/summary`. It requests a fixed trailing
24-hour window because the source requires millisecond start/end filters but
does not specify a maximum range. The projection returns only validated
int32 status, severity and category counts, plus raw category codes and
bounded category counts; it omits incident records and messages. The source
permission is `Incidents Page View`. Hardware Controller 6.3.0 and CBC
Standard 6.3.0 document the route; ER7212PC 6.2.14 does not. Live support is
unknown.

The site-scoped unresolved-incident count is exposed at
`GET /v1/sites/{site_ref}/incidents/unresolved-count`. The source schema
contains one optional int32 field, `activeNum`; the output includes only its
validated nonnegative count and completeness counters. Incident IDs, details
and messages are not returned. Hardware Controller 6.3.0 and CBC Standard
6.3.0 document the route with `Incidents Page View Only`; the ER7212PC 6.2.14
export does not. Projection, site binding and HTTP/MCP dispatch have fixture
coverage. Live support remains unknown.

The site incident distribution is exposed at
`GET /v1/sites/{site_ref}/incidents/distribution`. The route requests a fixed
trailing 24-hour window and returns at most 128 time buckets containing
validated severity/category counts and timestamps. It omits incident records,
identities and messages. Hardware Controller 6.3.0 and CBC Standard 6.3.0
document the route with `Incidents Page View Only`; ER7212PC 6.2.14 does not.
Fixture coverage does not establish live support.

Site incident categories are available at
`GET /v1/sites/{site_ref}/incidents/categories`. The connector returns at most
128 validated category aggregates and omits records and identities. Hardware
Controller 6.3.0 and CBC Standard 6.3.0 document the route with
`Incidents Page View Only`; ER7212PC 6.2.14 does not. Live support remains
unknown.

The bounded site incident list is available at
`GET /v1/sites/{site_ref}/incidents/list`. It reads page 1 with at most 50
items for the preceding 24 hours and returns codes, counts and timestamps,
without names or message parameters. Hardware Controller 6.3.0 and CBC
Standard 6.3.0 document the route; ER7212PC 6.2.14 does not. Live support is
unknown.


Device/client incident reads return only opaque references bound to the latest
site list snapshot. The detail read redacts raw IDs, MAC addresses, names,
causes and dynamic detail text. Offline HTTP/MCP fixtures pass; live support
has not been checked.


An individual AP overview is available at
`GET /v1/sites/{site_ref}/aps/{device_ref}/summary`. It returns validated model,
firmware, CPU and memory percentages, uptime and documented status codes. MAC,
name, IP addresses and uplink detail are omitted. All three supplied API
exports document the route with `Site Device Manager View Only`; fixture tests
verify site/AP binding, output limits and redaction. No live check has been made.


The site duplicate-SSID summary is exposed at
`GET /v1/sites/{site_ref}/ssids/duplicate-summary`. It reports bounded counts
from the documented SSID-name map and duplicate-name list, validates any
returned site ID against the selected site, and never returns SSID names. The
route is documented in Hardware Controller 6.3.0 and CBC Standard 6.3.0 with
`Site Settings Manager View Only` or `Network Config Page View Only`; it is not
documented in ER7212PC 6.2.14. Fixture and HTTP/MCP tests cover redaction,
site binding and response limits. Live support is unknown.


AP groups bound to an inventoried site SSID are summarized at
`GET /v1/sites/{site_ref}/ssids/{ssid_ref}/ap-groups`. The response contains
only group/AP counts, remaining-binding counts and the documented SSID limits
for 2.4 GHz, 5 GHz, 6 GHz and MLO. Group IDs and names are omitted. Hardware
Controller 6.3.0 and CBC Standard 6.3.0 document the operation with
`Site Settings Manager View Only` or `Network Config Page View Only`; ER7212PC
6.2.14 does not. Offline projection, site/SSID binding and HTTP/MCP tests pass;
live support is unknown.

Available wired networks and SSIDs can be summarized at
`GET /v1/sites/{site_ref}/topology/network-summary`. The response contains
bounded counts, including configuring, default-network and client totals, while
omitting network names, SSID names, identifiers and VLAN values. An aggregate
is `null` when any contributing optional source field is missing; the result is
marked partial instead of presenting an incomplete sum as zero. Hardware
Controller 6.3.0 and CBC Standard 6.3.0 document this read with `Site Map
Manager View Only` or `Site Dashboard Manager View Only`; ER7212PC 6.2.14 does
not. Offline projection and adapter tests pass. A passive read against one
Controller 6.3.0 returned a partial summary (one wired network, one SSID);
this confirms only that route on that controller, and does not establish
complete response fields or broad support.

Available wired VLANs can be summarized at
`GET /v1/sites/{site_ref}/topology/vlan-summary`. The result contains bounded
network, distinct-VLAN, default-network and configuring counts, while omitting
network names, identifiers and VLAN values. Hardware Controller 6.3.0 and CBC
Standard 6.3.0 document the route with the same read-only permissions as the
network summary; ER7212PC 6.2.14 does not. Projection, validation, HTTP and MCP
coverage are fixture-tested. Live support remains unknown because this
specific route has not been called.

### Device adoption checks and link topology

Three inventoried-device reads are available over HTTP and MCP. Adoption result
is limited to the documented error code and whether adoption asks for device
credentials; the returned device MAC is checked against the selected inventory
record and never returned. MAC type returns only the strict device flag and a
known device category. Link topology is reduced to bounded aggregate counts;
node names, addresses, models, MACs, rates, port details and topology labels are
not returned. All calls resolve the site and device from current opaque
inventory references before building a fixed controller path.

The API exports document adoption result and MAC type for all three controller
families. Adoption-result permission is `Site Adopt Device Manager Access`;
MAC-type permission is `Site Log & Audit Log Manager View Only`. Link topology
is documented for Hardware Controller 6.3.0 and CBC Standard 6.3.0, with
`Site Settings Manager View Only` or `Site Device Manager View Only`; it is not
present in the ER7212PC 6.2.14 export. Projection, path binding, HTTP and MCP
fixtures are tested. Live controller behavior remains unknown.

### RadSec compatibility summary

`GET /v1/sites/{site_ref}/devices/radsec-support` reports only the documented
Boolean that indicates whether the site contains a device without RadSec
support. It does not return affected device identities. The source exports for
Hardware Controller 6.3.0, CBC Standard 6.3.0 and ER7212PC 6.2.14 document the
read with `Site Device Manager View Only`. Projection, controller-bound path,
HTTP/MCP routing and reference validation have offline tests; live support
remains unknown.

### Online-upgrade task result

`GET /v1/sites/{site_ref}/devices/{device_ref}/upgrade-result` reads the two
schema-defined Boolean fields `finished` and `success`. It is bound to an
inventoried device and does not start or alter an upgrade. Hardware Controller
6.3.0, CBC Standard 6.3.0 and ER7212PC 6.2.14 document the GET with `Site
Device Manager Modify`. The connector exposes it as a read only; fixture tests
cover strict Boolean validation, fixed path, inventory binding, HTTP and MCP.
No live response has been observed.

### Device online timeline

`GET /v1/sites/{site_ref}/devices/{device_ref}/online-timeline` requests a
fixed trailing 24-hour interval for the current inventoried device. It returns
the number of intervals and the aggregate reported online duration in
milliseconds; exact event timestamps and the device MAC are omitted. Individual
interval fields are validated, and missing duration values or unknown fields
make the aggregate partial. All three exports document the GET with `Site
Device Manager View Only`. The object query serializes its documented `start`
and `end` fields as separate query parameters. HTTP/MCP routing, projection,
time-window bounds and exact path construction have offline tests. Live support
remains unknown.

### All-device inventory summary

`GET /v1/sites/{site_ref}/device-inventory-summary` reads the separate
documented `/devices/all` operation and returns only total count, coarse device
type counts and counts keyed by the documented integer status code. It emits
no device names, MACs, addresses, serials or raw rows. The response uses the
DeviceInfo fields documented for the paginated device inventory; the reduced
route catalog does not preserve a separate response schema for `/devices/all`,
so route-specific schema equivalence remains unconfirmed. Projection, bounds,
fixed-path binding, HTTP/MCP dispatch and source mapping have offline tests.
Live support remains unknown.


## Site MAC-authentication SSID inventory

`GET /v1/sites/{site_ref}/wlan-ssids/mac-auth?type=1|2|3` and MCP tool
`omada_site_mac_auth_ssid_inventory` expose `getSsidsBySite`. The three
exports require `type` (`1` for AP, `2` for wireless router, `3` for both),
with no request body. The source response is specifically the list of SSIDs
configured for MAC-based authentication; it is not a complete SSID inventory.
The projection keeps WLAN and SSID names, removes identifiers, and processes at
most 100 WLANs and 500 SSIDs. Invalid, unknown, missing or truncated data marks
the output partial. Fixture coverage only; live support is unknown.


## Site attack-defense defaults

`GET /v1/sites/{site_ref}/attack-defense/default-summary` and MCP tool
`omada_site_attack_defense_defaults_summary` expose `getDefaultAttackDefense`
through its fixed site route. All three exports define the same 14 required
Boolean fields; optional Boolean flags, seven bounded int32 thresholds and five
nested option flags are validated and returned under their source names.
Unknown or invalid fields and missing required fields mark the result partial.
No live request was made; live support remains unknown.


## WLAN-group detail

`GET /v1/sites/{site_ref}/wlan-groups/{wlan_group_ref}/detail` and MCP tool
`omada_site_wlan_group_detail_summary` expose `getWlanGroup`. The source v2
endpoint is marked legacy/deprecated in favor of the AP-group detail operation.
The connector requires a current opaque group reference from the wireless-group
inventory and returns only the name, primary/clone flags and resource code.
Controller identifiers and site IDs are omitted. Fixture coverage only; live
support remains unknown.


## Lock-to-AP candidate inventory

`GET /v1/sites/{site_ref}/lock-to-ap/ap-inventory` and MCP tool
`omada_site_lock_to_ap_brief_inventory` expose `getAllApBriefInfosBySite`. The
three contracts define the same AP fields and Site Device Manager View Only
permission, with no query or body. The connector aggregates nonzero documented status
and Lock-to-AP capability counts for at most 500 rows. MAC addresses, IPs,
names and model/version strings are omitted. Invalid/unknown values and
truncation mark partial. Live support remains unknown.


## APs unavailable for interference detection

`GET /v1/sites/{site_ref}/wifi/interference-ineligible-ap-summary` and MCP
tool `omada_site_ineligible_interference_ap_summary` expose
`getDisableFullChannelDetectApMacList`. The three exports define the same
`macList` response and Site Tools Manager View Only permission, with no query
or body. The connector validates and counts at most 500 MAC entries but never
returns the MAC values. Invalid, unknown, missing or truncated data marks the
result partial. Live support remains unknown.

## APs eligible for interference scans

`GET /v1/sites/{site_ref}/wifi/interference-scan-eligible-summary` and MCP
`omada_site_interference_scan_eligible_summary` expose
`getGridEnableFullChannelDetectApList`. The connector requests the first page
with 500 rows and returns counts by scan state, connection category, and power
mode. Device names, MAC addresses, IP addresses, and per-device records are not
returned. The upstream endpoint is paginated and this summary does not retrieve
pages after the first; live support remains unverified.

The batch interference history summary also returns site-bound opaque
`history_refs` for its first-page rows. `GET
/v1/sites/{site_ref}/wifi/interference-history/{history_ref}/ap-summary` and MCP
`omada_site_batch_interference_ap_summary` use a reference to read
`getBatchFullChannelDetectApList`. The connector aggregates AP capability
flags and omits raw history IDs, MAC addresses, names, and per-device records.
References are process-local and scoped to the site that issued them.

Because the eligible-AP response has no documented total or end-of-page marker,
its payload reports `page: 1`, `page_size: 500`, `total_count: null`,
`coverage_unknown: true`, and `partial: true`. `truncated` separately means
that more than the local processing cap was actually received. Counts describe
only the rows returned by that first request.

The batch Wi-Fi interference summary is available at
`GET /v1/sites/{site_ref}/wifi/interference-history/{history_ref}/wifi-interference-summary`
and MCP `omada_site_batch_wifi_interference_summary`. It reads the first 100
results with the required `filters.type=0` (“all device”) setting and returns
radio/channel/security counts and signal bounds. SSIDs, BSSIDs, AP identities,
record IDs and timestamps are omitted. The response total determines whether
more pages exist; no automatic pagination is performed.

The batch channel-load summary is available through a process-local AP
reference at
`GET /v1/sites/{site_ref}/wifi/interference-history/{history_ref}/aps/{device_ref}/channel-load-summary`
and MCP `omada_site_batch_channel_load_summary`. It returns only per-band
channel counts and load bounds/average; raw AP addresses and channel numbers
are omitted. The API exports do not define load units. References are limited
to the site and history that produced them and to the current process.

The batch interference result summary is exposed as
`GET /v1/sites/{site_ref}/wifi/interference-history/{history_ref}/interference-summary`
and MCP `omada_site_batch_interference_result_summary` for controllers whose
API export documents it (Hardware Controller 6.3.0 and CBC Standard 6.3.0).
The ER7212PC 6.2.14 export does not contain this operation. Its response schema
recursively defines only band lists, so the connector returns bounded entry
counts, marks first-page coverage unknown, and omits records and identities.

Batch interference status is available at
`GET /v1/sites/{site_ref}/wifi/interference-history/{history_ref}/status-summary`
and MCP `omada_site_batch_interference_status_summary`. The connector sends a
fixed upstream status query for the single history selected by the opaque,
same-site reference. It does not trigger a new scan. Raw history IDs are not
returned; documented statuses 0 and 1 map to `finished` and `scanning`.

An AP's passive full-channel-detection status is available at
`GET /v1/sites/{site_ref}/aps/{device_ref}/full-channel-detect-status` and MCP
`omada_site_ap_full_channel_detect_status`. The AP is selected through an
opaque inventory reference scoped to the site. Documented status codes map to
unscanned-with-result, unscanned-without-result, or scanning. The raw timestamp
is suppressed because the exports do not define its unit; this route does not
start a scan.


The AP supported-channel summary exposes the documented `getAvailableChannelOfAp` read through `GET /v1/sites/{site_ref}/aps/{device_ref}/available-channels-summary` and MCP. It compacts channel, frequency, and index sets into ranges per radio while preserving supported widths. It is bound to an inventoried AP in the selected site; live behavior remains unverified. A synthetic 86-channel fixture reduced 2,118 tokens for the upstream result array to 1,259 for the projected HTTP/MCP result (40.6%; js-tiktoken 1.0.21/o200k_base).


The per-AP interference result summary is available over HTTP/MCP using an inventoried AP reference. It counts only recursively declared band entries from the fixed first page and suppresses all result records and AP identity. It is documented for Hardware Controller and CBC; ER7212PC does not list it. The read does not initiate a scan.
 A synthetic 150-entry recursive response projected from 2,724 to 91 tokens (96.7%; js-tiktoken 1.0.21/o200k_base).


The per-AP channel-load summary reads existing detection results by an inventoried AP reference. It returns band counts and load ranges/averages without channel identifiers. The source does not specify load units, and the route never starts a scan.
A synthetic 86-channel fixture reduced the serialized upstream result array from 712 tokens to 134 projected HTTP/MCP tokens (81.2%; js-tiktoken 1.0.21/o200k_base).


The LAN network detail summary resolves one opaque network reference within the site and reports redacted addressing, VLAN, DHCP and selected feature flags. Names, network IDs, device MACs, domains, DNS and raw DHCP ranges are excluded.


`site_vlan_ssid_usage_summary` reads the paginated VLAN-to-SSID association for a validated site/network reference and a caller-supplied VLAN ID (1–4094). It returns the number of matching SSIDs and distinct WLAN groups, while discarding IDs and labels. The three API exports document this read and require Site Settings Manager View Only or Network Config Page View Only. Page parameters are fixed; responses are capped at 10,000 rows. No live controller request has been made.


`site_vlan_device_usage_summary` reads the documented non-paginated list of devices using one VLAN on a validated site network. It returns counts by documented device type, stack membership, and raw DHCP-mode code; names, MAC addresses, and stack IDs are discarded. The request is capped at 10,000 rows and rejects VLAN IDs outside 1–4094. No live controller request has been made.

`site_vlan_port_support_summary` checks a caller-selected VLAN against the selected network’s current inventory assignment, then reads the documented port-support result. It returns counts by device type and supported, unsupported, or unknown support status. Device MACs, port names, stack IDs and aggregation IDs are discarded. Missing port lists and unknown or malformed data are visible; response counts cover only returned rows because the API has no total-coverage field. ER7212PC documents a different object shape and is marked partial when its single-device shape is used. No live controller request has been made.


`site_wifi_calling_profiles_summary` exposes the documented site Wi-Fi calling profile read as counts of profiles, carriers, domain/IP endpoint types, configured endpoints, QoS priorities and source resource codes. Profile IDs, names, descriptions, carrier labels, domains and IP addresses are removed. The original API documents Site Settings Manager View Only or Device Config Page View Only; Hardware Controller and CBC additionally list Network Config Page View Only. No live controller request has been made.


`site_client_filter_options_summary` reads the documented client-list filter catalog and returns counts for vendor, device, network, SSID and device-type options, plus stacked-device counts. It discards every option string, MAC address, device name and stack name. The read is site-bound and uses fixed query-free routing; live support remains unknown.

`site_channel_reuse_summary` reads radio-detail and existing channel-load data for 1–16 selected APs. It groups only equal reported channels within a band, and carries reported bandwidth and matching load values. Adjacent-channel overlap and interference are not inferred because occupied channel ranges and load units are not specified. It does not start a scan. Detailed nested fields are present in ER7212PC 6.2.14; Hardware Controller and CBC 6.3 have generic response schemas. Live compatibility remains unverified.

### Scheduled reboot summary

GET /v1/sites/{site_ref}/reboot-schedule-summary reads the documented site reboot schedule list. It returns enabled state, recurrence, schedule clock fields, a next-execution timestamp when supplied, and current-inventory device references. Names, source IDs, and MAC addresses are omitted. The source does not specify the schedule timezone; the report does not guess it. A configured schedule is not evidence that a reboot occurred. Detailed response fields are available in the ER7212PC 6.2.14 export; Hardware Controller and Omada CBC 6.3 exports have generic response schemas. Schedule rows use a declared compact column list so the same field names are not repeated per schedule. A synthetic 12-schedule payload measured 796 source JSON tokens and 464 projected tokens (41.71% fewer with js-tiktoken 1.0.21/o200k_base). This compares serialized fixture payloads only and excludes inventory responses, prompts, schemas, framing and billed agent context. No live controller compatibility check has been made for this route.

### Backup inventory summaries

GET /v1/controller/maintenance/backup-inventory-summary summarizes controller-listed backup metadata alongside the existing controller backup status and schedule reads. GET /v1/sites/{site_ref}/backup-inventory-summary does the same for one selected site, without probing other sites. Both expose file count, listed bytes, the maximum timestamp in the returned list, status, and safe schedule fields. They omit filenames, paths, download URLs, credentials, and raw identifiers. Timestamp and size semantics are detailed only in ER7212PC 6.2.14; the Hardware Controller and CBC 6.3 schemas are generic. The status code 0 combines initial and finished states. A synthetic 12-file fixture measured 459 source JSON tokens and 103 summary tokens (77.56% fewer with js-tiktoken 1.0.21/o200k_base). This compares serialized fixture payloads and excludes tool schemas, prompts, framing and billed agent usage. No backup is downloaded or restored.

WAN maximum-speed configuration is available for one explicitly selected WAN port at `GET /v1/sites/{site_ref}/wan-ports/{wan_port_ref}/max-speed-summary`. The WAN-port inventory returns an opaque reference and index for each uniquely identified WAN port. Each read resolves the reference against a fresh `internet/ports-config` response and sends the matching documented `portId` as required `wanId`. The connector preserves upstream/downstream int32 values and labels the unit unspecified. It does not report current throughput. Live support is unknown.

`GET /v1/sites/{site_ref}/gateways/{device_ref}/info-summary` returns the documented model (`showModel`), firmware version and numeric last-seen source value for one gateway bound to the selected site's inventory. It omits MAC/IP addresses, IPv6 values, port details and unrelated operational fields. The source does not define units or epoch semantics for `lastSeen`; the connector preserves the integer without converting it or inferring online/offline state. Missing, invalid and unknown fields are reported. Live support remains unknown.


### AP SSID override audit summary

The AP-specific SSID override audit read is documented by Hardware Controller 6.3.0 and Omada CBC Standard 6.3.0, but is absent from the ER7212PC 6.2.14 export. Its connector route and MCP tool require an AP reference from the selected site's current inventory. The reader requests a fixed first page of 100 rows over the source default trailing seven-day period and projects only aggregate modification-flag counts and row-quality/truncation metadata. It drops SSID names, VLAN values and controller messages. The source rows contain no time or actor fields, so the output cannot establish event order or attribution. Runtime controller support remains unknown.
### Existing incident report comparison

`POST /v1/incident-reports/compare` and MCP tool `omada_compare_incident_reports` summarize 2–8 existing redacted `site_outage_report` JSON documents. They perform only local processing and make zero controller requests. The versioned allowlist compares event/alert totals only for identical windows with complete sources and compares current reachability only for identical observation timestamps. Different windows, partial reports, pagination limits, unsupported schemas and missing data remain visible. Report text, names, identifiers and raw observations are never copied into the result.

`omada_site_ipsec_sa_summary` provides redacted counts of documented IPsec security associations for one selected site, grouped by in/out direction. Peer addresses, IDs and algorithm details are not returned. The API has no connection-state field; this summary does not confirm tunnel connectivity.


A synthetic 20-row IPsec fixture measured 1,863 source JSON tokens versus 52 tokens for the projected counts (1,811 fewer; 97.21%) using js-tiktoken 1.0.21 with o200k_base. This excludes schemas, MCP framing, live responses and billed agent usage.

A synthetic 20-row policy-routing fixture measured 2,562 source JSON tokens versus 142 tokens for its redacted projection (2,420 fewer; 94.46%) using js-tiktoken 1.0.21 with o200k_base. This excludes schemas, MCP framing, live responses and billed agent usage.

The selected VPN server status summary reads one protocol per call, counts source status codes without guessing their meaning, and omits user, peer, address and traffic fields. The query accepts protocol codes 0–5 as documented by the API. No controller live-read has been made.

A synthetic 20-row VPN server status fixture measured 1,983 source JSON tokens versus 63 tokens for the code-count projection (1,920 fewer; 96.82%) using js-tiktoken 1.0.21 with o200k_base. This excludes schemas, MCP framing, live responses and billed agent usage.

`omada_site_wan_qos_summary` combines the documented WAN QoS list and paginated rule list. It counts configured ports, rule status and direction, and joins rules only on an exact unique WAN ID match. It omits IDs, names, bandwidth values and ratios: the exports do not specify bandwidth units or fully map ratio semantics. It describes configuration, not observed traffic.

A synthetic 10-port/20-rule fixture measured 1,180 source JSON tokens versus 118 tokens for the summary (1,062 fewer; 90.00%) using js-tiktoken 1.0.21 with o200k_base. This excludes schemas, MCP framing, live responses and billed usage.

`omada_site_upnp_template_comparison` compares four redacted fields for an explicitly selected site and template. It does not infer that the site is assigned to the template. The template read is documented only in CBC Standard 6.3.0; the two other exports do not include that endpoint. Live support is unverified.

A synthetic site/template comparison measured 75 source JSON tokens versus 49 projected tokens (26 fewer; 34.67%) with js-tiktoken 1.0.21/o200k_base. The comparison is limited to this fixture and excludes schemas, MCP framing and billed usage.

`omada_site_bridge_device_summary` combines the paginated adopted and pending bridge-device grids. It returns source status-code counts and stack-group status-code counts without interpreting those codes or exposing identifiers, names, IPs, serials or telemetry. Each grid reports its source total and whether all rows were returned. No adoption is initiated.

A synthetic 10-adopted/4-pending bridge-device fixture measured 1,042 source JSON tokens versus 127 projected tokens (915 fewer; 87.81%) with js-tiktoken 1.0.21/o200k_base. This excludes schemas, MCP framing and billed agent usage.

`omada_site_recent_clients_summary` requires a site and a millisecond start/end window no longer than 24 hours. It requests one page of up to 100 rows and returns the reported total and sampled count without identities. The source does not state the unit of `lastSeen`, so the connector does not interpret it or infer an outage.

A synthetic 20-client response measured 1,546 source JSON tokens and 83 projected tokens (1,463 fewer; 94.63%) with js-tiktoken 1.0.21/o200k_base. This is serialized fixture size, not agent billing.

`omada_site_vlan_affected_ports_summary` requires a selected site, network, and VLAN and returns one requested page of up to 100 devices. It counts device classes and reported numeric-port, standard-port, and LAG memberships, omitting identifiers and client data. Membership counts are not unique physical-port counts.

A synthetic 10-device response measured 1,445 source JSON tokens and 121 projected tokens (1,324 fewer; 91.63%) with js-tiktoken 1.0.21/o200k_base. ER7212PC documents these port arrays as strings; the other two exports use integers for numeric ports and LAGs. Live support is unknown.

The SSID client-list route `getGridSsidClients` is not exposed. It is absent from the ER7212PC export, and the required `queryDataVO` parameter has no explicit serialization style in the supplied schemas.

`omada_site_port_schedule_summary` requires a site and one page (up to 100 schedule rows). It counts enabled/disabled schedules, presence of time-range and next-execution values, DST flags and configured port memberships. It joins schedule MAC keys and integer port IDs against the unique same-site supported-port inventory, but returns only aggregate counts. The `nextExecute` unit is not specified, and the connector does not predict execution or its effect. Live support is unknown.

A synthetic 10-schedule/four-device response measured 1,729 source JSON tokens and 188 projected tokens (1,541 fewer; 89.13%) with js-tiktoken 1.0.21/o200k_base. This is serialized fixture size, not billed agent usage.

`omada_site_routing_table_summary` requires `device_type` (`gateway` or `switch`) plus a page number and page size. It reports sampled and total route counts and counts distinct, uninterpreted row type values. Destinations, next hops, VRFs, interfaces and device identities are omitted because the route table can contain those values and the source does not enumerate route type codes. Live support is unknown.

A synthetic 20-row routing table measured 3,151 source JSON tokens and 108 projected tokens (3,043 fewer; 96.57%) with js-tiktoken 1.0.21/o200k_base. This is serialized fixture size, not billed agent usage.

A synthetic 20-row routing table measured 3,151 source JSON tokens and 108 projected tokens (3,043 fewer; 96.57%) with js-tiktoken 1.0.21/o200k_base. This is serialized fixture size, not billed agent usage.

A synthetic 10-schedule/four-device response measured 1,729 source JSON tokens and 188 projected tokens (1,541 fewer; 89.13%) with js-tiktoken 1.0.21/o200k_base. This is serialized fixture size, not billed agent usage.

## VPN client status summary

`GET /v1/sites/{site_ref}/vpn/clients/status-summary?vpn_type=` accepts only the documented client protocol codes: 0 L2TP, 1 PPTP, 3 OpenVPN, or 4 WireGuard. It paginates the site-bound client status read and counts integer source status codes. The three exports define no meaning for those status codes. User, peer, address, traffic, and VPN identifiers are omitted; malformed or unknown fields mark the projection partial. Live support is unknown.

## VPN client status summary

`GET /v1/sites/{site_ref}/vpn/clients/status-summary?vpn_type=` accepts only the documented client protocol codes: 0 L2TP, 1 PPTP, 3 OpenVPN, or 4 WireGuard. It reads the selected site's paginated client status list and counts integer source status codes. The three exports define no meaning for those status codes. User, peer, address, traffic, and VPN identifiers are omitted; malformed or unknown fields mark the projection partial. Live support is unknown.

## Selected SSID client count

`GET /v1/sites/{site_ref}/ssids/{ssid_ref}/clients/summary` binds the opaque SSID reference to that site's SSID inventory. It uses only the documented first page (`page=1&pageSize=100`) and returns the source's documented `totalRows` plus sampled-row coverage, without client details or online-state claims. The operation exists in the Hardware Controller 6.3.0 and CBC 6.3.0 exports; it is absent from the ER7212PC 6.2.14 export. OpenAPI 3.0.1 defaults the required `queryDataVO` object to flat `form`/`explode` query parameters when no other serialization is specified. Live behavior is unknown.
