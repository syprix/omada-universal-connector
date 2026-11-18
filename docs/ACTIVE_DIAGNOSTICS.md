# Active diagnostic operations

This review is based on the Hardware Controller 6.3.0, ER7212PC 6.2.14 and
CBC Standard 6.3.0 API exports. Source references below identify the export,
OpenAPI path and operation ID; request and response names are the schemas
declared by those exports. No controller was contacted for this review.

The switch cable test is the only active diagnostic action currently exposed.
It uses a single-port preview, exact short-lived approval, one-time journaled
dispatch and redacted result polling. Other action routes remain absent from
the fixed HTTP and MCP registries. Existing result readers do not start work.

The fixed site-history reader `GET /v1/sites/{site_ref}/wifi/interference-history-summary`
uses the documented first-page `getGridFullChannelDetectHistory` operation.
It counts stored scan states and bounded scalar values while omitting history
IDs, AP details and raw `lastSeen` values. This is a read of existing data; it
does not start the batch interference action.

| Family | Source contract | Missing guarantee and current state |
| --- | --- | --- |
| AP RF scan | `POST /openapi/v2/{omadacId}/sites/{siteId}/aps/{apMac}/start-rf-scan`, `triggerRadioFrequencyScanV2`; request `RFScanCommand` (`radioIdList?: int32[]`, values 0–3 for bands, selection only applies to supporting devices; missing or empty means all bands); response `OperationResponseWithoutResult` (`errorCode`, `msg`). The export says Wi-Fi connectivity is lost for several minutes and recommends an idle period. The v1 operation is deprecated. | No run ID, cancellation route or bounded completion time in the response contract. Saved scan, status and neighbor reads remain available; start stays disabled. |
| AP interference detection | `POST /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/full-channel-detect-start`, `triggerFullChannelDetect`; request `FullChanScanCommandOpenApiVO`; response `OperationResponseWithoutResult`. ER7212PC declares `enableWifiInterference` and `enableChannelUtil`, while the Hardware Controller and CBC exports also declare `enableInterference`. Status is `GET .../full-channel-detect/status`, response `OperationResponseApFullChannelScanStatus`, with status fields but no run ID. | A status read exists, but there is no cancel operation or documented maximum duration/readback contract. The start changes detection state, so it stays disabled. Existing status and result reads remain available. |
| Site batch interference detection | `POST /openapi/v1/{omadacId}/sites/{siteId}/full-channel-detect-start`, `startBatchFullChannelDetect`; request `StartBatchFullChannelDetectCmdOpenApiVO` includes required `selectType`, optional `macList` and enable flags; response `OperationResponseWithoutResult`. `POST .../full-channel-detect/status` uses `QueryBatchFullChannelDetectStatusVO`. Deletion operations are `DELETE .../full-channel-detect/{historyId}`, `deleteBatchFullChannelDetectHistory`, and `DELETE .../full-channel-detect`, `deleteALLBatchFullChannelDetectHistory`. | The start response provides no run ID; no cancellation route or bounded completion time is documented. Both history deletions are destructive and have no recovery contract. Start and deletes remain disabled; existing status/result/history reads remain available. |
| AP speed test | `POST /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/start-speed-test`, `triggerSpeedTest`; request `SpeedTestCommand` requires `childMac` and describes it as a Main AP or Client AP in a Main–Client relationship; response `OperationResponseWithoutResult`. The export limits it to P2P devices. | No run ID, cancellation route or bounded completion contract. Saved result reads remain available; start stays disabled. |
| Gateway speed test | `POST /openapi/v1/{omadacId}/sites/{siteId}/gateways/{gatewayMac}/speedTest`, `startSpeedTestV2`; request `OpenApiSpeedTestSelectPortsVO` has optional `portUuidList` and `virtualWanIdList`; response `OperationResponseStartSpeedTestV2ResultVO` includes `deviceMac` but no run ID. `GET .../speedTestResult` returns status and port results. | A result read exists, but the start response does not identify a run and no cancel route or maximum duration is documented. Start stays disabled. |
| Package capture | `POST /openapi/v1/{omadacId}/sites/{siteId}/capture/device-type/{deviceType}/{deviceMac}/start`, `startPackageCapture`; request `PackageCaptureConfig` has `duration` in seconds but no schema min/max; response `OperationResponseCaptureInfo` includes `requestId`. Status is `GET .../{deviceMac}/{requestId}/status`, using `OperationResponseCaptureResult` with integer status. Stop is `GET .../{deviceMac}/stop`, `stopPackageCapture`, with `OperationResponseWithoutResult`; this path has no `requestId`. Capture download can return packet contents. | Although the duration unit is documented, the allowed bounds and terminal-state semantics are not. Stop addresses only the device, not the captured request, so it cannot safely target one run when multiple requests are possible. Packet data also needs explicit protection. The side-effecting GET stop is rejected as a public read; capture start, stop and download are not exposed. |
| Switch cable test | Start/cancel operations and port, log and result reads are documented in all three exports. | Implemented for one port with exact short-lived approval, a journaled one-time dispatch, separate cancel approval and correlation against new result/log data. A timeout without matching evidence is reported as unknown. Offline fixtures only; live device support and timing remain unverified. |

