# ==============================================================================
# scripts/build_dbt_docs.py - dbt Documentation Static Site Builder
#
# Generates dbt catalog and manifest documentation, and merges them into a
# standalone static HTML file in public/dbt-docs/index.html that works both
# on GitHub Pages and offline via file:// (zero CORS issues).
# ==============================================================================

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DBT_DIR = ROOT_DIR / "dbt" / "olist_dbt"
TARGET_DIR = DBT_DIR / "target"
OUTPUT_DIR = ROOT_DIR / "docs" / "dbt-docs"


def build_docs() -> None:
    """Compiles dbt documentation and creates self-contained static distribution."""
    print("\n" + "=" * 65)
    print(" NEXUSBI DBT DOCUMENTATION COMPILER")
    print("=" * 65)
    print(f" dbt Project Dir : {DBT_DIR}")
    print(f" Output Dir      : {OUTPUT_DIR}")
    print("=" * 65 + "\n")

    # Step 1: Run dbt docs generate
    print("[1/3] Generating dbt catalog and manifest...")
    cmd = ["dbt", "docs", "generate", "--profiles-dir", "."]
    res = subprocess.run(cmd, cwd=str(DBT_DIR), capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[ERROR] dbt docs generate failed:\n{res.stderr}\n{res.stdout}")
        sys.exit(1)
    print("   dbt docs generate completed successfully.")

    # Step 2: Read generated artifacts
    index_path = TARGET_DIR / "index.html"
    manifest_path = TARGET_DIR / "manifest.json"
    catalog_path = TARGET_DIR / "catalog.json"

    if not (index_path.exists() and manifest_path.exists() and catalog_path.exists()):
        print("[ERROR] Expected dbt build artifacts not found in target directory.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 3: Bundle into standalone HTML
    print("[2/3] Embedding manifest and catalog into standalone index.html...")
    with open(index_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_json = f.read()

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog_json = f.read()

    # Replace remote fetches with inline javascript payloads
    # dbt docs index.html looks for loadProject() calls
    search_str = 'o=[i("manifest","manifest.json"+t),i("catalog","catalog.json"+t)]'
    inline_str = f'o=[{{label:"manifest",data:{manifest_json}}},{{label:"catalog",data:{catalog_json}}}]'

    if search_str in html_content:
        standalone_html = html_content.replace(search_str, inline_str)
    else:
        # Fallback regex substitution
        standalone_html = re.sub(
            r'o=\[i\("manifest"[^\]]*\),i\("catalog"[^\]]*\)\]',
            inline_str,
            html_content,
        )

    out_file = OUTPUT_DIR / "index.html"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(standalone_html)

    # Also keep raw JSONs in output dir for multi-file hosts
    shutil.copy(manifest_path, OUTPUT_DIR / "manifest.json")
    shutil.copy(catalog_path, OUTPUT_DIR / "catalog.json")

    size_mb = round(out_file.stat().st_size / (1024 * 1024), 2)
    print(f"[3/3] Created standalone dbt docs bundle: {out_file} ({size_mb} MB)")
    print("\n" + "=" * 65)
    print(" [SUCCESS] Documentation built! Open in any browser:")
    print(f" {out_file.resolve().as_uri()}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    build_docs()

