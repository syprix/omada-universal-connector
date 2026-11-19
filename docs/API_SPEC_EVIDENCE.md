# Open API document evidence

Three TP-Link OpenAPI exports supplied for development were inspected locally.
The original JSON files are **not** included in this repository. Counts below
refer to distinct HTTP method and path pairs in each export, not to functions
verified on a running controller or managed device.

| Export | Documented operations | GET | POST | PUT | PATCH | DELETE | Versioned paths | MSP operations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Hardware Controller 6.3.0 | 1,783 | 803 | 500 | 133 | 201 | 146 | v1: 1,690; v2: 86; v3: 7 | 0 |
| ER7212PC 6.2.14 | 1,757 | 795 | 500 | 129 | 191 | 142 | v1: 1,687; v2: 66; v3: 4 | 36 |
| Omada CBC Standard 6.3.0 | 2,438 | 1,055 | 651 | 201 | 315 | 216 | v1: 2,336; v2: 94; v3: 8 | 141 |

The hardware and ER7212PC exports share 1,659 method/path pairs; hardware
has 124 others and ER7212PC has 98 others. Hardware and CBC Standard share
1,778 pairs; hardware has 5 others and CBC Standard has 660 others. The
controller families therefore need separate capability catalogs. A route in a
catalog does not prove the app role, site privilege, device model or firmware
can use it.

The supplied exports document `getAuditLogsForSite` at
`GET /openapi/v1/{omadacId}/sites/{siteId}/audit-logs` and
`getAuditLogsForGlobal` at `GET /openapi/v1/{omadacId}/audit-logs`. All three
accept `filters.times` as a JSON-encoded array of `{timeStart,timeEnd}` objects;
omitting it selects a vendor default seven-day period. The connector always
sends an explicit window, ascending time order and bounded pagination. The
ER7212PC export resolves the audit row schema, including millisecond `time`,
`auditType`, `level` and `result`. Hardware Controller and CBC 6.3 provide a
generic response schema for these operations. The connector therefore projects
only those fields, maps unrecognized category/status strings to `other`, and
does not return operator, IP, resource, content, labels, or old/new values.
This is contract-based offline implementation evidence, not a live controller
confirmation.

No Software Controller, Cloud Essentials, Fusion or Omada Pro export was
supplied. The three snapshots cannot establish Open API availability for
those products or for every firmware release within a product family.

The exports are OpenAPI 3.0 documents. Their `info.version` is `v0.1`, which
is the document's own version, **not** a firmware version. Their `servers`
entries use localhost addresses generated for documentation; a deployment
must get its actual interface address from that controller's Open API app
settings. No export declares an OpenAPI `securitySchemes` entry. The separate
access guide describes OAuth authorization-code and client-credentials modes,
but the supplied one-page capture does not contain complete token request
details. Authentication must be configured and verified separately.

The standard site, device and client list operations occur in all three exports at:

```text
GET /openapi/v1/{omadacId}/sites
GET /openapi/v1/{omadacId}/sites/{siteId}/devices
GET /openapi/v1/{omadacId}/sites/{siteId}/clients
```

All three require `page` and `pageSize`, with pages starting at 1. The documented
success envelope has `errorCode`, `msg` and `result`; the grid result includes
`totalRows`, `currentPage`, `currentSize` and `data`. Some device fields are
integers (for example `status`), so a string-only response parser would omit
them. An operation listing is documentation evidence only. The separate
authenticated test described in [STATUS.md](STATUS.md) verifies the two
inventory and client-list reads on one controller, not every documented
product or release.

`GET` is a read candidate, but method alone does not classify every
operation. Some `POST` operations retrieve statistics; other `POST`
operations change configuration. No general write proxy may be enabled merely
because a route appears in these exports. Mutations need specific input,
permission, preview, live readback and rollback behavior.

Coverage in the exports includes controller settings, sites, devices,
firmware, wireless and wired networks, switches, gateways, clients, DHCP,
DNS, routing, VPN, firewall controls, statistics, logs and reports. CBC
Standard additionally documents extensive MSP and template operations.
This is not a promise that every controller exposes every UI function. The
official Omada guide describes Open API coverage as **most** controller
services. Undocumented functions require separate, version-specific evidence.

## Client timeline event contract

All three exports document the following read with `start` and `end` as int64
milliseconds and `type` as int32:

