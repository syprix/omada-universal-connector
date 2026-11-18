# Omada controller compatibility

Compatibility depends on controller type and release, API availability and
permissions, and sometimes the firmware/model of the managed device. Open API
exposes REST operations for **most** controller services; it does not imply
that every UI feature or device operation is available.

| Controller | Open API status in TP-Link sources | Notes |
|---|---|---|
| OC200 | TP-Link's newer 2026 comparison lists Open API; another current product page says OC200 does not support it. | One 6.3.0.45 installation passed authenticated site, device, client and selected AP reads. Other releases and operations still need verification. |
| OC300 | Listed as supported in TP-Link's 2026 comparison. | Use the controller's documented endpoint/port for its model and release. |
| OC400 | Listed as supported in TP-Link's 2026 comparison. | Individual API features can still exclude some hardware, as release notes demonstrate. |
| Software Controller | Supported from Controller 5.12, per TP-Link. | Check the exact installed release and its in-controller API reference. |
| Cloud-Based Controller — Standard | Product comparison lists Open API. | Cloud service endpoint and authentication differ from an on-premises controller. |
| Cloud-Based Controller — Essentials | Product comparison does not list Open API. | Do not assume Standard capabilities apply to Essentials. |
| ER7212PC integrated controller | Listed as supported in TP-Link's 2026 comparison. | Verify the exact firmware and supported API operations. |
| Omada Fusion | Open API is not listed in TP-Link's 2026 comparison. | Treat as unsupported unless TP-Link documents otherwise. |
| Omada Pro or other integrated offerings | **Unknown for this connector.** | Confirm the exact product, release, endpoint, API documentation and entitlement before treating it as supported. |

TP-Link's API guide documents OAuth **client mode** and **authorization-code
mode**. Client applications can be assigned a role and site privileges, so
available operations depend on the configured permissions. The guide describes
Open API as covering most controller services, not every service. Use the
controller's own Online API Document for the version-specific operations and
paths. TP-Link says that for an on-premises controller accessed through cloud
management, this document is unavailable in that view; access the controller
locally to consult it. Do not infer a common base URL or port across local
hardware, software, and cloud deployments.

## Evidence from this development target

The read-only controller-info check observed `controllerVer=6.3.0.45` and
`apiVer=3`. The latter is a field from `/api/info`; it does not establish the
Open API route version. A later isolated test authenticated with Open API
client credentials on this OC200 and verified one site, four devices and 32
redacted clients
through fixed connector reads. Radio configuration, radio detail and
interference detection status succeeded on each of three APs. The
channel-load route was documented, but the same operation returned Omada
`errorCode=-39386` for all three APs inside HTTP 200 responses. The
scan-status response reported `channelLoadStatus=1` (no scan result in the
supplied export), but no documented link establishes the error's cause;
channel-load data is not verified available here. This is one
installation's behavior, not a promise for every OC200 or AP. No write
operation or production deployment was performed.

## Evidence from supplied OpenAPI exports

Separate TP-Link OpenAPI 3.0 JSON exports document Hardware Controller
6.3.0, ER7212PC 6.2.14 and CBC Standard 6.3.0. They contain 1,783,
1,757 and 2,438 method/path pairs respectively. Their operation sets are
different, and none of these exports covers every controller family or
firmware. See [API_SPEC_EVIDENCE.md](API_SPEC_EVIDENCE.md) for the counts,
shared operations and limitations. The source exports are not redistributed.

## Connector work needed for broad compatibility

The current source implements client-credentials OAuth and fixed reads for
sites, devices, clients and selected AP diagnostics. These passed only the limited
live checks listed above. It accepts an explicit HTTPS origin for local or
cloud access and provides system-CA verification or a configured certificate
pin, but the cloud path has not been tested. Supporting other documented
controller families still requires version-specific operation/permission
discovery and tested response shapes; authorization-code mode may also be
needed for applications that require that flow. The connector must report
unsupported or unknown operations explicitly rather than claiming universal
control or silently switching to a different API.

TP-Link also hosts a [general online API reference](https://use1-omada-northbound.tplinkcloud.com/doc.html#/home).
Its presence does not prove that it matches a particular local controller
release. The exact Online API Document should be opened through that
controller's local web interface.

Even when an API operation exists, the managed device may require a particular
model or firmware. Check the relevant controller and device release notes for
each feature; controller-level API availability alone is not proof that a
managed device supports it.

## TP-Link sources

- [Omada SDN Controller User Guide V6.2 — Open API](https://static.tp-link.com/upload/manual/2026/202604/20260401/1900002482_Omada%20SDN%20Controller_V6.2_User%20Guide.pdf)
- [How to Configure OpenAPI via Omada Controller](https://community.tp-link.com/en/business/kb/detail/412930)
- [Omada Controller V6 product comparison](https://www.tp-link.com/us/business-networking/omada-controller-cloud-based/omada-cloud-based-controller/v6/)
- [TP-Link 2026 controller comparison](https://support.omadanetworks.com/sg/document/13150/?app=decoa) — hardware, software, cloud tiers, Fusion and ER7212PC matrix
- [TP-Link guide: accessing the Online API Document](https://support.omadanetworks.com/us/document/109315/) — local access requirement for an on-premises controller
- [Omada Software Controller V5.12.7 release notes](https://community.tp-link.com/en/business/forum/topic/623348) — Open API introduction
- [OC200 release notes](https://static.tp-link.com/upload/firmware/2023/202307/20230712/OC200_Release_Note.pdf) — older announcement that conflicts with the current comparison
- [OC400 firmware 1.10.10 release notes](https://static.tp-link.com/upload/firmware/2026/202601/20260123/controller%20OC400%20v1.10.10%20release%20note.pdf) — feature-specific device exclusions
- [OC300 V5.12.9 release notes](https://static.tp-link.com/upload/firmware/2023/202309/20230919/OC300_Release_Note.pdf) — notes that some features require compatible device firmware

This matrix summarizes published documentation, not a certification of every
firmware, region, entitlement or managed-device combination.
