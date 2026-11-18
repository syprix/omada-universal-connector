# Live read evidence — 2026-11-15

This note records one bounded, passive HTTP check against the configured
controller. It contains no raw controller, site or device identifiers.

## Results

- The existing certificate pin matched. The fixed `GET /api/info` was
  validated by the existing controller-info reader and reported controller
  version `6.3.0.45`.
- `GET /openapi/v1/{controller_id}/sites?page=1&pageSize=50` returned one
  site.
- `GET /openapi/v1/{controller_id}/sites/{site_id}/devices?page=1&pageSize=50`
  returned four devices for that site: three access points and one gateway.
  All four exposed status code `1`.
- A separate pinned request to the read-only topology network-summary route
  returned one split network, one default network and six SSIDs. Some
  documented scalar fields were absent, so the redacted projection marked the
  result partial. No network or SSID name, raw ID or VLAN value was returned.
- The controller ID was validated and passed only inside the short-lived
  protected probe. Credentials and raw IDs were not printed. Temporary
  credential files were removed after the requests.

## Scope

These results live-confirm the pinned controller-info, site-inventory,
device-inventory and redacted topology-summary reads on this controller only.
The topology result was partial. No client inventory was read. No settings or
network state were changed; no active scan, speed test, cable test, packet
capture, restart, update, or port/PoE action was run.


## Client and capability acceptance — 2026-11-15

A fresh, unprivileged connector process ran on loopback only, with the existing
certificate pin, writes disabled and temporary credential files in memory-backed
storage. The controller-info bootstrap passed the pin check and returned
version 6.3.0.45. The process used a fresh site reference and made only the
listed reads. Client names, MAC addresses, raw site/controller IDs and response
bodies were not retained. Temporary files and the process were removed; port
18080 was closed afterward.

- HTTP: `GET /v1/sites` returned one site. Its fresh opaque reference was used
  for `GET /v1/sites/{site_ref}/clients`, which returned 31 items and a matching
  count of 31. The client projection intentionally does not echo `site_ref`;
  binding was through the validated request reference and the process-local
  reference map.
- HTTP capabilities: `GET /v1/capabilities` returned 199 instrumented
  operations, with `catalog_complete=false` and every support state
  `unknown`. This is the local connector catalog, not controller support.
  `GET /v1/sites/{site_ref}/capabilities` was bound to the same site and
  returned `partial=true`: 45 present, 4 missing, 0 invalid and 2 unknown
  source fields. `GET /v1/sites/{site_ref}/settings/existence` was bound to the
  same site and complete: 18 present, 0 missing, 0 invalid and 0 unknown.
- MCP: a JSON-RPC initialize and actual `tools/call` requests went through the
  Streamable HTTP `POST /mcp` endpoint. `omada_sites` returned the same fresh
  site reference; `omada_clients` returned 31 items with a matching count.
  `omada_site_capabilities` and `omada_site_setting_existence` returned the
  same partial/complete projections as HTTP. The local
  `omada_capability_summary` call returned its instrumented catalog scope and
  `catalog_complete=false`; it does not query the controller. This was a
  protocol-level MCP transport check, not a Hermes, Claude or Codex agent run.

All returned client/site references remained internal to the short-lived
process and redacted report. No active measurement or network change occurred.

## Gateway and event projection follow-up

A later read-only check reused the verified certificate pin and a temporary
loopback-only connector with writes disabled. The current inventory returned
one site and four devices; the gateway was selected from that inventory.

HTTP and real Streamable HTTP MCP calls both succeeded for gateway WAN health,
gateway health, gateway ports, saved gateway speed-test results, and site
events. The WAN response projected two rows and was marked partial after
redaction. Gateway health was marked partial and reported 576 missing samples
across the returned series; no missing values were substituted. The port read
returned seven rows and remained partial. The saved speed-test result was empty;
no speed test was started. The event read returned a 100-row sample and a
validated total of 5,451 events, with module totals summing to the reported
total. It was marked partial because the sample was bounded.

