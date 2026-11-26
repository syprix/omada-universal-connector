# MCP endpoint and client setup

The connector exposes a stateless MCP Streamable HTTP endpoint at `POST /mcp`, on the same HTTP listener as the versioned API. It requires the existing connector caller token as an `Authorization: Bearer …` header. `GET /mcp` is not supported. Requests use JSON-RPC and the MCP protocol versions advertised by `initialize`.

## Available tools

`omada_ssid_network_summary` compares at most 64 SSID configuration reads with the selected site's current network inventory, then summarizes available per-network VLAN and DHCP-pool evidence, site-wide DNS settings and bounded gateway inventory details. It returns counts and safe setting flags without names or references. DNS-to-WLAN and gateway-to-network associations remain explicitly unknown where the source projections do not expose a link. This read-only workflow does not modify WLAN or network settings.

For a synthetic four-SSID, four-network and one-gateway fixture, `js-tiktoken`
1.0.21 with `o200k_base` counted 1,063 tokens across the 19 compact connector
JSON responses used by the workflow and 313 tokens in its final JSON result
(750 fewer, 70.56%). This compares response bodies only: it excludes HTTP/MCP
framing, the agent's request and billed usage. No live network data was used.

`omada_site_wlan_group_summary` reads the legacy v1 WLAN-group list, which the source API marks deprecated in favor of the AP-group list. It returns only group, primary/clone and resource-code counts; group names, IDs and site IDs are omitted. Live support is unknown.

`omada_site_wlan_group_ssids_summary` uses a `wlan_group_ref` from the selected site's current WLAN-group inventory and reads at most 500 SSIDs. It returns band, documented security-code and flag counts; SSID names, IDs and VLAN values are omitted. The enabled-state property exists in Hardware/CBC but not ER7212PC, so those rows are reported unconfigured there. Live support is unknown.

`omada_site_wlan_group_ssid_config_summary` requires both a current `wlan_group_ref` and `ssid_ref` from the same site. It checks unique membership in that group's SSID list before reading the group-scoped `getSsidDetail` operation, then returns only documented enabled, band and EAP/gateway applicability flags. Names, IDs, VLAN values and credentials are omitted. Missing fields stay unknown; live support is unknown.

`omada_site_lte_wan_config_summary` counts LTE WAN settings and documented
modem-status codes for the selected site. It separates stored configuration
from status and does not infer Internet reachability. SIM/port identifiers,
names, provider values, APNs and raw band strings are omitted. Live support is
unknown. A synthetic 20-row response measured 4,328 tokens before projection
and 458 after (89.42% fewer) with `js-tiktoken` 1.0.21 and `o200k_base`.
These are serialized JSON response bodies only, not live or billed usage.

On synthetic fixtures, `js-tiktoken` 1.0.21 with `o200k_base` counted 533
tokens in a 20-row static-route interface response and 128 in its projection
(75.98% fewer). A selected-SSID flow fixture (inventory, group membership and
one detail response) measured 134 source-response tokens and 92 final-result
tokens (31.34% fewer). These are serialized JSON bodies only; no live response,
HTTP/MCP framing or billed agent usage is included.

`tools/list` returns pages of 25 tools. This development build registers fixed GET tools, bounded read workflows and the plan-based cable-test workflow documented below. `omada_wifi_diagnose_site` combines twelve fixed site reads: WLAN health timeline/details, channels, client signal distribution, 6-GHz AP presence, stored rogue-AP results, Wireless IDS events and dynamic blacklist summary, band-steering, RRM, roaming and topology summary. It returns one projected report without starting a scan or changing policy. `omada_wifi_diagnose_client` verifies an opaque `client_ref` against the selected site's fresh client inventory, then combines recent connection records, compact summaries of four event timelines, health history and redacted client history with the site WLAN summary; event-code meanings are not inferred. Its outage-timeline read also reports requested bounds, earliest/latest observed client and health samples, site event/alert counts and page-limit state, up to eight currently inventoried AP health timelines referenced by observed client events, and documented controller/client history settings. Empty sources never imply complete coverage; retention settings and observed bounds do not prove how much history is actually available. It accepts no client identifiers or controller paths. `omada_wifi_diagnose_ap` also accepts an opaque `ap_ref`, verifies it against the selected site's device inventory, and adds the AP's health, health timeline, radio configuration, existing RF scan and speed-test results, nearby WLAN channel/signal measurements, LAN traffic, redacted wired-downlink and wired-uplink readings, compact AP-port link/PoE/uplink counts, and VLAN-ID/native/tagged/untagged port counts. Speed-test entries are saved results; the workflow never starts an active measurement. `omada_wifi_compare_aps` checks two distinct AP references in one site's device inventory and returns compact side-by-side health, radio, existing scan-summary, redacted nearby-WLAN channel/signal counts and LAN-counter measurements; it does not rank or score the devices. `omada_network_diagnose_gateway` combines fixed WAN port status/details with gateway LAN counters, port type codes, health and its 24-hour score timeline, saved WAN speed-test results, and aggregated WAN online-detection codes for one gateway reference from the site inventory plus bounded site-wide gateway-setting presence and site-capability flags; it does not start a speed test, probe or configuration change. `omada_network_diagnose_switch` verifies a current switch reference and combines fixed health and its 24-hour score timeline, SDM category/entry-capacity values, stored cable-test logs and full/incremental results, configured-network and network VLAN summaries, interface type counts, route summaries, static-route counts, VRF enablement/default counts, VLAN-interface counts and switch/port statistics, port state, counters, PoE, VLAN membership and LLDP summaries. Cable-test logs and full results are stored data; no test is started. `omada_ap_ports` returns bounded link-status, speed, PoE and uplink counts for one inventoried AP without port names, numbers or VLAN identifiers. `omada_ap_available_channels` reads the AP-reported channel catalog through its fixed GET and site-bound inventory reference; `omada_ap_scan_status` reads the last AP interference-detection status without starting a scan; `omada_site_batch_interference_history` reads one fixed page of existing site scan history and returns status and aggregate counts while omitting history IDs, AP details and unscaled times; `omada_ap_wifi_interference` returns redacted nearby WLAN measurements with opaque neighbor references; `omada_ap_speed_test_results` reads prior AP link-speed results and never starts a speed test; `omada_site_wifi_summary` returns the fixed 24-hour aggregate AP/client counts, channel utilization and total traffic; `omada_site_client_health_timeline` returns the fixed 24-hour aggregate client health categories for a site. `omada_experience_index` reads existing WLAN optimization history; `omada_rf_deploy_history` reports the documented prior-optimization boolean; `omada_rf_planning_result` reads the last optimization status; `omada_rf_planning_dashboard` returns bounded interference and AP-density trends with AP identities removed; `omada_rf_planning_dashboard_current` exposes the separately documented dashboard route through the same projection over a fixed trailing 24-hour window; `omada_rf_planning_dashboard_history` adds a fixed 24-hour trend window; `omada_rf_planning_detail` returns stored radio recommendations without device identities; `omada_rf_planning_history` returns one bounded redacted page of stored optimization records with opaque history references; `omada_rf_planning_history_detail` reads a history reference returned by the most recent list call for that site; `omada_rf_planning_recent_history` reads up to 100 redacted records from a fixed last-30-day window; `omada_rf_excluded_aps` reads the first page of up to 256 exclusions and maps them to fresh opaque AP references. It validates controller page metadata when present, marks incomplete results partial, and treats a full array page without a total as partial. The AP diagnosis includes at most 64 nearby radios summarized by band, channel, signal and bandwidth; identifiers and timestamps are removed and excess rows are counted. All are read-only and never start an optimization or scan. `omada_gateway_firewall_rules`, `omada_switch_firewall_rules` and `omada_ap_firewall_rules` expose the existing redacted ACL readers. Their shared `site_ref` is resolved from the selected site's inventory; rule identifiers and free-text labels remain omitted. Each is read-only. `omada_site_events` reads the existing redacted, paginated event list. It defaults to a rolling 30-day window and accepts either an optional UTC millisecond pair (`start_ms`/`end_ms`) or local bounds (`start_local`/`end_local` plus an IANA `time_zone`) limited to 24 hours. For a fixed window of up to 30 days, callers can request one page using `start_ms`, `end_ms`, `page_number` (1–64) and `page_size` (1–200, capped by the configured connector page size; default 100). Each call reads exactly one page. Continuations must repeat the same window and page size and include the first page's `total_count` as `expected_total`; the connector rejects a changed total. No page is fetched implicitly. Aggregate pages and deduplicate opaque references client-side. `partial`, `next_page`, `window_exhausted` and `page_limit_reached` describe page coverage. The controller offers no documented snapshot or stable-order guarantee, so this is a bounded paginated observation, not a snapshot-consistent history. Results expose opaque event references and normalized module only. If the legacy full list exceeds its configured page limit, it returns an error. `omada_site_alerts` keeps its fixed rolling 30-day window and returns opaque alert references with bounded module and severity fields only. Neither tool returns log text. `omada_switch_port_tags` returns site-bound counts of configured switch-port labels and source codes without returning label text or IDs. `omada_dhcp_leases`, `omada_dns_cache_settings`, `omada_dns_proxy_settings` and `omada_lan_dns_records` expose bounded, redacted site reads. DHCP returns opaque references and classifications; DNS settings return only documented booleans, TTL and categorical mode, and DNS records omit labels, domains, addresses and network IDs. The registry also exposes `omada_device_firmware`, `omada_client_detail`, `omada_wlan_groups` and `omada_ssid_configuration`. Device/client and SSID detail require opaque references from the selected site’s fresh inventory; the readers retain their existing version, field and secret redaction. AP health, health timeline, radio configuration, AFC settings, radio detail, channel load, saved RF scan results and site retry/drop summaries are also available as separate fixed reads. The AP-bound tools require a current `device_ref`; these reads never start an RF scan. `omada_site_channel_limit` reads the documented site-wide channel limit; `omada_rrm_incompatible` returns bounded AP references and documented incompatibility codes. These are read-only, and the RRM tool does not infer a hardware cause. `omada_switch_port_status` and `omada_switch_port_poe_mode` return the selected port row from the switch overview. Their `port` argument is an integer from 0 to 4096 and both references must belong to the selected site. Other HTTP routes are not automatically exposed over MCP. Names use `omada_<operation_id>` for fixed reads; paths and HTTP methods are never accepted from the caller. Read tools are marked read-only. The cable-test tool is marked potentially destructive and uses the same preview, signed approval, journal and one-time dispatch flow as HTTP. A tool requiring a site uses the opaque `site_ref` returned by the connector; client, AP and switch workflows also require a reference from that site's current inventory. History references are scoped to the site and held in process memory; refresh the history list after a connector restart. Unknown tools, extra arguments, malformed references and non-local browser Origins are rejected.

`omada_capability_summary` reports the process-local capability-catalog counts and can return a compact view of one exact `operation_id`. It never contacts the controller and omits runtime target references. Runtime evidence separates the projected response shape from a response received through a TLS-verified controller connection; fixture or mocked responses do not count as live permission or support evidence. `catalog_complete` remains false; this tool does not assert that every controller/API capability has been implemented or verified.

`omada_diagnostic_capability_summary` groups the current catalog into the complete WLAN, client, AP, gateway, switch and site-network read workflows. For each required read it distinguishes source documentation, an observed successful controller response with a supported shape, unknown evidence and recorded failures. It makes no controller requests and omits runtime target references. Documentation counts refer to the bundled source exports, not necessarily the controller currently connected to the process; the catalog remains explicitly incomplete.

`omada_compare_site_capabilities` compares 2–16 explicitly selected `site_ref` values, refreshing the site inventory first. `GET /v1/sites/capability-comparison` accepts the same references as repeated `site_ref` query parameters. Feature values are aligned to the returned `site_refs` columns (`1` enabled, `0` disabled, `null` unknown). Missing values, permission failures and references absent from the current inventory remain distinguishable; no route probes or broad site discovery is performed.

`omada_ap_uplink_config` exposes the distinct read-only AP auto-uplink and port configuration. It is separate from the wired-link status reader and is not called automatically by a diagnostic workflow.

`omada_site_rogue_ap_results` summarizes stored rogue-AP scan results for a site. It removes SSIDs, BSSIDs, AP identities, record identifiers and timestamps; scan freshness is unknown. `omada_wifi_diagnose_site` includes this summary. Both paths read saved results only and never start a scan.

`omada_site_wids_summary` reads one fixed page of stored Wireless IDS events. It returns counts by documented severity and band codes, raw event type codes, and channel; device MAC addresses and detection times are discarded. If the API reports more rows than the page contains, the result is marked partial. The WLAN site diagnosis includes this bounded read. It does not start a scan. Fixture coverage only; live support remains unknown.

`omada_site_wids_blacklist_summary` reads one fixed page of the dynamic Wireless IDS blacklist. It returns the row count and data-quality counters only; station/AP MAC addresses and timestamps are discarded. The WLAN site diagnosis includes this read. Fixture coverage only; live support remains unknown.

`omada_ap_lldp_config` reads the inventoried AP's LLDP setting (`off`, `on` or `site_default`) and whether LLDP is supported. The AP diagnostic includes this fixed read. It does not change LLDP configuration.

`omada_ap_port_vlans` and `omada_wifi_diagnose_ap` include compact counts by VLAN ID and native, tagged and untagged port assignments. Network IDs, names, addresses and port labels are omitted. The fixed paginated read is covered by fixture tests; live support remains unverified.

`omada_ap_bridge_config` summarizes the inventoried AP’s documented P2P bridge and TDMA state. SSIDs, passwords, pairing codes, device identifiers and names are redacted; the report contains only state codes and bounded client/priority counts. Missing optional status/lists remain unknown and mark the result partial. The read is fixture-tested, and live controller support is unknown.

`omada_ap_mesh_candidates` returns a paginated, inventory-bound mesh-candidate summary by link, hop, recommendation, radio, channel and raw RSSI codes. Candidate AP names and MAC addresses are omitted. It reads the documented pre-adoption candidate list; it does not adopt an AP or start a scan.

`omada_ap_general_config` returns inventoried AP general settings while omitting the AP name, tag IDs and precise location. It exposes only scalar setting codes/booleans, tag and RSSI-threshold counts, and whether location is configured.

`omada_ap_ip_setting` reports the inventoried AP's `Static` or `DHCP` mode, safe fallback/reservation booleans and whether each settings section exists. IP addresses, masks, gateways, DNS values, network IDs, MAC addresses and other DHCP server identifiers are omitted.

`omada_ap_ipv6_setting` reports enablement, dynamic/static mode, DNS mode and static prefix length for an inventoried AP. IPv6 addresses and DNS server values are omitted.

`omada_ap_p2p_info` summarizes an inventoried AP's P2P bridge group as main-device presence and child-device count. AP names and MAC addresses are omitted.

