# Core read workflows

## Client identity matching

`GET /v1/sites/{site_ref}/clients/identity-match` and the matching MCP tool accept `client_name` and `ssid_name`. The connector reads every client inventory page within its configured page limit and matches case-insensitively against the documented client `name`, `hostName` or `model`, plus `ssid`, with `wireless=true`. It returns a fresh opaque `client_ref` only for exactly one match and only when no row with missing identity fields could also match. The response includes per-field presence counts and complete/incomplete row counts, without returning input labels, SSIDs, MAC addresses or controller identifiers. A definite zero-match with complete candidate coverage returns `unmatched`; missing fields that could hide a match return `incomplete` with `partial=true`. Multiple definite matches return `ambiguous`. An incomplete inventory raises a bounded-read error instead of returning any match state.

## WLAN network mapping

`GET /v1/sites/{site_ref}/ssid-network-summary` and the matching MCP tool reconcile up to 64 SSID bindings against the selected site's network inventory. For matched networks, the workflow reads VLAN/LAN detail and DHCP pool summaries for at most 32 networks, reads site-wide DNS cache/proxy settings, and checks internet metadata for at most four inventoried gateways. The result contains counts and safe setting values only; site, SSID, network and gateway references are omitted. Any reads beyond the bounds, incomplete inventory classifications, missing fields or failed reads keep the result partial or unknown.

VLAN values are summarized as counts rather than a list. DHCP ranges are counted; no address pool values are returned. DNS settings describe the site and cannot be linked to an individual WLAN in the available source projections. Gateway inventory/internet details likewise do not prove which gateway serves a specific network. The report names those relationships as unknown and does not suggest controller changes.

## Event and alert windows

The event and alert window endpoints accept UTC epoch milliseconds with a maximum 24-hour interval. They aggregate only counts by module and (for alerts) severity, plus observed time bounds. Raw log text and record identifiers are omitted. Event page one may include controller module totals; those totals do not stop pagination. When the configured page limit is reached before `total_count`, the response sets `partial=true`; a partial result cannot be used to conclude that the window had no matching logs.

## WLAN walk sessions and comparison

`tools/wifi_measurement_session.py` samples one wireless client's documented signal fields through the local connector. It requires explicit site/client references, refreshes the same-site AP inventory once, and uses only connector GET routes. Duration is capped at 600 seconds, intervals at 30 seconds, and sample count at 180. Files are created with mode `0600`, never overwritten, and omit site/client references, raw MAC addresses and credentials. A read gap is recorded as unavailable and stops the session; a non-wireless response is recorded as a state sample without inferring a cause. This is an operator-started measurement workflow; it has not been run against a live controller in this verification.

`tools/wifi_compare_sessions.py` reads two local session files and does not contact the connector. It aligns numeric samples only when duration, interval and sample limits match. It reports per-session AP changes and observed read gaps, but does not compare opaque AP references across files or infer that a read gap was a network outage. If sampling conditions differ or data is partial, the result says so and omits aligned deltas.

## Device measurement import

`python3 tools/import_device_measurements.py --input ./measurements.json --format json` and `--format csv` read local, owner-owned regular files only. The input is limited to 2 MiB and 10,000 samples; symlinks, extra fields, duplicate JSON keys and unbounded records are rejected. No controller route or network probe is used. The normalized result is printed to stdout and omits device/application names, addresses, MACs, SSIDs and arbitrary input identifiers.

The JSON v1 format is an object containing only `schema_version: 1` and `samples`. Each sample requires an ISO-8601 `timestamp` with a numeric timezone offset or `Z`, a boolean `wifi_connected`, and a fixed `wifi_source` (`system_log` or `diagnostic_export`). Rows must be strictly increasing in time, and timestamp precision must be an exact millisecond. The CSV v1 format uses the same fields in columns; its required header is `timestamp,wifi_connected,wifi_source`.

Optional observations must carry their own fixed source column/value pair: `local_reachability` (`reachable`/`unreachable`) with `local_reachability_source` (`reachability_check`/`diagnostic_export`); `dns_status` (`resolved`/`failed`) with `dns_source` (`dns_resolution_check`/`diagnostic_export`); `ipv4_status` and `ipv6_status` (`available`/`unavailable`) with their respective source (`interface_status`/`diagnostic_export`); and `cellular_transition` (`wifi_to_cellular`/`cellular_to_wifi`) with `cellular_transition_source` (`system_log`/`diagnostic_export`). A value without its matching source is rejected. Source kinds are declared by the file and are not independently verified, so output marks every observation `imported_unverified` and reports per-field coverage.

The CSV header may include any complete set of optional value/source pairs; unknown columns are rejected. For JSON, optional values and their matching source may be omitted together. Neither format accepts arbitrary source labels, host names, interface names or addresses.

## Device measurements and Omada timeline comparison

`python3 tools/compare_device_measurements.py` takes three saved local files: the v1 CSV/JSON device export, the JSON result from `tools/wifi_diagnose.py --client-timeline` (without compact mode), and a JSONL file from `tools/wifi_measurement_session.py`. The comparison requires explicit `--start-ms`, `--end-ms` and `--tolerance-ms`; the window is limited to 24 hours and tolerance to 30 seconds. It excludes every sample outside the requested interval. Ties at the nearest timestamp are marked ambiguous; timestamps without a sample inside tolerance are left unmatched.

The report keeps imported Wi-Fi and optional local reachability/DNS/IP/cellular observations separate from Omada timeline event families and passive session samples. It preserves the timeline route family and numeric event code without interpreting the code. A Wi-Fi state agreement or disagreement is counted only when an explicit passive sample says wireless or not-wireless. Local reachability, DNS, IP and cellular observations are shown as imported facts; they are not correlated with Omada because these inputs contain no matching Omada observations. Source ages are calculated from the newest timestamped data relative to `as_of_ms`; the current client-timeline export has no capture timestamp, so its age is explicitly unavailable. Declared device source kinds are not independently verified. Missing windows, partial inputs, session gaps and unmatched/ambiguous observations remain visible, and no outage cause is inferred.

