# Capability evidence

`GET /v1/sites/{site_ref}/topology/snapshot-summary` and MCP tool
`omada_site_topology_snapshot_summary` summarize the documented v2 site
topology snapshot separately from the existing inventory-mapped v3 topology
view. The response counts nodes, edges, documented blocked booleans, missing
or unreported endpoint references and rows without node references. It omits
MACs, names, port details and VLAN values, and makes no claim about current
traffic forwarding. Hardware Controller and CBC document the source; live
support is unknown.

`GET /v1/sites/{site_ref}/gateway-qos/service-profiles/summary` and MCP tool
`omada_site_gateway_qos_service_profiles_summary` read up to 10 bounded pages
and count configured service profiles by documented default flag and protocol
category. Profile names, IDs, port values and descriptions are omitted.
Unrecognized codes remain unclassified. Hardware Controller, CBC and
ER7212PC document this operation; live support is unknown.

`GET /v1/sites/{site_ref}/gateway-qos/service-references/summary` and MCP tool
`omada_site_gateway_qos_service_reference_inventory` read the separate,
unpaginated `service-type-summary` reference list. They report row counts and
the presence, validity and duplication of documented string IDs, plus name
field coverage, while omitting all IDs and names. Unknown fields mark the
result partial. The response has no total or pagination metadata, so the
summary does not claim server-side completeness or describe profile use.
Hardware Controller, CBC and ER7212PC document the source; live support is
unknown.

`GET /v1/sites/{site_ref}/static-route-summary` and MCP tool
`omada_site_policy_route_summary` provides a bounded, read-only summary of documented policy-routing rows for one selected site. It counts source, destination and interface types, enabled state and opaque reference occurrences; it marks unknown values and index quality. It does not disclose IDs or names, infer precedence, or claim that a route is carrying traffic.

`omada_site_static_route_summary` provide a bounded read-only overview of the
selected site's static gateway routes. The response counts documented route
types, status values and occurrences of interface, VPN-client and virtual-WAN
references. It does not return route identifiers, names, destination or
next-hop addresses, metrics or descriptions. Live controller support is
unknown until verified against a controller.

`GET /v1/sites/{site_ref}/static-routing/interfaces/summary` and MCP tool
`omada_site_static_route_interface_options_summary` summarizes the selected
site's documented static-route editor options by interface type and
`needNextHop` value. It omits interface IDs and names and labels these only as
selection choices, not configured or effective routes. Live support is unknown.

`GET /v1/sites/{site_ref}/wlan-groups/{wlan_group_ref}/ssids/{ssid_ref}/config-summary`
and MCP tool `omada_site_wlan_group_ssid_config_summary` first refresh the site
WLAN-group and SSID inventories, prove that the selected SSID occurs exactly
once in the selected group's SSID list, then read `getSsidDetail` through the
group-scoped path. The result contains only documented enabled, band and EAP /
gateway applicability flags. Names, IDs, VLAN values and credentials are
omitted. Missing fields remain unknown; live support is unknown.

`GET /v1/sites/{site_ref}/internet/lte-wan-config-summary` and MCP tool
`omada_site_lte_wan_config_summary` count LTE WAN setting flags and documented
mode/status codes. Settings and modem status remain separate; the status codes
do not establish Internet reachability. Port/SIM identifiers, names, provider
values, APNs and selected band strings are omitted. All three exports document
the source operation; live support is unknown.

Token counts for synthetic fixture payloads using `js-tiktoken` 1.0.21 and
`o200k_base`: the 20-row static-route interface response shrank from 533 to
128 tokens (75.98%). A selected-SSID flow fixture with inventories, group
membership and one detail response shrank from 134 to 92 tokens (31.34%).
The 20-row LTE settings fixture shrank from 4,328 to 458 tokens (89.42%).
These counts cover serialized source responses and final projections only, not
HTTP/MCP framing, live payloads or billed agent usage.

## Controller-wide event and alert windows

`GET /v1/controller/events/window` and `/v1/controller/alerts/window` (also
available as `omada_controller_events_window_summary` and
`omada_controller_alerts_window_summary` MCP tools) read the configured
controller's global event and alert logs for a bounded time window. The
projection returns counts, documented categories and time bounds; it omits log
text and record identifiers. Reads stop after at most 10 pages of 100 rows and
report partial coverage. All three supplied exports document both operations;
live support has not been verified.

A synthetic 20-row source-shaped event fixture measured 850 tokens before
projection and 82 after (768 fewer; 90.35%) with `js-tiktoken` 1.0.21 /
`o200k_base`. This is serialized payload only; it excludes tool schemas, MCP
framing, live responses and billed agent usage.

## Controller placed-site position coverage

`GET /v1/controller/placed-site-position-coverage` and
`omada_controller_placed_site_position_coverage` use the separate,
controller-wide `getPlacedSitePositions` list. They report bounded row and
documented-field coverage counts only. No site identifiers, names, regions,
addresses, coordinate values or raw rows are returned. Hardware Controller
and CBC describe numeric coordinate fields; ER7212PC describes opaque object
shapes, which the reader does not inspect. The list has no pagination or
completeness metadata, so the result makes no claim that all placed sites are
covered. This is distinct from the paginated site inventory and unplaced-site
position list. Live support is unknown.

## Controller unplaced-site position coverage

`GET /v1/controller/unplaced-site-position-coverage` and
`omada_controller_unplaced_site_position_coverage` read one fixed first page
from `getUnplacedSitePositions` (`page=1`, `pageSize=100`, with no search
filter). The reader returns counts for the documented `id`, `region`, `name`
and `type` field shapes, plus the separately reported `totalRows` and
`unplacedNum` counters. It does not compare those counters or interpret `type`
codes. A page shorter than `totalRows` is marked partial; when `totalRows` is
not reported, overall completeness remains unknown. Site values, identifiers
and raw rows are never returned. The single page does not guarantee a stable
controller snapshot. Live support is unknown.

## WAN-port availability by function

## Site-to-site VPN status codes

