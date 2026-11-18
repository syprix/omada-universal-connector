# Operating and troubleshooting guide

The service is still under development. Read [security](../SECURITY.md) and
verify the exact controller support before use. No deployment or action is
performed by these instructions.

## Read-only preparation

1. Configure an Omada Open API application with the minimum required rights;
   verify its API documentation for the actual controller version.
2. Provision client ID, client secret and separate connector caller token as
   protected runtime files. Do not put secret values into shell commands,
   project files, logs or issue reports.
3. Obtain the controller certificate pin through a trusted independent path, or
   configure the documented system-CA trust mode as appropriate. The provided
   read-only Compose override uses a pin and binds the host port to loopback.
4. Review and follow the [local read-only example](../README.md#local-read-only-start-example),
   including UID, permissions and distinct host-side token file if the CLI runs
   under another user. Validate the rendered Compose config before starting.
5. Check `/healthz` and `/state`, then call protected inventory routes with the
   separate caller token. Inspect `partial` and per-route errors; a healthy
   process does not prove the controller or every route is reachable.

The diagnostic tool can be used with a known site reference or `--site-auto`
when exactly one valid site is available. Its optional selectors require a
controlling terminal. Refer to the README for command examples and limits.

## Guided setup check

After the connector is running, invoke `python3 tools/setup_check.py` on a
machine that can reach it. The command checks five steps independently:
controller configuration, the configured TLS certificate/CA policy, Omada
client authentication, read access to the site inventory, and an authenticated
MCP `initialize` handshake. The inventory check returns only a site count; it
does not print site names or references. Failures include a stable error code
and a short explanation, while later independent checks still run when
possible.

The default MCP address is `http://127.0.0.1:18080`. Set
`OMADA_CONNECTOR_URL` to another connector address when needed; unencrypted
HTTP is accepted only for loopback. For a host-side run, set
`OMADA_CONNECTOR_TOKEN_FILE` to the protected caller-token file available to
that user. Do not put the token itself in the environment or command line.
Controller settings and credential-file paths must also be available through
the existing `OMADA_*` runtime variables. The tool never starts a scan, changes
network configuration, exposes secret values, or runs automatically at
startup.

The controller stages send one OAuth client-credentials request after the TLS
check and perform a bounded site-inventory read after authentication. The
inventory read verifies only that endpoint's permission; other API routes can
require different Omada roles. The MCP stage checks one handshake, not whether
a specific agent application's configuration is correct. Fixture tests cover
the step separation and redacted results. No live setup check was performed
for this change.

## Configuration snapshots

The local snapshot tool uses the existing read-only Omada client. Supply a
site reference plus optional AP, SSID and LAN-network references, and pair
each selected object with a short neutral local label. Do not use actual
device, WLAN or network names as labels. Example:

```sh
python3 tools/config_snapshot.py capture \
  --site-ref "$SITE_REF" --site-label home \
  --ap-ref "$AP_REF" --ap-label living-room-ap \
  --ssid-ref "$SSID_REF" --ssid-label guest-wifi \
  --network-ref "$NETWORK_REF" --network-label guest-lan \
  --output "$SNAPSHOT_PATH"
python3 tools/config_snapshot.py compare "$BEFORE_PATH" "$AFTER_PATH"
```

Controller references are used only for the bounded reads and are not written
to the snapshot. The file keeps only the connector's existing redacted radio,
SSID, LAN-detail and site DNS projections; resolver values, names, raw
references, addresses and credentials are excluded. Files are created with
owner-only permissions and are never overwritten. Use a new output filename
for each capture. Snapshots are local data; choose a protected directory and
do not attach them to reports without reviewing the selected settings.

Comparisons require the same site label. Only fields present in both complete
projections are compared. Missing fields and partial source responses are
reported as `not_comparable`, not as unchanged. VLAN settings are limited to
the numeric VLAN value returned by the existing redacted LAN-detail route;
the tool does not infer a setting from the separate aggregate VLAN summary.
Object labels are operator-supplied and do not prove the same controller object
was selected for both captures; the tool intentionally stores no object refs.
No live capture was performed for this change.

## Troubleshooting

| Observation | What to check |
|---|---|
| Protected route disabled | Caller-token and upstream credential file configuration; file ownership/mode; restart after changing the process environment. |
| Authentication failure | Connector caller token versus separate controller app credentials and the app's actual privileges. Do not print their values. |
| TLS failure | Controller origin, certificate and chosen CA/pin policy; do not disable verification as a workaround. |
| Controller responds with an error | Inspect redacted error category and controller documentation; HTTP success alone is not proof of operation success. |
| Missing values or `partial` | Device, firmware, permissions, collection window and projection limits. Missing data is not zero and not proof of lack of support. |
| Operation `in_doubt` | Do not automatically repeat. Check actual controller state and the plan journal; follow the documented close/verification procedure before making a new plan. |
| Missing action or MCP tool | Consult the current route list; scan starts and MCP are planned, not available today. |

For controlled changes, see [CONTROLLED_CHANGES.md](CONTROLLED_CHANGES.md).
No built-in rollback is guaranteed. Applying a plan requires all configured
controls and explicit authorization for that specific real-world change.
