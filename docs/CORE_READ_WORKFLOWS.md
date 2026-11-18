# Core read workflows

## Client identity matching

`GET /v1/sites/{site_ref}/clients/identity-match` and the matching MCP tool accept `client_name` and `ssid_name`. The connector reads every client inventory page within its configured page limit and matches case-insensitively against the documented client `name`, `hostName` or `model`, plus `ssid`, with `wireless=true`. It returns a fresh opaque `client_ref` only for exactly one match and only when no row with missing identity fields could also match. The response includes per-field presence counts and complete/incomplete row counts, without returning input labels, SSIDs, MAC addresses or controller identifiers. A definite zero-match with complete candidate coverage returns `unmatched`; missing fields that could hide a match return `incomplete` with `partial=true`. Multiple definite matches return `ambiguous`. An incomplete inventory raises a bounded-read error instead of returning any match state.

## Event and alert windows

The event and alert window endpoints accept UTC epoch milliseconds with a maximum 24-hour interval. They aggregate only counts by module and (for alerts) severity, plus observed time bounds. Raw log text and record identifiers are omitted. Event page one may include controller module totals; those totals do not stop pagination. When the configured page limit is reached before `total_count`, the response sets `partial=true`; a partial result cannot be used to conclude that the window had no matching logs.

## WLAN walk sessions and comparison

`tools/wifi_measurement_session.py` samples one wireless client's documented signal fields through the local connector. It requires explicit site/client references, refreshes the same-site AP inventory once, and uses only connector GET routes. Duration is capped at 600 seconds, intervals at 30 seconds, and sample count at 180. Files are created with mode `0600`, never overwritten, and omit site/client references, raw MAC addresses and credentials. A read gap is recorded as unavailable and stops the session; a non-wireless response is recorded as a state sample without inferring a cause. This is an operator-started measurement workflow; it has not been run against a live controller in this verification.

`tools/wifi_compare_sessions.py` reads two local session files and does not contact the connector. It aligns numeric samples only when duration, interval and sample limits match. It reports per-session AP changes and observed read gaps, but does not compare opaque AP references across files or infer that a read gap was a network outage. If sampling conditions differ or data is partial, the result says so and omits aligned deltas.

For a synthetic 30-sample walk session, the two JSONL inputs used 2,622 and 2,631 tokens; the comparison JSON used 741 tokens. That is 4,512 fewer tokens (85.90%) than passing both input files onward with the result. Counts use `js-tiktoken` 1.0.21 and `o200k_base`. This fixture measure covers serialized payloads only; it excludes tool schemas, requests, host framing and billed agent usage.

## Verification scope

These workflows have fixture and HTTP/MCP dispatch tests and are cross-checked against all three supplied API exports. No controller was queried for this change. Live support remains unknown.

A synthetic 100-event page measured 5,558 source-envelope tokens and 105 summary-response tokens (5,453 fewer; 98.11%) with `js-tiktoken` 1.0.21 and `o200k_base`. The fixture contains placeholder event messages and IDs. This compares serialized payloads only; it excludes tool schemas, requests, host framing and billed agent usage.
