# Change history

## Unreleased development

- Added fixed authenticated HTTP reads and stateless MCP tools for selected Omada controller, site, device, client, WLAN, gateway and switch data.
- Added bounded WLAN and network diagnostic summaries that combine existing reads without starting active scans or measurements.
- Added selected preview-and-approval configuration changes. Writes remain disabled by default; live evidence varies by operation.
- Recorded a verified apply-and-restore round trip for one supported AP QoS setting on one controller installation.
- Continued operation-level API contract, fixture, HTTP and MCP checks. These do not imply universal device support or live verification.
- Kept the offline OpenAPI catalog as reference metadata; it does not enable routes or represent implementation coverage.

This is a development history, not a release announcement. See [status and evidence](docs/STATUS.md) for dates, tested scope, and remaining work.
