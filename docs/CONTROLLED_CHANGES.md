# Controlled changes

`app/change_journal.py` is connected to the HTTP runtime and twenty-one change-plan
managers. It is opt-in and remains inactive when no journal directory is
configured. Apply additionally requires the caller token,
`OMADA_ENABLE_WRITES=true`, a ready shared journal runtime with a persistent
reference key, and a separate valid operator approval key. Each apply request
must include a valid short-lived HMAC approval for that exact plan. Without
these conditions, GET and preview remain available while apply is fail-closed.

For Docker, mount a private writable named volume at the image's existing
`/state/change-journal` directory and set
`OMADA_CHANGE_JOURNAL_DIR=/state/change-journal`. The image creates this
directory for UID 10001 with mode 0700. Also mount an operator-provisioned
32-byte reference key as a read-only secret file and set
`OMADA_REFERENCE_KEY_FILE` to its path. It must be a regular file with mode
0400 or 0600. The connector uses the already-loaded key; it never creates a
key. The checked-in Compose service remains read-only and leaves all optional
lines commented. It contains no host-path mount, Docker socket, secret, or
write enablement.

For every preview, the response includes `approval_request` with operation,
plan ID, opaque target references, before and target state, `before_hash`, and
a digest over that exact plan. Save that object and pass it on standard input to
`python3 tools/approve_plan.py --key-file <operator-key-path> --operator-id op_<24-hex>`.
The tool validates the digest, displays the target and before/after values on
the controlling terminal, and signs only after the operator enters exactly
`FREIGEBEN`. It performs no controller I/O. It prints an approval envelope;
the caller then supplies it to apply as `{"approval": <Envelope>}`. Each
preview needs a separate explicit approval, including rollback plans. Target
references are opaque: resolve them against authenticated inventory before
approving so the intended device and port are clear.

The operator key must be an existing private 32-byte file readable by UID
10001, mode 0400 or 0600. Set `OMADA_OPERATOR_APPROVAL_KEY_FILE` to its
read-only secret mount path. Keep it distinct from both the caller-token and
reference keys. Never place key material in this repository, image, shell
history, logs, or HTTP responses. Treat the signed envelope as a short-lived
credential: someone who obtains it before consumption could submit it. The service verifies a short-lived signature
bound to operation, plan ID, digest, operator ID, expiry, and nonce.

This HMAC mechanism proves only possession of the shared key. The server also
holds that symmetric key and can create signatures if compromised. The
operator ID is an opaque signed value, not independently authenticated proof of
a person. Nonce consumption is process-local RAM, not a durable approval audit.
Pending previews disappear on restart; dispatched plans recover as `in_doubt`
and are not replayed. The journal records change dispatch and outcomes, not a
durable personal approval record.

The journal is protected by an exclusive `flock`; use one connector process
for each journal. It is not multi-process or multi-host safe. Durable dispatch
intents are written before controller writes; an intent without a durable
outcome is recovered as `in_doubt`, is visible to the matching manager, and is
never replayed. An explicit operator close is persisted before the plan is
closed. The JSONL records use an allowlist of opaque references and bounded
change state, not names, raw controller IDs, URLs, credentials, or arbitrary
text. The hash chain detects corruption and partial records but is not a
tamper-proof audit mechanism: a privileged actor who can rewrite the volume can
replace the journal. There have been no live write, crash-recovery, or operator
close or approval tests against a controller.

For the 16 additional pre-send checks, each journal-required apply repeats the
complete bound before-state read after the durable dispatch intent and checks
the plan deadline again immediately before sending. The radio change also
rechecks its bound channel catalog; AP functions with support/default fields
include those fields in the compared snapshot. A read failure, changed snapshot
or expired plan prevents the controller write and leaves the operation
`in_doubt`/`unknown`, with no replay. This narrows the stale-state window but
does not provide compare-and-swap: the API does not document an atomic version
check, so another controller user can still change state between the final GET
and PUT/PATCH. These checks have fixture coverage only and have not been live
verified.

## DNS cache