`omada_ap_l3_access` reads the inventoried AP's layer-3 access enablement and whether the device supports the feature.
`omada_ap_paring_window` reads the saved pairing-window result as status, countdown and candidate status/RSSI counts. AP identity, model and version are omitted. It does not start pairing. `omada_ap_rf_scan_v2` reads the separately documented v2 saved-result endpoint; it uses the same bounded projection as the v1 result reader and does not start a scan. `omada_ap_management_ssid` reads the AP management WLAN enablement, broadcast/security codes and VLAN mode; SSID names, passwords, RADIUS profile IDs and network IDs are omitted. `omada_ap_snmp_config` reports the AP SNMP mode code and whether custom location/contact fields are set; their text is omitted. `omada_ap_vlan_v1` reads the separate v1 VLAN mode and bridge/network-binding presence; network IDs are omitted and the v2 route remains separate. `omada_ap_wlan_overrides` returns bounded SSID enabled/security/band and VLAN counters; SSID names, credentials, IDs and VLAN values are omitted.
`omada_ap_lag_config` reads the separate documented `/aps/{apMac}/lag` operation and returns only its bounded support, enabled and mode values. This remains distinct from the controller's `/trunk-setting` route.

`omada_site_device_tag_summary` reads the selected site's documented tag list and returns only the bounded count and name/ID presence counts. Tag names and IDs are not returned.
`omada_site_entity_summary` reads the inventory-bound site entity and returns only site tier, time-setting flags and switch-support flags. Site names, IDs, tags, region/time zone values, NTP addresses, precise coordinates and street addresses are omitted.
`omada_site_upnp_summary` reads documented UPnP settings for an inventory-bound site and returns the enable/support flags and the number of selected WAN ports and networks. WAN port and network IDs are omitted.
`omada_site_iot_aging_time` reads the deprecated Bluetooth aging-time GET. It returns only the documented interval and unit when both values fit the format-specific bounds; unknown fields are omitted. The three source exports list this route and the Site Settings Manager View Only or Device Config Page View Only permission. Live support remains unknown.
`omada_site_iot_radio_summary` reads the documented Bluetooth radio configuration. It reports only bounded enablement, console-mode, transmit-power and aging fields, and whether a passcode is configured. The six-digit passcode is never returned. The three exports list the `Site Settings Manager View Only` or `Device Config Page View Only` permission. Live support remains unknown.
`omada_site_mesh_summary` reports the documented mesh/failover flags and whether a customer-supplied gateway is configured; the gateway IP itself is omitted. The exports list `Site Settings Manager View Only`, `Site Map Manager View Only`, `Site Hotspot Manager View Only` or `Site Device Manager View Only`. Live support remains unknown.
`omada_site_hotspot_rate_limit_profiles_summary` reads the separate Hotspot profile list for one selected site. It reports enabled/disabled/unknown direction flags, default coverage and aggregate Kbps values only for valid enabled limits. Disabled-side values are ignored; the result omits profile names, IDs, site fields and raw limits, and does not claim a profile applies to clients. HTTP/MCP fixture coverage exists; live support is unknown.

`omada_site_multicast_rate_limit_summary` reports the documented broadcast/multicast enable switches, packets-per-second values and aggregate counts. It does not send or change traffic. The exports list site view permissions. Live support remains unknown.
`omada_site_beacon_control_summary` reads documented WLAN beacon intervals, DTIM and RTS thresholds, probe-response settings, and airtime-fairness flags. Numeric values are schema-bounded; unknown response fields are counted and omitted. The three exports list site view permissions. Live support remains unknown.
`omada_site_iot_transmit_power_summary` reads one fixed page of up to 100 IoT radio rows. It returns counts by documented transmit power and status category, override totals and whether more rows exist. Device names, addresses and identifiers are omitted. The three exports list `Site Settings Manager View Only` or `Device Config Page View Only`. Live support remains unknown.
`omada_site_bluetooth_advertising_v2_summary` uses only `GET /openapi/v2/{omadacId}/sites/{siteId}/setting/iot/devices/config?page=1&pageSize=100`, documented for Hardware Controller 6.3, CBC 6.3 and ER7212PC 6.2.14. It returns aggregate row, enable-flag and bound-device-count coverage totals; it never returns beacon names, IDs, MACs, UUID/major/minor values, AP detail or deprecated transmit power. The exports list `Site Settings Manager View Only` or `Device Config Page View Only`. More than 100 rows or incomplete/invalid page metadata is marked partial. Live support is unverified.
`omada_site_remember_setting_summary` reports the documented site remember-device Boolean. The three source exports list `Site Settings Manager View Only`. Live support remains unknown.
`omada_site_client_connection_summary` reads only the documented total, wired and wireless client counts. Client identities and details are not returned. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.
`omada_site_poe_usage_summary` aggregates documented PoE usage in watts and reported port counts across switches. Switch identities and raw per-switch values are omitted. It excludes percentage fields because the exports disagree on that field's schema. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.
`omada_site_poe_schedule_summary` combines a fresh switch inventory with PoE-capable ports, per-switch documented watt budgets, compact current port-state counts and scheduled port targets. MAC addresses are used only for the internal join; output uses opaque switch references and omits device names, schedule/profile names and IDs. Numeric port measurements are reduced to presence counts; their units remain unspecified. Next-execution timestamps are reported as presence only because the unit is undocumented. Detailed feed fields are documented in all three exports, with differences in field descriptions and numeric type wrappers; live controller support remains unknown.
`omada_site_device_counts_summary` aggregates the documented total, preconfigured, connected and disconnected device counts from the site dashboard. Category labels are omitted. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.
`omada_site_ipsec_tunnel_summary` reports tunnel and inbound/outbound SA counts plus enabled/disabled counts. Names, peer addresses and local/remote network segments are omitted. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.
`omada_site_client_association_time_summary` reads the documented connection-time bins and failure count over a fixed trailing 24-hour window. The time interval is set by the connector; callers cannot expand it. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.
`omada_site_network_activity_summary` reads aggregate traffic totals and wired, wireless and total client counts for a fixed trailing 24-hour window. Activity detail rows are discarded. The source contract does not specify traffic units, so the output does not label them. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.
`omada_site_client_rssi_distribution_summary` reports the documented RSSI category counts overall and for 2.4, 5 and 6 GHz. It returns no client rows or identifiers. Bucket labels retain the source's thresholds without inferring units or inclusive boundaries. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.
`omada_site_ap_rssi_density_summary` counts access-point rows in the documented signal buckets and returns only two presence flags. Access-point names, MAC addresses, models and health/traffic details are discarded. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.
`omada_site_client_attachment_distribution_summary` returns only the total client counts attached through access points and switches. Per-device distributions and client detail rows are discarded. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.
`omada_site_client_frequency_distribution_summary` exposes total, wired and wireless client counts from the client-frequency dashboard; only documented aggregate counts are returned. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.
`omada_site_device_traffic_summary` sums the documented AP and switch traffic values in MB over a fixed trailing 24-hour window. Device rows, names, MAC addresses and reported proportions are omitted. The time window is connector-controlled. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.
`omada_site_past_client_summary` reads total, wired and wireless client counts for a connector-fixed trailing 24-hour window. The client counts are aggregate values only. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.
`omada_site_current_client_summary` reads current total, wired and wireless client counts without returning client details. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.
`omada_site_lan_client_inventory_summary` reports paged LAN inventory coverage and device-type field presence, omitting MACs, names and raw types. It reads at most 1,000 entries and does not imply current connectivity. Fixture-tested; live support is unknown.
`omada_site_topology_root_candidates_summary` reports counts of documented topology root candidates and known type/flag codes. Names, device identifiers, model strings and subtype values are omitted. Hardware Controller and CBC document the operation; ER7212PC does not. It does not return topology links; live support is unknown.
`omada_site_isolated_preconfig_summary` reports isolated and preconfigured array totals separately and checks them against the documented total. Device identifiers, names, models, health scores and device-type values are omitted. Hardware Controller and CBC document the source, not ER7212PC; the summary does not initiate adoption or explain isolation.
`omada_site_vlan_topology_summary` requires a same-site network reference and its assigned VLAN, then counts the known device classes in the topology response after matching against that site's device inventory. MACs and identifiers are omitted; unknown and unmatched entries are reported as coverage gaps. Hardware Controller and CBC document the operation; ER7212PC does not.
`omada_site_es_network_overview_summary` resolves a switch reference from the site's current device inventory, then requires exactly one matching row in `getOswDetailInfoListForPortsView` with the documented `es` flag set to `true` before calling `getESNetworkOverview`. Missing or duplicate matches and non-Agile switches are rejected. It returns counts for networks and native, untagged and tagged port assignments plus array field coverage. It omits VLAN values, network identities and port numbers. All three exports document both reads; live hardware support is unknown.
`omada_site_port_schedule_ports_summary` counts devices and port IDs reported as eligible for scheduling, including documented gateway/switch types and port-list coverage. It omits device identities, port numbers and raw status meanings. This is the supported-port inventory, separate from configured schedule data; live support is unknown.
`omada_site_gateway_isp_summary` summarizes gateway and ISP status and peak upload/download utilization percentages. Gateway names, MAC addresses, ISP names, IP addresses, ports, configured speeds and other per-WAN details are omitted. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.

`omada_site_top_ap_retry_drop_summary` reads the documented top-AP-by-RT and top-AP-by-drop ranking over a fixed trailing 24-hour window. It returns each list count and the highest documented ratio percentage, with at most five source rows per list. Device identifiers, models, status, traffic, utilization, and row details are omitted. The three source exports list `Site Dashboard Manager View Only`. Live support remains unknown.

`omada_site_active_ap_summary` and `omada_site_active_switch_summary` summarize their documented activity rankings over a fixed trailing 24-hour window. They return row counts, connection-status counts, and traffic totals and maxima as unlabeled numeric values because the source description says bytes while its shared response schema says GB. Device names, MAC addresses, models, and row details are omitted. All three source exports list `Site Dashboard Manager View Only`; live support remains unknown.

`omada_site_device_memory_summary` summarizes the documented top-device memory ranking over a fixed trailing 24-hour window. It returns the row count and maximum and average memory-use percentages; device names, MAC addresses, models, and row details are omitted. All three source exports list `Site Dashboard Manager View Only`; live support remains unknown.

`omada_site_switch_dashboard_summary` reads the documented switch dashboard over a fixed trailing 24-hour window and returns wired-client, connected-switch, port-occupancy and traffic-byte totals. The API describes port occupancy as an integer rate without a scale; that value is returned without a unit. Device-level details are absent from the projected result. All three source exports list `Site Dashboard Manager View Only`; live support remains unknown.

`omada_site_ap_interference_summary` aggregates the documented top-AP lists by frequency band and returns row counts and maximum interference values. The endpoint has no time parameters, so the controller-selected period is left unchanged. The exports disagree on shape: the recursive response schema conflicts with an ER7212PC example containing direct `interUtil` rows. Direct example rows are summarized; a recursive nested response is marked partial rather than traversed. Device names, MAC addresses, models and nearby-AP names are omitted. Live support remains unknown.

`omada_site_application_category_summary` reads `getCategoryInfo` for a fixed trailing 24-hour window, page 1 with at most 100 categories. It returns page and category counts, traffic totals and maxima, traffic-share maximum, and allow/block application counts. Category, application, client names and identifiers are omitted. Traffic units are unspecified in the API exports, so values are labeled as unitless traffic values. The sources document `Site Dashboard Manager View Only`; live support remains unknown.

`omada_site_application_family_inventory` reads the site's documented DPI family list and returns only unique, valid nonnegative int32 family IDs as decimal `family_refs` for the existing category application/client readers. Names, descriptions and all source rows are omitted. Duplicate or invalid rows make the result partial; an oversized list is rejected. The source lists Site Settings Manager, Network Config Page, Site Device Manager, Site Statics Manager or Site Clients Manager View Only and requires a gateway that supports DPI. Live support is unknown.

`omada_site_gateway_supported_model_references` reads the documented site list of gateway model IDs and names offered for pre-configuration. It returns only validated, unique vendor reference pairs, bounded to 100 entries with names up to 128 characters. Duplicate or invalid rows make the result partial; a missing `supportModels` field is partial and is not treated as an empty list. This is reference data only and does not describe installed devices or infer current gateway support. The source documents Site Settings Manager View Only or Network Config Page View Only; live support is unknown.

`omada_site_category_application_summary` reads application traffic for a supplied numeric category ID over a fixed trailing 24-hour window. It returns row counts, traffic totals and maxima, block-event and active-user counts, and client-use counts. Application and client names, descriptions, MAC addresses and IDs are omitted. Traffic units are unspecified by the exports. The API returns an unpaged list; the connector accepts at most 1,000 rows and marks missing, invalid or unknown fields as partial. The sources document `Site Dashboard Manager View Only`; live support remains unknown.

`omada_site_category_client_summary` reads client traffic for a supplied numeric category ID over a fixed trailing 24-hour window. It returns client and application counts, traffic totals and maximums, and the count of clients with application rows. Client names, MAC addresses, application details, network names and VLAN IDs are omitted. Traffic units are unspecified. The API returns an unpaged list; the connector accepts at most 1,000 rows and marks missing, invalid or unknown fields as partial. The exports disagree on percentage field types (number versus object), so nonnumeric forms are marked invalid. Live support remains unknown.

`omada_site_open_vpn_tunnel_summary` reads OpenVPN tunnel statistics for type `0` (server) or `1` (client). It returns enabled/disabled VPN counts, tunnel count and transmitted/received byte totals, capped at 500 rows. Site and VPN names are omitted. The three source schemas agree on these fields and byte units; live support remains unknown.

`omada_site_client_activity_summary` reads client activity samples for a fixed trailing 24-hour window. It sums new and disconnected EAP/switch client counts and reports mean and peak active clients per sample. It returns sample count and raw timestamp bounds; the source does not specify the time unit. The list is capped at 2,000 rows, and malformed or unknown fields are reported as partial. The three source exports agree on the response fields; live support remains unknown.

`omada_site_client_association_activity_summary` reads only total, wired and wireless client counts for a connector-fixed trailing 24-hour interval. It does not return client records or identities. All three exports define the same count fields and list `Site Dashboard Manager View Only`; live support remains unknown.

`omada_site_client_traffic_summary` reads one page for a connector-fixed trailing 24-hour window. Supply a zero-based `page_number` (0–10,000) and `page_size` (1–100); the connector maps page zero to Omada's documented first page, and the result reports whether more pages remain. It returns traffic and application totals for that page without client, application, network or VLAN names, addresses or IDs. Traffic units are unspecified. ER7212PC declares percentage values as object references where the other two exports declare numbers, so percentages are omitted. The exports do not state a permission for this endpoint; live support remains unknown.

`omada_site_active_ap_v2_summary` reads the v2 AP activity endpoint for a fixed trailing 24-hour window, with `deviceNum=10`. It reports connected/disconnected counts, the maximum per-AP traffic in the documented GB unit and the reported site total value. AP names, MAC addresses and model details are omitted. ER7212PC describes the numeric traffic fields as object references; nonnumeric responses are marked partial. The exports do not state a permission for this endpoint; live support remains unknown.

`omada_site_hotspot_statistics_summary` reads hotspot authentication counts for a connector-fixed trailing 24-hour window. It sums new/existing client counts across up to 2,000 time buckets, returns raw time bounds, and includes aggregate authentication and hotspot type counts. Timestamp units are unspecified; no user-level data is returned. The three source schemas agree, while endpoint permission and live support are unstated.

