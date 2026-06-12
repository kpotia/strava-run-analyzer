import os
import json
import shutil


class LocalSiteManager:
    """
    Manages the local output/ directory that is committed to the 'deploy' branch
    and served by Vercel as a static site.

    Directory layout under output_dir:
        output/
        ├── index.html          ← dashboard (regenerated every run)
        ├── assets/
        │   └── style.css       ← copied from source assets/
        ├── data/
        │   └── runs.json       ← historical archive (persisted via git)
        └── reports/
            └── YYYY-MM-DD_run_<id>.html
    """

    def __init__(self, output_dir: str, source_assets_dir: str):
        """
        Args:
            output_dir: Absolute path to the output/ directory (will be created).
            source_assets_dir: Absolute path to the source assets/ folder
                               containing style.css.
        """
        self.output_dir = output_dir
        self.source_assets_dir = source_assets_dir

        # Sub-paths
        self.reports_dir = os.path.join(output_dir, 'reports')
        self.assets_dir = os.path.join(output_dir, 'assets')
        self.data_dir = os.path.join(output_dir, 'data')
        self.runs_json_path = os.path.join(self.data_dir, 'runs.json')
        self.index_path = os.path.join(output_dir, 'index.html')

        self._ensure_dirs()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self):
        """Create required sub-directories if they do not already exist."""
        for d in (self.reports_dir, self.assets_dir, self.data_dir):
            os.makedirs(d, exist_ok=True)

    def sync_assets(self):
        """
        Copy style.css from the source assets/ directory into output/assets/.
        Called once at the start of each pipeline run.
        """
        src = os.path.join(self.source_assets_dir, 'style.css')
        dst = os.path.join(self.assets_dir, 'style.css')
        if not os.path.exists(src):
            raise FileNotFoundError(
                f"Source stylesheet not found at {src}. "
                "Ensure assets/style.css is present in the repository root."
            )
        shutil.copy2(src, dst)
        print(f"Assets synced: {src} -> {dst}")

    # ------------------------------------------------------------------
    # Historical run archive (runs.json)
    # ------------------------------------------------------------------

    def load_runs(self) -> list:
        """
        Load the historical run archive from output/data/runs.json.
        Returns an empty list if the file does not exist yet (first run).
        """
        if os.path.exists(self.runs_json_path):
            try:
                with open(self.runs_json_path, 'r', encoding='utf-8') as f:
                    runs = json.load(f)
                print(f"Loaded {len(runs)} previously processed activities from runs.json.")
                return runs
            except Exception as e:
                print(f"Warning: Could not parse runs.json ({e}). Starting fresh.")
                return []
        else:
            print("No existing runs.json found. Starting fresh.")
            return []

    def save_runs(self, runs: list):
        """Persist the updated run archive back to output/data/runs.json."""
        with open(self.runs_json_path, 'w', encoding='utf-8') as f:
            json.dump(runs, f, indent=2, ensure_ascii=False)
        print(f"runs.json saved ({len(runs)} total activities).")

    # ------------------------------------------------------------------
    # File path helpers
    # ------------------------------------------------------------------

    def report_path(self, filename: str) -> str:
        """Return the absolute path where a report HTML should be written."""
        return os.path.join(self.reports_dir, filename)

    def report_url(self, filename: str) -> str:
        """
        Return the root-relative URL for a report as it will appear on Vercel.
        e.g. 'reports/2026-06-12_run_12345.html'
        """
        return f"reports/{filename}"

    # ------------------------------------------------------------------
    # Dashboard index
    # ------------------------------------------------------------------

    def save_index(self, html_content: str):
        """Write the generated dashboard index.html to output/."""
        with open(self.index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Dashboard index saved to {self.index_path}")
