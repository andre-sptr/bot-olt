# ISP Sheet Metadata Design

## Goal

Enrich each active OLT-down row with severity, OLO, K2, and K3 metadata from
the new Google Sheets source while preserving the existing Telegram parsing,
WhatsApp delivery, and escalation behavior.

## Source

- Spreadsheet ID: `1crQdVmqXoROtuiaB4-ce7sIwJh26oxKMPq3Mj6-GyLU`
- Worksheet GID: `1706912635`
- Read range: `E3:O`
- Hostname: column E, range-relative index 0
- Severity: column L, range-relative index 7
- OLO: column M, range-relative index 8
- K2: column N, range-relative index 9
- K3: column O, range-relative index 10

One range read is used to avoid separate network calls per metadata field.
Hostnames are normalized to uppercase before matching.

## Output

The OLT-down header becomes:

```text
NO | DISTRICT | HOSTNAME | DURASI DOWN | SEVERITY | NodeB | OLO | K2 | K3 | IdPLN
```

Severity keeps the existing normalized colored display. NodeB and IdPLN remain
 sourced from Telegram. Missing metadata, invalid severity, unknown hostnames,
and sheet-read failures display `-`.

## Testing

Tests cover range-relative column mapping, exact spreadsheet/GID/range access,
the new output order, missing metadata fallback, and sheet failure fallback.
The full suite must continue to pass, including the separate OLT escalation
message tests.