```text
GET /openapi/v1/{omadacId}/sites/{siteId}/clients/{clientMac}/client-timeline
```

Their `Client Connection Events.eventType` descriptions agree on the wireless event
codes: `0` is `CONNECT_WIRELESS`, `1` is `DISCONNECT_WIRELESS`, `2` is
`ROAMING`, and `3` is `BLOCK_WIRELESS`. The documented attributes identify the
AP MAC in `dev_mac` for connect/disconnect events and both previous and current
AP MACs for roaming. The schema documents these facts; it does not establish
live availability or guarantee that every controller returns all attributes.

For network diagnosis, the Hardware Controller 6.3.0 export specifically
documents AP radio configuration/detail, AP channel information, RF planning
configuration/status/results, and interference detection status, channel load
and interference results. It also describes actions to start an RF scan or
optimization. These are promising documented routes for diagnosing WLAN
problems, but starting a scan or optimization can affect the network and is
not part of the current read-only connector. On one tested installation,
radio configuration/detail and interference status worked on three APs;
channel load returned application error `-39386` on each. The cause is
unknown. Other APs and firmware still need separate checks.
The radio detail schema includes utilization and packet counters such as
`txUtil`, `rxUtil`, `interUtil`, `rxDropPkts`, `txDropPkts`, `rxRetryPkts` and
`txRetryPkts`. The interference result schema includes per-channel load.
These names are specification facts, not measured values from this network.

## Source snapshots

