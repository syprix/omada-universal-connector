# Scaling plan: operation registry and bounded execution

**Status:** staged technical refactor. Eight inventory and health GETs now use the registry
for public routing; other routes, upstream allowlisting and capability/matrix
metadata remain on the existing implementation. This is not a claim of live
support. Documented, fixture-tested, source-matched and live-verified operations
remain distinct states.

## Goal and boundary

Scale the connector from its current small route set toward a much larger
catalog (potentially 2,445 documented operations) without turning it into an
arbitrary controller proxy. Every callable operation must have an explicit,
reviewed contract and a fixed adapter. Unknown paths, methods, parameters,
headers, and bodies remain rejected.

## One operation registry

Introduce a version-controlled declarative registry as the sole source for
public routing, upstream allowlisting, capability entries, and offline matrix
source matching. Each entry should define:

- stable operation ID and registry/schema revision;
- public method and fixed route template;
- fixed upstream API family, controller-version range, method, and path template;
- access class (read or individually controlled write), required permission,
  and authentication provider;
- typed path/query/body input schema, required fields, bounds, and defaults;
- response schema/projection, redaction rules, and maximum payload/page limits;
- semantic contract revision and evidence state, with links or hashes for
  source specification, fixtures, and live verification where available.

Compile and validate the registry at startup. Reject duplicate public routes,
duplicate IDs, unbound path variables, unsupported methods, missing schemas,
unbounded arrays/strings, and any write entry lacking its explicit policy.
The router dispatches only by registry ID to a named adapter. The upstream
request builder accepts that adapter's fixed template and validated values;
it never accepts a caller-supplied path or URL. No generic proxy/fallback is
added.

Capabilities and the matrix are generated from registry metadata, but report
separate states: documented, implemented, fixture-tested, live-verified,
permission-denied, unsupported, or unknown. A path match alone must never
upgrade contract compatibility or live support. Compare semantic input and
response contracts, not just method/path. Preserve source document hashes and
version labels so controller-specific variants remain visible.

## Reference safety and concurrency

Replace the single lock around full upstream requests with short state locks
and a bounded per-controller request limiter. Keep each multi-step operation
atomic with respect to the reference state it consumes:

1. Under the state lock, resolve opaque references and capture the relevant
   site/device/client inventory generation plus immutable raw identifiers.
2. Release the state lock for network I/O while retaining the captured
   generation and target binding.
3. Before committing refreshed maps or returning a detail result, reacquire
   the lock and verify the relevant generation is unchanged. If a refresh
   invalidated the binding, fail with a stable stale-reference error; never
   silently apply a response to a different target.
4. Publish each refreshed inventory as one atomic snapshot. Bind child
   references to their parent site and inventory generation. Keep refresh
   invalidation rules explicit per reference type.

Bound concurrent requests, connection time, retries (if any), response bytes,
and queued work. Do not retry writes automatically. A concurrency limit of one
is a valid initial setting; increase it only after race tests and measured
controller behavior support it.

## Explicit pagination

Keep hard bounds, but expose pagination to callers instead of requiring the
connector to aggregate an entire inventory. A continuation token should be
opaque, integrity-protected, size-bounded, and bound to operation ID, site
reference, filters, page position, controller/config generation, and expiry.
Reject tampering, cross-operation/site reuse, expired tokens, and changed
filters. Return explicit `next_cursor`/completion metadata. Never return a
partial inventory as complete: upstream page-limit, response-limit, or
consistency failures produce a stable incomplete/error result. Document the
maximum page size and total work budget for each operation family.

## Privacy and diagnostics

Public responses, capability reports, matrix output, and logs must not expose
controller URLs/hostnames, credentials, access tokens, raw controller/site/
device identifiers, or raw upstream bodies. Use stable error codes and opaque
references. Source hashes and version labels are acceptable; sanitize any
operator-supplied labels before export. Tests should assert sensitive values
are absent from responses and logs, including on exceptions.

## Verification and rollout

1. **Inventory only:** generate registry candidates from current routes and
   matrix; review duplicates, semantic schemas, permissions, redaction, and
   controller-version variants. No runtime behavior changes.
2. **Shadow validation:** run existing requests through registry validation
   while retaining the current dispatch path. Compare route decisions and
   outputs on fixtures; report differences without sending extra controller
   calls.
3. **Read-only cutover:** switch a small operation group at a time. Require
   route/schema tests, negative arbitrary-path tests, contract variant tests,
   pagination completeness tests, concurrency/reference race tests, and
   redaction tests before each group.
4. **Controlled writes last:** migrate no write until its request schema,
   precondition, one-shot dispatch, readback, uncertainty handling, and
   rollback limits have dedicated review and tests. Keep writes disabled by
   default.
5. **Evidence update:** update live status only from bounded, authorized
   verification on the named controller/version. Fixtures and offline matrix
   matches remain labeled as such.

At each cutover, keep the previous dispatcher and registry revision available
for rollback. Roll back by configuration/commit to the last known-good route
group; do not alter controller state as part of rollback. Preserve evidence
and error reports. If the registry is invalid or a contract mismatch occurs,
fail closed for that operation and retain unaffected operation groups.

## Acceptance criteria

- Registry is the only maintained source for the four inventories above.
- No caller-controlled upstream URL/path/method or unbounded generic operation
  exists.
- Contract version and evidence state are explicit per operation and controller
  family; docs/source matches are never represented as live verification.
- Reference refreshes cannot redirect in-flight work across target bindings.
- Concurrency and pagination limits are enforced, observable through redacted
  stable codes, and cannot silently produce incomplete success responses.
- Staged rollback is documented and exercised before broad cutover.

## First staged cutover evidence

The public dispatcher now uses the registry for five inventory GET routes and
three controller/site health GET routes. All other routes, upstream allowlisting,
capability metadata and matrix matching still use the existing code. A loopback
shadow test compares the eight routes and their auth/negative cases. The
current image was built from hash-matched source files without build networking;
its direct entrypoint started in a temporary network-isolated, non-root,
read-only container. Health returned 200, the unconfigured inventory and
capability routes returned 503, and writes remained disabled. The test image,
container and source staging were removed. This is not live-controller
verification of the refactored routes.
