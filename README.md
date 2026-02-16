# va-ghg-dashboard

# Virginia Industrial Emissions Systems Map

Reproducible, open-source pipeline to generate a **1920×1080 PDF** dashboard showing Virginia industrial greenhouse gas emitters in a systems context.

https://ghgdata.epa.gov/flight/?viewType=line

https://www2.census.gov/geo/tiger/GENZ2023/shp/

## Output
- `output/va_ghg_dashboard.pdf` (generated)

## Repo structure
- `data/` emissions inputs
- `layers/` geospatial layers (downloaded or derived)
- `icons/` sector icon SVGs
- `scripts/` build pipeline
- `output/` rendered PDFs (not committed)

## Quickstart (Conda)
```bash
conda env create -f environment.yml
conda activate va-ghg-dashboard
python -m scripts.build --config config.yml

## Data Dictionary (EPA FLIGHT Export)

This project uses facility-level greenhouse gas emissions data exported from EPA’s FLIGHT tool (GHGRP).
Each Excel worksheet corresponds to a reporting year. The pipeline stacks all years and produces cleaned CSV outputs.

### Cleaned Output Files
- `data/flight_cleaned_all_years.csv` — all years combined, Virginia facilities only (STATE = VA)

### Columns

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
| `parent_companies` | str | Parent company ownership string as provided by EPA. |
| `ghg_quantity_metric_tons_co2e` | float | Total GHG emissions in metric tons CO2e (AR4 GWPs per EPA export notes). Negative values are treated as missing. |
| `subparts` | str | GHGRP subpart codes reported for the facility (uppercased, spaces removed). |
| `source_sheet` | str | Original worksheet name (typically the year). |
| `ghg_is_negative` | bool | Flag indicating the raw GHG quantity was negative (quantity set to null in cleaned output). |

### Cleaning Notes
- The workbook includes metadata rows above the header; the loader detects the header row by finding `REPORTING YEAR`.
- Column names are normalized to snake_case.
- Numeric columns (`reporting_year`, `ghgrp_id`, `latitude`, `longitude`, `ghg_quantity_metric_tons_co2e`) are coerced with invalid values set to null.
- Negative `ghg_quantity_metric_tons_co2e` values are set to null and flagged in `ghg_is_negative`.

# va-ghg-dashboard
## Virginia Industrial Emissions Systems Map

A reproducible, open-source pipeline that generates a publication-quality systems visualization of Virginia industrial greenhouse gas emitters.

The map situates emissions within terrain and infrastructure context to support:

- policy insight
- infrastructure understanding
- emissions transparency
- open scientific communication

---

## Data Sources

EPA GHGRP FLIGHT Tool  
https://ghgdata.epa.gov/flight/?viewType=line

US Census TIGER Boundaries  
https://www2.census.gov/geo/tiger/GENZ2023/shp/

---

## Output

output/va_ghg_dashboard.pdf

A publication-quality dashboard map.

---

## Repository Structure
data/
boundaries/ VA boundary geometry
curated/ cleaned emissions datasets

layers/ derived geospatial layers
icons/ sector icon SVGs
scripts/ build pipeline
output/ rendered outputs (ignored by git)


---

## Environment Setup (Miniforge / Conda)

Create the environment:

```bash
conda env create -f environment.yml
conda activate va-ghg
Activate it:

conda activate va-ghg


Run the pipeline:

python -m scripts.build --config config.yml

Data Pipeline Overview

Import EPA GHGRP facility emissions (FLIGHT export)

Clean & normalize multi-year data

Filter Virginia facilities

Generate terrain base & spatial context

Render systems map and emissions visualization

data/curated/flight_cleaned_all_years.csv
