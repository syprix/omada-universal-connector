# Core read workflows

## Client identity matching

`GET /v1/sites/{site_ref}/clients/identity-match` and the matching MCP tool accept `client_name` and `ssid_name`. The connector reads every client inventory page within its configured page limit and matches case-insensitively against the documented client `name`, `hostName` or `model`, plus `ssid`, with `wireless=true`. It returns a fresh opaque `client_ref` only for exactly one match and only when no row with missing identity fields could also match. The response includes per-field presence counts and complete/incomplete row counts, without returning input labels, SSIDs, MAC addresses or controller identifiers. A definite zero-match with complete candidate coverage returns `unmatched`; missing fields that could hide a match return `incomplete` with `partial=true`. Multiple definite matches return `ambiguous`. An incomplete inventory raises a bounded-read error instead of returning any match state.

## WLAN network mapping

`GET /v1/sites/{site_ref}/ssid-network-summary` and the matching MCP tool reconcile up to 64 SSID bindings against the selected site's network inventory. For matched networks, the workflow reads VLAN/LAN detail and DHCP pool summaries for at most 32 networks, reads site-wide DNS cache/proxy settings, and checks internet metadata for at most four inventoried gateways. The result contains counts and safe setting values only; site, SSID, network and gateway references are omitted. Any reads beyond the bounds, incomplete inventory classifications, missing fields or failed reads keep the result partial or unknown.

VLAN values are summarized as counts rather than a list. DHCP ranges are counted; no address pool values are returned. DNS settings describe the site and cannot be linked to an individual WLAN in the available source projections. Gateway inventory/internet details likewise do not prove which gateway serves a specific network. The report names those relationships as unknown and does not suggest controller changes.

## Event and alert windows

The event and alert window endpoints accept UTC epoch milliseconds with a maximum 24-hour interval. They aggregate only counts by module and (for alerts) severity, plus observed time bounds. Raw log text and record identifiers are omitted. Event page one may include controller module totals; those totals do not stop pagination. When the configured page limit is reached before `total_count`, the response sets `partial=true`; a partial result cannot be used to conclude that the window had no matching logs.

## Verification scope

These workflows have fixture and HTTP/MCP dispatch tests and are cross-checked against all three supplied API exports. No controller was queried for this change. Live support remains unknown.

A synthetic 100-event page measured 5,558 source-envelope tokens and 105 summary-response tokens (5,453 fewer; 98.11%) with `js-tiktoken` 1.0.21 and `o200k_base`. The fixture contains placeholder event messages and IDs. This compares serialized payloads only; it excludes tool schemas, requests, host framing and billed agent usage.