`omada_site_voucher_currency_options` reads the site's documented voucher currency short-code list and selected short code. It returns bounded strings as reported by the controller, tracks missing and invalid fields separately from a valid empty list, and reports duplicate/unknown-field counts. Codes are not classified as ISO currencies and no exchange rates, prices or voucher-setting changes are included. The source requires Site Hotspot Manager View Only; live support is unknown.

A synthetic page with 20 client rows and 40 nested application rows measured with `js-tiktoken` 1.0.21 / `o200k_base` decreased from 3,775 source-envelope tokens to 127 projected HTTP JSON tokens (3,648 fewer; 96.64%). This fixture excludes billed agent usage and MCP framing.

A synthetic 10-AP response measured with `js-tiktoken` 1.0.21 / `o200k_base` decreased from 473 source-envelope tokens to 91 projected HTTP JSON tokens (382 fewer; 80.76%). This fixture excludes billed agent usage and MCP framing.

A synthetic response with 96 time buckets and both distributions measured with `js-tiktoken` 1.0.21 / `o200k_base` decreased from 2,584 source-envelope tokens to 158 projected HTTP JSON tokens (2,426 fewer; 93.89%). This fixture excludes billed agent usage and MCP framing.

A synthetic three-count response measured with `js-tiktoken` 1.0.21 / `o200k_base` used 25 tokens in the source envelope and 61 tokens in the HTTP JSON result. The extra 36 tokens come from connector response metadata; this small aggregate read is useful for API coverage but does not reduce tokens on its own.

A synthetic 96-sample response measured with `js-tiktoken` 1.0.21 and `o200k_base` decreased from 5,004 source-envelope tokens to 181 projected HTTP JSON tokens (4,823 fewer; 96.38%). This fixture comparison does not measure billed agent usage or MCP framing.

`omada_site_vpn_tunnel_summary` reads dashboard VPN statistics for a selected type (`0` server or `1` client). It reports enabled/disabled VPN counts, total tunnel count and total transmitted/received bytes for up to 500 rows. Site and VPN names are omitted; traffic values are documented in bytes. Live support remains unknown.

`omada_site_isp_load_summary` reads WAN port load over a fixed trailing 24-hour window. It returns mean/peak total rate and mean/minimum/maximum latency across up to 5,000 samples from at most 64 ports; port names and IDs are omitted. The schema defines latency in milliseconds and says values should be within 0–1000, but does not state a unit for `totalRate`. Live support remains unknown.

`omada_site_traffic_activity_summary` reads AP and switch traffic samples over a fixed trailing 24-hour window. It returns sample counts, earliest/latest timestamps and mean/peak uplink/downlink sample values, with each list capped at 2,000 rows. The contracts describe traffic values in MB but do not define the sampling interval. ER7212PC describes the numeric values as objects referencing number(double); the other exports declare numbers. Live support remains unknown.

`omada_site_client_bubble_summary` reads the unpaged active-client bubble list through its fixed endpoint. It reports traffic totals and aggregate RSSI, SNR and health values, capped at 1,000 rows. Client names, MAC addresses, AP names and device types are omitted. Traffic and radio units are unspecified; Hardware Controller and CBC include an `incidents` field that ER7212PC omits. Live support remains unknown.

`omada_site_cpu_usage_summary` reads the top-five device CPU list over a fixed trailing 24-hour window. It reports only the device count and mean, minimum and maximum CPU utilization values. Device names, MAC addresses, models, model versions and types are omitted. The API describes `cpuUtil` as an int32 CPU utilization value but does not state its unit; live support remains unknown.

`omada_site_active_client_summary` reads the active-client dashboard list through its fixed endpoint with no query parameters. It returns client and wireless/wired counts, traffic totals and maximum observed client traffic. Names, MAC addresses, types and models are omitted. The unpaged list is capped at 1,000 rows; traffic units are unspecified and live support remains unknown.

`omada_site_active_application_summary` reads the most-active applications over a fixed trailing 24-hour window. It returns the number of rows, aggregate traffic and client-application counts, and maximum traffic/share values. Application and category names and IDs are omitted. The API list is unpaged; the connector accepts at most 1,000 rows. ER7212PC declares the percentage field as an object while the other exports declare a number; nonnumeric values are marked invalid. Traffic units are unspecified and live support remains unknown.

For the bounded dashboard summaries above, a five-row synthetic fixture was tokenized with `js-tiktoken` 1.0.21 and `o200k_base`. The comparison is the unprojected documented API response envelope (`errorCode`, `msg`, `result`) versus the projected connector HTTP JSON response; it includes neither request text nor MCP framing.

| Summary | Unprojected response | Projected response | Difference |
| --- | ---: | ---: | ---: |
| Top AP retry/drop (five rows in each ranking) | 874 | 82 | 792 fewer (90.62%) |
| Active APs (five rows) | 225 | 83 | 142 fewer (63.11%) |
| Active switches (five rows) | 225 | 83 | 142 fewer (63.11%) |
| Device memory ranking (five rows) | 222 | 65 | 157 fewer (70.72%) |
| Switch dashboard (four fields) | 33 | 75 | 42 more (127.27%) |
| Application categories (ten synthetic rows, nested detail present) | 4881 | 130 | 4751 fewer (97.34%) |
| Applications in one category (ten synthetic rows, client detail present) | 4551 | 120 | 4431 fewer (97.36%) |
| AP interference (five rows in each of four bands) | 1,029 | 124 | 905 fewer (87.95%) |

These are exact tokenizer counts for synthetic fixture JSON only. The switch-dashboard result is larger than the four-field source envelope because the connector adds routing and data-quality metadata; it is not token-saving on its own. The active-device source description says bytes while its shared schema says GB, so output values have no unit label. This does not establish live response sizes, Hermes/Codex/Claude runtime behavior, or billed-token savings; prompt, tool schemas, transport framing, and agent serialization are excluded.
`omada_site_gre_tunnel_summary` reads the documented EoGRE settings and returns enable state, bounded MTU/keepalive values and endpoint-presence flags. Tunnel endpoint addresses are omitted.
`omada_site_ssl_vpn_summary` reads the legacy SSL VPN settings endpoint and returns status, service/authentication mode, lock flags and capability switches. Server addresses, IP pools, DNS values, port IDs and RADIUS/LDAP profile data are omitted. The upstream operation is deprecated; prefer the current VPN server summary/detail operations when available.
`omada_site_ssh_summary` reads SSH enablement, Layer-3 access and the configured server port for the inventory-bound site. It does not connect to the SSH service.
`omada_site_mld_summary` reads the documented MLD enable/version settings and reports only whether a WAN port is selected and how many feature-description rows are present. WAN identifiers and feature-description text are omitted.
`omada_site_igmp_summary` reads IGMP enablement/version and WAN or virtual-WAN selection presence; identifiers and feature-description text are omitted.
`omada_site_templates` lists the controller's site templates using opaque references; descriptive names remain hidden unless explicitly enabled. `omada_site_template_igmp_summary` reads the CBC template IGMP fields through a reference returned by that inventory.
`omada_site_template_upnp_summary` reads the CBC template UPnP summary through the same opaque template inventory; WAN/network IDs are returned only as presence counts.
`omada_site_template_ssh_summary` reads the CBC template SSH settings through an opaque template reference. It returns enablement, Layer-3 access and the configured port; it does not connect to SSH.
`omada_site_template_iptv_summary` reads the CBC template IPTV settings through an opaque template reference. It returns enablement/mode, bounded LAN-port type counts and configuration presence; WAN/LAN IDs, names, VLAN values, DSL circuit details and feature text are omitted.
`omada_site_template_iptv_settings_summary` returns the CBC template's IGMP and IPTV summaries from the combined IPTV service GET. It uses one controller request and the same reference-bound inventory; raw port IDs and VLAN settings are omitted.
`omada_site_iptv_summary` reads IPTV mode and summarizes LAN port types; it omits WAN/LAN IDs, port names, VLAN values, DSL circuit values and feature-description text.

This is an MCP interface to registered connector reads. It does not make undocumented API operations executable, and it does not expose write previews/applies, scan starts or arbitrary controller requests. The AP workflow reads the controller's existing RF scan result; it never starts a measurement.

`omada_site_switch_health_history` uses the fresh switch inventory and the documented batch timeline read for one fixed 24-hour window, bounded to 64 switches. MAC rows are mapped back to opaque site-bound switch references; missing rows, invalid fields and switches beyond the limit are marked partial. Scores retain the documented int32 values; their scale is unspecified and is not interpreted. Live controller support remains unverified.

## Local request example

Use the read-only Compose example and a locally mounted caller-token file. The Compose host binding is `127.0.0.1:18080`; the container listens on port `8080`. A direct host-process run uses its configured `LISTEN_PORT` (default `8080`). Do not put a real token in shell history or a client config committed to a repository.

```sh
curl --silent --show-error http://127.0.0.1:18080/mcp \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <caller-token>' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"local-check","version":"0"}}}'
```

For discovery, send `tools/list`; for use, send `tools/call` with the exact advertised tool name and arguments. The local `tools/setup_check.py` command validates an authenticated initialize response, all paged tool-list responses, the advertised read-only hint for `omada_sites`, one safe site-inventory call, and the expected `tool_unknown` JSON-RPC error. It reports counts and protocol status only. This is a connector-side protocol check and does not prove compatibility with a specific agent application; see [client evidence](INTEGRATIONS.md).

## Agent connection settings

All three configurations below use the Compose host binding on the same
machine. Replace the URL with a secured private address only when the service
runs on another host; the loopback URL cannot be reached remotely.

### Hermes

In `~/.hermes/config.yaml`, add:

```yaml
mcp_servers:
  omada:
    url: "http://127.0.0.1:18080/mcp"
    headers:
      Authorization: "Bearer ${OMADA_CONNECTOR_TOKEN}"
```

Keep `OMADA_CONNECTOR_TOKEN` in Hermes' local `~/.hermes/.env`; Hermes
resolves environment placeholders in HTTP headers when connecting.

### Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.omada]
url = "http://127.0.0.1:18080/mcp"
bearer_token_env_var = "OMADA_CONNECTOR_TOKEN"
```

Set that environment variable in the environment that launches Codex. Codex
uses the variable name to read the token when it connects.

### Claude Code

Register the local server at user scope:

```sh
claude mcp add --scope user --transport http omada \
  http://127.0.0.1:18080/mcp