`POST /v1/sites/{site_ref}/dns/cache-preview` accepts exactly one field in
`changes`: `enable` (boolean) or `ttl` (integer, 1 through 86400 seconds).
The controller must return exactly both documented fields for planning;
missing or extra fields prevent the change. The preview reports the complete
before and target state and includes `approval_request`. `POST
/v1/dns-cache-plans/{plan_id}/apply` requires the caller token,
`OMADA_ENABLE_WRITES=true`, a ready durable journal, a persistent reference
key, and body `{"approval": <Envelope>}` signed for that preview.
It checks expiry and unchanged settings, consumes the plan before sending a
single full-state PUT, and reads back both fields. Timeout or a mismatch is an
uncertain result: inspect the controller before making a fresh plan. Rollback
requires a separate preview and apply, with the same safeguards.

The controller has no documented compare-and-swap precondition; another
administrator can change the setting between the final read and PUT. DNS
cache changes affect resolution behavior. These routes have fixture tests
only and have never been applied to a live controller.

Each preview also identifies its target by opaque references from the
authenticated inventory. Review those references against the inventory before
authorizing a change.

The switch is read from the connector process environment for each request.
Changing an external Compose or environment file does not change an already
running process; recreate the container to apply that configuration change.

Uncertain plans count against the per-manager plan limit. With the optional
journal, unresolved dispatches are durable and reloaded for their manager;
without it, the normal apply path is disabled and there are no journal-backed
plans to list. Authenticated callers can list them via
`GET /v1/change-plans/{kind}/in-doubt`, inspect one via
`GET /v1/change-plans/{kind}/{plan_id}`, and close it explicitly with
`POST /v1/change-plans/{kind}/{plan_id}/close` and body
`{"confirmation":"outcome_unknown_no_retry"}`. Kinds are `radio`,
`dns-cache`, `ssid`, `gateway-ipv6` and `poe`. Inspection takes at most one fresh
read; it does not establish whether the original write succeeded. Closing
does not retry a write and removes the plan from memory, so it cannot be
applied again. A durable dispatch intent without an outcome is reconstructed
as `in_doubt` after restart; the current controller state is not treated as
proof of the original write's result. Without the optional journal, any
process-local plan data is lost on restart. Neither mode is a tamper-proof
audit log; inspect the controller before making another plan.

## SSID enabled state

`POST /v1/sites/{site_ref}/ssids/{ssid_ref}/enable-preview` accepts exactly
`{"changes":{"ssidEnable":true}}` or the same object with `false`. The site
and SSID must first be inventoried, and the controller must return a boolean
`ssidEnable` from the corresponding detail GET. An unchanged value is rejected.
The preview reports the opaque target references, before and target values.
`POST /v1/ssid-plans/{plan_id}/apply` requires the caller token,
`OMADA_ENABLE_WRITES=true`, a ready durable journal, a persistent reference
key, and body `{"approval": <Envelope>}` signed for that preview. It checks expiry and current state,
sends exactly one single-field PATCH, and reads back the result. An uncertain
outcome cannot be replayed; inspect the controller before planning again.
Rollback requires a new preview and apply. A change can disconnect clients.

The existing SSID detail GET also exposes a minimal, redacted preflight context:
security-configuration and credential-field presence flags, an opaque network
reference when a valid documented LAN-network ID is returned, and an AP-group
binding count when its ID list is valid. Each field is omitted when source data
is absent or unknown. The projection never returns credential values, SSID
names by default, raw network/AP-group identifiers, or VLAN values. Presence
flags do not establish a secure configuration or prove test isolation.

This site-level GET/PATCH contract appears in the supplied Hardware Controller
6.3.0 and CBC Standard 6.3.0 exports. The supplied ER7212PC 6.2.14 export
does not document that contract; the connector does not substitute a broader
configuration update. The feature has fixture tests only and has never been
applied to a live controller. The final read and PATCH are not atomic against
other controller users.

## Switch-port PoE

PoE mode is changed only for a uniquely identified port of an inventoried
switch. `GET /v1/sites/{site_ref}/switches/{switch_ref}/ports/{port}/poe`
reads its setting. The matching `poe-preview` POST accepts exactly
`{"changes":{"poeMode":0}}` or `1`; `0` means off and `1` means 802.3at/af.
The documented port row must report PoE support and enabled profile override;
the connector will not enable override itself. `POST /v1/poe-plans/{plan_id}/apply`
requires the caller token, `OMADA_ENABLE_WRITES=true`, a ready durable journal,
a persistent reference key, and body `{"approval": <Envelope>}` signed for
that preview.
It rechecks the port state and expiry, sends one dedicated PUT and reads back
the result. An uncertain result is never automatically retried. Rollback is a
new plan. Turning off PoE can interrupt power and disconnect a device.

