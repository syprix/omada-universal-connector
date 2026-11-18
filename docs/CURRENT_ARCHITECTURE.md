# Current architecture

## Boundaries

```text
Authenticated caller -> connector HTTP service -> fixed Omada Open API client
                           |       |                       |
                     projections  change plans      HTTPS + trust policy
                           |       |                       |
                     redacted data |                   controller
                                   |
                      optional journal and approval
```

The connector is an independent service with a Docker image and a versioned
HTTP interface. `/healthz` and `/state` describe the service. The protected
`/v1` routes require a separate connector caller token. A legacy controller-info
read uses `/api/info`; that empirically observed path is not presented as an
official TP-Link Open API operation. Refer to the README for actual routes.

The upstream client uses runtime credential files, validates the configured
HTTPS origin and applies either system CA and hostname verification or the
explicitly configured certificate pin. The older controller-info path requires
a pin. Failure of one trust mode does not silently enable another. Timeouts,
pagination and response limits are bounded. The local OpenAPI catalog parser
reads supplied export files offline; the catalog is not an upstream proxy and
never grants access or enables an operation.

## Data and capabilities

Implemented reads project allowlisted fields rather than returning arbitrary
controller responses. Site/device references are opaque. Descriptive names are
disabled by default and require explicit opt-in. Missing and unclassified data
can produce `partial`; unknown extra AP-health fields have a known exception:
their omission alone does not necessarily mark `partial`. Consult the route
contract instead of interpreting `partial=false` as complete coverage.

Capability observations are process-local and incomplete. Documentation,
implementation, fixture coverage and live controller support are separate
facts. An upstream HTTP success can still contain an application error.

## Changes and reliability

Writes default to off. Implemented change types use explicit previews,
per-plan approval, pre-send checks and a readback where available. Applying
requires the configured caller token, write opt-in, persistent reference key,
journal and separately provisioned approval key. Uncertain dispatches are
`in_doubt`, are not replayed automatically and require investigation.
The journal is single-process and is not a tamper-proof audit log. The HMAC
mechanism proves key possession, not an independently authenticated person.
See [controlled changes](CONTROLLED_CHANGES.md) for exact requirements and
known limitations. No claim of live write verification follows from fixtures.

## Agent interfaces and diagnostics

The service exposes an authenticated, stateless MCP endpoint at `POST /mcp`
alongside its fixed HTTP API. The registry includes one hundred forty-eight fixed GET
operations and six bounded workflows: four WLAN workflows for site health,
client connectivity, AP diagnosis and AP comparison, plus gateway and switch
network diagnosis. The switch bundle includes health, its score timeline, SDM
category/capacity codes, stored cable-test logs, port eligibility, DHCP type/binding counts, OSPF neighbor-state counts, VLAN-by-port/LAG summaries, configured-network VLAN/type counts, network status/mode counts and full/incremental results, port state, counters, PoE,
VLAN membership and LLDP. Each workflow uses declared routes and current opaque
inventory references; callers cannot supply controller paths. The workflows
read stored results and counters only and do not initiate scans, tests or
changes. Site WLAN health includes redacted counts from stored rogue-AP scan rows; AP diagnosis includes the documented LLDP setting and support flag plus compact AP port-VLAN counts; separate P2P bridge, mesh-candidate and group-membership summaries redact credentials and AP identities. Standalone AP general-configuration, IPv4 management, IPv6 management, L3-access and SNMP-setting, AP VLAN v1 and AP WLAN override reads omit names, tags, addresses, network identifiers, passwords and custom contact/location text. The mesh read only summarizes the documented pre-adoption candidate list. Hermes, Codex and Claude connection settings are documented, but no
end-to-end client handshake has been tested. Browser access is deferred. See
[integrations](INTEGRATIONS.md), [MCP details](MCP.md) and the
[roadmap](ROADMAP.md).
