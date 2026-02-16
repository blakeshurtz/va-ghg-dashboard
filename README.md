# Virginia Industrial Greenhouse Gas Dashboard (`va-ghg-dashboard`)

A geospatial rendering pipeline for producing dark-theme dashboard layout artifacts of Virginia industrial greenhouse gas (GHG) facilities.

The project currently generates PNG layout outputs (base map + points overlay) using configurable data paths and style settings.

---

## What this project does now

- Loads and validates runtime configuration from `config.yml`.
- Reads a Virginia boundary dataset and reprojects it for plotting.
- Renders a 16:9 map + right-side panel layout in dark theme.
- Produces two render targets:
  - **base**: boundary-only layout (`layout_base.png`)
  - **points**: boundary + facility points (`layout_points.png`)

---

## Repository layout

```text
.
├── config.yml
├── environment.yml
├── scripts/
│   ├── build.py          # CLI entrypoint (`--target base|points|all`)
│   ├── config.py         # YAML load + schema/path validation
│   ├── io.py             # Boundary/CSV loading + GeoDataFrame utilities
│   ├── layout.py         # Figure, axes, and theme setup
│   ├── map_base.py       # Boundary draw + extent helpers
│   ├── points.py         # Point plotting helpers
│   └── render.py         # Render orchestration for each target
├── data/
│   ├── boundaries/
│   │   └── va_boundary_20m.geojson
│   ├── curated/
│   │   ├── facilities_va_validated.csv
│   │   └── rejects/
│   └── flight_cleaned_va_all_years.csv
├── notebooks/
└── output/               # Generated artifacts
```

---

## Quick start

### 1) Create environment

```bash
conda env create -f environment.yml
conda activate va-ghg
```

### 2) Run the renderer

Render both targets:

```bash
python -m scripts.build --config config.yml --target all
```

Render only one target:

```bash
python -m scripts.build --config config.yml --target base
python -m scripts.build --config config.yml --target points
```

Expected outputs (default config):

- `output/layout_base.png`
- `output/layout_points.png`

---

## Configuration reference (`config.yml`)

### Top-level sections

- `state`: state code (currently `VA`)
- `render`: output sizing, DPI, theme, and filenames
- `layout`: map/panel width fractions (must sum to `1.0`)
- `paths`: boundary and emissions input paths + lat/lon column names
- `style`: map colors, alpha, line width, marker size, and extent padding

### Required keys (validated at runtime)

- `render`: `width_px`, `height_px`, `dpi`, `output_dir`, `outputs`, `theme`
- `render.outputs`: `base_png`, `points_png`
- `layout`: `map_frac`, `panel_frac`
- `paths`: `va_boundary`
- `style`: `background`, `boundary_linewidth`, `boundary_alpha`, `points_size`, `points_alpha`

If configured, `paths.emissions_csv` must exist to render the `points` target.

---

## Data expectations

### Boundary input

`paths.va_boundary` should point to a valid geospatial file readable by GeoPandas.

### Emissions input

For `points` rendering, the CSV referenced by `paths.emissions_csv` must contain lat/lon columns defined by:

- `paths.emissions_lat_col` (default: `latitude`)
- `paths.emissions_lon_col` (default: `longitude`)

Rows with non-numeric or missing coordinates are dropped during point conversion.

---

## Troubleshooting

- **Config validation errors**: check required keys and section names in `config.yml`.
- **Boundary file errors**: confirm `paths.va_boundary` exists and is non-empty.
- **Points rendering errors**: verify `paths.emissions_csv` exists and includes valid lat/lon columns.
- **Import errors**: ensure dependencies from `environment.yml` are installed in the active environment.

---

## Roadmap (next sensible increments)

- Add panel content rendering (legends, metrics, labels).
- Add PDF export composition from rendered layers.
- Add automated tests for config validation and render smoke checks.

---

## License

No license file is currently included. Add a `LICENSE` file before public redistribution.
