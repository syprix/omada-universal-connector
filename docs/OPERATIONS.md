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