The comparison tool reads all inputs locally, uses only bounded existing file parsers, and makes no controller request or network probe. It projects only timestamps, categorical measurements, documented event kinds/codes, and allow-listed signal metrics; it never echoes site/client/AP references, labels, SSIDs, IP/MAC addresses or arbitrary source-file fields.

For a synthetic 30-sample walk session, the two JSONL inputs used 2,622 and 2,631 tokens; the comparison JSON used 741 tokens. That is 4,512 fewer tokens (85.90%) than passing both input files onward with the result. Counts use `js-tiktoken` 1.0.21 and `o200k_base`. This fixture measure covers serialized payloads only; it excludes tool schemas, requests, host framing and billed agent usage.

## Offline DNS incident diagnosis

`python3 tools/diagnose_dns_incident.py --measurements ./measurements.json --format json` uses the bounded device-measurement importer and makes no controller request, DNS lookup or network probe. Optional `--dns-snapshot` accepts a redacted local configuration snapshot, and `--network-summary` accepts a saved `ssid_network_summary` response. Both context files are validated and remain site-wide; they cannot be tied to a particular imported device because the input format deliberately carries no network identifier. Use `--start-ms` and `--end-ms` together to narrow the incident to a maximum 24-hour window; without them the imported sample window is used.

The report defaults to aggregate counts for lower token use. `--include-observations` adds the bounded allow-listed sample detail when needed. It counts declared DNS failures, resolutions and missing samples alongside separately imported Wi-Fi, local-reachability and IP availability states. It marks cross-source disagreement and co-occurring failures without deciding cause. Imported checks remain `imported_unverified`; configuration snapshots are historical context, and a site DNS setting does not prove which resolver a device used. Missing context and data gaps remain unknown or partial. The tool does not change configuration.

A synthetic 48-sample file measured 3,370 `o200k_base` tokens before summarization and 339 in the default aggregate report (3,031 fewer; 89.94%) using `js-tiktoken` 1.0.21. This is serialized fixture size only, not billed agent use; optional context and per-sample detail are excluded.

## AP quality history and passive-session comparison

`GET /v1/sites/{site_ref}/aps/quality-window` and MCP tool `omada_site_ap_quality_window` use a common, second-aligned 24-hour window for AP health scores and the site dashboard retry/drop lists. They include current radio settings by band, but never start a scan. Health-score and rate scales remain unclassified where the exports do not define them. Retry/drop rows have no band mapping, and absence from the bounded dashboard list is not zero. Per-hour buckets retain each source's sample count and minimum, maximum and last value; missing or malformed data stays partial.

Save that response as a local JSON file, then run `python3 tools/compare_ap_quality_session.py --quality-report ./ap-quality.json --session ./walk-session.jsonl` to show matching passive RSSI/SNR and categorical radio observations beside each AP's health and retry/drop summary. The join uses exact opaque AP references. The session file does not record its site, so the report says site binding is unavailable. This CLI uses only owner-owned saved files, makes no controller request, and does not infer an outage cause. Missing references and unassigned samples remain separate.

For a synthetic eight-AP case with 24 hourly source points per AP, the separate
source-response JSON used 11,527 tokens and the combined report used 10,196
(1,331 fewer; 11.55%), measured with `js-tiktoken` 1.0.21 and `o200k_base`.
This compares serialized data only, not billed agent usage or live responses.

## Site firmware summary

`GET /v1/sites/{site_ref}/firmware-summary` and `omada_site_firmware_summary`
combine the selected site's current device inventory with at most 64 existing
firmware-info reads. Results group device counts by known device type, model,
inventory firmware, current version and the source's `lastFwVer` latest version.
Statuses distinguish an exact version match, differing strings, missing
versions, inventory disagreement and failed reads. Version strings are not
ordered, and a difference is not called an available update. Excess inventory
and missing source data remain partial. The workflow does not start an update.

A synthetic 40-device site with repeated models used 3,871 `o200k_base` tokens
for inventory plus individual firmware responses, and 725 for the grouped
report (3,146 fewer; 81.27%). Measured with `js-tiktoken` 1.0.21, this compares
serialized payloads only, not billed agent usage or live responses.

## Site outage context

`GET /v1/sites/{site_ref}/outage-summary?start_ms=…&end_ms=…` and `omada_site_outage_summary` combine the current site reachability counters with bounded event and alert summaries for one UTC window of at most 24 hours. The current counters are timestamped separately from the requested log period. The workflow omits event details and identifiers, reports partial log pagination, and leaves site-wide scope indeterminate when sources cannot establish device correlation or cause. Fixture-backed HTTP and MCP dispatch are tested; no controller was queried.

To export that JSON response locally, save it to a private file and run `python3 tools/site_outage_report.py --input ./outage-summary.json --output ./outage-report.md`. The exporter does not connect to the controller, rejects symlinks and non-private input files, creates a new owner-only output file without overwriting, and omits site/device references from the report.

## Verification scope

These workflows have fixture and HTTP/MCP dispatch tests and are cross-checked against all three supplied API exports. No controller was queried for this change. Live support remains unknown.

A synthetic 100-event page measured 5,558 source-envelope tokens and 105 summary-response tokens (5,453 fewer; 98.11%) with `js-tiktoken` 1.0.21 and `o200k_base`. The fixture contains placeholder event messages and IDs. This compares serialized payloads only; it excludes tool schemas, requests, host framing and billed agent usage.
