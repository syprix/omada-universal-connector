# Omada Universal Connector

A self-hosted HTTP and MCP connector for selected TP-Link Omada controller data and bounded network diagnostics. It gives automation clients a small, authenticated interface for common WLAN and network checks, while keeping controller credentials and access controls under the operator’s control.

This is an active development build. The connector does not provide a generic controller proxy, complete coverage of the Omada API, or universal controller compatibility.

## What it can do

The current development build includes:

- Fixed, authenticated HTTP reads for selected controller, site, device, client, WLAN, gateway and switch data.
- A stateless MCP Streamable HTTP endpoint at `POST /mcp`, with fixed reads and bounded diagnostic workflows.
- Reusable WLAN and network summaries that combine selected existing controller data and omit many raw identifiers. These workflows do not start scans or change settings.
- Selected, narrowly scoped configuration previews and separately approved changes. Writes are disabled by default. Each operation has its own implementation and evidence status; see [controlled changes](docs/CONTROLLED_CHANGES.md).
- An offline reader for user-supplied OpenAPI exports. Its catalog is reference metadata, not a list of implemented or live-tested connector features.

The [capability evidence](docs/CAPABILITIES.md) and [status record](docs/STATUS.md) describe operation-level behavior and limits. A route or test fixture alone does not establish support on a real controller.

## Development status

The [core-function roadmap](docs/ROADMAP.md) names all fifteen agreed functions and separates accepted work, hardware checks still pending, and the active-diagnostics gap. Fourteen functions meet their documented acceptance scope. The remaining function covers active diagnostics: a bounded, approved switch cable-test flow is implemented and tested offline, but still needs compatible switch hardware for its hardware check. Other scan and measurement starts remain disabled where the API contract does not establish safe completion, cancellation, or result freshness. A clarification from TP-Link is pending.

One AP QoS setting was changed and separately restored on a single tested installation. That verifies this narrow path, not every change route, controller model or firmware. See the dated [status and evidence](docs/STATUS.md) for the full test boundary.

## Compatibility and integration tests

The only end-to-end controller evidence in this development build is from one OC200 running Omada Controller 6.3.0.45, using selected operations. The read-only controller probe and MCP site, device and client calls were verified there. Other controller families, releases, device models and firmware combinations are not certified; several documented routes have unknown live support.

- **Codex:** MCP handshake and three read calls passed in a temporary, loopback-only setup on 2026-11-13.
- **Claude Code:** setup notes are prepared; the client was unavailable for an end-to-end test.
- **Other MCP clients:** not tested; protocol and HTTP fixture tests do not establish client compatibility.
- **Offline checks:** fixtures and protocol tests are not live controller or agent-client tests.

See [integration evidence](docs/INTEGRATIONS.md) and the [controller compatibility notes](docs/CONTROLLER_COMPATIBILITY.md).

## Quick start with Docker Compose

Requirements: Docker Engine with the Compose plugin, an Omada Open API application with the required read permissions, and a trusted HTTPS endpoint for the controller.

1. Clone the repository and create a protected local directory for three separate files: the Open API client ID, the client secret, and a connector caller token of at least 32 printable ASCII bytes. Keep the files out of version control. For example, run `mkdir -p secrets && chmod 700 secrets`, then provision the files from your secret store. Follow the ownership and permissions in [the read-only Compose example](compose.read-only.example.yaml); the container runs as UID 10001.
2. Set the non-secret values in your shell:

   ```sh
   export OMADA_BASE_URL='https://your-controller.example'
   export OMADA_CONTROLLER_ID='your-controller-id'
   export OMADA_CERT_SHA256='your-64-character-certificate-sha256-pin'
   export OMADA_CLIENT_ID_HOST_FILE="$PWD/secrets/client-id"
   export OMADA_CLIENT_SECRET_HOST_FILE="$PWD/secrets/client-secret"
   export OMADA_CONNECTOR_TOKEN_HOST_FILE="$PWD/secrets/caller-token"
   ```

   The example uses a SHA-256 certificate pin. Obtain and verify the pin through a trusted channel. Do not disable TLS verification.
3. Validate and start the read-only service:

   ```sh
   docker compose -f compose.yaml -f compose.read-only.example.yaml config
   docker compose -f compose.yaml -f compose.read-only.example.yaml up --build -d
   ```

   The published port is bound to host loopback at `127.0.0.1:18080`. Writes remain disabled. Check `GET http://127.0.0.1:18080/healthz` for process health. Protected routes require the caller token as a Bearer credential.

For the MCP endpoint and client-specific examples, see [MCP setup](docs/MCP.md). Review [security guidance](SECURITY.md) and [operations](docs/OPERATIONS.md) before connecting an agent or exposing the service to another host. Do not put credentials in Compose environment values, shell history, logs or issue reports.

### Local WLAN summary

The optional Python CLI combines existing read-only connector routes. Run it on the host with a separate caller-token file owned by the host user; do not reuse the container-mounted token file.