`GET /v1/sites/{site_ref}/vpn/site-to-site/status-summary` and the matching
MCP tool require an explicit documented protocol selection (IPsec or
WireGuard). They count raw documented status integers over bounded pages and
omit all tunnel identities, peer details and addresses. The exports define no
meaning for the status integers, so the result does not say connected or
disconnected. This is distinct from IPsec security-association inventory and
does not close its status gap. Live controller support is unknown.

## Devices associated with a selected SSID in topology

`GET /v1/sites/{site_ref}/ssids/{ssid_ref}/topology-device-summary` and its
MCP tool bind the selected WLAN through that site's SSID inventory, then match
the documented topology MAC list only against the same site's v1 device
inventory. The result counts recognized device classes and reports unmatched,
ambiguous or unknown inventory coverage without returning MACs, names or IDs.
The topology endpoint is documented by Hardware Controller and CBC exports,
not ER7212PC. It does not measure radio coverage. Live controller support is
unknown.

`GET /v1/sites/{site_ref}/ssids/{ssid_ref}/topology-reference-count` uses the
separate documented v2 response, binds the SSID from a fresh inventory of the
selected site, and counts its bounded string list as opaque references. It does
not infer MAC or device-ID meaning, active connections or radio coverage. The
v2 operation appears in Hardware Controller and CBC exports, not ER7212PC.
Live controller support is unknown.

## Topology root candidates

`GET /v1/sites/{site_ref}/topology/root-candidates/summary` and its MCP tool
count the documented selectable root candidates and their switch/OLT/other
types, root and stack flags, and MLAG/VRRP code fields. Identifiers, names,
models and free-text subtype values are omitted. This endpoint is documented
for Hardware Controller and CBC 6.3.0, not ER7212PC. It supplements the
existing topology read with candidate-root information; it does not return
topology edges. The vendor notes that a gateway can result in an empty list,
so emptiness is not presented as a missing-topology finding. Live support is
unknown.

## IPsec failover configuration summary

`GET /v1/sites/{site_ref}/ipsec-failovers/summary` and its MCP tool read the
vendor-deprecated `getGridIpsecFailover` list, bounded to 1,000 rows. They count
rules, presence of primary references, candidate references, failback enablement
and failback-time field presence. Names, identifiers, nested tunnel status and
time values are omitted; the source does not document the time unit. The read
does not imply a failover, tunnel availability or current connectivity. The
vendor recommends its site-to-site VPN summary/detail operations instead. All
three source exports document this deprecated read; live support is unknown. A
synthetic three-rule response measured 181 source JSON tokens and 142 summary
tokens (21.55% fewer) using `js-tiktoken` 1.0.21 / `o200k_base`; schemas,
transport, prompts and billed agent usage are excluded.

## Gateway SIM, SMS and LTE capabilities

`GET /v1/sites/{site_ref}/gateways/{gateway_ref}/sim-capabilities-summary`
and its MCP tool refresh the selected site's device inventory, require one
unique gateway reference with a documented gateway type, then read
`getSupportSmsByMac`. The result reports the documented SIM SMS and LTE Boolean
flags, the documented count of SIMs supporting SMS, and whether the Dual-SIM
source field was present. The Dual-SIM integer has no documented value mapping,
so capability remains unknown. No SIM identity, message, send operation or
reachability is returned or inferred. The endpoint is documented in all three
source exports; live support is unknown. A synthetic four-field response
measured 33 source JSON tokens and 71 tokens for the projected response
(115.15% more) using `js-tiktoken` 1.0.21 / `o200k_base`. The extra size comes
from the bound references, response labels and explicit unknown-state fields;
this small read is not a token-saving summary. Counts cover serialized payloads
only, excluding schemas, transport, prompts and billed agent usage.

## Devices present in a selected VLAN topology

`GET /v1/sites/{site_ref}/networks/{network_ref}/vlan-topology-summary` and
its MCP tool first refresh the selected site's LAN-network inventory and
require the selected network to be a VLAN network assigned to the requested
VLAN. The connector then reads `getFilterDevicesOfVlan` and matches its
documented device MAC list only against that site's device inventory. It
returns recognized device-class counts and unmatched, unknown or ambiguous
inventory coverage; MACs and network identifiers are omitted. The API is
documented for Hardware Controller and CBC 6.3.0, not ER7212PC. This reports
topology membership for that VLAN and does not infer links between devices.
Live support is unknown.

The separate `GET /v1/sites/{site_ref}/networks/{network_ref}/vlan-topology-reference-count`
route and MCP tool expose the coarser documented v2 count. They require a
freshly inventoried VLAN network and the caller's VLAN number to match its
current inventory assignment, then count at most 4,096 opaque strings without
returning values. This is a reference-count view; it does not classify devices
or imply connectivity. The v2 operation appears only in Hardware Controller
and CBC exports, not ER7212PC. Live support is unknown.

A synthetic v2 response with 20 opaque references measured 231 source JSON
tokens and 60 summary JSON tokens (74.03% fewer) with `js-tiktoken` 1.0.21 /
`o200k_base`. This excludes tool schemas, transport framing, prompts and billed
agent usage.

## Isolated and preconfigured device counts

`GET /v1/sites/{site_ref}/topology/isolated-preconfig/summary` and its MCP
tool report the two source categories separately and compare their documented
row total with the response total. Device-type, health-score and IPPT-field
presence are counted without returning values, identifiers or descriptions.
Unexpected fields, invalid rows and a total mismatch are visible as partial
data. The source is documented for Hardware Controller and CBC, not ER7212PC.
The result does not infer adoption actions or causes for isolation. Live support
is unknown.

## Network and port assignments on a selected ES switch

`GET /v1/sites/{site_ref}/switches/{switch_ref}/es-network-overview/summary`
and its MCP tool refresh the selected site's device inventory and bind the
requested opaque switch reference to an inventoried switch MAC before calling
`getESNetworkOverview`. The result counts network rows and native, untagged
and tagged port assignments, with field presence for each array; network
names/IDs, VLAN values and port numbers are omitted. All three supplied exports document this route, but they do not
define a model allowlist for the ES-family endpoint. Compatibility with a
particular switch model and live hardware support remain unconfirmed.

## Ports eligible for schedules

