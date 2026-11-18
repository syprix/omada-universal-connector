Warning: truncated output (original token count: 34056)
Total output lines: 1287

# Development Open API inventory routes

## Controller threat severity counts

`GET /v1/controller/threat-severity-summary?start_ms=<UTC-epoch-ms>&end_ms=<UTC-epoch-ms>`
and MCP tool `omada_controller_threat_severity_summary` expose the source
operation `getThreatCount` through the fixed GET
`/openapi/v1/{omadacId}/security/threat-management/severity` route. Hardware
Controller 6.3.0, CBC Standard 6.3.0 and ER7212PC 6.2.14 document the same five
int64 fields: `critical`, `major`, `moderate`, `minor` and `low`. The source
documents `startTime` and `endTime` as required int64 query parameters but does
not specify the unit; the connector interprets these as UTC epoch milliseconds
and caps the interval at 24 hours. Output is limited to the five counters.
Missing fields remain `null` and mark the response partial.
No live controller request was made; support and timestamp-unit compatibility
remain unknown.

## Site-bound threat window summary

`GET /v1/sites/{site_ref}/threats/window?start_ms=<UTC-epoch-ms>&end_ms=<UTC-epoch-ms>&archived=false`
and MCP tool `omada_site_threat_window_summary` expose the documented
`getGlobalThreatList` read through one fixed controller endpoint. The connector
resolves one opaque site reference from its current site inventory and passes
only that site's ID upstream. The source requires `archived`, 1-based `page`,
`pageSize` from 1 to 1000, and `filters.startTime`/`filters.endTime` in seconds;
the public route accepts a UTC-millisecond window capped at 24 hours and fixes
page size at 1000 with at most 10 pages. Output contains counts for the five
documented severity codes, an unknown-severity count, the returned/total row
counts and observed time bounds. Threat IDs, signatures, classifications,
addresses, locations and other row fields are omitted. `partial` is true when
the page cap prevents reading all reported rows. All three original exports
document the same operation and row fields; permission is not specified in the
operation documentation. Fixture tests cover projection, paging, HTTP and MCP.
No live controller request was made.

## Controller scenario list

`GET /v1/controller/scenarios` and MCP tool
`omada_controller_scenarios` expose `getScenarioList` through the fixed
`/openapi/v1/{omadacId}/scenarios` route. All three exports describe a response
as a list of strings and provide no query/body parameters or operation-specific
permission. The connector validates each string, returns at most 100 items and
marks the response partial if an entry is invalid or the source list is longer.
No controller request was made; live support remains unknown.

## Controller scenario differences

`GET /v1/controller/scenario-differences` and MCP tool
`omada_controller_scenario_differences` expose `getScenarioListDifference`
through `/openapi/v1/{omadacId}/scenarios/difference`. All three exports
document a set/list of rows with a 1–128 visible-ASCII `name` and `isDefault`
boolean, with no query/body parameters or operation-specific permission. The
connector validates those fields, returns at most 100 rows and marks invalid or
truncated results partial. No live controller request was made.

The connector contains fixed, read-only Omada Open API
routes. Earlier reads have local fixture tests and some were checked on one
OC200 running controller 6.3.0.45. The Wi-Fi health timeline and switch
diagnostic routes below have fixture coverage only; no live tests were run
for them. Read routes do not enable configuration changes. A check on one
controller does not establish compatibility with other releases or families.

The current 2026-11-13 container probe exercised only the site inventory
(`GET /sites`). The 2026-11-11 read-only evidence records HTTP 200 for sites,
devices and clients on source commit `c72326070cf9c9ed16386298c73fed50ec07b0f0`;
device and client inventory have not been rechecked in the current image.