```

Then set `headersHelper` for the `omada` server in the user-level Claude MCP
configuration to an executable local helper. The helper must print a JSON
object containing the `Authorization` header and read its value from a local
credential store. This avoids putting the token in the project or shell
history. Claude Code runs this helper when it connects.

The user-level server entry has this shape:

```json
{
  "mcpServers": {
    "omada": {
      "type": "http",
      "url": "http://127.0.0.1:18080/mcp",
      "headersHelper": "/absolute/path/to/omada-mcp-headers"
    }
  }
}
```

These settings prepare the connection; they do not establish client
compatibility. Codex completed a separate end-to-end handshake and three tool
calls in a temporary loopback-only setup; Hermes and Claude Code remain
untested. Local protocol and HTTP tests use a fake controller client to verify
JSON-RPC handling, bearer authentication, direct WLAN reads, bundled workflows,
topology dispatch and Origin rejection. They do not launch an agent runtime.
The connector does not manage agent credentials.

Manufacturer setup references: [Hermes MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp), [Codex MCP](https://developers.openai.com/codex/mcp), [Claude Code MCP](https://code.claude.com/docs/en/mcp).

The setup snippets use the Compose host binding `127.0.0.1:18080` (container
port `8080`). On 2026-11-13, the connector's focused local regressions passed:
18 MCP tests and 65 HTTP tests. These fixture checks use a fake controller and
are separate from the Codex client run described in [client evidence](INTEGRATIONS.md).

## Security and limits

The route reuses the HTTP API's bearer authentication and read projections. It accepts absent Origin headers for non-browser clients and local HTTP(S) Origins only; browser Origins outside localhost are rejected. The endpoint has no separate MCP session state. Clients that require server-sent event streaming or session affinity are not covered. Tool listing and calls are constrained to the registered GET operations, the declared read workflows plus the explicit cable-test plan operations; the latter are the only MCP actions that can start or cancel a diagnostic and require the normal signed approval flow.

## Token measurement

The bounded `omada_wifi_diagnose_site` workflow combines the same four projected results as individual calls. On the checked-in fixture payloads, a paired serialization used `js-tiktoken` 1.0.21 with the `gpt-4o` / `o200k_base` encoding:

| Exchange | Calls | Request JSON | Full MCP response JSON | Total |
| --- | ---: | ---: | ---: | ---: |
| Four individual WLAN reads | 4 | 152 tokens | 1,741 tokens | 1,893 tokens |
| Bundled WLAN diagnosis | 1 | 40 tokens | 1,597 tokens | 1,637 tokens |

That is 256 fewer tokens (13.52%) across the serialized JSON-RPC requests and responses for this fixture. Counting only serialized tool-call requests plus the text content passed to a model gives 941 versus 811 tokens, a 130-token (13.81%) reduction. The four result text blocks alone are 789 tokens versus 771 for the bundle. The full-response count includes both `content` and the matching `structuredContent`, as this MCP endpoint currently returns both for backwards compatibility.

These are exact tokenizer counts for the compared payloads, not measured billed usage from a model or an agent client. They exclude system prompts, tool schemas, host framing, reasoning and any client-specific conversion of `structuredContent`. Hermes, Codex and Claude remain untested; their end-to-end token effect must be measured in those runtimes.

After adding stored Wireless IDS events to the site WLAN diagnostic, the checked-in empty-event fixture measured eleven individual GET path/response objects at 1,516 tokens and the bundled CLI request/report at 1,280 tokens with the same tokenizer (236 fewer; 15.57%). Without the WIDS endpoint, those objects measured 1,407 and 1,192 tokens. The WIDS summary contributed 109 tokens to the separate reads and 88 to the bundle. This CLI fixture comparison does not include MCP framing or establish live or billed agent usage.

After adding the dynamic WIDS blacklist summary, the same checked-in empty-event fixture measured twelve individual GET path/response objects at 1,594 tokens and the bundled CLI request/report at 1,337 (257 fewer; 16.12%). Without the blacklist read, the values were 1,516 and 1,280. This new result adds 78 tokens to separate calls and 57 to the bundle. Counts use js-tiktoken 1.0.21 / o200k_base; this is fixture serialization, not live data, MCP framing or billed usage.

For `omada_ssid_network_summary`, a separate fixture with one site, four SSIDs,
two networks and four configuration reads was tokenized with the same
`o200k_base` encoding. The seven constituent JSON results used 527 tokens; the
single summary result used 69 tokens, a reduction of 458 tokens (86.9%). This
counts serialized result JSON only, not the MCP request, schemas, prompts,
host framing or billed usage. It is a fixture measurement, not a live-network
measurement.

For the client-roaming workflow, a synthetic 128-event comparison counted four individual GET method/path/response objects at 2,407 tokens and the MCP tool request plus compact timeline summaries at 371 tokens (2,036 fewer, 84.59%). Event-type codes are preserved as numeric codes without interpretation. This fixture serialization excludes inventory, schemas, prompts, host framing and billed usage.

After adding site-level band-steering, RRM and roaming context, a separate
fixture comparison counted nine individual GET method/path/response objects
at 1,283 tokens and one MCP tool request plus projected report at 1,095 tokens
with the same tokenizer and encoding (188 fewer, 14.65%). This comparison
counts serialized HTTP fixture objects, not full JSON-RPC frames; inventory,
schemas, prompts, host framing and model billing are excluded. The older table
above is retained as its historical four-result comparison.

The AP workflow was measured against nine separate fixed HTTP GET request/response
pairs before nearby WLAN measurements were added, and ten pairs afterward.
Using js-tiktoken 1.0.21 with `o200k_base` and the same local fixture responses,
the HTTP payloads used 1,660 tokens before and 1,770 after. One MCP tool request
plus its returned diagnostic text used 1,391 tokens after the addition, saving
379 tokens (21.41%) against the ten individual HTTP payloads. The diagnostic
text grew from 1,305 to 1,361 tokens (56 more) to include the neighbor summary.
These are fixture serialization counts, not billed usage or measurements from a
live agent client. The comparison excludes tool schemas, host framing and prompts.
The full MCP JSON-RPC response duplicates data in `content` and
`structuredContent`; clients forwarding both may spend more tokens.

Before adding the wired-downlink component, the saved AP speed-test result was compared by serializing
each GET as a method/path request plus projected response, and the bundle as the
tool name/arguments plus report. With `js-tiktoken` 1.0.21 / `o200k_base`, eleven
separate site/AP exchanges used 1,898 tokens and the bundle used 1,452, saving
446 (23.50%). Under this serialization, the same ten-read fixtures use 1,770
and 1,393 tokens, respectively; the new exchange adds 128 tokens and the report
adds 59. This format excludes HTTP headers and the MCP JSON-RPC envelope, so its
bundle count differs slightly from the earlier actual MCP content-text count.
These are local projected fixtures, not connected-agent or billed-usage results.

Before the LAN-status route was added, the gateway network workflow had one projected WAN row and one health score. Four separate GET method/path requests plus their responses used 315 tokens; the bundled tool name/arguments plus report used 172 (143 fewer, 45.40%) with the same `o200k_base` tokenizer. The comparison excludes HTTP
headers, tool schemas and the MCP JSON-RPC envelope, and is only fixture evidence.

With current-inventory validation added to the gateway workflow, ten separate
diagnostic GET method/path/response fixtures used 831 tokens and the bundled
`omada_network_diagnose_gateway` request/report used 456 tokens (375 fewer,
45.13%) with js-tiktoken 1.0.21 / `o200k_base`. The two internal inventory
reads are required for reference validation and are not separate agent-tool
rounds. This remains a fixture serialization count, not billed usage.

After adding nearby-WLAN environment summaries, the AP comparison workflow was
measured against two separate `omada_wifi_diagnose_ap` request/reports using
js-tiktoken 1.0.21 / `o200k_base`. The two serialized diagnostics used 4,310
tokens; one `omada_wifi_compare_aps` request/report used 952 tokens, 3,358
fewer (77.91%). This fixture serialization comparison excludes schemas, host
framing, prompts and billed usage; it is not a live-agent measurement.


With the wired-downlink read included, a refreshed fixture run serialized twelve individual diagnostic GET method/path and response objects at 1,993 tokens. The bundled tool request plus report used 1,509 tokens, saving 484 (24.28%). Counts used js-tiktoken 1.0.21 / `o200k_base`. The scope excludes inventory calls, tool schemas, prompts, transport framing and billed agent usage.

After adding the redacted wired-uplink read to the AP workflow, thirteen site/AP GET method/path/response objects used 2,161 tokens; the bundled `omada_wifi_diagnose_ap` request and report used 1,613, saving 548 tokens (25.36%). Measured with js-tiktoken 1.0.21 / `o200k_base` over the local fixtures. Site and device inventory reads, schemas, prompts, HTTP headers, MCP framing and billed agent usage are excluded; this is not a live agent measurement.


After adding the redacted gateway LAN-status read, a refreshed fixture run serialized five separate GET method/path requests and responses at 392 tokens. The bundled tool request plus report used 211 tokens, saving 181 (46.17%) with js-tiktoken 1.0.21 / `o200k_base`. This excludes inventory calls, schemas, prompts, transport framing and billed agent usage.


The gateway network diagnostic now includes the documented gateway port inventory. A refreshed fixture serialization of six GET request/path and response objects used 475 tokens; the bundled tool request plus report used 246, saving 229 (48.21%) with js-tiktoken 1.0.21 / `o200k_base`. Port names are removed; only integer port and type codes are retained. The measurement excludes schemas, inventory calls, prompts, framing and billed agent usage.


`omada_gateway_dhcp_leases` reads the documented paged lease list for one inventoried gateway. It returns opaque lease references, device/client and dynamic/static classifications, and aggregate counts; it omits addresses, names, network IDs and lease-time strings. It is a fixed GET and may return a bounded multi-page result; the tool does not accept caller-supplied controller paths or page values.


`omada_gateway_internet_info` reads the documented gateway internet metadata through a fixed GET. It returns WAN support flags and raw online-detection codes aggregated by count; it omits gateway and port IDs, WAN settings, network names and address-bearing configuration. Status codes remain undocumented raw values and are not labeled online/offline. The workflow reads stored metadata only and starts no probe or test.

`omada_gateway_health` and `omada_gateway_health_timeline` expose the existing redacted gateway health projections as individual fixed GET tools. Both require `site_ref` and `gateway_ref`, read a fixed 24-hour window, and do not accept caller-supplied times or controller paths. Fixture-backed HTTP and MCP dispatch tests cover each tool; live MCP dispatch has not been tested.

`omada_gateway_wan_health` reads the existing bounded, redacted WAN detail projection for an inventoried gateway through one fixed GET. It returns up to 32 port measurements with raw documented codes; labels and address-bearing fields are omitted. Fixture-backed HTTP and MCP dispatch are tested; live MCP dispatch has not been tested.

`omada_gateway_wan_status` reads the existing whitelisted WAN port and link values for one inventoried gateway. It uses a fixed GET and returns at most 64 rows without assigning undocumented meanings to raw values. Fixture-backed HTTP and MCP dispatch are tested; no live MCP request was made.

`omada_gateway_wan_incident_window` accepts an inventoried `site_ref`, `gateway_ref`, and UTC epoch-millisecond `start_ms`/`end_ms` covering at most 24 hours. One call reads current WAN status codes, the same-window gateway health details and score timeline, and saved speed-test results. It summarizes timestamped health values, keeps undocumented codes undecoded, places current values in a separate section, and marks incident counts and speed tests without a documented time unit as undated. The load-balancing status response has no documented result fields, so participation remains `unknown`; the workflow makes no failover or cause claim. Fixture-backed HTTP and MCP dispatch and the source-reader composition have local tests; no controller request or live MCP request was made.

`omada_gateway_ipv6_ip_passthrough` reads only the documented enable Boolean for an inventoried gateway. It uses a fixed GET and does not include address-bearing configuration or call the separate PATCH change path. The HTTP and MCP dispatch are fixture-tested; no live MCP request was made.

`omada_ap_wired_uplink` exposes the existing redacted AP wired-uplink read as an individual fixed GET tool. It requires the site's opaque AP reference and uses the same bounded projection as HTTP, including partial-result reporting and removal of controller identifiers. Fixture-backed MCP dispatch has been tested; no live MCP request was made.

`omada_ap_lan_traffic` reads the eight documented AP packet and byte counters through its fixed GET. The AP must be referenced through the selected site's inventory; counter validation and redaction match the HTTP projection. Fixture-backed HTTP and MCP dispatch are tested, with no live request.


With WAN capability metadata added, a fixture tokenization of the eight gateway diagnostic GET method/path/response objects used 683 tokens, versus 366 for the bundled tool request/report (317 fewer, 46.41%). The comparison uses js-tiktoken 1.0.21 / `o200k_base`; it excludes inventory reads, tool schemas, prompts, host framing and billed agent usage.

The client workflow's eleven diagnostic reads (four site WLAN reads and seven client reads) used 1,584 tokens as individual method/path/response objects. The bundled tool request and report used 1,419 tokens, saving 165 (10.42%) with js-tiktoken 1.0.21 / `o200k_base`. The inventory lookups, tool schemas, prompts, transport framing and billed agent usage are excluded. This is a local fixture serialization count, not an agent-runtime measurement.

`omada_ap_afc_status` reads the AP's reported AFC operating state through its fixed GET. It returns only documented status fields and does not change AFC configuration. Fixture-backed HTTP and MCP dispatch are tested; no live request was made.

`omada_ap_mesh_statistics` reads a redacted mesh-link summary for an AP from the selected site inventory. It omits controller identities, labels, addresses and free text. The fixed HTTP request, projection and MCP dispatch have fixture coverage; no live request was made.

The fixed AP configuration reads `omada_ap_channel_limit`, `omada_ap_ofdma`, `omada_ap_qos`, `omada_ap_lag`, `omada_ap_load_balance`, `omada_ap_antenna`, `omada_ap_antenna_gain`, `omada_ap_power_saving` and `omada_ap_vlan` are available as separate tools. Each requires a current site-bound AP reference and uses the same validation and redaction as its HTTP route; GET access does not apply the corresponding setting. Fixture-backed MCP and HTTP dispatch have been tested; no live request was made.

Site-level status tools are also available for WLAN band steering, RRM mode, roaming, LED, LLDP and application control, plus gateway VoIP prioritization and outbound-tag QoS. They expose only their existing GET reads; the separate PATCH/PUT paths are not available through these tools. Fixture-backed HTTP and MCP dispatch are tested for each.

The twenty-three switch tools `omada_switch_ports`, `omada_switch_port_counters`, `omada_switch_port_poe_info`, `omada_switch_vlans`, `omada_switch_lldp_neighbors`, `omada_switch_health`, `omada_switch_health_timeline`, `omada_switch_sdm_usage`, `omada_switch_cable_test_logs`, `omada_switch_cable_test_full_results`, `omada_switch_cable_test_increment_results`, `omada_switch_cable_test_ports`, `omada_switch_dhcp_users`, `omada_switch_ospf_neighbors`, `omada_switch_port_networks`, `omada_switch_exist_networks`, `omada_switch_networks`, `omada_switch_interfaces`, `omada_switch_routing_table`, `omada_switch_static_routes`, `omada_switch_vrfs`, `omada_switch_vlan_interfaces` and `omada_switch_statistics` accept a site-bound `switch_ref`. They reuse the HTTP routes and redacted, bounded projections; switch-wide paginated feeds are filtered to the uniquely inventoried switch. DHCP output includes only opaque lease references and type/binding counts; OSPF output includes raw state counts; port-network output summarizes VLAN counts without names or network IDs; configured-network output summarizes VLAN and VLAN type counts plus documented support flags, omitting network names, IDs, IP settings and DHCP details; the paginated switch-network reader returns VLAN, status-code and DHCP-mode counts only. The interface reader aggregates the documented loopback/VLAN type codes and omits interface names and identifiers. The routing-table reader returns bounded type, distance and metric counts and omits destinations, next hops, VRFs and interface names. The static-route reader counts status, IP version, distance, resource and destination cardinality while omitting addresses, route names, descriptions and VRF identifiers. The VRF reader counts IPv4/IPv6 enablement, defaults and documented resource codes without returning VRF names or IDs; its pagination differences are handled by the documented no-parameter request and a bounded fallback, with live behavior still unverified. The VLAN-interface reader returns total and unique VLAN-interface counts only; names and IDs are omitted. The statistics reader aggregates documented device state, port link/type and PoE/STP codes and byte totals while omitting port labels, uplink identity and M-LAG identifiers. Cable-test reads inspect stored data and eligibility only; they never start a test. Fixture-backed MCP and HTTP dispatch are tested individually.

Eight individual client tools are available for connection history, client history, health, health timeline and the four fixed connection/association/roaming/disconnect timelines. Every call requires an opaque client reference from a fresh inventory for the same site; the API requests use fixed time windows and redacted projections. Fixture-backed HTTP/MCP dispatch is tested individually, with no live client data read.


`omada_site_switch_support` reads the two documented site-level switch-family support flags through a fixed GET. It requires a known `site_ref`, returns strict booleans with partial-response counts, and does not infer hardware or firmware support. Fixture-backed HTTP and MCP dispatch are tested; live support remains unknown.

`omada_site_switch_port_anomaly_summary` combines the fresh device inventory with the current site-wide switch port overview and cumulative counter feeds for up to 32 switches. It returns opaque references and raw port status codes without decoding controller-specific meanings. Nonzero TX/RX error counters are review signals. Hardware Controller, CBC Standard and ER7212PC define the same `portStatus`, `txErrors` and `rxErrors` fields; `txErrors` and `rxErrors` are documented int64 totals, and port status codes remain uninterpreted by this summary. Live controller support remains unknown. Drop counts are not available in the documented per-port counter response. It does not infer rates, trends or fault causes; missing data and incomplete coverage are explicit.


`omada_network_dhcp_server_capabilities` reads the documented DHCP server
capability flags for a network reference returned by the selected site's
network inventory. It exposes only the two strict support booleans and partial
response counts. HTTP and MCP dispatch, site/network binding and the upstream
path are fixture-tested. Live support has not been checked.


`omada_network_dhcp_server_info` reports only the aggregate number of available
addresses and bounded DHCP range counts for a network returned by the selected
site's inventory. It omits range addresses. The route is a fixed GET; HTTP/MCP
dispatch and reference binding are fixture-tested, while live support remains
unknown.

`omada_site_dhcp_pool_utilization` bundles the documented DHCP server-info
read for up to 64 inventory networks with the complete, fixed-page site DHCP
user list. It reports validated IPv4 pool capacity and available-address
counts, plus dynamic/static binding counts keyed by opaque network references.
It omits pool boundaries, network names, addresses and hardware identifiers.
The source does not associate leases with configured pool ranges, so lease
counts are not used to estimate pool occupancy. Missing, overlapping,
inconsistent or unclassified data remains partial or unknown. The route is a
read-only HTTP/MCP workflow; fixture dispatch and projection are tested, while
live support remains unknown.

`GET /v1/sites/{site_ref}/aps/quality-window` and
`omada_site_ap_quality_window` compare up to 32 inventoried APs using one shared
24-hour window for health-score history and the bounded site retry/drop lists,
plus current radio settings by band. The sources do not provide retry/drop
band mapping; their numeric scale and the health-score scale remain unspecified.
An AP absent from the dashboard list is marked `not_listed`, not zero. Radio
configuration is current state, not historical state. The report is read-only
and does not start a scan. Fixture-backed HTTP/MCP dispatch and AP reference
binding are tested; live support is unknown.

A synthetic eight-AP fixture with 24 hourly health, retry and drop samples per
AP used 11,527 `o200k_base` tokens for the serialized source responses and
10,196 tokens for the bundled report (1,331 fewer; 11.55%). Counts use
`js-tiktoken` 1.0.21. This payload comparison excludes request/tool schemas,
MCP framing and billed agent usage; it is not a live-agent measurement.

`GET /v1/sites/{site_ref}/firmware-summary` and the read-only
`omada_site_firmware_summary` tool group the selected site's inventory with no
more than 64 documented firmware-info reads. Groups include device type, model,
inventory version, current version, and source-labeled latest version. Exact
matches and differences are shown without ordering version strings or claiming
that a safe update is available. Missing versions, conflicting inventory data,
read failures and excess devices remain partial. Fixture-backed HTTP/MCP
dispatch is tested; no live firmware query or upgrade was made.

A synthetic 40-device site with repeated models measured 3,871 tokens for the
inventory and individual firmware responses versus 725 for the grouped report
(3,146 fewer; 81.27%), using `js-tiktoken` 1.0.21 / `o200k_base`. This is a
serialized-payload comparison only, not billed agent usage or live data.
`omada_msp_device_link_topology` is documented by CBC Standard with
`Site Settings Manager View Only` or `MSP Device Manager View Only`. The
connector resolves the selected site and device from inventory and returns
bounded topology counts without device names, MAC addresses or IP addresses.
Live support remains unknown.
`omada_msp_device_tags` is CBC-only. It returns tag and identifier-presence
counts without tag names or IDs. Live support remains unknown.
`omada_msp_mfa_status` is CBC-only and reports the documented MFA-enabled
switch with `MSP Other Settings View Only`. Live support remains unknown.
`omada_msp_license_auto_active` is CBC-only and reports the documented
license auto-activation switch with `MSP License Manager View Only`. Live
support remains unknown.
`omada_msp_customer_roles` is CBC-only and reports role type, source, default
and permission-presence counts without role names, IDs or permission entries.
It requires `MSP Roles Manager View Only`. Live support remains unknown.

`omada_site_switch_qos_scheduler_summary` and
`omada_site_switch_qos_dscp_summary` expose bounded switch QoS configuration
counts. They omit scheduler IDs/names and raw queue/DSCP values. Hardware
Controller and CBC define the response schemas; ER7212PC leaves both GET
responses generic. Live support remains unknown.


`omada_controller_client_recognition` reads the documented controller-wide
client-recognition flag as one strict Boolean. It is a fixed GET with no caller
arguments. Fixture-backed projection and HTTP/MCP dispatch tests pass; live
support remains unknown.


`omada_controller_device_statistics` reads aggregate controller-wide device,
activation and health counters. In addition to scalar totals, it projects the
documented `switchHealth`, `eapHealth` and `gatewayHealth` objects as bounded
`good`, `fair`, `poor` and `noData` counts under `health_counts`. Missing or
invalid nested counts are omitted and keep the result partial. The flat
`allSwitchsAndGateway` scalar remains a separate combined count. Unknown fields
are counted without exposing their names or values. The tool takes no
arguments and uses a fixed GET. Fixture coverage is local; live support
remains unknown.


`omada_controller_client_active_timeout` returns the documented client
active-timeout value as a validated int32. It does not change the setting and
accepts no caller arguments. The supplied description says 3–10 minutes, while
the ER7212PC example uses `0`; the connector therefore preserves the raw valid
int32. Fixture coverage exists, with live support still unknown.

`omada_controller_client_history_retention` reads the documented client-history
and trend-retention Boolean flags. It is a fixed GET and reports incomplete or
extra fields as partial.

`omada_controller_audit_notification` summarizes global audit-log webhook
enablement and aggregate category counts. It omits webhook IDs, category keys
and display labels and accepts no caller arguments.

`omada_controller_retention` reads bounded controller-wide retention flags,
values and available-day lists. It is a fixed GET and does not change data
retention; fixture coverage exists, with live support still unknown.

`omada_controller_dst_info` reads daylight-saving status, documented mode and
offset codes, schedule rules, timestamps and time zone. It is a fixed GET;
timestamps remain raw milliseconds and no local-time conversion is inferred.
Fixture coverage exists, with live support still unknown.

`omada_site_dst_info` reads the separate site-scoped DST response after resolving
the selected site reference from the current inventory. It reuses the bounded
DST validation. `startTime` and `endTime` are returned as raw integers under
`timestamps_unit_unspecified`, because the site schemas do not state their
unit; the documented next/last transition times remain under `timestamps_ms`.
It makes no claim about inheritance from controller settings. It is read-only;
live support is unknown.

`omada_controller_experience_improvement` reads the documented controller
experience-improvement participation Boolean through a fixed GET. It does not
change the preference; fixture coverage exists, with live support still unknown.

`omada_controller_client_detail_info` reads five documented client-data setting
flags through a fixed GET. It returns no client records and changes no setting;
fixture coverage exists, with live support still unknown.

`omada_controller_general_settings` reads the bounded controller name, locale
strings and validated DST settings. It is a fixed GET; fixture coverage exists,
with live support still unknown.

`omada_controller_device_access` reads the three documented controller-wide
device-access switches (`webControlHttp`, `webControlHttps` and `appDiscovery`)
as booleans. Unknown, missing or invalid fields are excluded and mark the
result partial. The read is available in all three supplied API exports under
the Global Other Setting View Only permission. It does not expose the separate
PATCH operation; fixture coverage is local and live support remains unknown.

`omada_controller_backup_schedule` returns whether a schedule is enabled,
bounded retention and storage-type facts, and configuration counts. It omits
file paths, available path values, file-server addresses and credentials. The
documented read requires `Global Other Setting Modify`; live support remains
unknown.

`omada_controller_cloud_access` returns enablement and the documented
connected/disconnected/disabled state. It reports only whether an owner value
exists and never returns the owner string. Live support remains unknown.

`omada_controller_device_management` reads the three documented HTTP, HTTPS
and app-discovery switches through the separate global `device-mgmt` GET. It
uses the same bounded Boolean projection as controller device access; live
support remains unknown.

`omada_controller_remote_binding` reports only whether remote binding is
enabled. `omada_controller_backup_result` and
`omada_controller_restore_result` report the source-defined task state; they do
not start, stop or restore anything. Live support remains unknown.

`omada_controller_privacy_policy` returns only the policy enabled Boolean. The
ER7212PC schema defines status values 0 and 1; Hardware Controller and CBC list
the GET but omit its response schema. Values outside that documented pair are
omitted and counted as invalid. Live support remains unknown.

`omada_controller_mail_status` reports only SSL/authentication switches and
whether documented mail configuration fields are set. It never returns email
addresses, the SMTP server or port, user name, server ID or authorization code.
The three source exports list the same GET and permit one of the documented
view permissions. Live support remains unknown.

`omada_controller_global_mfa_status` uses the documented fixed GET and the
`Global Other Setting View Only` permission. The source exports leave the result
object unspecified, so the projector recognizes a Boolean `enable` only and
counts unknown fields without returning them. No controller response has been
checked; live support remains unknown.

`omada_msp_cloud_access_status` accepts a caller-supplied `msp_ref` limited to
letters, digits, underscores and hyphens. It returns enablement, connection
state and owner presence only; the CBC and ER7212PC exports document this GET.
`omada_msp_privacy_policy` uses the same bounded reference and reports only the
enabled switch; CBC Standard alone documents that GET. Both remain live-unknown.
`omada_msp_client_detail_info` accepts the same bounded reference and returns
only the three documented client health/history/trend switches. CBC Standard
and ER7212PC document the read with the `MSP Other Settings View Only`
permission; Hardware Controller does not. Live support remains unknown.
`omada_msp_dst_info` uses the same bounded identifier and returns the CBC
documented DST settings and status through the existing bounded DST projector;
Hardware Controller and ER7212PC do not list this MSP GET. Live support remains
unknown.
`omada_msp_remote_logging` is CBC-only and returns its enabled state plus host
and port presence flags; the configured destination and port values are never
returned. Live support remains unknown.
`omada_msp_mail_server` is CBC-only. It reports whether the server, port,
transport, authentication and documented account fields are configured, but
never returns the SMTP target, port value, address or credential.
`omada_msp_general_settings` is CBC-only. It returns timezone and DST settings
through bounded projections, plus a name-presence flag without revealing the
MSP's configured display name. Live support remains unknown.
`omada_msp_log_notification_settings` is CBC-only. It returns bounded counts
for enabled alert, event, email and webhook notification types, plus switches
for webhook and alert-email settings. Event keys, messages and webhook IDs are
omitted.
`omada_msp_data_retention` is CBC-only and uses the same bounded retention
projection as controller settings. It exposes only documented retention
switches and values, not client records.
`omada_msp_ui_interface` and `omada_msp_user_interface` are the two CBC
documented UI preference reads. They return display and refresh codes plus
Boolean settings, while reducing private-label URL, file ID and filename to
presence flags.
`omada_msp_available_roles` and `omada_msp_available_customer_roles` summarize
the two CBC role catalogs by documented role type, source and default status;
custom role names and IDs are not returned.
`omada_msp_dashboard_overall` is a CBC-only aggregate read. It returns total,
wired, wireless and guest client counts, and rejects malformed numeric values;
it does not return individual client records. Live support remains unknown.
`omada_msp_cluster_nodes` is CBC-only and aggregates bounded node count and
managed-site/device counts. Node names, identifiers, roles, status values and
timestamps are not returned. Live support remains unknown.
`omada_msp_adopt_tip` is CBC-only. It reports only the documented adopted and
recommended device counts and does not issue adoption requests. Live support
remains unknown.
`omada_msp_audit_notification` is documented by CBC Standard alone with
`MSP Log Manager View Only`. It returns category counts and enablement flags;
notification labels and webhook identifiers are omitted. Live support remains
unknown.
`omada_msp_role_summary` is a CBC-only role inventory summary. It returns role
and default totals plus counts by documented privilege level; role names, IDs
and raw privilege values are omitted. Live support remains unknown.

`omada_site_switch_qos_mode` reads the documented switch QoS mode and reports
only the bounded mode and transition-complete state. The ER7212PC export lists
the GET but leaves its response generic; Hardware Controller and CBC provide
the two-field schema. No mode changes are performed and live support remains
unknown.

`omada_controller_remote_logging` returns the required enabled Boolean and
validated presence flags for the optional host and port. It never returns the
remote destination or port value. Missing, invalid or unknown fields mark the
response partial. The fixed GET appears in all three supplied exports and
requires `Global Other Setting View Only`; the setting's PATCH is not exposed.
The separate `omada_controller_remote_logging_tip` tool reads the documented
`syslog/tip` route through the same redacted projection. Fixture coverage is
local; live support remains unknown.

`omada_controller_remote_logging_tip` is a fixed read for the distinct
`getRemoteLoggingTip` operation. It returns the enabled state and only
validated presence flags for its host and port, never the target values. Its
schema and read permission match the remote-logging GET in all three exports.
Fixture coverage is local and live support remains unknown.

`omada_controller_radius_proxy` reads the controller-wide proxy status, port
and policy flags. Startup failure text is never returned.
`omada_controller_radius_server` reads the built-in RADIUS server status and
bounded settings; the shared secret, custom address, failure text and
certificate identifiers, names and password are omitted. Both fixed GETs are
documented for Hardware Controller 6.3.0 and ER7212PC 6.2.14, but not CBC.
Fixture checks are local; live support and Hermes, Codex or Claude client
interoperability remain unverified.

`omada_controller_radius_proxy_change` offers `preview` and `apply`. Preview
accepts only documented setting fields and returns the exact short-lived
approval request. Apply requires that request's signed approval, enabled
writes and the durable change journal; it checks current state, sends one
PATCH and verifies a readback. Optional flags omitted by the controller are
left out of the PATCH. This change can interrupt RADIUS authentication. The
Hardware Controller and ER7212PC exports document the route; CBC documents a
different MSP-scoped operation. No live PATCH or agent-client interoperability
test has been performed.

`omada_switch_cable_test` accepts only `preview`, `status`, `cancel_preview`, `apply` and `cancel_apply`. Preview is limited to one inventory-bound port and returns the exact approval request. Apply requires the complete short-lived signed approval object; cancellation requires its own preview and approval. Status returns redacted correlated results or an explicit unknown state. The tool does not retry a start. This flow has offline fixture coverage only. Hermes, Codex and Claude MCP clients have not been exercised end to end, and live controller support remains unconfirmed.


The cable-test lifecycle was counted with `js-tiktoken` 1.0.21 / `o200k_base` over local fixture JSON-RPC requests and full responses. Three separate cable-test GET tool calls used 339 tokens; a preview, approved start and status poll used 718 tokens, 379 more (111.80%). The active lifecycle is not token-saving: the additional payload represents the preview and exact operator approval. Schemas, inventories, prompts, transport framing and billed agent usage are excluded. This comparison is fixture serialization, not a measurement from Hermes, Codex or Claude.

`omada_msp_ap_health_detail`, `omada_msp_gateway_health_detail` and `omada_msp_switch_health_detail` return the redacted 24-hour health summaries for inventoried APs, gateways and switches. The corresponding `omada_msp_ap_health_timeline`, `omada_msp_gateway_health_timeline` and `omada_msp_switch_health_timeline` read their score histories. Each reuses the matching bounded score projection and requires caller-supplied MSP/customer path references plus site-bound device references. Names, addresses and unrelated upstream fields are omitted; live support remains unknown.

`omada_olt_detail_summary` returns site-inventory-bound status codes, CPU/memory percentages, uptime, ONU count, traffic totals, model and downlink count. `omada_olt_ports_summary` returns Ethernet and PON counts, link/admin/media/speed aggregates, and ONU totals; port labels, descriptions, LAGs, ONU rows and identities are omitted. Both omit device/site identifiers from projected data; the detail summary also removes addresses, serial and license values, location and raw port data. Firmware strings are represented only by presence flags. `omada_olt_system_info` returns uptime and OLT configuration flags without identity, contact or time strings. `omada_olt_system_info_msp` uses the documented MSP/customer/site/device route and the same redacted system projection. `omada_olt_management_interfaces` returns bounded interface and type counts only. These tools use view-only upstream GETs; interface values are omitted. Fixture tests cover dispatch and projection; controller support is not live-verified.

`omada_olt_onu_global_status` returns ONU isolation enablement and support flags. `omada_olt_onu_isolation_status` returns isolation and VLAN-scope flags plus whether a VLAN list is configured; VLAN IDs and ranges are omitted. The original exports document both reads and the `Site Device Manager View Only` permission. Live support remains unknown.

`omada_controller_roles_summary` and `omada_controller_available_roles_summary` return bounded role totals by documented type/source. Role IDs and names are omitted; the full role summary also omits permission labels and returns only permission-code counts. Both require the documented view-only role-management permission. The routes have fixture coverage only; controller support remains unknown.


## Controller-wide device summaries

The MCP tools `omada_controller_known_devices` and
`omada_controller_unknown_devices` provide the same bounded, redacted summaries
as the HTTP routes. They take no arguments and request only the first page using
the configured page size, capped at 200 rows. The response contains aggregate
type, status and series counts; it does not contain device identifiers,
addresses, names, models, serial numbers or raw rows. The API contract and
transport dispatch are fixture-tested offline. Live controller behavior is
still unknown.

`omada_site_ap_group_summary` reads the documented paginated AP-group list for
one site. It returns bounded group and AP counts, per-band remaining SSID
binding totals and the documented SSID limits. Group IDs, names and SSID labels
are omitted. It also returns opaque `group_ref` handles with the primary flag
and AP count so a caller can select one group for the detail read. It uses fixed
page parameters and supports no caller search or filter.

`omada_site_ap_group_assignment_summary` reads a bounded paginated AP list and
counts rows with and without a reported AP-group assignment, plus documented
SSID override totals. AP names, addresses, IDs and traffic are omitted.

`omada_site_ap_group_info_summary` takes a `site_ref` and a current `group_ref`
from the AP-group summary. It refreshes the group inventory and requires one
unique match before reading the detail. It returns the documented primary
flag, AP count and remaining SSID bindings by band. Group IDs, names and SSID
labels are omitted. Hardware/CBC document these reads; live support is unknown.

`omada_site_ap_oui_vlan_rules_summary` reads the paginated, documented AP OUI
VLAN rule list for one site. It reports only rule-state, SSID-binding,
VLAN-assignment and priority counts. Rule/profile IDs, names, SSID labels and
VLAN values are omitted. The source does not specify a permission, and live
support remains unknown. Projection, fixed paging and HTTP/MCP dispatch have
fixture coverage.


The tools `omada_controller_device_batch_adopt_summary` and
`omada_site_pending_devices_summary` expose bounded summaries for global
batch-adoptable devices and a selected site's pending devices. They take no
filter or page arguments; the site tool requires an opaque `site_ref`. Both
discard raw device rows and identities. They are fixture-tested, with no live
controller or external-agent interoperability claim.

`omada_olt_eth_config_summary` aggregates Ethernet port state, configured and negotiated speed, link state, port type and LAG membership. `omada_olt_lag_config_summary` reports bounded LAG counts and settings-state totals. Both omit port and LAG identifiers, descriptions and raw labels; the source documents `Site Device Manager View Only`. Live support remains unknown.

`omada_olt_auto_refresh_summary` returns the documented auto-refresh switch and interval value. `omada_olt_pon_information_summary` returns aggregate ONU and bandwidth totals with min/max optical measurements by metric; port identifiers and per-port data are omitted. Both use documented view-only OLT reads and leave live support unknown.

`omada_olt_onu_auto_auth_status` reports only whether ONU auto authentication is enabled. `omada_olt_onu_autofind_summary` reports the aging-time status, bounded interval and whether a PON scope is configured; the port-range string is omitted. Both are view-only reads with live support unknown.


`omada_olt_onu_reboot_status_summary` aggregates documented ONU online/reboot states. ONU keys and unknown fields are omitted; payloads above 1,000 rows are rejected. This fixed read uses the `Site Device Manager View Only` permission and remains unverified against a live controller. The inventory summary requires the caller to provide the documented `pon_port` selector; the adapter validates its GPON list/range syntax before requesting the selected OLT.

`omada_olt_onu_autofind_inventory_summary` requires a PON selector and bounded page number/size. It returns only the number of discovered ONUs on that page and warns when a page may continue. Authentication passwords, LOID credentials, serials, MAC addresses and device details are never returned. HTTP and MCP dispatch use the same validation; the controller read is not live-verified.

`omada_msp_ap_mesh_statistics` reads the selected AP through the MSP customer/site route and reuses the bounded mesh projection. Child AP and parent identities, names, addresses and uplink MACs are omitted. The MSP source contract exists in the ER7212PC and CBC Standard exports and requires `MSP Device Manager View Only`; live support remains unknown.

The MSP OLT reads expose inventory-bound OLT detail, Ethernet configuration, site-level Ethernet/PON ports and per-OLT PON configuration summaries. They reuse the existing bounded OLT projections, omit port/device identities and return only local opaque site/device references. Source coverage is ER7212PC and CBC Standard; permissions are recorded per operation in the HTTP read catalog. Live support remains unknown.


`omada_olt_pon_port_config_summary` aggregates documented PON laser, link, isolation, speed and DBA modes, plus bounded numeric setting ranges and online ONU totals. PON-port IDs and downstream-device details are omitted. This view-only GET has fixture and source-contract coverage; live controller support remains unknown.


`omada_olt_service_port_profiles_summary` reports a bounded service-port profile count, aggregate entry count and presence counts for documented usage flags. Profile names, IDs and raw flag values are omitted. The API documents `MSP Device Manager View Only` for this read; no live authorization or controller request has been verified.


`omada_olt_onu_inventory_summary` requires `site_ref`, `device_ref` and `pon_port`. It aggregates documented online, admin, configuration, template-match and active states for the selected PON ports, and reports only optical-power presence counts. ONU identities, descriptions, profiles, addresses, versions and raw optical values are omitted. Live support remains unknown.


`omada_olt_pon_port_config_page_summary` reads a caller-selected zero-based page (size 1–100) and returns checked page totals plus the same redacted PON configuration aggregates. Port IDs and downstream-device details are omitted. The required `Site Device Manager View Only` permission is documented; live support remains unknown.

`omada_site_allowed_application_summary` and `omada_site_blocked_application_summary` summarize the corresponding application dashboard pages. They accept zero-based `page_number` and `page_size` 1–100, use a fixed trailing 24-hour window, and return aggregate page counters plus whether more pages are available. App/client detail and percentages are omitted. Upstream permission is `Site Dashboard Manager View Only`; traffic units and live support are unknown.

For a synthetic 100-row page with eight nested clients per application, `js-tiktoken` 1.0.21 / `o200k_base` measured 44,819 tokens for the source response versus 107 for the projected summary (99.76% fewer). This is not billed usage or live data.

`omada_site_dashboard_all_tabs_summary` and `omada_site_dashboard_non_overall_tabs_summary` return counts for the full dashboard tab list and for tabs without the Overall tab. They cap lists, group counts by type, and omit names and IDs. The documented permission is `Site Dashboard Manager View Only`; live support is unknown.

A synthetic list of 50 tabs with 40 cards each measured 5,102 source JSON tokens versus 57 projected tokens with `js-tiktoken` 1.0.21 / `o200k_base` (98.88% fewer). This is not billed usage or live data.

`omada_site_specific_app_traffic_summary` takes an application ID from the caller and returns an identity-free traffic aggregate over a connector-fixed trailing 24-hour window. The ID is restricted to safe path characters, rows are capped at 1,000, and client/app details and percentages are omitted. The documented permission is `Site Dashboard Manager View Only`; traffic units and live support are unknown.

A synthetic 100-client response with three nested app details per row measured 23,039 source JSON tokens versus 56 projected tokens with `js-tiktoken` 1.0.21 / `o200k_base` (99.76% fewer). This is not billed usage or live data.

`omada_site_specific_client_traffic_summary` accepts only a fresh opaque site-scoped `client_ref`; the source MAC is resolved from the current client inventory and never returned. The read uses a fixed trailing 24-hour window and aggregates up to 1,000 application rows. Application/client details, names, MACs, network/VLAN labels and percentages are omitted. Upstream permission is `Site Dashboard Manager View Only`; traffic units and live support are unknown.

`omada_site_application_traffic_summary` reads the documented top ten application traffic rows over a connector-fixed trailing 24-hour window. It returns only the row count and aggregate upload, download and traffic counters; application names and IDs are omitted. Source units are bytes. The exports place the operation under `Application Control`; live support is unknown.

`omada_site_wan_lan_status_summary` returns a compact summary of gateway adoption/override flags, IPv6 support code and WAN, IPTV and named-port counts. Port IDs, names, WAN addresses/prefixes and model labels are omitted. The API contract describes configuration metadata; this summary does not establish physical link health. Live support is unknown.

`omada_site_arp_detect_status_summary` reads the documented ARP-detection and snooping flags for one site. It returns only the two booleans with partial-response counts. The source operations specify no permission value; live support remains unknown. A synthetic complete envelope measured 24 source tokens and 59 projected tokens (js-tiktoken 1.0.21 / o200k_base), so this small read adds 35 tokens on its own.

`getGridArpDetects` is documented with required `page` and `pageSize` parameters, but all three exports leave its result as a generic object and do not reference a row schema. It is not exposed over HTTP or MCP until the response contract defines fields that can be projected safely. Live support remains unknown.

`omada_site_disaster_mode_status` returns the site’s documented `status` int32 code after validation. The exports give no code meanings, so the value is not labeled as an enabled/disabled state. The source operation specifies no permission; live support remains unknown. A synthetic full envelope measured 14 source tokens versus 52 projected tokens (+38) with js-tiktoken 1.0.21 / o200k_base; this simple status read is not token-saving by itself.

`omada_site_specification_summary` returns the three documented site-supported counts: interfaces, URL-filtering entries and MAC-group addresses. Each value is validated as a non-negative int32; unknown fields are omitted and counted. The source operation specifies no permission; live support remains unknown.

`omada_controller_gateway_wan_status_summary` accepts a zero-based `page_number` (0–10000) and `page_size` (1–100) and reads one bounded page using the controller-global WAN-status endpoint. It counts physical/internet/online-detection/health states and averages latency and packet loss; rates and error-packet counters are summed. Site/device identifiers, uptime, WAN port labels, IP addresses and protocol values are omitted. The source contracts agree on operation, paging and response shape; the ER7212PC loss field uses a numeric reference. Live support remains unknown.


A synthetic 100-row client-specific response with three nested app details per row measured 20,038 source JSON tokens versus 50 projected tokens with `js-tiktoken` 1.0.21 / `o200k_base` (99.75% fewer). This is not billed usage or live data.

A synthetic page of eight gateways, each with one WAN status record, measured 1,438 source-envelope tokens versus 182 projected-response tokens with `js-tiktoken` 1.0.21 / `o200k_base` (1,256 fewer; 87.34%). This compares the fixture response JSON to the connector result JSON; it excludes MCP framing and billing, and is not a live measurement.



`omada_site_portal_logout_domain` reads the site-bound portal logout domain. The three source exports define `domain` as a string; two add a domain pattern, while one omits it and shows an empty-string example. The connector accepts any documented string, including empty, and does not infer or enforce a controller-specific pattern. Permission and live support are unspecified/unknown.

`omada_site_portal_domain_setting_state` reads the separate portal `autoRefresh` setting. It returns the strict Boolean state and whether a nonempty URL was reported only when auto-refresh is explicitly false. The URL value, host and path are never returned; the URL field is not inspected when auto-refresh is enabled or unknown. Missing and invalid values remain distinct, and unknown fields are counted only. The source requires Network Config Page View Only; live support is unknown.


`omada_site_wids_config` reads the site’s documented wireless IDS fields. It returns the enabled flag, the numeric detection level and optional detection codes. The source exports disagree about code 15, so the connector preserves int32 codes and does not enforce that enum list. Detection codes are required only when the level is Custom; permission and live support are unspecified/unknown.


`omada_site_wips_config` reads wireless IPS status, deauthentication, dynamic blocking and lock duration. `lockTime` is validated as an int32 from 300 through 36000 and is required by the source contract when dynamic blocking is enabled. The source operation specifies no permission; live support is unknown.


`omada_site_acl_config_mode` returns the validated site ACL mode code and its documented label: `0` is Through profiles and `1` is Custom. The source operation specifies no permission; live support is unknown.


`omada_site_attack_defense_summary` reads the common site attack-defense flags and thresholds. It validates documented flood-limit and large-ping ranges, and reports missing or invalid fields. `specifiedOption` is omitted because the source schemas conflict; `featureDescription` is omitted because one export lacks it. Permission and live support are unspecified/unknown.


`omada_site_alg_config` reads common application-layer gateway settings. It validates the five required ALG booleans, optional typed port lists, and SIP timeout values from 1 through 86,400 seconds. The source operation specifies no permission; live support is unknown.


`omada_site_firewall_defaults` reads the site firewall default timeout values and four documented flags. Values are range-checked, missing fields remain partial, and no unit is inferred because the source exports do not specify one. Live support is unknown.

`omada_site_firewall_settings` reads the 12 required firewall thresholds and four booleans. The thresholds are validated against the source range of 1–2,097,151; malformed, missing and unknown fields are reported. Permission and live support are unspecified/unknown.


`omada_site_bandwidth_control` reads the site control flags and summarizes configured port rates by Kbps/Mbps. Threshold values and per-port rates are range-checked. Raw `portUuid` values are never returned. The source operation specifies no permission; live support is unknown.

`omada_site_wan_ports_summary` counts WAN and USB-LTE ports and summarizes documented protocol/configuration codes and IPv6/DSL flags. It never returns port identifiers, addresses, MAC values, account names, passwords, PINs, APNs, or raw settings. Live support is unknown.

`omada_site_virtual_wan_summary` reads the bounded virtual WAN grid and available-virtual-WAN list. In all three exports, `VirtualWanInfoOpenApiVO.id` and `VirtualWanAvailableOpenApiVO.virtualWanId` are both documented as the virtual WAN ID; the summary joins only unique values and returns matched, unmatched and ambiguous counts. It omits WAN identifiers and settings. No join to physical port configuration or current WAN status is defined, so that reconciliation remains open. Live support is unknown.

`omada_site_vlan_network_summary` reads at most five fixed pages of 100 VLAN-network rows, aggregates purpose-code counts and distinct VLAN count, and omits network names, IDs and VLAN numbers. A larger listing is reported as truncated. Live support is unknown.

`omada_site_lan_network_config_summary` reads at most five fixed pages of 100 LAN-network rows and reports purpose counts plus counts for 20 shared Boolean fields. Network and device identifiers, VLANs, addresses, DHCP and portal configuration are omitted. The three API exports differ in optional row properties and nested schemas; the reader uses only fields present in all three. Live support is unknown.

`omada_site_internet_summary` reports selected Internet enablement and WAN feature flags, configured port/status counts and load-balance flags. It omits site/gateway/port/network identifiers, names, addresses, weights and credentials. Live support is unknown.

`omada_site_internet_load_balance_summary` reads the dedicated site load-balance settings route. It validates the shared feature flags and mode codes, then returns only array counts and setting-presence flags. WAN and virtual-WAN IDs, names, weight values, method text and time-range IDs are omitted. Live support is unknown.

`omada_site_internet_basic_port_summary` reports the online-detection interval and bounded port-mode/type counts. Port names and IDs and the raw gateway model number are omitted. Live support is unknown.

`omada_site_vpn_session_summary` reads at most five pages of 100 VPN sessions and returns type-code counts and traffic totals. User/VPN/interface identifiers, IP addresses, uptime and DNS values are omitted; incomplete counters are not replaced with zero. Live support is unknown.

`omada_site_dhcp_candidate_summary` counts devices returned by the DHCP-capable-device listing, with a fixed 500-row cap. Complete source rows are discarded because the exports differ substantially in DeviceVO detail. Live support is unknown.

`omada_site_network_reservation_summary` reads the bounded site-level reservation-server listing. The source documents `Site Settings Manager View Only` or `Network Config Page View Only`. It reports network/server and DHCP-setting counts plus the number of configured ranges. Names, identifiers, device details, addresses and range values are omitted; incomplete source fields remain unknown. Live support is unknown.

`omada_site_dhcp_reservation_summary` reads at most five fixed pages of DHCP reservations without search or sorting filters. It returns reservation totals and enabled/device/client counts; MACs, IPs, names, descriptions, network/server identifiers and option values are omitted. The source documents Site Settings Manager View Only, Network Config Page View Only or Site Device Manager View Only. Live support is unknown.

`omada_site_dhcp_snooping_status` reads the site's documented `dhcpSnoopEnable` flag. Other response fields are unspecified and are counted without being returned. The source documents Site Settings Manager View Only or Network Config Page View Only. Live support is unknown.

`omada_site_dhcp_snoops_summary` reads at most five fixed pages of 100 configured DHCP snooping devices. It reports device-type counts and the source status-code counts without interpreting the status codes. Device/site identifiers, names, MACs, models, stack and port/topology details are omitted. Live support is unknown.

`omada_site_snmp_settings_summary` returns the SNMPv1/v2c and SNMPv3 flags and validated security/authentication/privacy mode codes. Community strings, usernames, passwords, location and contact are never returned. Live support is unknown.

`omada_site_ddns_summary` reads up to five fixed pages of Dynamic DNS records and returns validated service-code and enabled/disabled counts plus support flags consistent across pages. Usernames, passwords, domains, update URLs, interface IDs and row identifiers are omitted. Live support is unknown.

`omada_site_mdns_rule_summary` reads at most five fixed pages of site mDNS rules and reports enabled/disabled and raw type-code counts. The type-code meaning differs between controller families, so the connector does not assign a shared meaning. Rule/profile names and IDs, VLANs and network identifiers are omitted. Live support is unknown.


`omada_site_vlan_ssid_usage_summary` takes a site reference, a network reference from that site’s inventory, and `vlan_id` (1–4094). It reports only matching SSID and WLAN-group counts. Page selection is fixed by the connector; configured identifiers and labels are omitted. This is a read-only fixture-tested operation; live support remains unknown.


`omada_site_vlan_device_usage_summary` takes a site reference, an inventory-bound network reference, and `vlan_id` (1–4094). It returns bounded counts by documented device type, stack membership, and DHCP-mode code. Names, MAC addresses, and stack IDs are omitted. Live support remains unknown.

`omada_site_vlan_port_support_summary` takes a site reference, a network reference from that site, and `vlan_id` (1–4094). The read proceeds only when the VLAN matches that network’s current inventory assignment. It returns redacted counts of ports reported as supporting, not supporting, or having unknown support for that VLAN, grouped by device type. Returned rows do not establish total network coverage; live support remains unknown.


`omada_site_wifi_calling_profiles_summary` reads one site's Wi-Fi calling profiles and returns only profile, carrier, endpoint-type, priority and source-code counts. Profile and carrier identities plus configured domains and IP addresses are omitted. It performs no scan or configuration change; live support remains unknown.


`omada_site_client_filter_options_summary` reports only counts from the selected site's client filter catalog, including whether listed devices include stack membership. Option strings, MAC addresses, names and stack names are omitted. This is a fixed read-only request; live support remains unknown.

`omada_change_journal_summary` reads status counts from the already-open, controller-bound local journal. It returns no plan identifiers, target references, before/after settings, journal records, or credentials. It does not accept a path, contact the controller, or mutate the journal. If the journal is unconfigured or unavailable, the result says so. The same summary is available at authenticated `GET /v1/change-journal/summary`. The integrity marker means the journal passed its hash-chain and schema checks when this process opened it; it does not indicate a fresh disk reread.

# Site outage context

`omada_site_outage_summary` takes a site reference and UTC epoch-millisecond bounds for a window of at most 24 hours. It combines the site overview's AP, gateway and switch reachability counters with redacted event and alert counts. The reachability snapshot includes its own observation time and is not represented as a historical measurement for the requested window. Event counts are not assigned to individual devices; the workflow does not infer an outage cause. Fixture-backed HTTP and MCP dispatch are tested; live support remains unknown.

To create a shareable local report from the HTTP JSON response, use `python3 tools/site_outage_report.py --input ./outage-summary.json --output ./outage-report.md`. It is offline, omits site/device references, requires an owner-only input and creates a new mode-`0600` report without replacing an existing file.

omada_site_reboot_schedule_summary reads a bounded site reboot schedule list. It redacts schedule names, source IDs, and device MACs, resolves targets only through the current inventory, and labels the source-unspecified timezone. The report describes configured schedules, not completed or started reboots. It uses one shared column declaration for compact schedule rows. A 12-schedule synthetic fixture measured a 41.71% reduction in serialized JSON tokens (796 to 464; js-tiktoken 1.0.21/o200k_base); this excludes inventory and agent framing.

`omada_site_stack_connections_summary` reports declared switch-stack members and redacted LLDP neighbor counts by local port. Member MACs are mapped internally to fresh switch references. LLDP `deviceId` strings are not treated as inventory identifiers, so no neighbor links are inferred. The operation is read-only; live support remains unknown.
The existing `omada_site_topology` result includes the same report under `stack_connections`; partial stack coverage marks the combined topology response partial.

`omada_site_topology_snapshot_summary` reads the documented v2 topology
snapshot. It counts nodes and edges independently, reports documented blocked
edge booleans, and counts absent or unresolved endpoint references. MACs, names,
port fields, VLAN values and device identities are omitted. The result
describes snapshot fields only and does not assert that links currently pass
traffic. Hardware Controller and CBC document the source; live behavior is
unknown.

`omada_site_gateway_qos_service_profiles_summary` reads at most 10 pages of
1,000 Gateway QoS service profiles. It counts documented default flags and
protocol categories while omitting profile names, IDs, port values and
descriptions. Unclassified codes are counted without interpretation, and a
page-limit truncation is reported as partial. The three supplied exports
document this operation; live behavior is unknown.

omada_controller_backup_inventory_summary summarizes controller-listed backup metadata, the existing activity status, and safe schedule fields. omada_site_backup_inventory_summary applies the same report to one caller-selected site. The tools omit filenames, paths, URLs, credentials, and source IDs; the site tool does not fan out across the site inventory. Listed backup timestamps do not confirm completeness or restore success. A synthetic 12-file payload measured 459 source JSON tokens and 103 summary tokens (77.56% fewer; js-tiktoken 1.0.21/o200k_base), excluding schemas, prompts and agent framing.

`omada_site_channel_reuse_summary` accepts one site reference and 1–16 selected AP references. It compares reported radio channels and bandwidth with matching values in existing channel-load results. Equal channels are grouped by band. Adjacent-channel overlap and interference cause are left unknown. The tool is read-only and starts no scan.

A synthetic eight-AP fixture with 608 channel-load rows measured 9,324 source JSON tokens and 2,046 report tokens (7,278 fewer; 78.06%) using `js-tiktoken` 1.0.21 / `o200k_base`. It includes inventory plus eight radio-detail and eight existing channel-load responses; schemas, prompts, framing and billed agent usage are excluded.

`omada_site_wan_max_speed_summary` requires one `wan_port_ref` returned by the WAN-port inventory. It rereads that inventory, resolves the selected reference to one documented `portId`, and sends the required `wanId` query. It returns upstream/downstream int32 values without interpreting units; the source gives no unit. This is configuration, not current throughput. Live support is unknown.

`omada_gateway_info_summary` requires a gateway `device_ref` from the selected site's device inventory. It returns only the documented model, firmware version, and unscaled `lastSeen` integer. The source does not define the time unit or epoch, so no online/offline status is inferred. Addresses, MAC values, IPv6 values, and port details are omitted. Live support is unknown.

`omada_site_policy_route_summary` accepts `site_ref` and returns redacted counts from the paginated policy-routing read. Protocol mapping is omitted because the three API exports refer to an external guide. Unique indices are reported without inferring route precedence.

`omada_site_static_route_summary` reads the selected site's paginated static gateway-route list. It counts only documented route types, enabled status and occurrences of interface, VPN-client and virtual-WAN references. Route names, IDs, destination and next-hop addresses, metrics and descriptions are omitted. Pagination is bounded by the connector limit; an incomplete or oversized response is reported as an error rather than a complete summary. Live support is unknown.

`omada_site_static_route_interface_options_summary` counts the selected site's documented static-route interface choices by type and `needNextHop` value. It omits interface IDs and names and does not represent configured or effective routes. The list is unpaginated, capped at 1,000 returned rows, and reports unknown fields or truncation as partial. All three source exports document this read; live support is unknown.


`omada_ap_ssid_override_audit_summary` reads the selected inventoried AP's stored SSID override audit rows. It requests only a fixed first page of 100 from the source default trailing seven-day window and returns aggregate modification counts; SSID names and VLAN values are omitted. Source rows provide no timestamp or actor, so the result is not chronological or attributable. The source operation appears in Hardware Controller and CBC 6.3 exports and is absent from the ER7212PC 6.2.14 export. Live MCP support has not been tested.
### Comparing existing incident reports

`omada_compare_incident_reports` accepts 2–8 already-redacted JSON documents from the local site-outage report workflow. It does not call the controller. Only `site_outage_report` schema version 1 is comparable; other schemas are counted and explicitly marked unsupported. Event and alert totals are compared only when report windows are identical and every report is complete. Current reachability snapshots are compared only when their observation timestamps match exactly. Overlapping windows and pagination/missing-field gaps are shown; names, identifiers, free text and raw observations are omitted. The accepted JSON is capped at 60 KiB.

A synthetic pair of existing-format outage reports measured 688 source JSON tokens and 783 comparison-result tokens (95 more) with js-tiktoken 1.0.21 / `o200k_base`. This payload-only sample excludes prompts, schemas, framing and billed agent use; the comparison metadata exceeds the two compact input reports in this case.

`omada_site_ipsec_sa_summary` takes `site_ref` and returns a bounded count of IPsec security-association rows by direction. It omits peer addresses and all row details. The source contract has no connected/disconnected field, so connectivity remains unknown.


For the synthetic 20-row example, the redacted IPsec summary used 52 tokens versus 1,863 for the source-shaped JSON (1,811 fewer; 97.21%; js-tiktoken 1.0.21, o200k_base). This is serialized fixture size only, not measured agent billing.

For a synthetic 20-rule policy-routing fixture, the summary used 142 tokens versus 2,562 for source-shaped JSON (2,420 fewer; 94.46%; js-tiktoken 1.0.21, o200k_base). This is fixture serialization only.

`omada_site_vpn_server_status_summary` requires a site and a protocol code (0 L2TP, 1 PPTP, 2 IPsec, 3 OpenVPN, 4 WireGuard, 5 SSL VPN). It returns only counts by the source's integer status code. The exports do not define status-code meanings, and user or address fields are not returned.

On a synthetic 20-row VPN server status fixture, the redacted summary used 67 tokens versus 1,535 source-shaped tokens (1,468 fewer; 95.64%; js-tiktoken 1.0.21, o200k_base). This is serialized fixture size only.

`omada_site_wan_qos_summary` reports configured WAN and rule counts with exact, unique port association. Because bandwidth units are unspecified, it omits numeric bandwidth and ratio values. On a synthetic 10-port/20-rule fixture the projection measured 118 tokens versus 1,180 for the source-shaped JSON (1,062 fewer; 90.00%; js-tiktoken 1.0.21, o200k_base), excluding schemas, MCP framing and billed usage.

`omada_site_upnp_template_comparison` requires an explicit site and template reference. It compares enabled state, WAN-reference count, network-reference count and the DS-Lite/Map-E support flag; it does not infer template assignment. The template API is documented only for CBC Standard 6.3.0.

A synthetic four-field comparison measured 40 projected tokens versus 68 for the two source-shaped responses (28 fewer; 41.18%; js-tiktoken 1.0.21, o200k_base), excluding schemas, MCP framing and billed usage.

`omada_site_bridge_device_summary` reads only the documented adopted and pending bridge-device lists. It reports redacted status-code and group counts plus per-list pagination coverage; code meanings are not inferred.

On a synthetic 10-adopted/4-pending bridge inventory, the projection measured 127 tokens versus 1,042 source-shaped tokens (915 fewer; 87.81%; js-tiktoken 1.0.21, o200k_base), excluding schemas, framing and billed usage.

`omada_site_recent_clients_summary` accepts `site_ref`, `start_ms` and `end_ms`. The window is limited to 24 hours and returns one page of up to 100 rows as counts only. It does not interpret the undocumented `lastSeen` unit or infer outages. A synthetic 20-client fixture measured 1,546 source tokens and 83 summary tokens (94.63% fewer; js-tiktoken 1.0.21/o200k_base).

`omada_site_vlan_affected_ports_summary` accepts `site_ref`, `network_ref`, `vlan_id`, `page_number` and `page_size` (1–100). It counts documented device types and port/LAG memberships for the selected network/VLAN; identifiers and client details are omitted. The counts are memberships, not unique physical ports. A synthetic 10-device fixture measured 1,445 source tokens and 121 summary tokens (91.63% fewer; js-tiktoken 1.0.21/o200k_base).

The documented SSID client-list read is not exposed because the ER7212PC export omits the route and leaves `queryDataVO` serialization unspecified.

`omada_site_port_schedule_summary` accepts a site plus `page_number` (zero-based) and `page_size` (1–100). It returns redacted schedule and supported-port counts. The join uses the documented device MAC key only when it is unique in the selected site. It does not expose port identifiers or predict schedule execution; the `nextExecute` timestamp unit is unspecified.

A synthetic 10-schedule/four-device fixture measured 1,729 source tokens and 188 summary tokens (89.13% fewer; js-tiktoken 1.0.21/o200k_base), excluding schemas and billed usage.

`omada_site_routing_table_summary` accepts a site, `device_type` (`gateway` or `switch`), zero-based `page_number`, and `page_size` (1–100). It returns only page coverage and counts of uninterpreted route type values. It omits destinations and hops and makes no configuration changes.

A synthetic 20-row route table measured 3,151 source tokens and 108 summary tokens (96.57% fewer; js-tiktoken 1.0.21/o200k_base), excluding schemas and billed usage.

`omada_site_vpn_client_status_summary` requires a site and `vpn_type` (0 L2TP, 1 PPTP, 3 OpenVPN, 4 WireGuard). It returns only row counts grouped by the integer status code. The API exports do not define status-code meanings; user, peer, IP, traffic and VPN identifiers are omitted. Fixture checks do not establish live controller support.

`omada_site_vpn_client_status_summary` requires a site and `vpn_type` (0 L2TP, 1 PPTP, 3 OpenVPN, 4 WireGuard). It returns only row counts grouped by the integer status code. The API exports do not define status-code meanings; user, peer, IP, traffic and VPN identifiers are omitted. Fixture checks do not establish live controller support.

A synthetic 50-row client VPN payload measured 3,472 tokens before projection and 81 after projection (3,391 fewer; 97.67%) with `js-tiktoken` 1.0.21 using `o200k_base`. This fixture comparison excludes tool schemas, prompts, transport framing, and billed agent usage; it is not a live response or model-token measurement.

`omada_site_ssid_client_count_summary` requires an explicitly selected `site_ref` and opaque `ssid_ref`. It returns the documented total row count and whether the sampled first page covers the total; it omits client rows and makes no online-state claim. `queryDataVO` is sent as `page=1&pageSize=100`, following the OpenAPI 3.0.1 default `form`/`explode` serialization. This operation is absent from the ER7212PC export. A synthetic 100-row response measured 4,723 tokens before projection and 73 after (4,650 fewer; 98.45%) using `js-tiktoken` 1.0.21 / `o200k_base`; this excludes schemas, prompts, transport framing, and billed agent usage.

`omada_site_remote_logging_summary` is bound to one selected site. It returns the enable flag, optional client-log flag, documented resource category (new, template, override), and destination host/port presence. Destination values are omitted, and delivery is not verified. Unknown categories and fields mark the result partial.

A synthetic single-record source response measured 32 tokens before projection and 80 after projection (48 more tokens; 150% larger) with `js-tiktoken` 1.0.21 / `o200k_base`. The summary's safety and quality metadata outweigh the small payload in this case; it is not a token-saving read. The fixture comparison excludes schemas, prompts, transport framing, and billed agent usage.

`omada_controller_upgrade_log_summary` is scoped to the configured controller and reads one page of at most 100 logs. It aggregates documented rollback, failed-device and upgrade-time presence fields; names, IDs, versions, model details, and raw timestamps are omitted. Page coverage is explicit, and no upgrade is started. A synthetic 25-row response measured 2,004 tokens before projection and 107 after (1,897 fewer; 94.66%) with `js-tiktoken` 1.0.21 / `o200k_base`; this fixture excludes schemas, prompts, host framing and billed agent use.

`omada_controller_global_log_notification_summary` is controller-scoped and distinct from the site notification summary. It reports only category totals and documented alert/event/email/webhook switch counts, without category labels, message text, webhook identifiers, or delay values. It does not indicate whether a notification was delivered. HTTP and MCP routing are fixture-tested; live support is unknown.

`omada_controller_upgrade_model_list_summary` is controller-scoped and reads up to 1,000 planned model rows. It returns only model metadata coverage and documented critical/upgrade status counts. Model names and firmware versions are omitted; it does not initiate updates or infer per-device compatibility. HTTP and MCP routing are fixture-tested; live support is unknown.

`omada_controller_firmware_email_reminder_status` is a fixed controller-wide
read of the firmware email-reminder `enable` Boolean. False is valid; missing,
null or non-Boolean values remain incomplete. It reports configuration only
and does not send mail or perform an upgrade.

`omada_controller_try_beta_settings_summary` reads the documented preview-firmware enable switch and channel through two fixed controller GETs. Missing fields are marked incomplete; the selected channel does not confirm an update or firmware status. `omada_controller_auto_check_upgrade_summary` reads up to 10 pages of 100 plans and counts documented channels and site associations. It omits names, model details, IDs, schedule values and recurrence, and never starts an update. Both are fixture-tested over HTTP and MCP; live support is unknown.

`omada_controller_firmware_inventory_summary` reads at most 10 pages of 100 uploaded firmware records and reports only entry totals and metadata-field coverage. It omits names, IDs, model values, descriptions and timestamps; it does not claim device compatibility or firmware suitability. `omada_site_agile_switch_general_config_summary` refreshes one site's switch inventory, requires one matching port-detail row with `es: true`, then summarizes only documented LED, jumbo-frame and power-alert settings. It omits names, locations, tags and device identifiers. Both operations are fixture-tested over HTTP and MCP; live support is unknown.

`omada_site_s2s_vpn_inventory_summary` lists same-site opaque VPN references and documented VPN types. Use one returned `vpn_ref` with `omada_site_s2s_peer_status_summary`; that read refreshes and checks the VPN against the selected site's inventory before requesting peers. It returns only peer status counts (0 disconnected, 1 connected); other codes and missing status stay unknown. It omits peer/VPN identities, addresses, names and traffic. These are separate from the general S2S tunnel/IPsec association summaries. Live support is unknown.

`omada_site_nat_exception_summary` summarizes documented NAT exception
configuration for one selected site through a bounded paginated read. It omits
rule identities and raw LAN/WAN references, and does not claim that a rule is
effectively enforced. Live support is unknown.

`omada_site_s2s_vpn_v2_summary` reports bounded counts for the selected site's
v2 site-to-site VPN inventory, including documented type and status flags,
network-selection coverage and S2S support flags. It omits identities, raw
network/WAN values, peer details and user/client counts. The status boolean
does not establish tunnel connectivity; live support is unknown.


`omada_site_stack_network_summary` takes a site and an opaque `stack_ref` returned by the stack connection summary. It refreshes stack inventory before reading that stack's VLAN-network configuration, returning counts for documented DHCP modes and status/management/IPv6 coverage. VLAN/network IDs, names, stack members, addresses and DHCP values are omitted. The read is capped at 1,000 rows; live stack support remains untested.

`omada_site_stack_static_routing_summary` refreshes the selected site's stack
inventory and binds the opaque `stack_ref` to one unique current stack. It reads
at most 1,000 documented route rows and counts IPv4/IPv6 and enabled/disabled
configuration. Destinations, next hops, names, VRF values and device identifiers
are omitted; configured status does not establish active forwarding. Live stack
support is unknown.

`omada_site_stack_ospf_neighbor_summary` uses the same fresh site-stack binding
and a bounded read of the documented OSPF neighbor grid. It reports row and
coverage counts plus how many rows include a state field. State strings are not
interpreted; addresses, router IDs, interfaces and process IDs are omitted.
Live stack support is unknown.

`omada_site_intelli_recover_summary` reports the documented automatic-recovery
enable state and reboot-device limit. Interval values are omitted because the
exports do not document their units; the result only indicates whether each
interval field was reported. No restart or recovery action is performed.

`omada_site_port_forwarding_summary` reads at most 1,000 configured forwarding
rows and counts documented enable state, protocol codes and source codes. It
preserves code 0 without interpreting the export's ambiguous label, and names
code 1 as limited-address source. Rule names, addresses, ports and WAN references
are omitted. The summary makes no traffic, reachability or runtime-statistics
claim.

`omada_site_switch_oui_vlan_summary` takes a `site_ref` and returns bounded
counts of documented rule enable flags and port-scope modes. It omits rule and
device identities, ports, OUI values and VLAN values, and does not infer VLAN
enforcement or assignments. The ER7212PC export marks this endpoint as Omada
Pro-only and documents `-44119` for non-Pro use; ER7212PC is therefore not
claimed as supported. Live support is unknown.

`omada_site_stack_dhcp_user_summary` takes the selected site's opaque
`stack_ref`, refreshes the stack inventory and binds it to exactly one current
stack before the read. It counts documented device/client types and
dynamic/static binding states from at most 1,000 rows. Addresses, names,
binding rows and network/server identities are omitted. This is not a claim
about current leases or wired clients. Live stack support is unknown.

`omada_site_stack_vlan_interface_summary` accepts a site and the opaque stack
reference returned by the site's stack inventory. It refreshes that inventory
and rejects missing, ambiguous or incomplete binding. The bounded projection
counts documented VLAN-interface rows, duplicate/missing/invalid interface IDs
and field coverage; interface names, IDs and VLAN numbers are omitted. Hardware
and CBC document the typed response; the ER7212PC export does not.

`omada_site_snmp_incompatible_summary` reports up to 1,000 controller-reported
SNMP incompatibility rows as counts only. Hardware/CBC use a narrow `DeviceVO`
schema, while ER7212PC declares a broader device record. Device fields,
identities and individual assignments are omitted; the summary does not infer
device configuration or SNMP state. Live support is unknown.

`omada_site_gateway_general_config_summary` takes a `site_ref` and gateway
`gateway_ref` from the site inventory. It refreshes that inventory, then reports
the documented LED mode and presence-only coverage for optional settings.
Device names, tags, locations, SNMP values and undocumented `rememberDevice`
code meanings are omitted.

`omada_site_switch_general_config_summary` takes a `site_ref` and inventoried
`switch_ref`. It refreshes the inventory, then reports the documented LED mode,
Jumbo setting scope and range validity, LAG hash setting scope and documented
mode, plus SDM object presence. It does not return raw device settings or infer
actual forwarding behavior. Missing source-specific follow fields stay marked
missing.
`omada_controller_sdwan_group_summary` takes no site argument because the API
read is controller-scoped. It reports group counts, hub metadata field coverage
and the sum of documented device counts across groups (not a distinct-device
count). IDs, names and hub values are omitted. Hardware/CBC document the read;
ER7212PC does not. Unique current group rows also receive opaque `group_ref`
handles for the separately documented member summary; raw IDs remain omitted.
No operational status is inferred.

`omada_site_vpn_server_config_summary` takes a selected `site_ref`. It counts
configured VPN server rows by documented protocol and by the source boolean
status flag. It omits IDs, names, WAN/network values, user/client counts and
other row details. The flag is not tunnel connectivity, and this summary is
separate from `omada_site_vpn_server_status_summary`.

`omada_site_remote_access_tunnel_status_summary` takes a `site_ref`. It counts
documented remote-access tunnel connection states separately from the
open/closed flag, omits tunnel IDs and names, and reports unknown values and
truncation. This is remote-access tunnel status, separate from client-to-site
VPN server configuration and status.

`omada_site_ids_ips_config_summary` accepts a `site_ref` and returns only
the enable/geo flags, documented IDS/IPS mode and detection level codes, and
custom-category count. Schedule IDs and raw category values
are omitted. It does not report attack detection or enforcement.
`omada_site_gateway_webfilter_summary` accepts a `site_ref`. It returns bounded
counts by documented rule type and enabled state, plus coverage of the optional
keyword, category and time-schedule flags and the source feature-support flags.
The output omits identifiers, names, URLs, keywords, category values, source
IDs and schedule values; it does not describe effective filtering.

`omada_site_gateway_qos_class_summary` accepts a `site_ref` and returns bounded
counts for class-rule enable state, documented IP versions and class values.
Address groups, service and rule identifiers, and DSCP values are omitted. It
does not report traffic matches or effective throughput.

`omada_site_ap_webfilter_summary` accepts a `site_ref` and returns bounded AP
URL-filter counts by documented type, mode, status and feature-flag coverage.
It omits rule text, URLs, keywords, categories, schedules, names and source
identities, and makes no enforcement claim.

`omada_site_url_filter_general_summary` accepts a `site_ref` and reports only
the documented SafeSearch and block-page flags. The optional message text is
omitted, and effective filtering is not inferred.

`omada_site_wan_unsupported_function_summary` reads the selected site's
DS-Lite/MAP-E limitation list with the fixed documented `filter=1` query. It
returns an entry count and result quality only; API label text is neither
exposed nor interpreted as device status. Live support is unknown.

`omada_site_mdns_profile_summary` takes a `site_ref` and counts configured
Bonjour profiles by default-profile flag and by zero to three documented
service entries. Profile IDs, names and service strings are omitted; results
are capped at 1,000 profiles. This complements the rule summary and does not
claim Bonjour reachability. Live support is unknown.

`omada_site_vpn_client_config_summary` takes a selected `site_ref`. It reads
the documented v2 client grid with only `page` and `pageSize`, then counts
documented protocol codes and the source boolean VPN status flag. It omits
addresses, peer details, identifiers, credentials and other settings. The flag
does not establish a live tunnel connection; controller support is unknown.

`omada_controller_sdwan_group_devices_summary` takes a `group_ref` returned by
the SD-WAN group inventory summary. Each call refreshes that inventory and
requires one unique current match before reading the group. It counts returned
members and documented SD-WAN NAT capability flags. Device, site and group IDs,
names, WAN IPs, and member details are omitted. The read is documented for
Hardware Controller and CBC Standard; ER7212PC does not document it. Live
support is unknown.

A synthetic 20-client V2 grid measured 1,787 source-envelope tokens and 127
projected JSON tokens (92.89% fewer) with `tiktoken` 0.9.0 and `o200k_base`.
The count covers only the serialized grid envelope and returned JSON, not
transport framing or billed agent usage.

A synthetic 20-member SD-WAN group measured 2,798 detail-payload tokens and 78
summary tokens (97.21% fewer) with `tiktoken` 0.9.0 and `o200k_base`. This
excludes the separate fresh group-inventory request, transport framing and
billed agent usage.

`omada_site_lan_interface_isolation_summary` accepts a `site_ref` and counts
reported true, false, missing and invalid isolation flags. It uses no search or
filter query, omits interface identities and VLAN values, and does not infer
real network separation. All three exports document the endpoint; the
ER7212PC operation ID omits the `_1` suffix.

`omada_site_ospf_interface_summary` accepts a `site_ref` and reports bounded
counts for documented interface type, network type and valid cost values, plus
optional field coverage. Names, IDs, addresses, VLAN values and authentication
keys are omitted. Missing source fields are shown as unreported; neighbor
state is not inferred.

`omada_site_switch_qos_summary` accepts a `site_ref` and reports bounded counts
for documented QoS rule state, type and queue. It omits names, IDs, addresses
and ports and does not describe traffic behavior. The ER7212PC export provides
no typed grid contract; unsupported response shapes are rejected.

`omada_site_switch_ddm_summary` accepts a `site_ref` and inventoried switch
`device_ref`. It refreshes the site's device inventory, requires one unique
switch match, and counts documented data-valid, transmit-fault and signal-loss
flags. Port values and optical measurements are omitted; no health diagnosis
is inferred. ER7212PC lacks an effective row contract.

`omada_controller_try_beta_settings_summary` combines the documented firmware
preview enable switch and channel from two fixed controller GETs. Missing
values or unknown channel codes are marked incomplete. The selected channel
does not confirm an update or device support. `omada_controller_auto_check_upgrade_summary`
reads at most ten pages of 100 configured automatic-check plans and counts
documented channels and selected-site associations. It omits IDs, names, models,
schedule values and recurrence, and does not start an update. Both are
fixture-tested over HTTP and MCP; live support is unknown.

`omada_controller_firmware_pool_channel_counts` makes one fixed controller GET
for stable channel 0, page 1 and page size 1. It reports only stable,
release-candidate and beta quantities from the documented channel map. `reported_count`
counts documented channel keys present, including keys with invalid values;
`missing_count` counts only absent documented keys, `invalid_count` counts present
keys with invalid values, and unknown keys are counted separately. Page metadata
requires integer `currentPage` (int32) and `totalRows` (int64); returned rows cannot
exceed the reported total. Firmware rows and identifiers are omitted, and no installed
state, update availability or security status is inferred. HTTP/MCP fixture coverage
exists; live support is unknown.

`omada_controller_firmware_inventory_summary` reads at most ten pages of 100
uploaded records and counts entry and metadata-field coverage only. It omits
all firmware names, IDs, model values, descriptions and upload times, and does
not infer compatibility. `omada_site_agile_switch_general_config_summary`
refreshes the selected site's inventory and checks for one unique matching
switch row with `es: true` before reading the Agile general config. It returns
only LED, jumbo-frame and power-alert settings. Names, locations, tags and
device identifiers are omitted. Both operations are fixture-tested; live
support is unknown.

# Site incident category counts

`omada_site_incident_category_counts` requires the selected site's `site_ref`
and one integer `category` from 11 through 19. It reads only that category
over a connector-fixed trailing 24-hour window and returns the chosen code and
window once as query context. Omitting the category or supplying a value
outside the documented range is rejected before any controller request. The
result rows keep their existing redacted fields; codes have no inferred
manufacturer meaning.
One OC200 request for a selected category returned a partial result through
HTTP and MCP. Other category codes and ER7212PC remain unverified.

`omada_client_health_detail_v2` returns bounded, redacted version-two health
metrics for a current same-site client reference. Its `series_point_coverage`
aggregate counts inspected structurally valid points and distinguishes
`pastNum` absent, explicitly null, or present and non-null. It counts no more
than 64 points per series; null values remain invalid for the existing numeric
projection, and points beyond the cap remain unclassified. These counts do
not assign meaning to null and do not change partial status.