`GET /v1/sites/{site_ref}/port-schedule-capable-ports/summary` and its MCP
tool expose `getPortSchedulePorts`. They count returned devices by the
documented gateway/switch type and count total ports and port IDs listed as
supporting schedules. Device identifiers, names, serials, port numbers and
raw status values are omitted; status is reported as field presence only.
This is separate from `getPortScheduleList` and the existing configured
schedule summary. All three exports document the source; live support is
unknown.

## Client counts at a selected access point

`GET /v1/sites/{site_ref}/aps/{device_ref}/topology-clients/summary` and its
MCP tool first refresh the selected site's AP inventory, then read the
documented topology-client list for that AP. The projection counts only the
documented wireless, guest and client-type field presence; client type values
are unenumerated and are not exposed. It omits client and AP identifiers. The
response is a topology snapshot with no source timestamp; it is not a roaming
history or proof that a client remains connected. Hardware Controller and CBC
document the operation, not ER7212PC. Live support is unknown.

A synthetic 20-client source-shaped topology fixture measured 982 tokens
before and 117 after projection (88.09% fewer) with `js-tiktoken` 1.0.21 /
`o200k_base`. This is serialized payload only.

## Delivery state for a selected LAN network

`GET /v1/sites/{site_ref}/networks/{network_ref}/delivery-summary` and its
MCP tool refresh the selected site's LAN network inventory before reading the
network's documented delivery process. The output counts successful, failed
and in-progress device/stack entries and returns the documented state code and
device totals. It omits all device and network identities. A completed
configuration delivery does not establish that devices are reachable. Live
support is unknown.

`GET /v1/sites/{site_ref}/session-limit/enable-state` and MCP tool
`omada_site_session_limit_enable_state` read the required site `enable` boolean
from the fixed session-limit route bound to the selected site's current
inventory. Explicit `false` is preserved; missing, invalid or unknown fields
are reported as incomplete coverage. This reports configured state only and
does not imply policy enforcement, client scope, device support or a numeric
limit. All three supplied API exports document the GET with `Site Settings
Manager View Only`, `Network Config Page View Only`, or `Site Device Manager
View Only` permission; live support remains unknown.

`GET /v1/sites/{site_ref}/mac-filtering/general-state` and MCP tool
`omada_site_mac_filtering_general_state` read the fixed site MAC-filter
setting. The projection preserves the required `enable` boolean and optional
documented mode and direction fields; selector IDs are never returned, only
bounded counts. Missing optional fields remain absent, while missing required
or invalid/unknown values are reported as incomplete coverage. This describes
configuration only and does not infer enforcement, traffic, device support or
defaults. The source marks direction as Gateway-only; an absent direction stays
absent without inferring a target type. All three supplied API exports document
the GET with `Site Settings Manager View Only`, `Device Config Page View Only`,
or `Site Device Manager View Only` permission; live support remains unknown.

`GET /v1/sites/{site_ref}/devices/model-whitelist-coverage` and MCP tool
`omada_site_device_model_whitelist_coverage` summarize only returned record
counts and coverage of the documented `model` and `hwVersion` strings. They
never expose model/version values or device identities. A valid empty array is
reported separately from malformed output. The API schema supplies no paging
or truncation marker; a local limit rejects responses over 512 rows, and a
valid response therefore does not establish server-side completeness or any
authorization decision. Live support remains unknown.

`GET /v1/sites/{site_ref}/portals/coverage` and MCP tool
`omada_site_portal_inventory_coverage` return only bounded list and activation
coverage counts. They omit portal names, identifiers, URLs, authentication
types, social-login settings and all RADIUS settings. Empty arrays are distinct
from missing or invalid list fields. The API contract has no paging or
truncation marker, so returned counts do not establish server completeness or
active connections; this reader makes no policy or device-support inference.
Live support remains unknown.

A synthetic delivery response with 20 device/stack entries measured 120 tokens
before and 96 after projection (20% fewer) using `js-tiktoken` 1.0.21 /
`o200k_base`; serialized payload only.

## LAN port profile overview

`GET /v1/sites/{site_ref}/lan-port-profiles/summary` and its MCP tool read the
selected site's paginated LAN profile list. They count the documented profile
type/source flag enums and safe enablement/mode fields; names, IDs, VLAN and
network references are discarded. Profiles are not linked to a device by this
read. Pagination is capped at ten pages of at most 100 profiles, and incomplete
or malformed rows are reported. Live support is unknown.

## Switch LAN profile assignments

`GET /v1/sites/{site_ref}/lan-switch-profile-assignments/summary` and its MCP
tool read the separate `getOswPortLanNetInfo` grid. The OpenAPI contract is a
direct grid response with `totalRows`, `currentPage`, `currentSize` and `data`;
pagination is capped at 1,000 rows. The summary counts device rows and entries
in each documented profile map while omitting profile values, names, MACs,
VLANs and ports. A missing profile map is reported as unavailable data rather
than zero assignments. The export does not define map entries for ER7212PC, so
that hardware's profile-assignment count remains unknown. Live support is
unknown.

A synthetic payload with 20 switch rows and 480 profile-map entries measured
4,302 source JSON tokens and 84 summary JSON tokens (98.05% fewer). Twenty
opaque topology strings measured 191→55 tokens (71.20% fewer). Both use
`js-tiktoken` 1.0.21 / `o200k_base`; tool schemas, prompts, transport framing
and billed agent usage are excluded.

