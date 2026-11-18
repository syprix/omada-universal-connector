# Planned functions

This is the earlier Phase 2 planning snapshot. Some read-only inventory and
AP diagnostics have since been implemented in the current development build;
the [current status](STATUS.md) and [route contract](OPENAPI_READ_ONLY.md)
take precedence. The remaining items are possibilities, not commitments to
API paths or device support.

## Planned read-only functions

- **Controller capability inventory:** report only controller resources and
  API capabilities that are explicitly verified for the installed firmware.
- **Device status inventory:** expose redacted read-only status for managed APs,
  switches, gateways, and other devices after a fixed, allowlisted read path
  is verified.
- **WLAN and client status:** expose read-only WLAN, client, roaming, and
  health summaries through fixed allowlisted queries.
- **Firmware/update status:** report device firmware versions and update flags
  without starting an update.
- **Structured diagnostics:** provide bounded, redacted diagnostics with stable
  error codes and freshness metadata.

## Planned security/integration functions

- **Private consumer integration:** a future profile-bound adapter needs its
  own secret boundary, scope and revocation path. The standalone connector's
  current Open API routes already read runtime client credentials and require
  a separate caller token.
- **Consumer integration adapter:** expose verified results through a fixed,
  authenticated connector contract with direct readback and redaction.
- **Audit/readback records:** persist non-secret operation IDs, target identity,
  route, result classification, and verification timestamps.

## Explicitly not planned for the current phase

- No arbitrary URL or path proxy.
- No unauthenticated write operation.
- No controller or managed-device mutation.
- No reuse of the historical `/api/v2/users/current` login/session path.
- No claim that `/api/info` is an official TP-Link OpenAPI route.

Any future write function or additional authentication provider requires a
separate design, allowlist, approval boundary and live verification. This list
itself does not authorize execution.
