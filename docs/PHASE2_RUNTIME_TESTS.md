# Phase 2 runtime evidence

## Scope

Phase 2 contains exactly one unauthenticated, read-only controller-info query.
The standalone connector sends only:

```text
GET https://<configured-controller>/api/info
```

The client rejects `http://`, requires a configured SHA-256 certificate pin,
and has no downgrade or login fallback. It does not mount secrets, read
credentials, send a login POST, use cookies, or request
`/api/v2/users/current`.

The route `/api/info` is recorded as empirically confirmed legacy/controller
Web API behavior for the target OC200. It is not claimed to be an official
TP-Link OpenAPI route. A `200` response without a valid `result.omadacId` is
reported as incomplete and is never returned as `verified`.

## Automated positive and negative tests

The test suite verifies, using disposable local HTTPS fixtures:

- positive `/api/info` response with certificate pin;
- redacted output: the raw controller ID is absent;
- exactly one `GET /api/info` and no `POST`;
- HTTP scheme rejection;
- missing-pin rejection;
- incomplete HTTP-200 rejection;
- unreachable-controller error without response-body leakage;
- runtime smoke success and bounded `502 controller_unreachable` failure.

The local negative runtime assertion is exact: an unreachable controller
returns HTTP 502 with `{"error":"controller_unreachable","status":"error"}`.
These are connector/fixture tests, not an OC200 live result.

## Approved new-image live test

The following facts come from the recorded project plan
`a169e993-8535-42ed-8f63-445b0ea6e111`. No live execution is repeated here.

### Build binding

- Tested source commit: `13f5e3d42a1490c85d9cd75a7e505a56d74e2d60`.
- The four staged files were read back on the host and their Git blob hashes
  matched the expected commit-bound values before building.
- The image was built from the local host context with
  `docker build --pull=false`; the image revision label matched the tested
  commit.

### Container and route proof

The temporary service container had no published host port and no mounts. It
ran on the bridge network with a read-only root filesystem, dropped
capabilities, and `no-new-privileges`. A separate short-lived probe container
from the new image used `--network container:<service>` and
`--entrypoint python3`, not `docker exec` and not a host-port request.

The probe queried all three HTTP routes in the new image:

- `/healthz` → `status=ok`;
- `/state` → `status=ready` and fixed query `/api/info`;
- `/omada/controller-info` → `status=verified`, fixed path `/api/info`, and
  `controller_id_present=true`.

The plan's exact verified output was:

```text
http=verified healthz=ok state=ready controller_info=verified
```

The last route performed the read-only OC200 request `GET /api/info` over HTTPS
with the already verified certificate pin. The connector returned a redacted
projection and did not expose `omadacId`. The plan receipt does not preserve
the raw OC200 response body or a controller version, so neither is claimed
here.

### Cleanup and current readback

The plan's third step verified:

```text
cleanup=verified container=absent probe=absent image=absent
```

A fresh read-only Docker inspection subsequently found both temporary container
names absent. The read-only share observer could not inspect the staging path
because it returned `permission_denied`; this is an observer limitation, not a
claim that the plan's earlier privileged hash readback failed.

The plan ledger records `executed` with all three steps `completed` and
`verified`. No OC200 configuration, managed device, or persistent Docker
service was changed.

## Limits

- `/api/info` is empirically confirmed for this OC200; it is not an officially
  documented TP-Link OpenAPI route.
- This phase is read-only and unauthenticated. It does not prove write access,
  authenticated API behavior, broader API coverage, or device-management
  operations.
- The live receipt proves the redacted connector projection and route checks;
  it does not prove the raw response body, controller version, or any other
  endpoint.
- The historical `/api/v2/users/current` path is not part of this connector.
- No OC200 or managed device is changed by this project.
