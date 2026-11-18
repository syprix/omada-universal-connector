# Controller integration approach

The connector uses fixed, authenticated operations for documented controller capabilities. The goal is to expose useful behavior supported by the controller release, device firmware, API permissions and a verified request contract; it does not promise every vendor API operation or universal device compatibility.

## Supported integration layers

1. **Official Omada Open API:** Use the version-specific API document from the controller as the source for method, path, parameters, response fields and permissions. Keep authentication modes and trust policies explicit.
2. **Version-specific controller APIs:** Consider an additional adapter only for a confirmed gap, with independent versioning and evidence. Do not add arbitrary URL/path proxying or silently fall back between API families.
3. **Device-specific APIs:** Consider only when a needed function is not available through the controller and the device interface can be verified and safely bounded.

Each operation needs a known request and response contract, permission requirements, input/output bounds, redaction, failure behavior and evidence state. Reads and controlled changes are tracked separately. Changes require a target-bound preview, separate approval, readback and documented rollback limits; writes remain disabled by default.

## Evidence states

Record separately whether an operation is documented, implemented, covered by fixtures, verified against a live controller, permission-limited, unsupported or unknown. A path match, HTTP success status or fixture result does not prove device or firmware support.

## Remaining coverage

After the fifteen core functions meet their acceptance criteria, review remaining operations from the three supplied API exports by family. The specific next operations and order are not yet prioritized. See the [roadmap](ROADMAP.md), [capability evidence](CAPABILITIES.md) and [release checklist](RELEASE_CHECKLIST.md).

## Release boundary

Before distributing source or a container image, review the rights for included materials, third-party notices, source availability, security settings and support scope. Controller addresses, identifiers, credentials, logs and live inventory do not belong in source control or images. The original manufacturer API exports are excluded pending redistribution-rights confirmation.

The controller's own Online API Document and installed firmware remain the authoritative sources for a specific deployment.