The supplied ER7212PC 6.2.14 export lists the port in the path but omits it
from that operation's parameter list. Runtime support on this or any other
controller has not been established. The final read and PUT are not atomic
against other controller users.

## Switch-port enabled state

`GET /v1/sites/{site_ref}/switches/{switch_ref}/ports/{port}/status` reads
the enabled state of one inventoried port. The preview route
`POST /v1/sites/{site_ref}/switches/{switch_ref}/ports/{port}/status-preview`
accepts exactly
`{"changes":{"status":0},"disruption_confirmed":true}` or the same object
with `status: 1`. `0` means off and `1` means on. The acknowledgement flag is
required by the request contract, but it is not user authorization. A user
must approve the specific target and value before each actual change is
applied, including a separately planned rollback. The service requires a
short-lived HMAC approval envelope for apply. This proves possession of a
shared key, not a person's identity; the server also knows the key and could
forge approvals if compromised.

Turning a port off can disconnect an uplink, an access point, or the
management path used to reach the controller or connector. Loss of that path
can prevent an immediate readback and leave the result `in_doubt`. The plan
rechecks the prior port state and expiry, writes a durable dispatch intent
before the single controller request, then reads the status back. It is
single-use, journal-bound and never automatically retried. An uncertain
outcome requires inspection and explicit closure; rollback, if needed, is a
new reviewed plan.

`POST /v1/switch-port-status-plans/{plan_id}/apply` requires the caller token,
`OMADA_ENABLE_WRITES=true`, a ready durable journal, a persistent reference
key, and body `{"approval": <Envelope>}` signed for that preview. The
checked-in service remains
read-only by default. The route is documented in the supplied Hardware
Controller 6.3.0, ER7212PC 6.2.14 and CBC Standard 6.3.0 exports, but has no
live write test and does not establish universal controller or firmware
support. The mapping of GET `disable` to PUT `status` follows the field
descriptions and is checked against `connectedStatus`; the exports do not
explicitly define this crosswalk. The final state check and controller write are not atomic against
other controller users.

## Gateway IPv6 IP-passthrough

The read route is
`GET /v1/sites/{site_ref}/gateways/{gateway_ref}/ipv6-ip-passthrough`.
`POST` to the corresponding `ipv6-ip-passthrough-preview` route accepts only
`{"changes":{"enable":true}}` or `false`. The preview also returns an
`approval_request`. `POST /v1/gateway-ipv6-plans/{plan_id}/apply` requires
body `{"approval": <Envelope>}` signed for that preview. The plan binds the inventoried
gateway, checks the previous value and expiry again, sends one single-field
PATCH and verifies a fresh GET. Apply requires the caller token,
`OMADA_ENABLE_WRITES=true`, a ready durable journal, and a persistent reference
key. Writes default to off, a replay is rejected, and an uncertain outcome
requires inspection before a new plan. Rollback is
another separately reviewed plan. These are specifically IP-passthrough LAN
IPv6 settings, not a general IPv6 switch. Their use can interrupt connectivity.

The GET/PATCH contract is documented in the three supplied exports. No live
test has been performed. The final read and PATCH cannot be atomic against
other controller users.

## Radio power and channel

The development source supports AP transmit-power level Low (0), Medium (1),
High (2), or Auto (4), and channel index changes for the 2.4 GHz and 6 GHz
radios. The AP-reported channel catalog and current channel width are checked
at preview and again before dispatch. Index 0 denotes automatic channel.
5 GHz channel changes remain disabled because radio-to-setting mapping is not
proven. Custom power, channel width changes, radio disabling, firmware actions
and arbitrary controller paths are not admitted.

The supplied controller exports identify radio IDs 1 and 2 as the two 5 GHz
radios, but do not establish which `radioSetting5g`, `radioSetting5g1`, or
`radioSetting5g2` field corresponds to each ID, or whether channel indexes
are shared between radios. Comparing the current configuration with the
available-channel GET response can provide evidence for a particular AP and
firmware only; it cannot establish a universal mapping.

Channel-width writes are not admitted. The supplied schemas do not establish
all band-specific combinations or whether a width-only patch can also change
channel or frequency. Auto-channel additionally has no concrete catalog index
to validate. A reversible operation requires separate evidence and verification
of the full affected state.

