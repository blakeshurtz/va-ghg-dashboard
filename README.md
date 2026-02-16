# Virginia Industrial Greenhouse Gas Dashboard (`va-ghg-dashboard`)

A reproducible geospatial analytics project for mapping Virginia industrial greenhouse gas (GHG) facilities and preparing a systems-style dashboard export.

> **Current project state:** the repository includes data preparation artifacts, project configuration, and a scaffolded build entrypoint (`scripts/build.py`) that loads config and prepares output targets. Full map rendering modules are planned but not yet implemented.

## What this repository contains

- A configurable build entrypoint for dashboard generation.
- Curated Virginia facility datasets and coordinate-validation rejects.
- Virginia boundary geometry inputs.
- Notebooks for cleaning and coordinate validation workflows.

## Repository layout

```text
.
├── config.yml                        # Runtime configuration (render + inputs + layers)
├── environment.yml                   # Conda environment specification
├── scripts/
│   └── build.py                      # Build entrypoint (config load + output prep)
├── data/
│   ├── curated/
│   │   ├── facilities_va_validated.csv
│   │   └── rejects/
│   │       ├── rejects_missing_or_invalid_coords.csv
│   │       ├── rejects_out_of_latlon_range.csv
│   │       └── rejects_outside_va_polygon.csv
│   ├── boundaries/
│   │   └── va_boundary_20m.geojson
│   └── flight_cleaned_va_all_years.csv
├── notebooks/
│   ├── clean_flight.ipynb
│   └── validate_coordinates.ipynb
└── output/                           # Generated artifacts (for build outputs)
```

## Quick start

### 1) Create and activate the conda environment

```bash
conda env create -f environment.yml
conda activate va-ghg
```

### 2) Run the build entrypoint

```bash
python -m scripts.build --config config.yml
```

This currently:
- loads `config.yml`
- prepares the configured output path
- prints the next planned pipeline stages

## Configuration

The main runtime config is `config.yml`.

Key sections:
- `state`: target state code (currently `VA`)
- `render`: output size/theme/PDF destination
- `emissions`: source CSV path and filtering thresholds
- `layers`: boundary, terrain, and infrastructure layer paths
- `terrain`: terrain style controls

Example output target:
- `output/va_ghg_dashboard.pdf`

## Data notes

The repository already includes:
- Cleaned multi-year Virginia emissions table (`data/flight_cleaned_va_all_years.csv`)
- Validated facility coordinate table (`data/curated/facilities_va_validated.csv`)
- Rejected-record diagnostics under `data/curated/rejects/`


## Data dictionary (EPA FLIGHT cleaned output)

Primary table: `data/flight_cleaned_va_all_years.csv`

| Column | Type | Description |
|---|---:|---|
| `reporting_year` | int | Reporting year for facility emissions. |
| `facility_name` | str | Facility name as reported to EPA. |
| `ghgrp_id` | int (nullable) | EPA GHGRP facility identifier. |
| `reported_address` | str | Reported street address. |
| `city_name` | str | City name (title-cased during cleaning). |
| `county_name` | str | County name (title-cased during cleaning). |
| `state` | str | Two-letter state abbreviation (uppercased). |
| `zip_code` | str | ZIP code stored as a string (padded to 5 digits when numeric). |
| `latitude` | float | Facility latitude in decimal degrees. |
| `longitude` | float | Facility longitude in decimal degrees. |
| `parent_companies` | str | Parent-company ownership string from EPA export. |
| `ghg_quantity_metric_tons_co2e` | float | Total GHG emissions in metric tons CO2e (negative values are treated as missing). |
| `subparts` | str | GHGRP subpart codes reported for the facility (uppercased, spaces removed). |
| `source_sheet` | str | Original worksheet/tab name from the source workbook (typically the year). |
| `ghg_is_negative` | bool | Whether raw GHG quantity was negative before nulling in cleaned output. |

### Cleaning notes

- Header rows are detected by finding `REPORTING YEAR` in raw worksheet exports.
- Source columns are normalized to `snake_case`.
- Numeric fields are coerced; invalid parses are set to null.
- Negative `ghg_quantity_metric_tons_co2e` values are nullified and tracked via `ghg_is_negative`.

## Development notes

- The build script is intentionally minimal and acts as a stable CLI/config scaffold.
- Planned next steps (already signposted in `scripts/build.py`) include terrain tint generation, VA layer clipping, map layout rendering, and PDF export.

## Troubleshooting

- If `conda env create` fails on `environment.yml`, verify the file encoding and platform-specific fields (for example, hard-coded local `prefix` paths from another machine).
- If `python -m scripts.build --config config.yml` fails, ensure `PyYAML` is available in your active environment.

## License

No license file is currently included in this repository. Add a `LICENSE` file before public redistribution if needed.
