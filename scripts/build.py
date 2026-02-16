import argparse
from pathlib import Path
import yaml

def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yml")
    args = ap.parse_args()

    cfg = load_config(args.config)

    out_pdf = Path(cfg.get("render", {}).get("output_pdf", "output/va_ghg_dashboard.pdf"))
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    print(f"[OK] Loaded config: {args.config}")
    print(f"[OK] Output target: {out_pdf}")

    # Next modules we’ll implement:
    print("[NEXT] terrain tint generation")
    print("[NEXT] load + clip VA layers")
    print("[NEXT] render map layout + 2x10 facets")
    print("[NEXT] export 1920x1080 PDF")

if __name__ == "__main__":
    main()
