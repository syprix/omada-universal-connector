# Third-party notices and distribution notes

The connector's own code is licensed under [GNU GPL version 3](LICENSE)
(`GPL-3.0-only`). Third-party components retain their upstream licenses and
notices.

| Component | Role | License and source |
| --- | --- | --- |
| CPython 3.13 and its standard library | Runtime. The connector installs no additional Python packages. | PSF license and component-specific notices in the [Python 3.13 license](https://docs.python.org/3.13/license.html). Python documents GPL compatibility for this version. |
| Docker Official Image `python:3.13-alpine` | Base image | The [upstream Docker packaging](https://github.com/docker-library/python) and the Python and Alpine components inside the image have separate terms. |
| `actions/checkout` v4.2.2 | CI only | [MIT](https://github.com/actions/checkout/blob/11bd71901bbe5b1630ceea73d27597364c9af683/LICENSE) |
| `actions/setup-python` v5.6.0 | CI only | [MIT](https://github.com/actions/setup-python/blob/a26af69be951a213d495a4c3e4e4022e16d87065/LICENSE) |
| TP-Link Omada API documentation | Interface reference | The [API evidence notes](docs/API_SPEC_EVIDENCE.md) describe the reduced route catalog. Manufacturer exports and PDF captures are excluded from the project license. Confirm permission for redistribution of any manufacturer-derived material before including it in a release. |

## Base image audit

The Linux amd64 manifest examined was
`sha256:d76f585fb0d5107dd47143da5e61554fd9cae656a30f3470f815cb8475769b6a`.
The table lists license declarations from the installed Alpine package database.
The upstream package notices and sources remain authoritative.

| License declaration | Alpine packages in the snapshot |
| --- | --- |
| GPL-2.0-only | alpine-baselayout, alpine-baselayout-data, apk-tools, busybox, busybox-binsh, libapk, scanelf, ssl_client |
| GPL-3.0-or-later | gdbm, readline |
| MIT | alpine-keys, alpine-release, libffi, musl |
| MPL-2.0 AND MIT | ca-certificates, ca-certificates-bundle |
| MIT AND BSD-2-Clause AND GPL-2.0-or-later | musl-utils |
| Apache-2.0 | libcrypto3, libssl3 |
| X11 | libncursesw, libpanelw, ncurses-terminfo-base |
| BSD-3-Clause | libuuid |
| bzip2-1.0.6 | libbz2 |
| GPL-2.0-or-later AND 0BSD AND Public-Domain AND LGPL-2.1-or-later | xz-libs |
| blessing | sqlite-libs |
| Public-Domain | tzdata |
| Zlib | zlib |

The package database excludes components installed outside APK, including
CPython and its bundled tooling. The Docker tag can resolve to different
images over time or on another architecture. For each image distributed to
others, record the exact base digest and architecture, inventory the resulting
image including bundled components, and preserve the applicable notices and
source-access obligations. Supply the connector's corresponding source for
that exact release, including the files needed to build it, under the GPLv3
distribution terms. See [GNU GPLv3, section 6](https://www.gnu.org/licenses/gpl-3.0.html#section6).
