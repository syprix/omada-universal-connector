# Core functions and remaining work

The project uses fifteen end-to-end functions as its core acceptance plan. A function is complete only when its required connector behavior and evidence exist; a route catalog entry or fixture alone is not sufficient. The table records the current acceptance scope, not universal controller support.

## Core acceptance status

| # | Function | Current status |
| ---: | --- | --- |
| 1 | Secure controller connection | Accepted for the tested client-credentials and TLS paths. Live evidence is from one controller installation. |
| 2 | Agent connection over HTTP/MCP | Accepted: Codex completed a real MCP handshake and three calls. Claude Code and other clients have not been tested end to end. |
| 3 | Device and site overview | Accepted for bounded site, device and client inventory on one tested installation. |
| 4 | Capability detection | Accepted for the documented process-local report and site capability projections. Unknown support remains explicit. |
| 5 | Network overview and topology | Accepted as a bounded workflow; some live sections can be partial or unavailable. |
| 6 | Full Wi-Fi diagnosis | Accepted for the implemented read-only diagnostic workflows. They use stored controller data and do not start scans. |
| 7 | Client and roaming diagnosis | Accepted for the scoped inventory-bound summaries and their documented limits. |
| 8 | AP comparison and radio analysis | Accepted for the scoped read-only comparison and radio summaries. Live support varies by operation. |
| 9 | Gateway and Internet diagnosis | Accepted for the bounded health and stored-result workflows. It does not start tests or probes. |
| 10 | Switch, port and PoE diagnosis | Implemented and accepted offline. Hardware verification is deferred because no compatible switch was available. |
| 11 | LAN, VLAN, DHCP and DNS overview | Accepted for the bounded, redacted reads and summaries in the current contract. |
| 12 | Evaluate events and warnings | Accepted for the scoped redacted event, alert and diagnostic summaries. Unknown field meanings are not inferred. |
| 13 | Change Wi-Fi and radio settings | Accepted for the documented guarded scope. One supported AP QoS setting was applied and separately restored on one installation; this does not live-verify every change route. |
| 14 | Control switch ports and PoE | Implemented and accepted offline. Hardware verification is deferred because no compatible switch was available. |
| 15 | Run active diagnostic tests | In progress. A bounded, approved switch cable-test workflow is implemented and tested offline; its hardware check awaits a switch. Other scan and measurement starts remain disabled until their contracts establish safe bounds, termination and result freshness. |

See [status and evidence](STATUS.md), [capability records](CAPABILITIES.md), and [operation evidence](OPERATION_EVIDENCE.json) for operation-specific sources and test boundaries.

## Work after the core functions

After function 15 meets its acceptance criteria, continue the overall API coverage work by reviewing remaining operations family by family against the three supplied API exports. The current operation-level item is a site-level switch-health timeline using the documented batch read, with a 24-hour bound, fresh inventory binding, redaction and explicit gaps. This is continued operation-level coverage, not a promise that every vendor operation can or should be exposed.

## Follow-on read workflows

| # | Function | Current status |
| ---: | --- | --- |
| 11 | Import device measurements | Implemented for bounded CSV/JSON with explicit timestamps, source labels, and local privacy filtering; fixture-tested offline. |
| 12 | Compare device and Omada history | Implemented for explicit windows and tolerances against saved client timelines and passive sessions; fixture-tested offline. |
| 13 | WAN load-balance status | Open: the source response has no documented status fields, so line availability, participation, and failover are not labeled. |
| 14 | WAN incident window | Implemented as a compact HTTP/MCP report combining current status codes, time-bounded gateway health, score history, and saved test counts. Untimed observations remain separate; no cause or load-balance participation is inferred. |
| 15 | DHCP pool utilization | Implemented as a bounded HTTP/MCP report of documented per-network pool capacity, available addresses, and dynamic/static lease counts. Lease-to-pool membership is unspecified, so address occupancy is not inferred. Fixture-tested offline; live support remains unverified. |
| 16 | DNS incident diagnosis | Implemented as an offline CLI joining bounded imported device observations with optional redacted DNS settings and WLAN/network context. Cross-source disagreements and missing evidence remain explicit; it makes no probes and infers no cause. Fixture-tested. |
| 17 | AP quality history | Implemented as a shared-window HTTP/MCP report of hourly health-score and retry/drop summaries plus current per-band radio settings; saved passive sessions can be joined offline by opaque AP reference. Unspecified scales, absent rows and site-binding gaps remain explicit. Fixture-tested; no live request or scan. |

The agreed coverage families are:

- Controller and system information and settings.
- Site health, dashboards, analytics and reports.
- WLAN, access point, client and roaming data.
- Gateway, switch, port and PoE data.
- LAN services, including VLAN, DHCP and DNS.
- Events, alerts and stored diagnostic results.
- Individually reviewed configuration changes where the source contract, permissions, safeguards and verification path support them.

Many operations in these families already have a connector route; the remaining gap is operation-specific. For each candidate, establish the exact source contract and response fields, implement a bounded fixed operation, add focused failure/redaction tests, and report live support separately. Do not infer support from a catalog match.

## Active diagnostics boundary

Some documented start operations can disrupt service or create sustained activity. Before enabling one, the source contract must establish a bounded duration or reliable stop, a way to verify terminal state, and a way to associate results with the requested run. Until then the connector leaves that action disabled. No live scan or measurement is implied by this roadmap.
