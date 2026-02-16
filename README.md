# va-ghg-dashboard

# Virginia Industrial Emissions Systems Map

Reproducible, open-source pipeline to generate a **1920×1080 PDF** dashboard showing Virginia industrial greenhouse gas emitters in a systems context.

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
