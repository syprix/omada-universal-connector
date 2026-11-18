# Contributing and verification

Contributions are welcome under the terms of [GPL-3.0-only](LICENSE). Before opening a change, review the [current status](docs/STATUS.md), [roadmap](docs/ROADMAP.md), route contract and [security boundaries](SECURITY.md).

Use GitHub Issues for general questions, bug reports and feature requests. No response time is promised. Keep vulnerability details and private network data out of public issues; see [security reporting](SECURITY.md).

## Development practice

1. Start from the current default branch and keep credentials, controller identifiers and real network data outside the repository.
2. For each Omada operation, record the source contract and verify its method, path, parameters, permissions and documented behavior. A catalog row is not an implementation.
3. Keep routes fixed and bounded. Do not add arbitrary controller URLs, generic proxying, or undocumented field assumptions.
4. Add focused tests for successful responses, malformed or incomplete data, permissions and uncertain outcomes. Separate fixture results from live controller and agent-client evidence.
5. Update the relevant user guide and dated status entry. Do not claim broader compatibility than the evidence supports.
6. Keep changes reviewable and related. Do not perform live scans, measurements or configuration changes as part of routine tests.

## Local checks

Run the existing offline checks relevant to the change:

```sh
python3 -m unittest discover -s tests -q
python3 tests/smoke_runtime.py
```

The CI workflow also checks the read-only Compose configuration and builds an isolated container. CI results must be read from the exact commit; a local test run does not establish that hosted CI passed or that a controller operation works live.

Do not commit secrets, real controller exports, packet captures or customer network data. The three supplied manufacturer OpenAPI exports are not redistributed. Before adding manufacturer-derived or other third-party material, verify that redistribution is permitted and update [third-party notices](THIRD_PARTY_NOTICES.md).

By submitting a contribution, you agree that it is distributed under this project's GPL-3.0-only license. You must have the rights needed to submit it. No separate CLA is currently specified.
