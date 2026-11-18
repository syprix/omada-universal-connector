# Release readiness

This checklist tracks evidence and remaining work before public contributions or distribution. An unchecked item remains open; this page does not itself publish or release the project.

## Verified

- [x] Fourteen of the fifteen agreed core functions meet their documented acceptance scope. Active diagnostics remain in progress and are described accurately in [status](STATUS.md).
- [x] The application, tests, and tooling prepared for the 2026-11-18 launch match the source that passed 2,980 offline tests and the runtime smoke check.
- [x] The exact source built with Docker using networking disabled. A read-only, credential-free container reached healthy status and was removed after the check.
- [x] Docker Compose 5.8.0 base configuration and isolated smoke startup were checked. The smoke build and container had no network or published ports, and the read-only container reached healthy status.
- [x] The project license remains GPL-3.0-only and third-party notices are included. See [third-party notices](../THIRD_PARTY_NOTICES.md) for the components and distribution notes.
- [x] A measured live network-overview workflow serialized to 1,630 tokens, compared with 6,416 tokens for twelve separate reads. The measurement limits are documented in [status](STATUS.md).

## Open

- [ ] Complete the active-diagnostics acceptance scope. The cable-test hardware check awaits a compatible switch; other active starts remain disabled while upstream API lifecycle and result-correlation guarantees are unavailable.
- [ ] A GitHub account restriction prevented hosted CI from starting; no hosted test result is available. Confirm a successful hosted CI run before relying on hosted checks for a release.
- [ ] Configure and verify branch protection and the intended least-privilege Actions settings on the release repository before accepting public contributions.
- [ ] Enable and verify the appropriate vulnerability-reporting and security-contact path before inviting public contributors.
- [ ] Before distributing a container image, record its base digest and architecture, inventory bundled components, and preserve the applicable source and notices.

The current evidence is limited to the specific offline suite, smoke checks, controller operations, and client flows described in the project documentation. It does not establish universal API, device, firmware, or client compatibility.