```sh
python3 tools/wifi_diagnose.py \
  --site-auto \
  --token-file /path/to/host-caller-token \
  --format text
```

The default connector URL is the local Compose listener. The CLI can also select an AP or client from the selected site's inventory; see `python3 tools/wifi_diagnose.py --help` for its bounded options. It does not contact Omada directly or start active scans.

### Guided setup check

With the runtime settings available to the local user, run `python3 tools/setup_check.py` to check controller TLS, Omada authentication, site-inventory read access, and one authenticated MCP handshake separately. See the [setup-check details](docs/OPERATIONS.md#guided-setup-check); this explicit command makes bounded read requests and never starts a scan or changes settings.

### Compare configuration snapshots

Use `python3 tools/config_snapshot.py capture` to save selected AP radio, SSID, LAN-network and site DNS settings with a schema version. Give selected objects short neutral labels rather than their device or network names; the snapshot omits controller references, addresses and secret values and is created with owner-only permissions. The comparison marks partial or missing fields as not comparable. See the [snapshot procedure](docs/OPERATIONS.md#configuration-snapshots).

### WLAN walk session

For a deliberately started walk test, the separate session tool polls one wireless client's current read-only detail through the local connector and writes JSON Lines to a new file with owner-only permissions:

```sh
python3 tools/wifi_measurement_session.py \
  --site-ref <site-ref> \
  --client-ref <fresh-client-ref> \
  --token-file /path/to/host-caller-token \
  --output ./walk-session.jsonl \
  --duration-seconds 120 \
  --interval-seconds 5 \
  --max-samples 24
```

Client references are short-lived and must come from the current site inventory. The session makes repeated GET requests via the local connector; it does not send probes, start scans or change controller settings. The duration, interval and sample count are capped, and Ctrl+C or SIGTERM closes the file with a stop record. Existing files are never overwritten. Samples contain signal metrics and a site-bound AP reference when the local inventory resolves it; they omit site/client references, raw MAC addresses and credentials. Run it only during an authorized measurement.

Two saved sessions can be compared without a connector or network connection:

```sh
python3 tools/wifi_compare_sessions.py \
  --first ./walk-session-a.jsonl \
  --second ./walk-session-b.jsonl
```

The comparison aligns samples only when their duration, interval and sample limits match. It reports raw signal differences, per-session AP change counts and missing/non-wireless samples; it does not match AP references across separate files or infer an outage cause.

### Import device measurements

Import an explicitly documented CSV or JSON export offline with `python3 tools/import_device_measurements.py --input ./measurements.json --format json`. The importer limits file size and row count, requires timezone-qualified timestamps, drops names, addresses and raw identifiers, and labels declared source types as unverified. It makes no controller calls or network probes; see [the input format](docs/CORE_READ_WORKFLOWS.md#device-measurement-import).

Compare those observations with a saved `wifi_diagnose.py --client-timeline` JSON report and a passive WLAN session using an explicit UTC-millisecond window and tolerance: `python3 tools/compare_device_measurements.py --device-input ./measurements.json --device-format json --client-timeline ./client-timeline.json --session ./walk-session.jsonl --start-ms 1800000000000 --end-ms 1800000300000 --tolerance-ms 5000`. This offline comparison reports source coverage and age, and only compares device Wi-Fi state with an explicit passive wireless/not-wireless sample; it does not infer a cause.

For a gateway incident review, call `GET /v1/sites/{site_ref}/gateways/{gateway_ref}/wan-incident-window?start_ms=...&end_ms=...` or MCP tool `omada_gateway_wan_incident_window`. It bundles current WAN codes, the gateway's timestamped health history and score timeline, and saved speed-test counts. Unknown codes remain undecoded; undated incident counts and saved tests are not placed on the timeline. Load-balancing participation and outage cause remain unknown where the API response does not define them.

## Project documents

- [Current architecture](docs/CURRENT_ARCHITECTURE.md)
- [Capabilities and evidence](docs/CAPABILITIES.md)
- [Roadmap](docs/ROADMAP.md)
- [HTTP read contract](docs/OPENAPI_READ_ONLY.md)
- [MCP endpoint and client setup](docs/MCP.md)
- [WLAN and network workflows](docs/CORE_READ_WORKFLOWS.md)
- [Security](SECURITY.md) and [controlled changes](docs/CONTROLLED_CHANGES.md)
- [Contributing and verification](CONTRIBUTING.md)
- [Community standards](CODE_OF_CONDUCT.md)
- [Change history](CHANGELOG.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)
- [Open-source release checklist](docs/RELEASE_CHECKLIST.md)

Questions, bug reports and feature requests go through GitHub Issues. No response time is promised. Do not post credentials, private network details or vulnerability information in a public issue.

## License

The connector code is provided under the GNU General Public License v3.0 only. You may use, study, change, and redistribute it under the terms in [LICENSE](LICENSE). Third-party components and manufacturer materials keep their own terms; see [third-party notices](THIRD_PARTY_NOTICES.md).