The exports also include a deprecated site speed-test command and a speed-test
schedule-setting POST. Neither is the supported one-shot diagnostic contract;
changing a schedule is a settings change and is not exposed as a diagnostic.

## Verification and remaining work

Offline HTTP and MCP fixture tests verify that disabled start actions, the
capture stop GET, packet download and batch-history DELETE cannot reach the upstream client.
They also verify that the permitted scan-status, neighbor and saved speed-test
result readers continue to work. These are local contract tests, not controller
or device tests.

For any disabled family to be enabled, the source contract must support target
binding, a bounded run, a safe stop or completion guarantee, and readback that
identifies the same run. Capture additionally needs explicit duration units and
bounds plus safe handling of packet data. Where these guarantees are absent,
the action remains disabled; no device capability is inferred from an API
catalog entry.

No active diagnostic was started while preparing this inventory. Device
support, permissions, duration and network impact remain unverified live.

## Site-wide WLAN optimization is a configuration change

All three exports also document the site-wide `startOptimization` and
`startRrmOptimization` actions plus `cancelRadioFrequencyPlanning`. These
operations do not form a bounded diagnostic-run contract: the start response
uses a generic operation envelope without a run identifier, while the status
GET is site-wide and its history identifier is not an input to the start or
cancel calls. The result reports optimizer status and score indexes, not a
complete before/after state for every radio. The action can deploy channel,
width, band and power changes across the site, so it is kept outside the
read-only diagnostic tools and rejected by the generic guarded-write allowlist.
Existing status, dashboard, detail and history GETs remain available. A future
exposure would need an exact target-bound preview, approval and full-state
readback contract before any optimization action could be enabled.

## Related product guidance

TP-Link's controller UI guide for Omada Controller v6.0+ describes local-mode
packet-capture durations of 1–300 seconds. This is useful product context, but
it does not state that the Open API `PackageCaptureConfig` enforces the same
bounds, nor does it change the API's device-wide stop path into a run-specific
cancel operation. It therefore does not satisfy the API safety checks above.
See the [Omada network diagnostic tools guide](https://support.omadanetworks.com/cl/document/113838/)
and its [wireless capture details](https://support.omadanetworks.com/th/document/106887/).

TP-Link's device guide also says RF scanning may take several minutes and
clients on the AP disconnect while it is offline. That confirms the service
impact but gives no maximum duration or API cancellation guarantee; see the
[controller user guide](https://www.tp-link.com/us/user-guides/omada-sdn-software-controller/chapter-6-configure-and-monitor-omada-managed-devices.html).
