# Security

This connector is under active development. An API operation, passing fixture, or route registration does not prove that it is safe or supported on every controller and device.

## Deployment

- Keep writes disabled unless an operator has reviewed the specific change flow and its controls.
- Bind the service to loopback or a protected private interface. Do not expose it directly to the public internet.
- Store controller credentials, caller tokens and optional approval keys in separate protected runtime files. Never commit them or place them in container images, logs, shell history or issue reports.
- Verify the controller certificate using the configured trust policy. Obtain certificate pins through a trusted channel.
- Run the container with minimal privileges. Do not mount the Docker socket or unnecessary host paths.
- Treat device names, network identifiers and diagnostic output as potentially sensitive, even when the connector projects or redacts fields.

## Changes and diagnostics

Writes are disabled by default. Supported change flows require a concrete preview, separate approval and readback; see [controlled changes](docs/CONTROLLED_CHANGES.md). These checks do not create an atomic transaction with other administrators. Do not automatically retry an uncertain write.

Some diagnostic operations may interrupt service or generate traffic. Obtain explicit operator approval before using an active diagnostic. The development build intentionally leaves several starts disabled where the documented API contract lacks a safe termination or result-correlation guarantee.

## Reporting a vulnerability

Please do not disclose suspected vulnerabilities or exposed credentials in a public issue. Use GitHub's private vulnerability reporting for this repository when it is enabled. If that option is unavailable, open an issue that only asks maintainers to establish a private reporting channel; do not include vulnerability details. Continue only after maintainers provide a private channel. Never attach credentials, controller addresses, packet captures or personal device data.

Private vulnerability reporting is not available while this repository is private. Immediately after a separately authorized public visibility change, maintainers should enable and verify a private reporting channel in repository settings. Until then, do not publish vulnerability details.