A client first requests a preview through
`POST /v1/sites/{site_ref}/aps/{device_ref}/radio-preview` with JSON such as
`{"changes":{"radioSetting2g":{"txPowerLevel":1}}}`.
The service reads the current settings, validates a recoverable previous
level, and returns a random plan ID, previous/desired values and expiry.
Preview does not send a controller mutation.

The preview includes an `approval_request`. `POST
/v1/radio-plans/{plan_id}/apply` requires body
`{"approval": <Envelope>}` signed for the exact preview, plus
`OMADA_ENABLE_WRITES=true`, a ready durable journal, a persistent reference
key, and the configured caller bearer token. Enabling writes therefore gives holders of this operator
token access to the admitted changes; keep the service local and the token
private. Writes are disabled by default, including the checked-in deployment.

Before dispatch the service checks the complete redacted radio snapshot has
not changed. Plans expire after five minutes and are consumed before a write
is sent. A timeout, transport failure or mismatching readback leaves an
uncertain outcome and cannot be retried using that plan. Inspect the actual
controller state before preparing any new plan. There is no automatic retry
or automatic rollback. A successful change returns the prior values for a
separate rollback preview, which performs the same fresh-state checks.

The controller endpoint does not offer a documented compare-and-swap
precondition. Another administrator could still change settings between the
final read and the controller accepting the patch; the preflight check is not
an atomic lock on other controller clients.

Pending previews are bounded and held in memory; restart invalidates them.
Dispatch intent and outcome survive restart when journaling is configured.
An unresolved intent remains `in_doubt` and cannot be replayed. A successful
model response or HTTP transport alone is not success: the service reads the
radio settings again and checks every requested value.

The PATCH route and power-level enum occur in all three supplied controller API
exports. Channel catalog and response assumptions require per-controller
verification; no channel change has been live tested. Local tests exercise preview, stale state, expiry, readback,
disabled writes and replay prevention. No live power change or rollback has
been performed. Before live use an operator must choose the AP/band and
intended change and accept the possibility of interrupted client connections.
Other controller/device combinations require their own verification.

## Site band steering

`GET /v1/sites/{site_ref}/wifi/band-steering` returns the redacted current
site mode. The preview route
`POST /v1/sites/{site_ref}/wifi/band-steering-preview` accepts exactly
`{"changes":{"mode":0|1|2},"disruption_confirmed":true}`. Mode `0` turns
band steering off, `1` prefers 5/6 GHz, and `2` balances bands. The service
rejects a current-state response with missing or unknown fields rather than
assuming they will survive a PATCH. A mode change may temporarily disconnect
wireless clients.

`POST /v1/band-steering-plans/{plan_id}/apply` requires the same caller,
write-opt-in, journal, persistent-reference-key, and separately signed
short-lived HMAC approval as the other seven apply operations. The preview binds
the site, exact before/target modes and digest. `disruption_confirmed` is an
acknowledgement field only; it never replaces personal approval of the exact
network change. Writes remain disabled by default. The GET/PATCH contract and
mode values are documented in all three supplied exports, but no live write
test has been run and no universal controller/firmware support is claimed.

The site WLAN optimization/RRM overview is exposed at
`GET /v1/sites/{site_ref}/wifi/optimization`; its upstream `timeRangeId` is
redacted. The narrowly controlled mode operation below uses the documented
PUT only after validating and preserving the complete known state.

## WLAN RRM mode

`POST /v1/sites/{site_ref}/wifi/optimization-preview` accepts exactly
`{"changes":{"mode":0|1},"disruption_confirmed":true}`. Apply uses
`POST /v1/rrm-mode-plans/{plan_id}/apply` with a separate short-lived signed
approval for the exact preview, in addition to the caller token, write opt-in,
ready journal and persistent reference key. Writes remain disabled by default.

Before preview and again before dispatch, the current optimization GET must
return exactly these five documented fields: `mode` (integer 0 or 1),
`timeRangeEnable` (false), `resource` (integer 0, 1 or 2), `timeRangeId` (empty
string), and `timeRangeAction` (integer 0 or 1). Missing, extra, or differently
typed/valued fields block the plan. Only `mode` can change. The complete known
state is sent with the PUT; readback must match the target exactly. The API does
not explicitly define the meaning of an empty profile ID; effects on time ranges
are not live verified. A later concurrent edit between the
final GET and PUT cannot be prevented atomically.