| Connector route | Controller request | Result |
|---|---|---|
| `GET /v1/sites` | Paginated `GET /openapi/v1/{omadacId}/sites` | Opaque site references |
| `GET /v1/controller/settings/client-recognition` | `GET /openapi/v1/{omadacId}/controller/setting/client-recognition` | Strict documented `enable` Boolean only; requires `Global Other Setting View Only`; all three API exports document the same field |
| `GET /v1/controller/devices/statistics` | `GET /openapi/v1/{omadacId}/devices/stat` | Fourteen documented int32 inventory/health counters only; nested switch/EAP/gateway health objects are omitted because the exports differ on their schemas; requires `Site Device Manager View Only` or `MSP Device Manager View Only` |
| `GET /v1/controller/settings/client-active-timeout` | `GET /openapi/v1/{omadacId}/controller/setting/active-timeout` | Returns the documented int32 minute value; all exports describe 3–10 minutes, while the ER7212PC example is `0`; requires `Global Other Setting View Only` |
| `GET /v1/controller/settings/ui-interface` | `GET /openapi/v1/{omadacId}/controller/setting/ui-interface` | Returns documented time-zone, refresh-rate, private-labeling-enabled and MAC-format codes; private-label URL and file metadata are reduced to presence flags; requires `Global Other Setting View Only` |
| `GET /v1/controller/settings/retention` | `GET /openapi/v1/{omadacId}/controller/setting/retention` | Bounded data-retention flags, numeric values and available-day codes; requires `Global Other Setting View Only` |
| `GET /v1/controller/dst-info` | `GET /openapi/v1/{omadacId}/dst-info` | Validated DST enable/status, mode and offset codes, schedule rules, timestamps and time-zone string; no specific permission is stated in the exports |
| `GET /v1/controller/settings/experience-improvement` | `GET /openapi/v1/{omadacId}/global/controller/setting/exp-improve` | Strict documented experience-improvement participation Boolean; requires `Global Other Setting View Only` |
| `GET /v1/controller/client-detail-information` | `GET /openapi/v1/{omadacId}/client-detail-information` | Client-recognition, health, history and trend enablement flags plus the documented MSP-follow setting; requires `Global Other Setting View Only` |
| `GET /v1/controller/settings/general` | `GET /openapi/v1/{omadacId}/global/controller/setting/general` | Bounded controller name, time zone and region plus validated nested DST configuration; requires `Global Other Setting View Only` |
| `GET /v1/controller/roles/summary` | `GET /openapi/v1/{omadacId}/roles` | Role totals by documented type and source, default-role count and permission-code counts; role IDs, names and permission field names are omitted; requires `Global Roles Manager View Only`; all three exports document the same response schema |
| `GET /v1/controller/roles/available-summary` | `GET /openapi/v1/{omadacId}/roles/available` | Available-role totals by documented type and source; role IDs and names are omitted; requires `Global Roles Manager View Only`; all three exports document the same response schema |
| `GET /v1/controller/settings/device-access` | `GET /openapi/v1/{omadacId}/controller/setting/services/device-access` | Three documented Boolean switches only (`webControlHttp`, `webControlHttps`, `appDiscovery`); requires `Global Other Setting View Only`; all three exports document the same read schema |
| `GET /v1/controller/settings/backup-schedule` | `GET /openapi/v1/{omadacId}/backupschedule/task` | Enabled state and bounded retention/storage facts; file paths, file-server details and credentials are omitted; `Global Other Setting Modify`; Hardware Controller and CBC only |
| `GET /v1/controller/cloud-access` | `GET /openapi/v1/{omadacId}/cloud/status` | Enablement and validated connection status; owner value omitted; all three exports |
| `GET /v1/controller/settings/device-management` | `GET /openapi/v1/{omadacId}/device-mgmt` | Three documented Boolean device-access switches through a separate global path; `Global Other Setting View Only`; all three exports |
| `GET /v1/controller/cloud-binding` | `GET /openapi/v1/{omadacId}/cloud/remote/bind/status` | Remote binding enabled state only; all three exports |
| `GET /v1/controller/maintenance/backup-status` | `GET /openapi/v1/{omadacId}/maintenance/backup/result` | Documented idle/finished or running state; Hardware Controller and CBC require `Global Other Setting Modify`, ER7212PC requires `Global Other Setting View Only` |
| `GET /v1/controller/maintenance/restore-status` | `GET /openapi/v1/{omadacId}/maintenance/restore/result` | Documented finished/prepared/running/failed state; Hardware/CBC: one of `Global Other Setting Modify` or `Maintenance Page Modify`; ER7212PC: one of four documented view-only permissions |
| `GET /v1/controller/settings/privacy-policy` | `GET /openapi/v1/{omadacId}/privacy-policy` | Returns only an enabled Boolean from status 0/1; the ER7212PC schema defines those values, while Hardware Controller and CBC omit the response schema; all three list the GET |
| `GET /v1/controller/settings/mail-server-status` | `GET /openapi/v1/{omadacId}/mail/status` | Returns transport/authentication Booleans and configuration-presence flags; email addresses, server, port, user and authorization code are omitted; one of `Global Other Setting View Only`, `Global Users Manager View Only` or `Global Export Data Access`; all three exports |
| `GET /v1/msp/{msp_ref}/cloud-access` | `GET /openapi/v1/msp/{mspId}/cloud/status` | Enabled/connection state and owner presence only; CBC Standard and ER7212PC |
| `GET /v1/msp/{msp_ref}/privacy-policy` | `GET /openapi/v1/msp/{mspId}/privacy-policy` | Enabled state only; CBC Standard only, `MSP Other Settings View Only` |
| `GET /v1/msp/{msp_ref}/dst-info` | `GET /openapi/v1/msp/{mspId}/dst-info` | Bounded DST mode, enablement, availability, offset, timezone, schedule rules and timestamps; CBC Standard only; live support unknown |
| `GET /v1/msp/{msp_ref}/settings/remote-logging` | `GET /openapi/v1/msp/{mspId}/remote-logging` | Enablement and host/port presence only; target and port values redacted; CBC Standard only; live support unknown |
| `GET /v1/msp/{msp_ref}/settings/mail-server` | `GET /openapi/v1/msp/{mspId}/settings/mail-server` | Configuration-presence and documented Boolean status only; server, port, addresses and credentials redacted; CBC Standard only; live support unknown |
| `GET /v1/msp/{msp_ref}/settings/general` | `GET /openapi/v1/msp/{mspId}/general-setting` | Timezone and bounded DST settings with MSP name reduced to a presence flag; CBC Standard only; live support unknown |
| `GET /v1/msp/{msp_ref}/settings/log-notifications` | `GET /openapi/v1/msp/{mspId}/log-notification` | Bounded counts and enablement summaries only; keys, messages, and webhook IDs omitted; CBC Standard only; live support unknown |
| `GET /v1/msp/{msp_ref}/settings/retention` | `GET /openapi/v1/msp/{mspId}/retention` | Documented retention switches and values through the bounded retention projector; CBC Standard only; live support unknown |
| `GET /v1/msp/{msp_ref}/settings/ui-interface` | `GET /openapi/v1/msp/{mspId}/ui-interface` | UI preferences and bounded codes; private-label URL, file ID and name redacted; CBC Standard only; live support unknown |
| `GET /v1/msp/{msp_ref}/settings/user-interface` | `GET /openapi/v1/msp/{mspId}/settings/user-interface` | Refresh and private-label enablement summary; URL, file ID and name redacted; CBC Standard only; live support unknown |
| `GET /v1/msp/{msp_ref}/roles/available-summary` | `GET /openapi/v1/msp/{mspId}/roles/available` | Role type/source/default counts only; role names and IDs omitted; CBC Standard only; live support unknown |
| `GET /v1/msp/{msp_ref}/roles/customer/available-summary` | `GET /openapi/v1/msp/{mspId}/roles/customer/roles/available` | Customer-role type/source/default counts only; role names and IDs omitted; CBC Standard only; live support unknown |
| `GET /v1/controller/settings/remote-logging` | `GET /openapi/v1/{omadacId}/global/controller/setting/syslog` | Enabled state and host/port presence only; actual destination and port values are redacted; requires `Global Other Setting View Only`; all three exports document the read |
| `GET /v1/controller/settings/remote-logging-tip` | `GET /openapi/v1/{omadacId}/global/controller/setting/syslog/tip` | Same redacted projection on a separate documented operation; requires `Global Other Setting View Only`; all three exports document the read |
| `GET /v1/sites/{site_ref}/devices` | Paginated `GET /openapi/v1/{omadacId}/sites/{siteId}/devices` | Opaque device references, model, type, status and firmware when present |
| `GET /v1/sites/{site_ref}/device-inventory-summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/devices/all` | Total, coarse type and documented integer-status counts; no device identities; response-schema equivalence to the paginated DeviceInfo route remains unconfirmed in the reduced catalog |
| `GET /v1/sites/{site_ref}/olts/{device_ref}/system-info` | `GET /openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/system/system-info/configs` | Site-inventory-bound OLT; keeps uptime and documented configuration status flags, while omitting description, name, contact, MAC, serial, versions and system time; `Site Device Manager View Only`; all three exports document the schema |
| `GET /v1/sites/{site_ref}/olts/{device_ref}/management-interfaces` | `GET /openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/system/management-system-interface/get` | Site-inventory-bound OLT; returns interface count and counts by documented type; omits interface values and IDs; `Site Device Manager View Only`; all three exports document the schema |
| `GET /v1/sites/{site_ref}/olts/{device_ref}/onu-autofind-inventory-summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/olts/{deviceMac}/pon/onu-register/autofinds/list` | Requires validated `pon_port`, `page_number` and `page_size`; reports only the discovered ONU count and page bounds; credentials, serials, MACs, LOIDs and device details are omitted; `Site Device Manager View Only`; all three exports document the schema; live support unknown |
| `GET /v1/msp/{msp_ref}/customers/{customer_ref}/sites/{site_ref}/aps/{device_ref}/mesh` | `GET /openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/aps/{apMac}/mesh/statistics` | Uses the current site inventory to resolve the AP; returns the existing bounded, identity-free mesh projection; `MSP Device Manager View Only`; ER7212PC and CBC Standard exports; live support unknown |
| `GET /v1/msp/{msp_ref}/customers/{customer_ref}/sites/{site_ref}/olts/{device_ref}/summary` | `GET /openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/olts/{deviceMac}` | Inventory-bound OLT detail summary; identifiers, addresses, serial/license/location fields and raw downstream devices omitted; `MSP Device Manager View Only`; ER7212PC and CBC Standard; live support unknown |
| `GET /v1/msp/{msp_ref}/customers/{customer_ref}/sites/{site_ref}/olts/{device_ref}/ports-config-summary` | `GET /openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/olts/{deviceMac}/l2-feature/eth-port/port/unit1/list` | Aggregated Ethernet port states/speeds only; physical labels, descriptions and LAG names omitted; `MSP Device Manager View Only`; ER7212PC and CBC Standard; live support unknown |
| `GET /v1/msp/{msp_ref}/customers/{customer_ref}/sites/{site_ref}/olt-ports-summary` | `GET /openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/eth-port/and/pon-port/list` | Site-level Ethernet/PON counts and status aggregates; port/downlink identities omitted; `Site Device Manager View Only`; ER7212PC and CBC Standard; live support unknown |
| `GET /v1/msp/{msp_ref}/customers/{customer_ref}/sites/{site_ref}/olts/{device_ref}/pon-port-config-summary` | `GET /openapi/v1/msp/{mspId}/customers/{customerId}/sites/{siteId}/olts/{deviceMac}/pon/pon-port/configs/list` | Aggregated PON settings and ONU totals only; port/downlink device details omitted; `MSP Device Manager View Only`; ER7212PC and CBC Standard; live support unknown |
| `GET /v1/sites/{site_ref}/clients` | Paginated `GET /openapi/v1/{omadacId}/sites/{siteId}/clients` | Opaque client references and selected radio/health scalars when present |
| `GET /v1/sites/{site_ref}/clients/identity-match?client_name=…&ssid_name=…` | Paginated `GET /openapi/v1/{omadacId}/sites/{siteId}/clients` | Case-insensitive match across documented client name/host/model and SSID fields, with `wireless=true`; response counts presence of each field without values. Only one definite match and no incomplete possible duplicate returns an opaque client reference. An unresolved candidate returns `incomplete`/`partial=true`; complete zero and multiple definite matches return `unmatched` and `ambiguous` respectively. Names, SSIDs and MACs are omitted |
| `GET /v1/sites/{site_ref}/devices/{device_ref}/firmware` | `GET /openapi/v1/{omadacId}/sites/{siteId}/devices/{deviceMac}/latest-firmware-info` | Current/latest firmware version strings for a device from the selected site's current inventory |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}` | Validated AP model, firmware, CPU/memory percentages, uptime and status codes; identifiers, addresses and uplink details are omitted |
| `GET /v1/sites/{site_ref}/ssids/duplicate-summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/wireless-network/ssids/duplicate-name` | Counts only; SSID names and returned site ID are omitted; Hardware Controller and CBC document this route |
| `GET /v1/sites/{site_ref}/ssids/{ssid_ref}/ap-groups` | `GET /openapi/v1/{omadacId}/sites/{siteId}/wireless-network/ssids/{ssidId}/ap-groups` | Current-inventory SSID reference; group names/IDs omitted; returns bounded group/AP and SSID-limit counts; Hardware Controller and CBC document this route |
| `GET /v1/sites/{site_ref}/topology/network-summary` | `GET /openapi/v2/{omadacId}/sites/{siteId}/topology/available-network` | Bounded counts for wired networks and SSIDs; incomplete aggregates are `null` and partial; names, IDs and VLAN values are omitted; Hardware Controller and CBC document this route |
| `GET /v1/sites/{site_ref}/topology/vlan-summary` | `GET /openapi/v2/{omadacId}/sites/{siteId}/topology/available-vlans` | Returns bounded counts for wired networks and distinct VLANs; incomplete aggregates are `null` and partial; omits names, IDs and VLAN values; Hardware Controller and CBC document this route |
| `GET /v1/sites/{site_ref}/lan-network-config-summary` | Paginated `GET /openapi/v3/{omadacId}/sites/{siteId}/lan-networks` | Bounded purpose and feature-flag counts; network/device identifiers, VLANs, addresses and raw configuration are omitted; all three exports document the route |
| `GET /v1/sites/{site_ref}/internet/load-balance-summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/internet/load-balance` | Validated feature flags, documented mode-code counts and bounded array counts; WAN IDs, names, weights and schedule references are omitted |
| `GET /v1/sites/{site_ref}/internet/basic-port-summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/internet/basic-info` | Documented port mode/type distributions and online-detection interval; port names, IDs and raw gateway model number are omitted |
| `GET /v1/sites/{site_ref}/clients/{client_ref}` | `GET /openapi/v1/{omadacId}/sites/{siteId}/clients/{clientMac}` | Selected validated client counters and connection scalars; names, addresses and upstream identifiers are omitted. The documented wireless AP MAC maps to an opaque same-site AP reference when the site inventory binds it. |
| `GET /v1/sites/{site_ref}/wireless-groups` | Paginated `GET /openapi/v2/{omadacId}/sites/{siteId}/wireless-network/wlans` | Bounded safe group properties and resource-type codes; credentials and names are omitted |
| `GET /v1/sites/{site_ref}/wlan-group-summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/wireless-network/wlans` | Legacy deprecated route; returns only bounded primary/clone/resource counts, omitting group/site IDs and names |
| `GET /v1/sites/{site_ref}/wlan-groups/{wlan_group_ref}/ssids-summary` | Paginated `GET /openapi/v1/{omadacId}/sites/{siteId}/wireless-network/wlans/{wlanId}/ssids` | Uses a group reference from the current site's inventory; reports band/security/flag counts and omits SSID names, IDs and VLAN values |
| `GET /v1/sites/{site_ref}/ssids/{ssid_ref}` | `GET /openapi/v1/{omadacId}/sites/{siteId}/wireless-network/ssids/{ssidId}` | Redacted SSID enable/security/band flags for a fresh opaque SSID reference returned by that site's inventory |
| `GET /v1/sites/{site_ref}/clients/{client_ref}/history` | Paginated `GET /openapi/v1/{omadacId}/sites/{siteId}/clients/{clientMac}/client-history` | Fresh site-bound client reference; rows are internally MAC-checked and only whitelisted raw scalars are returned |
| `GET /v1/sites/{site_ref}/clients/{client_ref}/health/timeline` | `GET /openapi/v1/{omadacId}/sites/{siteId}/clients/{clientMac}/health/timeline?start=<ms>&end=<ms>` | Fresh site-bound client reference; fixed 24-hour millisecond window with redacted timestamps and raw int32 score values |
| `GET /v1/sites/{site_ref}/clients/{client_ref}/outage-timeline` | Client `client-timeline` and health timeline, plus site event/alert window summaries | Bounded UTC-ms window or local wall-time bounds with explicit IANA zone; combines redacted client event codes/timestamps and raw health scores with site-wide event/alert counts. Per-source samples, age, partial state and missing-field indicators are shown. Site log timestamps have no named unit in the source schema, so no event age or client-specific correlation is inferred. Resolvable roaming APs appear only as opaque, site-bound references; raw MACs, log text and inferred connection causes are excluded. |
| `GET /v1/sites/{site_ref}/health/client/timeline` | `GET /openapi/v1/{omadacId}/sites/{siteId}/health/client/timeline?start=<ms>&end=<ms>` | Fixed 24-hour aggregate timeline of documented good, average, poor and no-data client counts; fixture-tested, with no live verification |
| `GET /v1/sites/{site_ref}/capabilities` | `GET /openapi/v1/{omadacId}/sites/{siteId}/capacity` | Returns the documented 49 site capability flags, with missing/invalid/unknown counts; all three API exports document boolean values; no specific permission is stated in the supplied descriptions |
| `GET /v1/sites/{site_ref}/switch-support` | `GET /openapi/v1/{omadacId}/sites/{siteId}/switch-support` | Returns strict booleans for support of Agile and non-Agile Series Switch adoption; the route and schema match in all three API exports; no specific permission is stated in the supplied descriptions |
| `GET /v1/sites/{site_ref}/incidents/notification` | `GET /openapi/v1/{omadacId}/sites/{siteId}/anomaly/notification` | Returns bounded event and alert flags, a resource code and recipient count; recipient email addresses are never returned. All three exports document the route. ER7212PC documents it for Omada Pro only; controller support is unknown. |
| `GET /v1/sites/{site_ref}/events/window` | Paginated `GET /openapi/v1/{omadacId}/sites/{siteId}/logs/events` | Supply either `start_ms`/`end_ms` as UTC epoch milliseconds or `start_local`/`end_local` plus an IANA `time_zone`; local wall times are converted to UTC before using the documented upstream filters. Both bounds are limited to 24 hours. Ambiguous/nonexistent daylight-saving times are rejected. Returns counts and first/last upstream times only, never log text or identifiers; controller module totals are retained when supplied. Includes fetched page count and configured bounds; `partial` indicates the page limit stopped the read. |
| `GET /v1/sites/{site_ref}/alerts/window` | Paginated `GET /openapi/v1/{omadacId}/sites/{siteId}/logs/alerts` | Supply either `start_ms`/`end_ms` as UTC epoch milliseconds or `start_local`/`end_local` plus an IANA `time_zone`; local wall times are converted to UTC before using the documented upstream filters. Both bounds are limited to 24 hours. Ambiguous/nonexistent daylight-saving times are rejected. Returns counts by module and severity plus first/last upstream times only, never log text or identifiers. Includes fetched page count and configured bounds; `partial` indicates the page limit stopped the read. |
| `GET /v1/sites/{site_ref}/incidents/settings` | `GET /openapi/v1/{omadacId}/sites/{siteId}/anomaly/setting?page=1&pageSize=100` | Reads at most the first 100 site event settings and optional aggregate statistics. Raw parameter values are omitted. All three exports document the route and the fixed page filters; ER7212PC describes it for Omada Pro only. |
| `GET /v1/sites/{site_ref}/incidents/{incident_ref}/influencing-clients` | `GET /openapi/v1/{omadacId}/sites/{siteId}/anomaly/{mac}/influencing-clients?anomalyCode=<bound>&page=1&pageSize=100` | Uses an incident reference from a current device/client health-incident snapshot, with its MAC and anomaly code held server-side. Returns opaque known client references and safe connection/health flags; names, MACs and IP addresses are omitted. Hardware/CBC only; ER7212PC does not document the operation. |
| `GET /v1/sites/{site_ref}/incidents/{incident_ref}/influencing-devices` | `GET /openapi/v1/{omadacId}/sites/{siteId}/anomaly/{mac}/influencing-devices?anomalyCode=<bound>&page=1&pageSize=100` | Uses the same current-snapshot incident binding and returns opaque known device references with bounded status/health/type codes. Hardware/CBC only; ER7212PC does not document the operation. |
| `GET /v1/sites/{site_ref}/wlan-group-capacity` | `GET /openapi/v1/{omadacId}/sites/{siteId}/wireless-network/cmd/countWlans` | Returns the documented WLAN-group count and limit flag. This legacy operation is documented in all three exports and marked for future deprecation in favor of AP-group count. |
| `GET /v1/sites/{site_ref}/ap-group-capacity` | `GET /openapi/v1/{omadacId}/sites/{siteId}/count-ap-groups` | Returns the documented AP-group count and controller-wide limit flag. Hardware Controller and CBC document it; ER7212PC does not. |
| `GET /v1/sites/{site_ref}/ap-groups` | Paginated `GET /openapi/v1/{omadacId}/sites/{siteId}/ap-groups` | Bounded AP-group/AP counts, remaining SSID bindings and SSID limits; group identities and SSID labels are omitted. Hardware Controller and CBC document it; ER7212PC does not. |
| `GET /v1/sites/{site_ref}/ap-oui-rules/summary` | Paginated `GET /openapi/v1/{omadacId}/sites/{siteId}/ap-oui-rules` | Counts enabled state, SSID bindings and VLAN assignments without rule/profile identities, names, SSID labels or VLAN values; the source does not state a permission |
| `GET /v1/sites/{site_ref}/networks/{network_ref}/dhcp-server/capabilities` | `GET /openapi/v1/{omadacId}/sites/{siteId}/networks/{networkId}/dhcp-server/capabilities` | Returns the two documented DHCP client-table and server-info support booleans for a network listed in the selected site; `Site Settings Manager View Only` or `Network Config Page View Only`; all three API exports document the route and response fields |
| `GET /v1/sites/{site_ref}/networks/{network_ref}/dhcp-server/info` | `GET /openapi/v1/{omadacId}/sites/{siteId}/networks/{networkId}/dhcp-server-info` | Returns only the total available-IP count and DHCP range counts for an inventoried network; start/end addresses are omitted; `Site Settings Manager View Only` or `Network Config Page View Only`; all three API exports document the route |
| `GET /v1/sites/{site_ref}/settings/existence` | `GET /openapi/v1/{omadacId}/sites/{siteId}/setting/exist` | Returns the documented 18 gateway-setting presence flags, with missing/invalid/unknown counts; requires `Global Site Template Manager View Only`; all three API exports document this read |
| `GET /v1/sites/{site_ref}/wifi/6ghz-ap-presence` | `GET /openapi/v1/{omadacId}/sites/{siteId}/wireless-network/multi-band-6g/exist` | Reports only the documented `exist6GAp` boolean as `has_6ghz_ap`; all three API exports document the read; requires `Site Settings Manager View Only` or `Network Config Page View Only` |
| `GET /v1/sites/{site_ref}/wifi/rogue-ap-results` | Paginated `GET /openapi/v1/{omadacId}/sites/{siteId}/insight/rogueaps` | Summarizes stored scan rows by radio, channel, security and mode codes plus signal range; identities and timestamps are omitted, scan age is unknown; requires `Site Insight Manager View Only` or `Site Tools Manager View Only`; no scan is started |
| `GET /v1/sites/{site_ref}/wifi/wids-summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/insight/wids?page=1&pageSize=1000` | Reads one bounded page and returns counts by documented level/band codes, raw event type code, and channel. MAC addresses and detection times are omitted; truncation or unknown fields are reported. Requires `Site Insight Manager View Only` or `Network Config Page View Only`; no scan is started. |
| `GET /v1/sites/{site_ref}/wifi/wids-blacklist-summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/insight/wids/blacklist?page=1&pageSize=1000` | Reads one bounded dynamic blacklist page and returns the row count only. Station/AP MAC addresses and timestamps are omitted; truncation or unknown fields are reported. Requires `Site Insight Manager View Only` or `Network Config Page View Only`. |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/lldp-config` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/lldp` | Exposes only the documented setting code and label (`off`, `on`, `site_default`) plus support flag; requires `Site Device Manager View Only`; the AP must be present in the selected site's inventory |
| `GET /v1/sites/{site_ref}/wifi/summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/dashboard/wifi-summary?start=<seconds>&end=<seconds>` | Fixed trailing 24-hour counts for connected APs and clients, average channel utilization and total traffic in KB; null utilization is preserved; ER7212PC declares the traffic schema as an object reference although its example is numeric, so that runtime shape remains uncertain |
| `GET /v1/sites/{site_ref}/wifi/optimization/history` | `GET /openapi/v1/{omadacId}/sites/{siteId}/experienceIndex` | Existing WLAN optimization history: before/after indices, completion, AP count, duration and scheduled/one-click mode; read only, fixture-tested, no live verification |
| `GET /v1/sites/{site_ref}/wifi/optimization/status` | `GET /openapi/v1/{omadacId}/sites/{siteId}/rfPlanning/result` | Status and optional before/after indices of the last optimization; planning IDs are redacted; read only, fixture-tested, no live verification |
| `GET /v1/sites/{site_ref}/wifi/optimization/dashboard` | `GET /openapi/v1/{omadacId}/sites/{siteId}/rfPlanning/dashboard/status` | Bounded per-band interference and AP-density trends plus current aggregate AP counts; AP names and MAC addresses are not returned |
| `GET /v1/sites/{site_ref}/wifi/optimization/dashboard/current` | `GET /openapi/v1/{omadacId}/sites/{siteId}/rfPlanning/dashboard` | Current RF-dashboard representation using the shared bounded projection; AP identities are redacted; fixture-tested, no live verification |
| `GET /v1/sites/{site_ref}/wifi/optimization/dashboard/history` | `GET /openapi/v1/{omadacId}/sites/{siteId}/rfPlanning/dashboard/history?start=<ms>&end=<ms>` | Fixed 24-hour interference/AP-density trend window; AP identities and current detail are redacted; fixture-tested, no live verification |
| `GET /v1/sites/{site_ref}/wifi/optimization/excluded-aps` | `GET /openapi/v1/{omadacId}/sites/{siteId}/rfPlanning/excludeAps` | RF-planning exclusions mapped to fresh opaque AP references; names, IPs and MACs are redacted; fixture-tested, no live verification |
| `GET /v1/sites/{site_ref}/wifi/optimization/deployment-history` | `GET /openapi/v1/{omadacId}/sites/{siteId}/rfplanning/history` | Documented `firstDeploy` boolean projected as `first_deployment`; read-only, fixture-tested, no live verification |
| `GET /v1/sites/{site_ref}/wifi/optimization/detail` | `GET /openapi/v1/{omadacId}/sites/{siteId}/rfPlanning` | Stored optimization settings and radio before/recommended values; AP identity and failure messages are omitted; read only, no live verification |
| `GET /v1/sites/{site_ref}/wifi/optimization/history/records` | `GET /openapi/v1/{omadacId}/sites/{siteId}/planningHistory?page=1&pageSize=100` | First bounded page of stored optimization history; raw IDs become short-lived site-bound references, while messages and MAC lists are redacted; truncation is explicit |
| `GET /v1/sites/{site_ref}/wifi/optimization/history/records/{history_ref}` | `GET /openapi/v1/{omadacId}/sites/{siteId}/planningHistory/{id}` | Detail for a reference returned by a recent history-list call; requires the in-memory site-bound reference map; AP identities and messages are redacted |
| `GET /v1/sites/{site_ref}/wifi/optimization/history/recent` | `GET /openapi/v1/{omadacId}/sites/{siteId}/planningHistoryByTime?currentPage=1&currentPageSize=100&start=<ms>&end=<ms>` | Fixed last-30-day window and first bounded page; same redacted projection; fixture-tested, no live verification |
| `GET /v1/sites/{site_ref}/clients/{client_ref}/timeline/{connect\|association\|roaming\|disconnect}` | `GET /openapi/v1/{omadacId}/sites/{siteId}/clients/{clientMac}/client-timeline?start=<...>&end=<...>&type=<0..3>` | Four type-specific reads; each is bounded to 24 hours and has separate capability evidence. Documented roaming AP MACs map to opaque same-site AP references when the current device inventory binds them. |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/radio-config` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/radio-config` | AP radio channel, width, power and enabled state when present |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/radios` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/radios` | Channel utilization and packet counters when present |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/scan-status` | AP interference detection status | Status and last detection time when present; reads existing status and does not initiate detection |
| `GET /v1/sites/{site_ref}/wifi/interference-history-summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/full-channel-detect/grid/scan-history?page=1&pageSize=100` | First bounded page of stored site scans; counts running/finished/unknown states, reported AP totals and detection flags. History IDs, AP details and unscaled times are omitted. `Site Tools Manager View Only`; no scan is started. All three exports document the same response properties. |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/available-channels` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/available-channel` | Per-radio channel, frequency and allowed-width values; capped at four radios, 256 channels per radio and eight widths per channel; AP-bound opaque reference |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/speed-test-results` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/speed-test-result` | Existing link-speed test state/results; AP MACs become opaque inventory references, controller error text is omitted; read only, no live verification; does not start a test |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/ports` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/ports` | Counts AP link-state/speed codes, PoE capability/state, VLAN capability and uplink presence; omits port numbers, labels, IDs and VLAN identifiers; read only |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/mesh` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/mesh/statistics` | Redacted mesh-link status and signal/rate measurements; AP identities, names, addresses and free text are omitted; fixture-tested, no live verification |
| `GET /v1/sites/{site_ref}/gateways/{device_ref}/lan-status` | `GET /openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/lan-status` | VLAN and byte counters plus client counts; LAN labels and address data are omitted; fixture-tested, no live verification |
| `GET /v1/sites/{site_ref}/gateways/{device_ref}/wan-status` | `GET /openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/wan-status` | Whitelisted WAN port and link measurements for the inventoried gateway; raw values are preserved without inferred meanings; fixed GET and bounded to 64 rows |
| `GET /v1/sites/{site_ref}/gateways/{gateway_ref}/ipv6-ip-passthrough` | `GET /openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/network/ipv6` | Only the documented Boolean `enable` state is returned; address-bearing configuration is omitted |
| `GET /v1/sites/{site_ref}/gateways/{device_ref}/wan-health` | `GET /openapi/v1/{omadacId}/sites/{siteId}/health/gateways/{gatewayMac}/wans/details` | Up to 32 WAN port rows with raw integer codes and measurements; names, IPs and identifiers are omitted, extra fields are counted, and truncation marks the response partial |
| `GET /v1/sites/{site_ref}/gateways/{device_ref}/ports` | `GET /openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/ports` | Bounded integer port type/mode codes; labels are omitted; fixture-tested, no live verification |
| `GET /v1/sites/{site_ref}/gateways/{device_ref}/internet-info` | `GET /openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/internet` | WAN support flags and counts of raw online-detection codes; WAN/IP configuration, port IDs and network labels are omitted; fixture-tested, no live verification |
| `GET /v1/sites/{site_ref}/gateways/{gateway_ref}/dhcp/leases` | `GET /openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/dhcp/user-list?page=<page>&pageSize=<size>` | Paged lease/device classifications only; IP, MAC, names, network IDs and lease times are omitted; fixture-tested, no live verification; MCP argument is `gateway_ref` |
| `GET /v1/sites/{site_ref}/gateways/{device_ref}/speed-test-results` | `GET /openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/speedTestResult` | Previously saved WAN speed-test values; ISP, port and server/location labels are removed; fixture-tested, read only, no live verification; never starts a test |
| `GET /v1/sites/{site_ref}/speed-test/settings` | `GET /openapi/v1/{omadacId}/sites/{siteId}/setting/speedTest` | Site schedule and resource enum fields; descriptive feature labels are omitted; Site Settings Manager View Only or Network Config Page View Only; does not change or start a test |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/channel-load` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/full-channel-detect/channel-load` | Bounded per-band channel/load rows when present; does not initiate a scan |
| `GET /v1/sites/{site_ref}/wifi/channel-limit` | `GET /openapi/v1/{omadacId}/sites/{siteId}/channel-limit` | Deprecated site setting, read only |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/channel-limit` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/channel-limit` | AP support, channelLimitType and default values |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/ofdma` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/ofdma` | Four OFDMA enable and four support booleans |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/qos` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/qos` | Eight optional band/support and delivery booleans; missing or invalid fields mark partial |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/lag` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/trunk-setting` | Redacted `supportTrunkSetting`, `enable` booleans and integer `mode` 0–2 |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/load-balance` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/load-balance` | Four documented bands with max-client and RSSI-threshold settings; partial on missing, invalid or unknown fields |
| `GET /v1/sites/{site_ref}/aps/{device_ref}/antenna` | `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/ant-switch` | Global antenna mode/state and per-band settings; missing, invalid or unknown values mark…14056 tokens truncated…only
in the connector. AP channel-limit GET/PUT and preview/apply are separate:
the AP change is allowed only for a full status with
`supportChannelLimit=true`, `channelLimitType` 0–2 and both documented default
booleans. A single AP value is changed per plan, with full before-state
approval, stale-state validation and readback. The value mapping is `0`
default, `1` false, `2` true; this documentation implies no further technical
or regulatory effects. There is no live write verification or universal
support claim. See [CONTROLLED_CHANGES.md](CONTROLLED_CHANGES.md).

Client detail references change on each client-list refresh and are invalidated by a site-list refresh. The client detail route is fixture-tested and not yet live verified.


The separate AP antenna-gain GET maps to `/antenna-gain`. The documented
`anteGainList` entries contain `radioId` (0–3) and `anteGain` (0–30); the
projection assigns no unit or regulatory meaning. Missing, invalid, unknown or
duplicate entries mark partial. The route is documented in all three supplied
exports and has fixture coverage only, with no live verification. No PATCH is
implemented because list partial/full replacement semantics and effects on
other radio settings are unknown. This does not establish non-support.


The Wi-Fi sub-health detail route calls `/wifi/sub/health/timeline` with a
fixed 24-hour `start`/`end` millisecond window. It returns whitelisted raw
score, support, interference and onboarding values without inferring scales,
causes or units. Incident structures are excluded, including IDs, MAC
addresses and free text. Missing, invalid, unknown or out-of-window values mark
the projection partial. All three supplied exports document this GET; it has
fixture coverage only and no live verification. The ER7212PC 6.2.14 export has
no onboarding dimension and lacks the extended interference-average schema;
absent values therefore remain unknown/partial.


The AP power-saving GET maps to `/power-saving`. Documented constraints include
`mode` 0–3, boolean `timeEnable`, `bandEnable` and `supportPowerSaving`, band
values 0–3, and hour/minute schedule ranges. `idleDuration` is validated only
as int32; no unit or further range is inferred. Missing, invalid or unknown
fields mark partial, and the support flag's cause is not inferred. Although all
three exports document the route, the ER7212PC 6.2.14 schema has no `mode`
field, which remains missing/unknown. No PUT is implemented because of this
version difference, unclear partial/full semantics and unverified supported
bands. No live compatibility or unsupported state is claimed.


The AP VLAN route uses `/openapi/v2/.../aps/{apMac}/vlan`. The documented
`mvlanSetting` and `voipVlanSetting` modes are 0/1; optional `bridgeVlan`
and `voipBridgeVlan` are int32, and `ipType` is 0/1. Raw `lanNetworkId`, IP,
mask, gateway and DNS values are discarded. Missing, invalid or unknown fields
mark partial. All three supplied exports document V2; this route has fixture
coverage only and no live verification. There is no PUT because management
VLAN/IP changes can affect the uplink and request full/partial semantics are
unclear. No controller or device non-support is inferred.


The AP wired-uplink GET projects documented duplex, port type, rate, byte,
packet, drop, error, activity and link values with their schema types. It does
not add enum or unit interpretations beyond what the source states. Optional
`poeState` and `voipState` are documented in Hardware Controller 6.3.0 and
CBC Standard 6.3.0 but absent from ER7212PC 6.2.14. Names, MAC/IP addresses,
stack/port IDs and model information are fully omitted. Missing core, invalid or
unknown values mark partial; optional readings may be absent. ER sensor schemas
have unresolved numeric references. All three exports document this GET; there is
fixture coverage only and no live verification. No write operation is
provided.


Switch-port counters are fetched from the paginated site-wide counters endpoint
and filtered by exact inventoried switch identity before projection. Returned
values are current cumulative byte/frame/multicast/broadcast/error counters by
port, not calculated rates or time series. Port values are conservatively
restricted by the connector to 0–4096; this is not an API-declared range.
Higher or otherwise invalid port values are omitted and mark the response
partial. Sensitive names, MAC/IP addresses, stack data and port labels are
omitted. The endpoint is documented in all three supplied specifications;
only simulated fixture tests exist, with no live verification.


Switch-port PoE-info is fetched from the paginated site-wide endpoint and
filtered by exact inventoried switch identity. The response omits sensitive
names and identifiers and projects finite numeric measurements without
assigning units or inferring PoE support. Port values are limited to 0–4096 by
the connector; this is a connector bound. ER7212PC's exported PoE measurement
schema is ambiguous, so no type or unit compatibility is inferred for that
family. The route is documented in all three supplied specifications and has
simulated-fixture coverage only, with no live verification.


The gateway health timeline uses the exact inventoried gateway reference and a
fixed 24-hour millisecond query window. The result exposes only millisecond
timestamps and raw int32 score values; no score scale is inferred. Missing,
invalid or out-of-window samples mark partial, and unknown fields are omitted.
The route is documented in all three supplied specifications and has
simulated-fixture coverage only, without live verification.


Switch-port rename uses the documented name GET and single-field PUT at
`/openapi/v1/{omadacId}/sites/{siteId}/switches/{switchMac}/ports/{port}/name`.
The connector exposes
`POST /v1/sites/{site_ref}/switches/{switch_ref}/ports/{port}/name-preview`
and `POST /v1/switch-port-name-plans/{plan_id}/apply` for one unique inventory
port; apply requires separate approval of exact old/new names. Missing or
invalid old
name fails closed; an empty old name is accepted. Apply stale-checks, dispatches
one PUT, then reads back. Unknown outcomes remain in doubt with no automatic
retry. Journal events store only a fixed redaction marker, not either name or
a name-derived hash. Writes remain off by default and require explicit operator approval of the exact plan. The operation is documented in all three exports
and has simulated fixtures only; there is no live write/support verification.


Site DPI and traffic logging use GET/PUT
`/openapi/v1/{omadacId}/sites/{siteId}/applicationControl/status`. Both the
read and write schema require the full boolean pair `dpi`, `loggingTraffic`.
The public preview changes one and preserves the other; apply sends both after
stale checking and a separately approved one-use plan, then reads the full
state back. Uncertain results remain in doubt, with no automatic retry.
Enabling traffic logging can record usage data. Other DPI side effects are
unknown. Writes remain off by default and require explicit operator approval
before any network change. The three supplied specifications document GET/PUT;
verification is simulated fixtures only, not live operation.


Gateway VoIP prioritization uses GET/PUT
`/openapi/v1/{omadacId}/sites/{siteId}/qos/gateway/voip-prioritization` with
exactly `enable` (boolean) and `sipUdpPort` (integer 0–65535) in the full
state/body. Although the source schema marks the port optional, the connector
requires a valid port in every state, including when disabled; absent or invalid
values fail closed before PUT. Preview changes only `enable`, preserves
`sipUdpPort` and requires `disruption_confirmed: true`; that flag does not
replace explicit operator approval. Apply re-reads state shortly before
dispatch, then requires a journal plus separate one-use HMAC approval, sends
both fields, and reads back the full state. The re-read reduces but cannot
eliminate a concurrent change by another controller user; the API documents no
atomic version check. Unknown outcomes remain in doubt without replay. The
setting may affect VoIP traffic;
success is not guaranteed. Writes default off and require explicit operator approval before a real network change. The three offline exports document
GET/PUT; no live verification exists.


Gateway tag-outbound QoS uses GET/PUT
`/openapi/v1/{omadacId}/sites/{siteId}/qos/gateway/tag-outbound-traffic`.
Its state is exactly a four-entry `tagConfigList`: each row has only
`classType` (each of 0–3 exactly once), `enable` (boolean) and `dscp` (string).
The connector accepts only the 20 explicit DSCP strings `8`, `10`, `12`, `14`,
`16`, `18`, `20`, `22`, `24`, `26`, `28`, `30`, `32`, `34`, `36`, `38`,
`40`, `46`, `48` and `56`. Missing/extra fields, duplicate or missing classes,
unknown/empty DSCP values, or invalid types block preview and PUT. Preview
requests one class and its new `enable` value plus `disruption_confirmed: true`;
the complete list order and all DSCP values are retained while only that
class's enable value changes. The ER7212PC export contains a contradictory
example, so this validation is deliberately strict and has no live
compatibility confirmation.

Apply requires writes to be enabled, the durable journal and separate
one-use HMAC approval. It checks the complete before-state after journal intent,
checks expiry, sends one full PUT, and requires exact full readback; uncertain
outcomes remain `in_doubt` without replay. The API does not document atomic
compare-and-swap, so another controller user can change state between the last
GET and PUT. This site-wide QoS behavior and side effects are unknown. Writes
are off by default and explicit operator approval is required for each actual
network change. All three supplied exports document GET/PUT; no live test or
support guarantee exists.

Client history uses the paginated
`GET /openapi/v1/{omadacId}/sites/{siteId}/clients/{clientMac}/client-history`
operation and a fresh site-bound client reference. Returned rows are checked
against the requested MAC internally. Raw IDs, names, MACs, IPs, SSIDs, reason
text and authentication information are omitted. The projection exposes only
validated raw int64 `download`, `upload`, `duration`, `lastSeen`, `associated`,
int32 `port`, `vid`, `reasonType`, `associationTime`, and boolean `guest`,
without units or enum/causal interpretation. Missing, invalid or unknown
fields and omitted/unmatched rows mark partial. Pagination reaching configured
`max_pages` errors rather than silently truncating. No controller snapshot
token is documented, so concurrent additions may shift page contents and an
atomic complete history is not guaranteed. All three offline exports document
the operation; there is no live verification.

AP LAN traffic uses the documented `lan-traffic-info` GET for an inventoried
AP bound to the selected site. Its eight optional nonnegative int64 fields are
`rxPkts`, `txPkts`, `rx`, `tx`, `rxDropPkts`, `txDropPkts`, `rxErrPkts` and
`txErrPkts`. The export describes `rx` and `tx` as byte totals, with the
remaining fields as packet counts. No rates, time window, reset behavior or
other meaning is inferred. Missing, invalid or unknown fields mark partial.
All three offline exports document the route; it has no live verification and
does not change controller state.

## Site unresolved-incident count

`GET /v1/sites/{site_ref}/incidents/unresolved-count` uses the site-bound
upstream route
`GET /openapi/v1/{omadacId}/sites/{siteId}/anomaly/unresolved-incidents`.
The documented `ActiveIncidentCountVO` contains optional int32 `activeNum`,
described as the total unresolved-incident count. The connector accepts only
nonnegative int32 values and omits all other response values; missing,
malformed or unknown fields mark the summary partial. The source permission is
`Incidents Page View Only`. The operation appears in Hardware Controller 6.3.0
and CBC Standard 6.3.0, but not ER7212PC 6.2.14. Fixture coverage does not
establish live support.

## Site incident overview

`GET /v1/sites/{site_ref}/incidents/summary` uses
`GET /openapi/v1/{omadacId}/sites/{siteId}/anomaly/overview/statistics` with
the required `filters.startTime` and `filters.endTime` in milliseconds. The
connector fixes the interval to the preceding 24 hours. It projects the
documented int32 totals/status/severity/category counts and raw anomaly-code
strings, validates bounds, and omits incident IDs, device/client identities
and messages. The deprecated `others` counter is labeled as such; category
level values remain raw codes. The source permission is `Incidents Page View`.
The operation appears in Hardware Controller 6.3.0 and CBC Standard 6.3.0, but
not ER7212PC 6.2.14. Fixture coverage does not establish live support.

## Site incident distribution

`GET /v1/sites/{site_ref}/incidents/distribution` uses
`GET /openapi/v1/{omadacId}/sites/{siteId}/anomaly/overview/incident-distribution`
with millisecond start/end filters fixed to the preceding 24 hours. The
response contains `incidentCounts` time buckets with int32 severity/category
counts and an int64 `time` timestamp in seconds. The projection limits the
response to 128 buckets, validates each value, and omits unknown fields and
incident records. The source permission is `Incidents Page View Only`.
Hardware Controller 6.3.0 and CBC Standard 6.3.0 document the route; ER7212PC
6.2.14 does not. Fixture coverage does not establish live support.
## Site incident category counts

`GET /v1/sites/{site_ref}/incidents/categories` uses
`GET /openapi/v1/{omadacId}/sites/{siteId}/anomaly/category`. The response is
a list of category aggregates: anomaly code, active/total/current-status
counts, influencing device/client counts and level. The connector validates
nonnegative int32 values, limits the list to 128 entries, and omits all
unrecognized fields. The permission is `Incidents Page View Only`. Hardware
Controller 6.3.0 and CBC Standard 6.3.0 document the operation; ER7212PC 6.2.14
does not. Fixture coverage does not establish live support.
## Site incident list

`GET /v1/sites/{site_ref}/incidents/list` uses
`GET /openapi/v1/{omadacId}/sites/{siteId}/anomaly/incidents` with page 1,
page size 50 and a fixed trailing 24-hour window. The projection returns
validated category/severity/status codes, anomaly codes, counts and
timestamps. It deliberately omits title/content parameters, object names,
device/client maps and MAC addresses. The source permission is
`Incidents Page View Only`. Hardware Controller 6.3.0 and CBC Standard 6.3.0
document the route; ER7212PC 6.2.14 does not. Fixture coverage does not prove
live support. Additional pages are indicated in the response.


## Device and client incident detail

`GET /v1/sites/{site_ref}/devices/{device_ref}/incidents` and
`GET /v1/sites/{site_ref}/clients/{client_ref}/incidents` read the documented
`GET /openapi/v1/{omadacId}/sites/{siteId}/health/incident/{mac}` route. They
return opaque `incident_ref` values and bounded code/time fields. Each new
read replaces the current site's incident-reference snapshot.
`GET /v1/sites/{site_ref}/incidents/{incident_ref}` resolves only a reference
from that snapshot and reads the documented
`GET /openapi/v1/{omadacId}/sites/{siteId}/anomaly/incident/{incidentId}` route.
Raw incident IDs, object names, client/device identities, causes and dynamic
title/content/detail fields are omitted. Both source routes are documented in
Hardware Controller 6.3.0 and CBC Standard 6.3.0, but not ER7212PC 6.2.14.
Offline fixtures verify reference binding and response redaction; live support
is not confirmed.


## Controller-wide known and unknown device summaries

`GET /v1/controller/devices/known-summary` and
`GET /v1/controller/devices/unknown-summary` read page 1 of the corresponding
controller-wide device list using the configured page size (at most 200 rows).
The adapter returns aggregate device type, status-code and series-type counts,
plus missing, invalid and unknown-field counts. It omits device IDs, MAC and IP
addresses, names, model and serial values, site/tag names, uptime, and raw row
data. The supplied ER7212PC 6.2.14, Hardware Controller 6.3.0 and Omada CBC
Standard 6.3.0 exports document both GET routes. Fixture tests cover the
projections, fixed request paths and HTTP/MCP dispatch. Live controller support
remains unknown; this implementation has not contacted a controller.


## Batch-adoptable and site-pending device summaries

`GET /v1/controller/devices/batch-adopt-summary` reads page 1 of the
documented controller-wide batch-adopt information route. The adapter sends no
caller-controlled search, sort or tag filter. `GET
/v1/sites/{site_ref}/pending-devices/summary` reads page 1 for the inventory-
bound site. Both use the configured page size, capped at 200 rows, and return
aggregate device type, status, license, compatibility and series counts plus
data-quality counts. Boolean availability flags are summarized as counts.
Device IDs, MAC/IP addresses, names, models, serial values, and source rows are
discarded. The batch response has no total field, so it reports only the
sampled row count and marks a full page as partial; the site response includes
the documented total row count and reports whether the first page is partial.
Both GETs appear in the three supplied exports. Their documented permissions
are `Site Adopt Device Manager Access` or `Site Add Device Manager Access` for
batch-adopt information, and `Site Device Manager View Only` for pending
devices. Fixture tests cover the projection, fixed path,
controller/site binding and HTTP/MCP dispatch. Live controller support remains
unknown.


## Site metadata summary

`GET /v1/sites/{site_ref}/metadata/summary` reads the documented
`GET /openapi/v1/{omadacId}/sites/{siteId}` after resolving `site_ref` through
the current site inventory. It returns only the documented basic/pro tier,
NTP enabled state and server count, whether a time zone is configured,
Daylight Saving Time enabled state, a coordinate-presence flag, and the two
documented switch-support Booleans. Site identifiers, names, tag identifiers,
region/time-zone strings, NTP addresses, scenario labels, precise coordinates
and addresses are omitted. The source exports specify
`Global Dashboard Manager View Only`; runtime support remains unknown.


## Site UPnP settings

`GET /v1/sites/{site_ref}/settings/upnp-summary` resolves the site through inventory and reads the documented `getUpnpSetting` GET. The response contains enable/support flags and bounded WAN-port/network counts; the returned controller IDs are omitted. The three API exports specify the same response properties and permissions. Controller support remains unknown.

## Site EoGRE tunnel settings

`GET /v1/sites/{site_ref}/settings/gre-tunnel-summary` resolves the site from inventory, then reads the documented `getGreTunnelConfig` GET. It returns enable state, bounded MTU/keepalive values and address-presence flags; address strings are omitted. The three source exports specify identical fields and view-only permissions. Live controller support remains unknown.

## Legacy SSL VPN settings

`GET /v1/sites/{site_ref}/settings/ssl-vpn-summary` resolves the site from inventory, then reads the documented deprecated `getSslVpnServerSetting` GET. The public projection omits server identity and WAN IDs, IP addresses and pools, DNS values, and all RADIUS/LDAP profile details. The three exports list this operation as deprecated and specify `Site Settings Manager View Only` or `Network Config Page View Only`. Prefer the current VPN summary/detail operations when available. Live support remains unknown.

## Site SSH settings

`GET /v1/sites/{site_ref}/settings/ssh-summary` resolves the site from inventory and reads the documented `getSshSetting` GET. It returns the SSH enable flag, Layer-3 accessibility flag and server port after source-defined validation. No SSH connection is made. The three API exports specify the same result fields and view-only permissions. Live support remains unknown.

`GET /v1/site-templates/{site_template_ref}/settings/ssh-summary` reads CBC Standard's documented `getSshSettingTemplate` through the paginated template inventory. The reference is opaque and current-inventory-bound. The response exposes only the enable flag, Layer-3 accessibility flag and validated server port; unexpected fields are omitted and counted. The documented permission is `Global Site Template Manager View Only`. Hardware Controller 6.3.0 and ER7212PC 6.2.14 do not document this operation. It does not connect to SSH. Live support remains unknown.

`GET /v1/site-templates/{site_template_ref}/services/iptv-summary` reads CBC Standard's `getIptvTemplate` through the paginated template inventory. It reuses the bounded site IPTV projection: enablement/mode, configuration presence and LAN port type counts. WAN/LAN identifiers, port names, VLAN values, DSL circuit details and feature-description text are omitted. The documented permission is `Global Site Template Manager View Only`; the other two exports do not document this operation. Live support remains unknown.

`GET /v1/site-templates/{site_template_ref}/services/iptv-settings-summary` reads CBC Standard's combined `getIptvTemplateServerSetting` operation through the paginated template inventory. One controller call yields redacted IGMP and IPTV summaries; identifiers, names, VLAN values and descriptive text are omitted. The documented permission is `Global Site Template Manager View Only`; the other two exports do not document the operation. Live support remains unknown.

## Site MLD settings

`GET /v1/sites/{site_ref}/services/mld-summary` resolves the site from inventory, then reads the documented `getMld` GET. It reports enablement, the documented version code, WAN-port presence and an optional bounded feature-description count. WAN-port IDs and descriptions are omitted. All three source exports identify the same required enable/version fields and `Site Settings Manager View Only`; live support remains unknown.

## Site IGMP settings

`GET /v1/sites/{site_ref}/services/igmp-summary` resolves the site from inventory and reads the documented `getIgmp` GET. It returns enablement, IGMP version, WAN/virtual-WAN presence and a bounded feature-description count. Port identifiers and description text are omitted. All three API exports document required enable/version fields and tag the operation `IPTV`; optional WAN and feature-description fields vary by export. Live support remains unknown.

## Site IPTV settings

`GET /v1/sites/{site_ref}/services/iptv-summary` resolves the site from inventory and reads the documented `getIptv` GET. It returns enable/mode, configuration-presence flags and a bounded count by LAN port type. Controller port IDs, names, custom VLAN IDs/priorities, DSL circuit values and feature-description text are omitted. The three exports document this response family and the same view-only permission set. Live support remains unknown.

- `GET /v1/sites/{site_ref}/application-usage/allowed-summary` and `/blocked-summary` map to `getAllowApp` and `getBlockApp`; both use a fixed trailing 24-hour window, bounded zero-based pages of up to 100 rows, and identity-free page aggregates.

- `GET /v1/sites/{site_ref}/dashboard/tabs-summary` and `/tabs-without-overall-summary` map to `listAllTabs` and `listTabs`; each returns bounded tab/card counts grouped by type and omits tab labels and identifiers.

- `GET /v1/sites/{site_ref}/application-usage/{application_id}/traffic-summary` maps to `getSpecificAppInfo`; it uses a fixed trailing 24-hour window, validates the application path ID, caps rows at 1,000 and aggregates traffic without client identity fields.

- `GET /v1/sites/{site_ref}/client-application-usage/{client_ref}/traffic-summary` maps to `getSpecificClientInfo`; it binds a fresh opaque client reference, uses a fixed trailing 24-hour window and returns identity-free traffic totals.

- `GET /v1/sites/{site_ref}/application-traffic-summary` maps to `getApplicationControlTraffics`; it reads the documented top ten over a fixed trailing 24-hour window and returns only aggregate numeric counters.

- `GET /v1/sites/{site_ref}/wan-lan-status-summary` maps to `checkWanLanStatus` / `checkWanLanStatus_1`; it returns bounded gateway/WAN metadata counts and validated flags. It does not report physical link health.
- `GET /v1/controller/gateway-wan-status-summary?page_number=0&page_size=20` maps to `getSpecifiedGatewayInfos`; it summarizes one bounded page of global WAN health. It reports link/internet state counts, latency/loss averages and total rates/error counters; site/device IDs, uptime, WAN labels and addresses are omitted. This read is not live-confirmed.


## Site LAN network inventory

`GET /v1/sites/{site_ref}/lan-networks/inventory` and
`omada_site_lan_network_inventory` expose `getAllLanNetworks` via the fixed
`/openapi/v1/{omadacId}/sites/{siteId}/lan-networks/all` read. The three
exports specify a list response with no query/body and the Site Settings
Manager View Only or Network Config Page View Only permission. The response is
projected into bounded purpose, DHCP and feature counts; network identities,
addresses and nested configuration are omitted. Processing is capped at 500
rows, with invalid, unknown or truncated results marked partial. No live request
was made; live support remains unknown.


## Longest client uptime dashboard read

`GET /v1/sites/{site_ref}/dashboard/longest-client-uptime-summary` and
`omada_site_longest_client_uptime_summary` expose `getLongestClientUptime`
through `/openapi/v1/{omadacId}/sites/{siteId}/dashboard/longest-uptime`. The
three exports define the same three int32 fields (`total`, `wiredClient`,
`wirelessClient`), no query/body and the Site Dashboard Manager View Only
permission. The schemas give no descriptions or units for these fields; the
connector preserves the source names and does not interpret them. No client
identities are returned, and no live request was made.


## Site MAC-authentication SSID inventory

`getSsidsBySite` is exposed through the fixed site-bound route
`GET /v1/sites/{site_ref}/wlan-ssids/mac-auth?type=1|2|3` and MCP tool
`omada_site_mac_auth_ssid_inventory`. All three exports require the int32 query
parameter `type` (1=AP, 2=wireless router, 3=both) and define no request body.
The response lists WLANs and their SSIDs configured for MAC-based
authentication. The projection returns only WLAN/SSID names, caps output at 100
WLANs and 500 SSIDs, and omits identifiers. Missing, invalid, unknown or
truncated data is marked partial. No live request was made; support remains
unknown.


## Site attack-defense defaults

`getDefaultAttackDefense` is exposed through fixed site-bound HTTP and MCP as
`GET /v1/sites/{site_ref}/attack-defense/default-summary` and
`omada_site_attack_defense_defaults_summary`. All three source contracts define
no query or body, and require one common set of 14 Boolean flags. The connector
validates those flags, optional Boolean values, documented int32 threshold
ranges and the known nested option flags. It preserves source field names and
marks missing required, invalid and unknown fields partial. No live request was
made; support remains unknown.


## WLAN-group detail

`getWlanGroup` is exposed as HTTP
`GET /v1/sites/{site_ref}/wlan-groups/{wlan_group_ref}/detail` and MCP tool
`omada_site_wlan_group_detail_summary`. It uses the v2 source endpoint and an
opaque WLAN-group reference issued by the site's wireless-group inventory.
The source describes this endpoint as legacy/deprecated in favor of Get an
existing AP Group info. The projection exposes only the group name, primary and
clone flags, and resource code; group IDs and the site identifier are omitted.
No live request was made; support remains unknown.


## Lock-to-AP candidate inventory

`getAllApBriefInfosBySite` is exposed through the fixed site route
`GET /v1/sites/{site_ref}/lock-to-ap/ap-inventory` and MCP tool
`omada_site_lock_to_ap_brief_inventory`. All three exports define a list of the
same 12 AP properties, no query/body and Site Device Manager View Only
permission. The projection aggregates nonzero status and Lock-to-AP capability counts
for at most 500 rows; device names, MACs, IPs, and model/version strings are
not returned. Unknown/invalid values and truncation mark the summary partial.
No live request was made; support remains unknown.


## APs unavailable for interference detection

`getDisableFullChannelDetectApMacList` is available through fixed site-bound
HTTP and MCP as `GET /v1/sites/{site_ref}/wifi/interference-ineligible-ap-summary`
and `omada_site_ineligible_interference_ap_summary`. All three source exports
define a list of MAC strings and the Site Tools Manager View Only permission;
there are no query or body parameters. The connector returns counts only,
processes at most 500 entries and omits all MAC values. No live request was
made; support remains unknown.

`getGridEnableFullChannelDetectApList` is exposed as fixed site-bound HTTP and
MCP read `GET /v1/sites/{site_ref}/wifi/interference-scan-eligible-summary` /
`omada_site_interference_scan_eligible_summary`. The three source exports
require `page` and `pageSize` (1–1000); this implementation requests page 1
with size 500 and returns only aggregate scan-status, connection-category,
and power-mode counts. It omits identifiers and per-device fields. Only the
first page is inspected, so this is not a complete site-wide count when more
than 500 eligible devices exist. No live request was made.

`getGridFullChannelDetectHistory` returns site-scoped opaque `history_refs` in
source row order; raw `historyId` values are never returned. The paired
`getBatchFullChannelDetectApList` read is exposed as
`GET /v1/sites/{site_ref}/wifi/interference-history/{history_ref}/ap-summary`
and MCP `omada_site_batch_interference_ap_summary`. It accepts only a
reference issued by a recent history read for the same site, aggregates the
scan AP count and documented capability flags, and emits opaque `device_refs`
only for rows with a valid MAC. These references let the paired channel-load
read resolve its required MAC internally. Names and raw MACs are omitted. The
path parameter is named `historyId`, but its description in all three exports
says “AP MAC address”; the connector treats the value as opaque and uses only
IDs returned by the paired history endpoint. No live request was made.

The eligible-AP payload marks `coverage_scope` as `first_page_only`, sets
`total_count` to null and `coverage_unknown` to true, and marks the result
partial because the schema provides no total or end-of-page signal. Actual
processing overflow uses the separate `truncated` flag. Counts are only for
returned rows.

`getBatchWifiInterferencesResult` is exposed through a site-scoped opaque
`history_ref` as `GET /v1/sites/{site_ref}/wifi/interference-history/{history_ref}/wifi-interference-summary`
and MCP `omada_site_batch_wifi_interference_summary`. The adapter fixes page 1,
pageSize 100, and required `filters.type=0` to request all devices; it omits the
optional AP-MAC filter. Aggregates include radio, channel, PHY mode, security,
and signal bounds. SSIDs, BSSIDs, AP identities, result IDs, and timestamps are
not returned. `totalRows` is retained as an aggregate and sets `has_more`; the
connector does not fetch later pages. The three exports call the path parameter
`historyId` but describe it as “Customer ID”; only a value from the paired site
history response is accepted. No live request was made.

`getBatchChannelLoadsResult` is exposed as
`GET /v1/sites/{site_ref}/wifi/interference-history/{history_ref}/aps/{device_ref}/channel-load-summary`
and MCP `omada_site_batch_channel_load_summary`. The required AP MAC query is
resolved internally from a process-local AP reference emitted by the paired
AP-list read. The operation returns per-band channel count and load minimum,
maximum and average; it omits channel numbers and device identity. No load units
are specified by the API contracts, so none are inferred. The required
`historyId` path value is described as “Customer ID” in all three exports and
remains unverified live. No controller request was made.

`getBatchInterferencesResult` is documented by Hardware Controller 6.3.0 and
Omada CBC Standard 6.3.0, but is absent from the ER7212PC 6.2.14 export. Its
HTTP/MCP summary reads page 1 with pageSize 100 through a site-scoped opaque
history reference. The supplied schemas recursively reference `ApInterference`
and define only the 2G/5G/6G list fields, without item fields or measurement
units. The connector therefore reports bounded counts by documented band and
marks coverage unknown/partial; it does not return source rows. The required
`historyId` description says “Customer ID”. No live request was made.

`getBatchFullChannelDetectStatus` is exposed as the read-only public HTTP GET
`/v1/sites/{site_ref}/wifi/interference-history/{history_ref}/status-summary`
and MCP `omada_site_batch_interference_status_summary`. All three exports
document an upstream POST with a required `QueryBatchFullChannelDetectStatusVO`
body. The connector sends an `idList` containing only the selected history ID
resolved from the same-site opaque reference; it does not start a scan. The
response history ID is checked and suppressed. Status 0 maps to `finished`,
status 1 to `scanning`, as documented. No live request was made.

`getFullChannelDetectStatus` is exposed through
`GET /v1/sites/{site_ref}/aps/{device_ref}/full-channel-detect-status` and MCP
`omada_site_ap_full_channel_detect_status`. All three exports require an AP MAC
path value and document Site Device Manager View Only. The connector resolves
that value only from a device reference in the selected site inventory. It maps
the four documented 0/1/3 status fields, omits the raw AP address and timestamp,
and reports whether `lastSeen` was present because its time unit is unspecified.
This reads current status and does not trigger a scan. No live request was made.

## AP supported channels summary

`GET /v1/sites/{site_ref}/aps/{device_ref}/available-channels-summary` and MCP tool `omada_ap_available_channels_summary` expose `getAvailableChannelOfAp` through its fixed AP `available-channel` GET. The AP is selected with a same-site inventory reference. The result uses compact positional rows per radio while preserving channel, frequency, index and per-channel bandwidth associations. It omits the AP MAC and channel row objects. Unknown or incomplete schema values mark the result partial. All three supplied API exports document this operation; permission and live controller behavior remain unknown. A synthetic 86-channel fixture measured 2,118 tokens for the upstream result array and 1,259 for the projected HTTP/MCP result (40.6% fewer) with js-tiktoken 1.0.21/o200k_base. This is a serialization-size comparison, not a live response measurement.


## AP interference result summary

`GET /v1/sites/{site_ref}/aps/{device_ref}/interference-result-summary` and MCP tool `omada_ap_interference_result_summary` expose `getInterfResult` through the fixed AP `full-channel-detect/grid/interference` GET. The connector selects an AP from the same-site inventory and fixes the required query to page 1 with page size 100. It counts recursively nested entries in the documented 2G, 5G and 6G arrays; the source schema does not define record fields or measurement units, so no interference rows are returned and coverage remains unknown/partial. Hardware Controller 6.3.0 and CBC Standard 6.3.0 document this operation; ER7212PC 6.2.14 does not. Permission is Site Device Manager View Only. This read does not trigger a scan; live behavior remains unverified. A synthetic recursive response with 150 nested band entries measured 2,724 upstream-result tokens and 91 projected HTTP/MCP tokens (96.7% fewer; js-tiktoken 1.0.21/o200k_base).


## AP channel-load summary

`GET /v1/sites/{site_ref}/aps/{device_ref}/channel-load-summary` and MCP tool `omada_ap_channel_load_summary` expose `getChannelLoadResult` through the fixed AP `full-channel-detect/channel-load` GET. The AP must come from the selected site's inventory. The connector returns per-band counts and min/max/average of documented `load` integers; it omits channel numbers and the AP MAC. The exports do not define the load unit or percentage scale, so the result does not label values as percentages. All three exports document this read with Site Device Manager View Only permission. It reads existing results and does not start a scan; live behavior remains unknown. A synthetic 86-channel fixture measured 712 tokens for the upstream result array and 134 for the projected HTTP/MCP response (81.2% fewer; js-tiktoken 1.0.21/o200k_base).


## LAN network detail summary

`GET /v1/sites/{site_ref}/lan-networks/{network_ref}/summary` and MCP tool `omada_site_lan_network_detail_summary` expose `getLanNetwork` through the fixed `/openapi/v1/{omadacId}/sites/{siteId}/lan-networks/{networkId}` GET. The network ID is resolved only from the selected site's network inventory. The projection returns documented purpose/device-type labels and codes, VLAN configuration summary, IPv4 gateway subnet, DHCP enabled/pool count, and selected isolation, multicast, portal and security flags. It omits network name/ID, site ID, device MAC, domains, DNS values, raw DHCP ranges and unrelated configuration. All three exports document the operation with Site Settings Manager View Only or Network Config Page View Only permission. Live behavior remains unknown.


| `GET /v1/sites/{site_ref}/networks/{network_ref}/vlan-ssids/summary?vlan_id=...` | Paginated `GET /openapi/v1/{omadacId}/sites/{siteId}/networks/{networkId}/vlan/{vlan}/ssids` | Requires a validated site network reference and VLAN ID 1–4094; counts associated SSIDs and WLAN groups, omits identities and labels; fixed paging, 10,000-row limit; source permission is Site Settings Manager View Only or Network Config Page View Only |

| `GET /v1/sites/{site_ref}/networks/{network_ref}/vlan-devices/summary?vlan_id=...` | `GET /openapi/v1/{omadacId}/sites/{siteId}/networks/{networkId}/vlan/{vlan}/devices` | Summarizes documented device type, stack membership, and DHCP-mode counts; removes names, MAC addresses, and stack IDs; caller VLAN ID 1–4094; maximum 10,000 rows; source permission is Site Settings Manager View Only or Network Config Page View Only |

| `GET /v1/sites/{site_ref}/wifi-calling/profiles/summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/profiles/wifi-calling` | Counts profiles, carriers and nested ePDG endpoint codes while omitting IDs, names, descriptions, domains and IPs; source permission is Site Settings Manager View Only or Device Config Page View Only; Hardware Controller and CBC additionally list Network Config Page View Only |

| `GET /v1/sites/{site_ref}/clients/filter-options/summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/clients/search-fields-options` | Counts client filter options and stacked-device presence while discarding labels, MAC addresses and names; Site Clients Manager View Only or Site Device Manager View Only |

| `GET /v1/sites/{site_ref}/dot1x/eap-candidates/summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/dot1x/eap/candidates` | Counts documented device status categories and port 802.1X/MAB capability flags; names, MAC addresses, models, firmware versions and port numbers are omitted; no permission is specified in the exports |

| `GET /v1/sites/{site_ref}/dot1x/switch-candidates/summary` | `GET /openapi/v1/{omadacId}/sites/{siteId}/dot1x/candidates` | Counts switch status, VRF/MAB support, port authentication types and Boolean flags; names, MAC addresses, VRF IDs, port numbers and operation labels are omitted; no permission is specified in the exports |