- TP-Link export `Hardware_Controller_6.3.0.json`, supplied as a ZIP.
- TP-Link export `ER7212PC_6.2.14.json`, supplied as a ZIP.
- TP-Link export `Omada_CBC_Standard_6.3.0.json`, supplied as a ZIP.
- TP-Link *Organization Level Open API Access Guide*, supplied as a one-page PDF capture.
- [TP-Link guide to app roles and the Online API Document](https://support.omadanetworks.com/en/document/109315/).

Only metadata and short interface facts are recorded here. The exports and
the capture remain outside the repository pending a separate redistribution
decision.

## Offline route catalog

[`OPENAPI_ROUTE_CATALOG.json`](OPENAPI_ROUTE_CATALOG.json) is a reduced,
generated documentation index of method/path-template pairs found in the
three listed exports. It records source-family labels and SHA-256 hashes of
the original JSON document bytes. It contains no raw specifications,
operation descriptions, examples, response schemas, secrets, or server
addresses. The generator retains only standard HTTP method names and validated
path templates; the catalog is explicitly marked as documentation presence
only, with implementation, controller-support and live status unknown.

Regenerate it offline with the three supplied ZIPs in the directory above the
repository:

```bash
python3 tools/build_openapi_catalog.py
```

For an alternate input directory, pass `--source-dir DIR`. To compare the
current generated bytes without writing, use:

```bash
python3 tools/build_openapi_catalog.py --source-dir DIR --check
```

The default output is `docs/OPENAPI_ROUTE_CATALOG.json`; `--output PATH` selects
another destination, and `--backup PATH` explicitly preserves an existing
output before replacement. The catalog is inert metadata: it does not
describe connector implementation, prove live support, authorize execution,
or create automatic routes or a proxy. Export presence is not a guarantee of
universal support across controller families or releases.

The command accepts only the exact three JSON snapshots identified by its
embedded SHA-256 values. A newer or different export requires separate review
before updating those values. It requires regular files and operating-system
support for nonblocking and no-follow opens; directory synchronization after
replacement is best effort. The older `tools/full_api_matrix.py` produces a
broader report that may include source text and server URLs; review and redact
its output before sharing it.

## PoE budget and schedule source review

The three local OpenAPI exports contain GET operations `getPoeUsage`,
`getPoePortsList`, `getGridSwitchesPortsPoe`, `getPoeScheduleList` and
`getTimeRangeList` at the documented site paths used by the composite read.
Hardware Controller 6.3.0 and Omada CBC 6.3.0 provide generic/empty response
contracts for these operations. ER7212PC 6.2.14 supplies operation-specific
schemas and examples. That schema documents `PoeUsage.totalPowerUsed` and
`PoeUsage.totalPower` in watts, schedule status and target port mapping, and
time-range profile IDs. The schedule's `nextExecute` unit is unspecified, as
are port measurement units. No source export establishes live support on a
particular controller; these are source-contract observations, not hardware
or runtime confirmation.

## Reboot schedule source review

The site GET /openapi/v1/{omadacId}/sites/{siteId}/reboot-schedules is present in all three exports. Its operation ID is getRebootScheduleList_1 in Hardware Controller 6.3 and Omada CBC 6.3, and getRebootScheduleList in ER7212PC 6.2.14. The two 6.3 response schemas are generic; ER7212PC supplies the detailed schedule fields used here: enabled status, target device MACs, recurrence type, local schedule hour/minute, optional weekday/month-day, and next-execution timestamp in milliseconds. The source does not define a schedule timezone. The output therefore preserves the configured hour/minute without assigning a timezone, maps target MACs only through a unique current site inventory match, and omits schedule IDs, names, and raw MACs. The compact schedule row columns are declared once as enabled, recurrence, hour, minute, weekday-or-month-day, target count, target device refs, unresolved target count, and next execution milliseconds. A schedule is configuration evidence and does not prove that a device rebooted.

## Stack and LLDP source review

The three exports contain `getGridOswStackList` at
`GET /openapi/v1/{omadacId}/sites/{siteId}/stacks` and
`getGridStackLldpNeighborTable` at
`GET /openapi/v1/{omadacId}/sites/{siteId}/stack/{stackId}/lldp-neighbors`.
Hardware Controller 6.3.0 and Omada CBC 6.3.0 expose generic response
contracts; ER7212PC 6.2.14 documents stack `id`, status and member MAC fields,
plus LLDP local `portId` and neighbor identity strings. The LLDP contract does
not define a format or join rule for `deviceId`, so the connector reports
per-port neighbor counts but does not infer topology links from those strings.
No source export proves live endpoint support on another controller.

## Backup inventory source review

All three exports document controller-level getSelfServerFileList at GET /openapi/v1/{omadacId}/maintenance/backup/files and site-level getSelfServerSiteFileList at GET /openapi/v1/{omadacId}/sites/{siteId}/maintenance/backup/files. They also document getBackupResult and getSiteBackupResult status reads. Hardware Controller 6.3 and Omada CBC 6.3 use generic response schemas; ER7212PC 6.2.14 documents fileList rows with fileName, backupTime in milliseconds, and size in bytes, and status 0 (finished or initial) / 1 (running). The inventory summaries expose counts, aggregate listed bytes, the highest timestamp among returned rows, and the existing schedule/status summaries. Filenames, paths, URLs, credentials, and raw controller/site identifiers are omitted. The site route is bound to one selected site and does not enumerate sites. A listed timestamp is evidence only for the returned list, not proof of a successful restore or a complete history.

## Selected AP uplink and mesh path source review

All three exports include `getUplinkWiredDetail` at
`GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/wired-uplink` and
`getMeshStatistics` at
`GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/mesh/statistics`.
They also include the site device inventory operation. The 6.3.0 hardware and
CBC exports use response schemas for the two AP reads; the ER7212PC 6.2.14
export supplies operation-specific fields and examples. `ApWiredUplinkInfo`
documents a peer MAC, negotiated rate (`0` means disconnected), duplex, byte,
packet, drop/error counters, and link fields. `ApMeshStatisticsOpenApiVO`
documents the `wirelessLinked` Boolean and `wirelessUplink` peer AP, RSSI, SNR,
and integer transmit/receive rates in Mbps. `DeviceInfo` documents
`uplinkDeviceMac`, status codes `0`–`4`, and link-speed codes. The connector
maps peer MACs only to current same-site opaque references, exposes only one
observed hop, reports unknown continuations, and treats nonzero cumulative
counters as review signals rather than rates. No source documents thresholds
for RSSI/SNR or meanings for wired `linkStatus`/`linkSpeed`; these remain raw
values without quality labels. These contracts do not establish live support.

## AP channel reuse source fields

The three exports document `getRadiosDetail` at `GET /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/radios` and `getChannelLoadResult` at the AP `full-channel-detect/channel-load` path. ER7212PC 6.2.14 resolves the radio detail to `ApRadiosDetail` and `ApRadioChannel`, including `actualChannel` and `bandWidth`; it resolves channel-load rows to `channel` and `load`, described as channel load. Hardware Controller 6.3.0 and CBC Standard 6.3.0 use generic response schemas for these operations, so those nested fields are not independently specified there. The exports do not define occupied channel ranges or load units. The connector therefore groups only equal channel values on the same reported band and does not infer adjacent-channel overlap or interference from load.