RF optimization can modify WLAN radio parameters and interrupt client
connections. `disruption_confirmed` is only an acknowledgement; personal
approval of the exact target remains necessary before every apply. The
operation is documented in the three supplied exports, but has no live write
test and does not establish universal controller or firmware compatibility.

## Site LED state

`GET /v1/sites/{site_ref}/led` reads the documented site LED enable state.
`POST /v1/sites/{site_ref}/led-preview` accepts exactly
`{"changes":{"enable":true|false}}`. `POST
/v1/site-led-plans/{plan_id}/apply` requires the normal caller token, write
opt-in, persistent journal/reference key and a separate short-lived approval
for that exact preview. Apply sends only the documented `{"enable":bool}` PUT,
then reads the state back and verifies it. Writes are disabled by default.

The API does not specify which concrete devices are affected by this setting.
Do not infer the LED effect from a successful API response. A person must
review the intended site and explicitly approve each exact change. The GET/PUT
schema appears in all three supplied exports, but there is no live test or
universal compatibility claim.

Site roaming is exposed as a read-only settings view. It contains five
documented booleans; missing or unknown fields make the result partial. Some
exports mark two options as deprecated. No site-roaming write route is
implemented and these schema details do not establish runtime support.

## AP AFC enable state

`GET /v1/sites/{site_ref}/aps/{device_ref}/afc` reads exactly two booleans:
`supportAfc` and `enable`. A successful GET establishes that the read endpoint
returned a valid response. `supportAfc: false` is reported as the device value;
it does not identify a particular hardware or firmware cause, and preview is
blocked unless `supportAfc` is exactly true.

`POST /v1/sites/{site_ref}/aps/{device_ref}/afc-preview` accepts exactly
`{"changes":{"enable":bool},"disruption_confirmed":true}`. Preview binds
the inventoried site/AP references, the before state including
`supportAfc: true`, and the boolean target. `POST
/v1/ap-afc-plans/{plan_id}/apply` requires the normal caller token, write
opt-in, persistent journal/reference key, and a separate short-lived approval
for that exact plan. The controller PUT body contains only
`{"enable":bool}`. Apply checks the current state again before dispatch,
journals intent before the write, then reads back and verifies the state. A
stale plan is rejected; dispatched plans are never replayed automatically.
Writes remain disabled by default.

The API describes the field as indicating AFC support or enabling AFC. It
does not establish broader RF or regulatory effects. A person must review the
exact AP and state and explicitly approve every network change; an approval
envelope alone does not prove a person's identity. The GET/PUT schema appears
in all three supplied exports, but no live write or compatibility test has
been performed.

## Site LLDP setting

This site-level setting is separate from `GET
/v1/sites/{site_ref}/switches/{switch_ref}/lldp-neighbors`, which reads switch
neighbor information. `GET /v1/sites/{site_ref}/lldp` reads the site LLDP
enable state. `POST /v1/sites/{site_ref}/lldp-preview` accepts exactly
`{"changes":{"enable":bool},"disruption_confirmed":true}`. The controller
uses `GET` and `PATCH /openapi/v1/{omadacId}/sites/{siteId}/lldp`; the request
body is exactly `{"lldp":{"enable":bool}}`.

`POST /v1/site-lldp-plans/{plan_id}/apply` requires the caller token,
`OMADA_ENABLE_WRITES=true`, a ready persistent journal/reference key and a
separate short-lived approval for the exact preview. Plans check for stale
state, persist dispatch intent before sending one PATCH, then read back and
verify the setting. A dispatched plan is never replayed; writes are disabled
by default.

The API does not specify which concrete devices are affected. Do not infer a
network effect from the setting name or response. A person must review the
site and explicitly approve each change; HMAC proves key possession, not the
person's identity. The GET/PATCH contract appears in all three supplied
exports, but has no live test and no universal support claim.

## AP channel-limit type

The deprecated site-level channel-limit setting is exposed only as
`GET /v1/sites/{site_ref}/wifi/channel-limit`; no site-level write route is
implemented. AP values are read at
`GET /v1/sites/{site_ref}/aps/{device_ref}/channel-limit`.