A synthetic 20-profile source-shaped payload measured 2,543 tokens before and
475 after projection (81.32% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`;
this is serialized payload only.

## LAN multicast settings

`GET /v1/sites/{site_ref}/lan-multicast-summary` and its MCP tool read the
site's paginated LAN multicast snooping settings. They count the documented
IGMP/MLD protocol and unknown-multicast selection values, selected enablement
flags, and field coverage. Names, addresses, identifiers, and nested device or
network configuration are omitted. This is configuration only and does not
measure multicast traffic. Pagination is capped at ten pages of 100 rows. The
ER7212PC example has inconsistent pagination metadata and is not treated as a
valid response. Live support is unknown.

A synthetic 20-entry configuration fixture measured 5,398 source tokens and
237 projected tokens (95.61% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`;
this counts serialized payloads only.

## Bandwidth policy overview

`GET /v1/sites/{site_ref}/bandwidth-control-rules/summary` and its MCP tool
read the site's paginated bandwidth-control policies. They count activation,
documented source and mode categories, upstream/downstream units, and safe
coverage indicators. Rule names, identifiers, targets, and configured rate
values are discarded. These policies remain separate from WAN QoS settings and
do not measure traffic. Pagination is capped at ten pages of 100 rules. The
ER7212PC example has inconsistent page metadata and is not accepted as a valid
response. Live support is unknown.

A synthetic 20-rule fixture measured 1,620 source tokens and 236 projected
tokens (85.43% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; serialized
payloads only.

`GET /v1/sites/{site_ref}/rate-limit-profiles/summary` and its MCP tool read
the separate site-wide rate-limit profile list. They return profile and
default-state counts, directional enable coverage, and Kbps aggregates only
for limits whose direction is enabled and whose value is a strict signed
`int64`. Profile IDs, names and raw limit values are omitted; disabled-side
numbers are not counted. The manufacturer contract documents no profile
pagination or truncation marker, so server completeness remains unknown.

This route is distinct from
`GET /v1/sites/{site_ref}/hotspot/rate-limit-profiles/summary`. The Hotspot
reader uses another path and a different profile shape (`id`/`site`/`isDefault`)
with its own documented 1–10,485,760 Kbps constraint. Neither reader infers
that the profile lists, assignments or client applicability are shared. Live
support for the site-wide route remains unknown.

## Log notification settings

`GET /v1/sites/{site_ref}/log-notification-summary` and its MCP tool read the
selected site's log notification settings. They count notification categories
and documented alert, event, email, and webhook switch states, plus email and
webhook configuration switches. Category keys, message text, webhook IDs, and
delay values are omitted. Enabled settings do not prove an external delivery.
The source response has no delivery result. Live support is unknown.

A synthetic 20-category fixture measured 787 source tokens and 187 projected
tokens (76.24% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; serialized
payloads only.

## LAN network interface overview

`GET /v1/sites/{site_ref}/lan-network-interfaces/summary` and its MCP tool read
the selected site's unpaginated LAN network interface list. They count the
documented VLAN/interface purpose, single/multiple interface type, and device
application scope, plus interface-reference and subnet presence. The optional
`interface_type=0` filter is the only exposed value; omitting it leaves the
source filter unset. Names, identifiers, VLAN values and addresses are
discarded. Interface IDs are not joined to router or VLAN records. Live support
is unknown.

A synthetic 20-network fixture measured 2,104 source tokens and 159 projected
tokens (92.44% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; serialized
payloads only.

## Scheduled firmware plans

`GET /v1/controller/firmware-upgrade-plans/summary` and its MCP tool read at
most ten pages of 100 controller-wide plan rows. The summary reports coverage,
site associations, current-version entry counts, schedule/model/version field
presence and rollback-origin counts. It does not return model names, site
names, versions, operators, IDs or scheduled dates. The source has no execution
state, and scheduled plans are kept distinct from upgrade logs/results. Live
support is unknown.

A synthetic 20-plan payload measured 2,002 source tokens and 166 projected
tokens (91.71% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; serialized
payload only.

With `js-tiktoken` 1.0.21 (`o200k_base`), a synthetic 20-tunnel
source-shaped payload measured 1,743 tokens before projection and 90 after
(94.84% fewer serialized-payload tokens). This is a fixture measurement, not
observed agent billing or controller traffic.

`GET /v1/sites/{site_ref}/wan-ports/availability-summary` and its MCP tool
`omada_site_wan_port_availability_summary` query the selected site with one
documented function code from 0 through 15. The redacted result counts rows and
documented flags without returning port labels, UUIDs, protocol strings or IP
addresses. It does not identify a physical port or report link state. Hardware
Controller 6.3.0 and CBC 6.3.0 document the operation; ER7212PC does not. Live
support remains unknown.

A synthetic eight-port response measured 554 serialized source tokens and 98
projected tokens (456 fewer; 82.31%) with `js-tiktoken` 1.0.21 /
`o200k_base`. This excludes MCP framing, live data and billed agent usage.

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

A synthetic 20-MAC topology response measured 241 tokens before projection and
87 after (63.90% fewer serialized-payload tokens) with the same tokenizer.
This comparison does not include MCP framing or tool schemas.

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

`GET /v1/sites/{site_ref}/lan-client-inventory/summary` and
`omada_site_lan_client_inventory_summary` read the LAN client inventory route
(`getGridAllClients_1` in the 6.3.0 exports; `getGridAllClients` in ER7212PC).
They fetch at most ten fixed pages of 100 rows and report the documented total,
returned coverage and whether each row has a usable device-type field. MACs,
names and raw device-type values are omitted. Results above 1,000 rows are
partial; this inventory does not establish live connectivity or recent activity.
The three source schemas match, but live behavior has not been tested.

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

`site_stack_network_summary` accepts one `stack_ref` from the site's stack
connection summary, refreshes the site stack list, and binds that reference to
exactly one current stack before reading `getStackNetworkList`. It reports
bounded row counts, documented DHCP modes, state and IPv6 coverage. VLAN IDs,
network IDs/names, member details, addresses, DHCP settings and VRF identifiers
are omitted. The read caps at 1,000 rows and reports omissions. Offline tests
cover binding and projection; no stack hardware was available for live testing.

`site_switch_oui_vlan_summary` reports only documented enable flags and port
scope modes (`0` all device ports, `1` custom device ports) for up to 1,000
rules. Rule names and IDs, device/port lists, OUI prefixes and VLAN values are
omitted, and no enforcement or actual assignment is inferred. All three API
exports contain the operation. The ER7212PC export explicitly restricts it to
Omada Pro and documents error `-44119` for non-Pro controllers, so ER7212PC is
not described as supported. Fixture tests cover projection and routing; live
support remains unknown.

`site_stack_dhcp_user_summary` accepts a stack reference from the site's stack
inventory, refreshes that inventory, and proceeds only when the reference
matches exactly one stack in a complete result. It counts documented user
types (`0` device, `1` client) and binding states (`0` dynamic, `1` static) in
up to 1,000 returned rows. Addresses, names, binding rows, network/server
identities and mapping objects are omitted. It does not claim current leases or
wired-client state. All three exports document the operation; stack hardware
and live support were not tested.

`site_stack_vlan_interface_summary` binds the supplied `stack_ref` against a
complete, fresh inventory for the selected site before reading the documented
VLAN-interface list. It counts rows, unique/duplicate/missing/invalid interface
IDs, and field coverage for interface names and VLAN IDs. Names, IDs and VLAN
numbers are omitted. Hardware and CBC document the typed list response; the
ER7212PC export does not contain this operation. No live stack read was made.

`site_snmp_incompatible_summary` reads up to 1,000 controller-reported rows for
devices that do not support the documented SNMP v3 enhanced configuration.
It reports only total, returned, omitted and malformed row counts. It does not
project device details, identify individual devices or infer their SNMP
configuration. Hardware/CBC describe a narrow `DeviceVO` with MAC, stack ID,
port and IMPB fields; ER7212PC describes a broader device record. These source
schemas are kept distinct in the contract matrix. Live support is unknown.

`site_gateway_general_config_summary` refreshes the selected site's device
inventory and binds `gateway_ref` to exactly one current gateway. It reports the
documented LED mode and whether the optional `rememberDevice` and SNMP setting
objects are present. It does not infer a meaning for `rememberDevice` codes or
expose names, tags, locations or SNMP values.

`site_switch_general_config_summary` refreshes the selected site's inventory
and binds `switch_ref` to exactly one current switch. It reports the documented
LED mode, Jumbo setting scope and range validity, LAG hash setting scope and
documented mode, and SDM object presence. Source-specific site-follow fields
are reported as missing when the export does not declare them. Names, tags,
locations and SNMP values are omitted; actual forwarding is not inferred.


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
group names and SSID labels are discarded. It provides opaque `group_ref`
handles with documented primary and AP-count summaries for selecting one group.
Hardware Controller and CBC
Standard document `getApGroupList` with `Site Settings Manager View Only` or
`Network Config Page View Only`; ER7212PC does not document this route. The
fixed reader fetches bounded pages and accepts no caller filters. Offline
projection, paging, HTTP and MCP tests cover the implementation; live support
remains unknown.

`omada_site_ap_group_assignment_summary` counts AP rows with and without a
reported group assignment and the documented SSID-override counts. It omits AP
names, addresses, device/group IDs, model information and traffic values. It
uses bounded pagination without caller filters. Hardware Controller and CBC
document the typed row fields; ER7212PC does not document the route. Live
support is unknown.

`omada_site_ap_group_info_summary` takes a `site_ref` and a `group_ref` from the
fresh site AP-group summary. It refreshes that group inventory, requires one
unique matching group, then reports the documented primary flag, AP count and
remaining SSID bindings by band. Group IDs, names and SSID labels are omitted.
Hardware Controller and CBC document this read; ER7212PC does not. It reports
controller configuration only and makes no claim about effective WLAN service.

A synthetic 20-group AP inventory with repeated SSID labels was serialized and
counted with js-tiktoken 1.0.21 / `o200k_base`: the raw page used 1,412 tokens
and the aggregate plus group-selection references used 728. It excludes HTTP
framing, MCP schemas, prompts and billed agent usage; it is not a live
controller measurement.

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

`omada_site_group_profiles_coverage` reads the separate fixed
`getGroupProfiles` site list; it does not use the optional type-specific route
or the AP-group and ACL readers. The output is bounded to 500 rows and contains
only documented field-presence/type counts, including `type`, `count` and
`buildIn`. It does not return identifiers, labels, setting values or list
contents, and it does not establish list completeness, effective rules or
enforcement. All three supplied exports document the route and view-only
permissions. Live support is unknown.

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
documented int32 inventory and activation counters, plus the documented
`good`, `fair`, `poor` and `noData` int32 counters nested under switch, EAP and
gateway health objects. The separate flat `allSwitchsAndGateway` counter
remains the combined switch/gateway total. The same nested shape is present in
the hardware 6.3, CBC 6.3 and ER7212PC 6.2.14 exports. Missing or invalid values are omitted and
mark the result partial; identifiers and unknown names/values are not exposed.
All three descriptions list `Site Device Manager View Only` or `MSP Device
Manager View Only`. Fixture tests cover each mapping, malformed values, exact
GET, response redaction, HTTP/MCP dispatch and controller binding. No live
controller response has been observed.


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

`GET /v1/sites/{site_ref}/dst-info` is the separate documented site-scoped DST
read. It binds the opaque site reference through the current site inventory and
reuses the same bounded DST projector, including its timestamp and timezone
validation. The exports describe `timeZone` as the site's timezone; they do not
document inheritance from controller settings or a required permission. The
result reports only the selected site's documented response fields. Fixture
coverage exists; live support is unknown.


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
`GET /v1/sites/{site_ref}/incidents/categories` with the required integer
query parameter `category` (11 through 19). The MCP tool accepts the same
required integer argument. The caller must select one documented numeric
category code; there is no default. The
connector uses a fixed trailing 24-hour window, returns the selected code and
window as query context, and returns at most 128 validated aggregates without
records or identities. Hardware
Controller 6.3.0 and CBC Standard 6.3.0 document the route with
`Incidents Page View Only`; ER7212PC 6.2.14 does not. Live support remains
partially verified: one OC200 request for a selected category returned a
partial result through HTTP and MCP. Other category codes and ER7212PC remain
unverified.

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

The controller-wide adoption tip is a separate count-only read at
`GET /v1/controller/device-adoption-tip/summary`. It maps the documented
controller `GET /openapi/v1/{omadacId}/adopt-tip` and returns only the bounded
`adopted_device_count` and `recommended_device_count` fields. Explicit zero is
valid; missing, invalid, or unknown fields are reported through coverage
counts. This is distinct from the MSP adoption-tip route and does not describe
site membership, pending hardware, future device support, or caller permission.
The route and both fields are documented in the supplied ER7212PC 6.2.14,
Hardware Controller 6.3.0, and CBC Standard 6.3.0 exports. Offline HTTP/MCP and
projection fixtures cover the fixed GET; live controller behavior remains
unknown.

The controller client-correction option catalog is a separate fixed GET at
`GET /v1/controller/client-correction-options/summary`, mapped to the
documented `/openapi/v1/{omadacId}/correction-list`. It exposes only bounded
`key` and `label` pairs from the documented `typeList` and `vendorList`; icons
and unknown fields are omitted. Each source list may contain at most 1,200
options; missing, malformed, duplicate, or over-limit options are reported as
incomplete coverage. This route-local bound does not change the connector's
shared response-size or timeout limits. Successful MCP replies for this tool use
UTF-8 outer-envelope serialization to avoid ASCII-escape expansion while
preserving both result forms. The shared 1 MiB response cap still applies. It
does not correct clients or read client resources. The GET is documented in
the supplied ER7212PC 6.2.14, Hardware Controller 6.3.0, and CBC Standard
6.3.0 exports with controller ID as its only parameter and `Site Clients
Manager View Only` permission. Offline HTTP/MCP and projection fixtures cover
the fixed route; live controller behavior remains unknown.

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

## Site remote-logging summary

`GET /v1/sites/{site_ref}/remote-logging/summary` reports the documented enable flag, optional client-log flag, and `resource` category (0 new, 1 template, 2 override). It only indicates whether destination host and port are configured; their values are omitted. The connector does not claim that logs were delivered. All three API exports document this read; live behavior is unknown.

## Controller firmware failed-device counts

`GET /v1/controller/firmware-upgrades/inventory?page_number=1&page_size=100` returns opaque selectors for one page of the documented controller firmware-log inventory. Pages are one-based, limited to ten, and accept at most 100 rows each; reported coverage is therefore capped at `page_size × 10` and marked partial when the controller has more. It omits log IDs, names, sites, operators, dates, models and firmware versions.

`GET /v1/controller/firmware-upgrades/{upgrade_log_ref}/failed-devices-summary` refreshes the bounded inventory, resolves one unique selector, then reads failed-device pages. It counts only documented `gateway`, `switch` and `ap` types; unknown types and truncated results are marked partial. Names, MAC addresses, sites, versions and raw IDs are omitted. It never changes firmware. The source exports document this read; live support is unknown.

A synthetic workflow with 20 failed-device rows measured 1,433 source-response tokens against 191 tokens for the two connector responses (86.67% fewer) using `js-tiktoken` 1.0.21 / `o200k_base`. This includes the selector inventory read and its fresh re-read; it excludes prompts, tool schemas and billed agent usage.

## Switch-stack cable-test log counts

`GET /v1/sites/{site_ref}/stacks/{stack_ref}/cable-test-log-summary` refreshes the selected site's stack inventory and reads stored stack cable-test logs. It reports documented log-type and port-list entry counts across at most 64 logs, with at most 128 entries per port list. Repeated port mentions count as logged entries rather than unique ports. Port identifiers and raw timestamps are omitted; the result does not start a test or assert when the stored logs were produced. Live support is unknown.

A synthetic 20-log response with 200 port-list entries measured 1,510 source-response tokens against 124 projected tokens (91.79% fewer) with the same tokenizer. It excludes prompts, tool schemas and billed agent usage.

## Site application-family selectors

`GET /v1/sites/{site_ref}/application-families` reads the documented site DPI
family list. It returns only unique, valid nonnegative int32 family IDs as
decimal `family_refs` for the existing category application/client readers.
Family names, descriptions and raw rows are omitted. Invalid or duplicate
entries make the result partial, and lists over 100 rows are rejected. The
manufacturer documents view-only site permissions and requires a DPI-capable
gateway; live support is unknown.

## Site gateway model reference list

`GET /v1/sites/{site_ref}/gateway-supported-model-references` reads the
documented site list of gateway model IDs and names offered for
pre-configuration. It returns only validated, unique reference pairs, bounded
to 100 entries with names up to 128 characters. Duplicate or invalid rows make
the result partial; a missing `supportModels` field is not treated as an empty
list. The result is reference data only and does not describe installed devices
or imply current gateway support. The manufacturer documents Site Settings
Manager View Only or Network Config Page View Only; live support is unknown.

## Site portal domain setting state

`GET /v1/sites/{site_ref}/portal-domain-setting-summary` reads the
documented `autoRefresh` state and, only when it is explicitly false, reports
whether a nonempty URL value was present. No URL string, host, address, path or
credential is returned. The URL field is ignored when auto-refresh is enabled
or unknown. Missing and invalid states remain distinct; the read changes no
portal setting. The source requires Network Config Page View Only; live
support is unknown.

## Site voucher currency options

`GET /v1/sites/{site_ref}/hotspot/voucher-currency-options` reads the
documented `currencyList` and `selectedCurrency` short-code fields. It preserves
the selected string separately from the candidate list, and distinguishes a
missing or malformed list from a valid empty list. Candidate codes are bounded
to 100 rows and 32 printable characters; duplicate and invalid values are
counted. The result does not classify ISO currencies, provide exchange rates or
prices, or change voucher settings. The source requires Site Hotspot Manager
View Only; live support is unknown.

## All-time hotspot voucher summary

`GET /v1/sites/{site_ref}/hotspot/vouchers/all-time-summary` reads the selected site's documented all-time hotspot voucher summary. It reports independent `voucher_counts` and `voucher_durations_minutes` maps for `current`, `inuse`, `expired`, `unused` and `created`. Missing values are `null`; `missing_fields` and `invalid_fields` identify each affected metric. Amount and currency source values are omitted. The output contains no voucher codes or user data and does not report revenue or derive relationships among category totals. `supportVoucherTrafficStat` is reported only as the documented capability flag; it is not a traffic measurement. Live support is unknown.

A synthetic complete five-category response measured 124 source JSON tokens and 98 tokens in the full connector result (20.97% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`. This fixture measurement is not billed agent usage.

## Controller upgrade-log summary

`GET /v1/controller/firmware-upgrades/summary` reads only the first 100 rows from the authenticated controller's documented upgrade log. It reports source total and sample coverage plus counts of rollbacked entries, rows with reported failed devices, and rows with an upgrade time. It returns no dates, device/model details, site names, operator names, versions, or identifiers. It never starts or changes an upgrade. Live support is unknown.

The controller-wide log notification summary (#78) reads `getLogSettingForGlobalV2`, distinct from the site-scoped rules in #69. It counts only documented alert, event, email and webhook switches and top-level enablement presence. Category keys, message text, webhook IDs and delay values are omitted. The schema does not report delivery outcomes; live support is unknown.

A synthetic 20-category source response and projection measured 695 → 150 serialized tokens (78.42% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; this fixture result is not billed agent usage.

The firmware-plan model summary (#79) reads the paginated `getGridPlanUpgradeModelList` route from all three exports. It counts model-type metadata presence and the documented good/critical and up-to-date/new-version status codes. Model names and firmware versions are omitted. Pagination is capped at 1,000 rows with coverage marked when the source total is larger. It does not trigger an update or imply compatibility. Live support is unknown.

## Controller critical firmware-model count

`GET /v1/controller/firmware-critical-model-count/summary` reads the documented
controller-wide `GET /openapi/v1/{omadacId}/upgrade/overview/critical` route.
Hardware Controller 6.3, CBC 6.3 and ER7212PC 6.2.14 document the route,
`criticalNumber` as an int32, and `Site Manual Firmware Upgrade View Only`.
The connector exposes only a valid nonnegative count and coverage fields; an
explicit zero is complete, while a missing, invalid, or additional unknown
field remains partial. The general error table associates `-1501` with the
Omada Cloud Platform; the route-specific cause remains unspecified, and the
standard connector error path retains the numeric code when returned. This
count does not identify models or establish
current firmware security, platform availability, or that an upgrade ran.
Offline verified; live controller support is unknown.

`GET /v1/controller/firmware-email-reminder/status` reads the documented
controller-wide firmware email-reminder `enable` Boolean. Missing, null or
non-Boolean values remain incomplete; false is valid. The result reports the
configured switch only and makes no claim about delivery, recipients,
authorization or upgrades. It sends no mail and performs no upgrade.

A synthetic 20-model source response and projection measured 789 → 117 serialized tokens (85.17% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`; this fixture result is not billed agent usage.

The selected S2S VPN peer summary (#80) first refreshes the selected site's documented VPN inventory, then resolves a unique opaque VPN reference before requesting its peer-status pages. It reports counts for the documented `status` filter meanings (0 disconnected, 1 connected); other or missing codes remain unknown. VPN and peer identities, names, addresses, ports and traffic counters are omitted. The inventory's separate `status` flag is not interpreted as tunnel connectivity. Live support is unknown.

A synthetic workflow with 20 VPN inventory records and 20 peer rows measured 2,608 source JSON tokens versus 597 projected tokens (77.11% fewer) using `js-tiktoken` 1.0.21 / `o200k_base`. This compares the two serialized API responses with the two connector summaries; it excludes prompts, schemas and billed agent usage.

`GET /v1/sites/{site_ref}/nat-exceptions/summary` and MCP tool
`omada_site_nat_exception_summary` page through the selected site's documented
NAT exception configuration. The result counts documented rule status, LAN
list coverage and entry totals, plus WAN-interface coverage; it omits rule
names, IDs, descriptions and raw network/interface values. This describes
stored configuration only and does not establish effective enforcement or
traffic behavior. The operation is documented by Hardware Controller and CBC,
not ER7212PC. Live support is unknown.

A synthetic 20-rule response measured 1,200 serialized JSON tokens before
projection and 150 in the final result (87.5% fewer) using `js-tiktoken`
1.0.21 with `o200k_base`. These fixture bodies exclude transport framing,
live payloads and billed agent usage.

`GET /v1/sites/{site_ref}/vpn/site-to-site-v2-summary` and MCP tool
`omada_site_s2s_vpn_v2_summary` read the paginated v2 S2S VPN inventory. This
adds the documented VPN type and status flags, network-selection coverage and
four S2S support flags to the existing v1 opaque-reference inventory. It
counts only; names, identifiers, WAN/network references, custom subnet values,
peer details and user/client counts are omitted. The boolean VPN status is not
a tunnel connectivity result. All three exports document the operation; live
support is unknown.

A synthetic 20-row v2 inventory measured 2,999 serialized source-response
tokens and 328 projected-result tokens (89.06% fewer) with `js-tiktoken`
1.0.21 and `o200k_base`. Fixture bodies exclude HTTP/MCP framing, live payloads
and billed agent usage.


`controller_sdwan_group_summary` reads the controller-scoped
`getGridSdWanGroupBrief` endpoint using bounded pagination. It returns group and
page counts, field-presence coverage for hub type/model/version, and the sum of
documented per-group device counts. That sum is group memberships, not distinct
devices. IDs, group names and hub values are omitted. Hardware Controller and
CBC Standard document the operation; ER7212PC does not. It issues opaque refs
only for unique current group IDs, for the separate member summary; raw IDs
remain omitted. No status or enabled field is documented, and live support is
unknown.

A synthetic 20-group fixture measured 902→55 serialized JSON tokens (93.90% fewer) with `js-tiktoken` 1.0.21 and `o200k_base`. The fixture and summary exclude HTTP/MCP framing, live payloads and billed agent usage.

`site_vpn_server_config_summary` reads the documented v2 client-to-site VPN
server grid and reports counts by protocol and by its boolean VPN status flag.
It omits identities, WAN/network values, user/client counts and other settings.
The source flag does not establish tunnel connectivity; the separate operational
status read remains distinct. All three source exports document the operation;
live support is unknown.

The synthetic 20-server fixture measured 882→128 serialized JSON tokens
(85.49% fewer) with `js-tiktoken` 1.0.21 and `o200k_base`; this excludes
transport framing, live payloads and billed agent usage.

`site_remote_access_tunnel_status_summary` reads the site-scoped
`getTunnelsStatus` operation and counts the documented remote-access connection
codes separately from the open/closed flag. Tunnel IDs and names are omitted;
unknown values remain unknown and the list is capped at 1,024 rows. All three
source exports document the fields; live support is unknown.

The synthetic 20-tunnel fixture measured 450→110 serialized JSON tokens
(75.56% fewer) with `js-tiktoken` 1.0.21 and `o200k_base`; transport framing,
live payloads and billed agent usage are excluded.

`site_ids_ips_config_summary` reads `getIpsConfig` for one selected site. It
reports the documented enable and geo-identification flags, mode and detection
level codes, and the number of configured custom categories. It omits schedule
IDs and raw category values, and reports configuration only; it does not claim
that attacks were detected or blocked. All three API exports document the
operation; live support remains unknown.

A synthetic IDS/IPS response fixture measured 65 source JSON tokens and 46
summary JSON tokens (29.23% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`.
`site_gateway_webfilter_summary` reads the documented gateway URL-filter grid
for one site, at most 1,000 rules. It summarizes the documented gateway/AP rule
type, enabled state, optional keyword/category/schedule flags and source
feature-support flags. Rule IDs, names, URLs, keywords, category values, source
IDs and schedule values are omitted. It reports configuration only; live support
is unknown.

A synthetic 20-rule gateway response measured 2,005 source JSON tokens and 225
summary JSON tokens (88.78% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`.

`site_gateway_qos_class_summary` reads the documented gateway QoS class-rule
grid for one site, at most 1,000 rules. It counts documented enabled/disabled
state, IPv4/IPv6 codes and class 1/2/3 values. Local/remote address-group
values, service IDs, rule IDs and DSCP values are omitted. The output describes
configuration only; it does not infer traffic matches or throughput.

A synthetic 20-rule gateway fixture measured 1,109 source JSON tokens and 113
summary JSON tokens (89.81% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`.

A synthetic 20-rule webfilter page measured 2,005→225 serialized JSON tokens
(88.78% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`.

`site_ap_webfilter_summary` reads the separate AP URL-filter grid for one site,
up to 1,000 rules. It counts documented AP rule types, URL/category filter
modes, reported status and feature-flag coverage, plus grid feature support.
Rule text, URLs, keywords, categories, schedule values, names and source
identities are omitted. Unexpected gateway or unknown rows make the result
partial; the summary does not claim enforcement.

`site_url_filter_general_summary` reports the site's documented SafeSearch and
block-page flags. It omits the optional block-page message and describes
controller-reported settings only. Effective filtering is not inferred. Live
support for both reads remains unknown.

## WAN limitation entry summary

`GET /v1/sites/{site_ref}/wan/unsupported-functions/summary` and
`omada_site_wan_unsupported_function_summary` use the documented fixed upstream
query `filter=1` for DS-Lite/MAP-E WAN functions. The response reports only the
number of string entries; entry text is discarded and is not treated as a
device capability or active WAN state. Empty, missing, invalid and truncated
lists are distinct. All three exports document the operation; live support is
unknown.

A synthetic 20-entry response measured 331 source tokens and 40 summary tokens
(87.92% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`. This excludes prompts,
tool schemas, transport framing and billed agent usage.

## Bonjour profile summary

`GET /v1/sites/{site_ref}/bonjour/profiles/summary` and
`omada_site_mdns_profile_summary` read the site's documented Bonjour service
profiles. The summary counts default-profile flags and the number of documented
`serviceIds` entries per profile, capped at 1,000 profiles. Profile IDs, names
and service strings are omitted. It complements the separate mDNS rule summary
and does not report Bonjour reachability. All three exports document the read;
live support is unknown.

A synthetic 20-profile response measured 722 source tokens and 103 summary
tokens (85.73% fewer) with `js-tiktoken` 1.0.21 / `o200k_base`. This excludes
prompts, tool schemas, transport framing and billed agent usage.

`site_vpn_client_config_summary` reads the documented v2 client-to-site VPN
client grid using only its required page parameters. It counts documented
protocol codes and the boolean VPN status flag, while omitting client
identities, addresses, peer details and credentials. The flag is not interpreted
as tunnel connectivity. Live support is unknown.

## Saved SD-WAN group member summary

`GET /v1/controller/sdwan-groups/{group_ref}/devices/summary` accepts an
opaque `group_ref` from the controller SD-WAN group inventory. The connector
refreshes that inventory for each read and proceeds only for one unique match.
It counts member records and documented boolean `supportSdWanNat` values.
Device/site/group identifiers, names, WAN IPs and member details are omitted;
NAT support is a documented capability flag, not a routing or traffic result.
Hardware Controller and CBC Standard document the endpoint; ER7212PC does not.
Live support is unknown.

Synthetic token measurements used `tiktoken` 0.9.0 / `o200k_base`: a 20-client
VPN grid was 1,787→127 serialized tokens (92.89% fewer); a 20-member SD-WAN
group detail was 2,798→78 tokens (97.21% fewer). The latter excludes its fresh
inventory request. Both measures exclude transport framing and billed agent
usage.

`site_lan_interface_isolation_summary` counts only controller-reported
isolation flags for a site's LAN interfaces. It sends no optional filters,
omits names, IDs and VLAN values, and does not claim real network separation.
All three exports document the endpoint; the ER7212PC operation ID is
`getAllInterfacesForBatchIsolate` without the `_1` suffix.

`site_ospf_interface_summary` reads at most 1,000 OSPF interface rows per site.
It counts documented interface and network types, valid configured link costs,
and optional-field coverage. It omits device/interface identities, names,
addresses, VLAN values and authentication keys. Missing source fields are
reported as unreported; no neighbor state is inferred. The ER7212PC export
does not declare several loopback and passive-interface fields present in the
Hardware/CBC schemas. Live support remains unknown.

`site_switch_qos_summary` reads a site's typed switch QoS grid, at most 1,000
rules. It sends only `page` and `pageSize`, and counts documented enabled state,
rule type and queue 0–7. Names, identifiers, addresses and ports are omitted;
it makes no claim about actual traffic. The ER7212PC export declares only a
generic response for this operation, so live support there is unknown and
nonconforming responses are rejected.

`site_switch_ddm_summary` takes a `site_ref` and `device_ref` from the site's
device inventory. Each read refreshes that inventory and requires one unique
switch match. It counts only the documented data-valid, transmit-fault and
signal-loss flags. Port identifiers and optical readings are omitted; it does
not diagnose switch or module health. The ER7212PC export has no effective row
contract, so support is not claimed there.
