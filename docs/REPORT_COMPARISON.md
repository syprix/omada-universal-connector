# Comparing saved incident reports

Use this workflow to compare existing, redacted site-outage reports. It does not fetch controller data or trigger any diagnostics.

## Supported input

The supported source is JSON written by `tools/site_outage_report.py --format json`, with `report_schema_version: 1`. Pass 2–8 reports through one of:

- Local CLI: `python3 tools/compare_site_outage_reports.py --input report-a.json --input report-b.json --format json`
- HTTP: `POST /v1/incident-reports/compare` with `{"reports": [reportA, reportB]}`
- MCP: `omada_compare_incident_reports` with a `reports` array

Each input must already be the redacted report document. The API accepts at most 60 KiB of report JSON; HTTP additionally caps the request body at 64 KiB.

## Comparability

The result shows each report's UTC window, observation time, event and alert totals, pagination limits, and partial-data indicators. It calculates a common overlapping window when all input reports use the supported schema. Event and alert totals are compared only for identical windows and complete reports. Current reachability snapshots are compared only when every snapshot has the exact same observation timestamp. It does not infer an outage, cause, correlation, or trend from different windows.

Other report schemas are returned as unsupported and are excluded from metric comparisons. The result never returns input text, SSID names, device names, identifiers, or raw observations. Unknown fields are counted and make that report partial.

## Token measurement

A synthetic pair of existing-format outage reports measured 688 source JSON tokens and 783 comparison-result tokens (95 more), using js-tiktoken 1.0.21 with `o200k_base`. The comparison adds indexes, overlap, gap and comparability metadata. This covers only those serialized objects and excludes prompts, MCP schemas, HTTP framing and billed agent use; it does not save tokens at this sample size.