An AP preview is accepted only when the complete response has exactly
`supportChannelLimit: true`, `channelLimitType` as integer 0, 1 or 2, and
boolean `defaultInstType5g` and `defaultInstType6g`. It changes exactly one AP
through `POST /v1/sites/{site_ref}/aps/{device_ref}/channel-limit-preview`;
the request accepts only the chosen `channelLimitType` and
`disruption_confirmed: true`. The documented values
are `0` default, `1` false and `2` true. This documents value mapping only; no
additional effect is inferred.

`POST /v1/ap-channel-limit-plans/{plan_id}/apply` requires the standard caller,
write opt-in, durable journal/reference key and a separate approval for the
exact preview. The approval binds the complete prior AP state, including
support/default fields. Apply rechecks that state before dispatch, records
journal intent, performs one PUT and verifies by readback. Stale plans are
rejected and dispatched plans are never replayed. Writes remain disabled by
default. There is no live write verification or broad compatibility claim.
Only a person who has reviewed the individual AP plan should approve it.

## AP OFDMA single-band setting

`GET /v1/sites/{site_ref}/aps/{device_ref}/ofdma` reads the documented four
enable and four support booleans. The preview accepts exactly one
`ofdmaEnable2g`, `ofdmaEnable5g`, `ofdmaEnable5g2` or `ofdmaEnable6g` boolean.
It is allowed only when the full before state contains all eight booleans and
the corresponding `supportOfdma*` value is `true`. The preview binds the
complete eight-boolean before and target states. Only the single selected
enable field is sent in the PATCH request.

`POST /v1/sites/{site_ref}/aps/{device_ref}/ofdma-preview` and
`POST /v1/ap-ofdma-plans/{plan_id}/apply` use the shared journal and a separate
short-lived approval for the exact plan. Apply checks the full state for
staleness, journals dispatch intent, sends one PATCH, then reads back and
compares all eight booleans. It never replays a dispatched plan. Writes remain
disabled by default.

The three supplied exports document the GET/PATCH contract, but no write has
been tested. Partial PATCH semantics and effects on other settings or clients
are not live verified. Readback detects such changes only after the write; it
cannot prevent them. The operation may interrupt clients, so a person must
review and explicitly approve each individual change. HMAC proves possession
of a shared key, not a person's identity.

## AP Advanced QoS per-band setting

The documented `PATCH /openapi/v1/{omadacId}/sites/{siteId}/aps/{apMac}/qos`
is exposed through a fixed preview/apply plan. Preview requires one supported
`deliveryEnable*` Boolean and a disruption acknowledgement. It binds all
eight GET fields, including the four band support flags. If 5 GHz is split,
the GET's `deliveryEnable5g` maps to PATCH `deliveryEnable5g1`; the complete
supported-band body also carries `deliveryEnable5g2`. For unsplit 5 GHz, the
PATCH field is `deliveryEnable5g`. Other supported bands are preserved in the
full request body. Apply uses the shared journal, separate per-plan operator
approval, a fresh-state check and full GET readback. Client U-APSD effects
are not live verified. Writes remain disabled by default.

## Controller RADIUS proxy

`POST /v1/controller/settings/radius-proxy-preview` accepts a `changes` object
with one or more of `enable` (boolean), `port` (signed 32-bit integer),
`requireMessageAuthenticator` (boolean) and `limitProxyState` (boolean). Preview
reads the exact documented controller-wide GET first. The GET must include
valid `enable` and `port` fields and no unrecognized values; the two optional
flags may be absent. Only fields observed in the GET are included in the PATCH,
so a missing optional flag is not guessed or overwritten. The preview binds the
before and target states and returns `approval_request`.

`POST /v1/controller-radius-proxy-plans/{plan_id}/apply` requires a signed
approval for the exact preview, enabled writes, a durable journal and a fresh
matching state. It sends one PATCH, reads the setting back and verifies the
result. An uncertain result is marked in-doubt and is never replayed. Rollback
requires a fresh preview and approval. Changes can interrupt client RADIUS
authentication. The Hardware Controller 6.3.0 and ER7212PC 6.2.14 exports
document the controller-wide route; CBC only documents a separate MSP route.
Adapter, approval, journal, HTTP and MCP checks use offline fixtures. No live
PATCH or agent-client interoperability test has been performed. The controller
API documents no atomic state precondition, so another administrator can still
change the settings between the last read and this PATCH.