The local connector used the current site and device inventory references for
all calls. The MCP results were `isError=false`. Temporary credentials and
connector files were removed, the process was stopped, and the loopback port
was confirmed closed. No controller setting or network state was changed.


## Gateway diagnostic follow-up

A focused gateway diagnostic run through the pinned local connector and the
actual Streamable HTTP MCP transport preserved an upstream HTTP 200 response
with API code -1 as a sanitized `openapi_rejected` section. The value is
retained only as a number; its meaning and support status are unknown. Other
selected gateway sections completed without error after the direct WAN-list
projection fix. The saved speed-test read remained empty; no active test or
network change was started.


## Network overview and topology acceptance follow-up

The pinned, loopback-only connector was started with writes disabled. An actual
Streamable HTTP MCP initialization, initialized notification and
`tools/call` for `omada_network_overview` completed successfully. All 12
sections returned `status=ok`; the overall result remained partial to preserve
bounded and incomplete source data. The event section returned a total of
5,431 events with a 100-row sample and module totals summing to 5,431; it had
no section error. Alerts returned 17 rows.

The live topology graph summary reported four nodes and two edges, while
marking five nodes and five edges omitted. The network/SSID summary returned
one split network, one default network and six SSIDs. The aggregate SSID client
count was `null` because at least one contributing source field was missing;
the wired VLAN summary's configuring-network count was likewise `null`. Both
summaries stayed partial, and the connector did not substitute zero for these
incomplete totals. The other projected counts and unknown-field counts are
recorded by the returned summary. No active measurement or configuration
change occurred. The process stopped, its temporary RAM files were removed,
and the loopback service was closed. This confirms the workflow on this
controller only; it does not establish complete topology or broader support.


## WLAN, AP and gateway follow-up reads

After the topology projection correction, a pinned, loopback-only connector
with writes disabled ran the site Wi-Fi diagnosis through actual Streamable
HTTP MCP. Initialization, notification and tool call succeeded; all ten
report sections returned without section errors. The overall report remained
partial because source measurements were incomplete, and the SSID client-count
aggregate remained `null`. A focused offline regression run passed 19 tests.

A subsequent AP-comparison MCP call used two APs selected from the current
inventory. Health, radio, saved RF scan and LAN traffic reads returned; both
saved nearby-WLAN sections returned `connector_http_error`. The aggregate
report was partial. No scan was started, and the route failures do not prove
that the controller lacks support.

A gateway-diagnosis MCP call returned nine sections without errors. The
Internet-information section again returned `openapi_rejected`, with upstream
HTTP 200 and numeric API code -1. The code's meaning remains unknown. Saved
speed-test results were read without starting a test. No active measurement or
network change occurred. The current inventory has no switch; switch-specific
live checks therefore remain unverified. LAN/VLAN/DHCP/DNS and event/alert
reads are covered by the successful network-overview call above. Temporary
credentials, RAM-backed files and connector processes were removed after each
read-only run.


## AP nearby-WLAN result investigation

The pinned, loopback-only connector was restarted with writes disabled. Actual
MCP calls read the AP scan status and the stored nearby-WLAN results for two
APs selected from the current inventory. Both status reads returned
`wifiInterfStatus=1`; the original exports define this as unscanned with no
stored result. Each nearby-WLAN result call returned a sanitized
`openapi_rejected` section with upstream HTTP status 200 and API code `-39378`.
The API code is not listed or explained in any of the three local exports.

After changing MCP error forwarding, the actual `omada_wifi_compare_aps` tool
was called again. Both per-AP nearby-WLAN sections retained the same numeric
upstream error while the comparison stayed partial and kept its other reads.
The focused comparison and dispatch regression run passed seven tests. No
scan or setting change occurred. Temporary processes and RAM files were
removed after the calls.
