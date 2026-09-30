# ORCA — INCOIS data integration

ORCA does **not** require an INCOIS API key for the public sources used here.

## Oceansat-2 OCM / chlorophyll

The Ocean Agent reads the public INCOIS ERDDAP dataset:

- Base: `https://erddap.incois.gov.in/erddap`
- Dataset: `incois_oceansat2_datasets`
- Variables used: `CHL` (chlorophyll-a), with latitude/longitude/time dimensions.

ORCA requests only a small spatial window around the user's coordinates and the
latest available time (or the requested time when supplied). It does not
hard-code a historical observation and does not download the full archive.

## Potential Fishing Zone (PFZ)

The Fisheries Agent uses the official public INCOIS PFZ sources:

- Bulletin/text: `https://www.incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en`
- WebGIS: `https://incois.gov.in/geoportal/MFASPFZ/index.html`

The PFZ parser is deliberately conservative. If the current public response
does not expose machine-readable coordinates, ORCA reports PFZ as unavailable
instead of generating a synthetic fishing zone.

## Environment variables

```text
INCOIS_ERDDAP_BASE_URL=https://erddap.incois.gov.in/erddap
INCOIS_OCM_DATASET_ID=incois_oceansat2_datasets
INCOIS_PFZ_BULLETIN_URL=https://www.incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en
INCOIS_PFZ_WMS_URL=https://incois.gov.in/geoportal/MFASPFZ/index.html
OCEAN_AGENT_ALLOW_MOCK=false
```

No INCOIS credential is placed in the repository.
