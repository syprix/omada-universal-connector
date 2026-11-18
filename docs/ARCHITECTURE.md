# Historical Phase 2 architecture

This records the earlier three-route Phase 2 baseline. The current private
development branch has additional authenticated Open API reads; see
[OPENAPI_READ_ONLY.md](OPENAPI_READ_ONLY.md) and [STATUS.md](STATUS.md) for the
current boundary. The diagram below is historical.

```text
HTTP caller
   |
   v
Python HTTP layer
   |-- GET /healthz                 -> process status
   |-- GET /state                   -> fixed connector state
   `-- GET /omada/controller-info  -> redacted controller-info result
                                      |
                                      v
                               OmadaClient
                                      |
                         HTTPS + SHA-256 certificate pin
                                      |
                              fixed GET /api/info
                                      |
                                      v
                              target OC200 controller
```

## Implemented components

- **Historical HTTP layer:** exposed exactly the three documented connector routes and
  returns bounded JSON responses.
- **Omada client:** accepts only HTTPS, requires the configured certificate
  pin, sends only `GET /api/info`, and rejects caller-selected paths.
- **Redaction boundary:** requires a valid `result.omadacId` for a verified
  result but returns only a presence flag, a hash reference, and an optional
  version. The raw controller ID and response body are not returned.
- **Container boundary:** runs as a non-root user with a read-only root
  filesystem, dropped capabilities, and `no-new-privileges` in the verified
  temporary runtime. No controller port is published by that test.
- **Failure boundary:** controller and validation failures become stable,
  redacted error codes; the local unreachable-controller case returns bounded
  HTTP 502 with `controller_unreachable`.

## Deliberate non-components

Phase 2 contains no login flow, session-cookie handling, token handling,
secret mount, authenticated user query, write route, device mutation, or
arbitrary controller-path proxy. `/api/info` is empirical legacy/controller
Web API behavior for the target OC200, not a claim of official TP-Link OpenAPI
coverage.
