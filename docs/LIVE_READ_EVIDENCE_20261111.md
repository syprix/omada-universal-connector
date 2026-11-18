# Read-only OC200 live probe — 2026-11-11

The connector source at commit `c72326070cf9c9ed16386298c73fed50ec07b0f0` was built from six individually SHA-256-verified allowlisted files with Docker build networking disabled. The existing pinned-TLS controller configuration was used. The controller ID was read internally from the pinned `/api/info` response and was not recorded here.

The existing Bitwarden one-shot was run with an allowlist containing only `OMADA_CLIENT_ID` and `OMADA_CLIENT_SECRET`. Credential files were temporary and private. The connector ran as a non-root user with a read-only root filesystem, all Linux capabilities dropped, no published port, and writes disabled. Requests below were bounded HTTP GETs through the connector. Output was reduced to HTTP status, stable error code, or aggregate count.

| Read route | Result |
| --- | --- |
| Sites | HTTP 200, 1 |
| Devices | HTTP 200, 4 |
| Clients | HTTP 200, 30 |
| Networks | HTTP 200, 1 |
| SSIDs | HTTP 200, 6 |
| Site health summary | HTTP 200 |
| Site health timeline | HTTP 502, `openapi_response_invalid` |
| DHCP leases | HTTP 200, 35 |
| DNS cache settings | HTTP 200 |
| DNS proxy settings | HTTP 200 |
| LAN DNS records | HTTP 200, 0 |
| Gateway ACLs | HTTP 200, 0 |
| Switch ACLs | HTTP 200, 0 |
| AP ACLs | HTTP 200, 0 |
| AP available channels | HTTP 200 |
| AP RF scan results | HTTP 200 |
| AP Wi-Fi neighbors | HTTP 502, `openapi_rejected` |
| Controller health route | HTTP 404, `not_found` |

Errors are recorded as observed; they do not establish that an API is unsupported. The RF route read existing results only. No scan was started and no controller, device, WLAN, or network setting was changed.

The temporary connector and secret-sync containers, both temporary images, source staging, probe scripts, credential files, and local staging were removed. A separate check confirmed their absence.

A separate read-only diagnosis found the timeline contains one sample just before the requested window and all observed negative score values equal `-1`. The API export does not explain that marker. The source now drops a boundary sample with an explicit count and maps -1 to a null score with an unclassified-marker field; the correction and controller health dispatcher were subsequently live reverified on source commit `500b0aac169c6287f8ee92ff43db464a94df8a9f`: both returned HTTP 200. The timeline returned 143 in-window points, explicitly discarded one boundary point and marked 715 unclassified -1 fields. The meaning of -1 remains undocumented. The six built source files matched the independently retrieved GitHub tree. Temporary containers, images and credentials were removed.
