# CLAUDE.md

## What this repo is

`pdfgrabba` — a small Poetry-managed CLI that downloads academic PDFs from a BibTeX file. Single entry point: `pdfgrabba` (with optional positional `bib_file`). Headed Chrome via `undetected-chromedriver`; the user clicks "Download PDF" when the publisher needs it, the script watches the Downloads folder and renames the result.

The tool is installed once per machine. Per-project paths (the .bib and the literature folder) live in a `pdfgrabba.yaml` next to the project; global identity (email, optional `downloads_dir`) lives in `~/.config/pdfgrabba/config.yaml`.

## Layout

```
pdfgrabba/
├── pdfgrabba/           # the package
│   ├── cli.py           # argparse entry point + interactive prompts
│   ├── config.py        # two-tier YAML config (global + project)
│   ├── manifest.py      # bib parsing, CrossRef, manifest build/save/load
│   └── download.py      # selenium driver, download watcher, run loop
├── pyproject.toml       # Poetry; console script "pdfgrabba" = pdfgrabba.cli:main
├── config_example.yaml  # template; real configs are gitignored
├── README.md
└── LICENSE              # MIT
```

## Pipeline

`build_manifest` (manifest.py) → `download.run` (download.py). The manifest (`<output>/download_manifest.json`) is the single source of truth for progress and is rewritten after every paper, so sessions are crash-safe and resumable. `cli.py` runs both stages by default; it skips stage 1 if a manifest already exists in the output dir.

Statuses `pending`, `failed`, and `skipped_manual` are retried on re-run; `downloaded`, `skipped`, and `no_doi` are terminal.

## Config resolution

`load_config()` merges two YAML files; project values override global:

1. `~/.config/pdfgrabba/config.yaml` (or `$XDG_CONFIG_HOME/pdfgrabba/config.yaml`)
2. `./pdfgrabba.yaml` (or whatever `--config PATH` points to)

CLI flags override both. Path resolution order for `bib_file` and `output_dir` in `cli.py`: CLI arg → config → interactive prompt. After prompting, the user is offered a one-click save to `./pdfgrabba.yaml` via `write_project_config`.

## Install model

pdfgrabba is meant to be installed once per machine via **pipx** so the
`pdfgrabba` entry point lands on `$PATH` and can be invoked from any project
directory. `poetry run pdfgrabba` only works *from inside this repo* because
Poetry resolves against the local `pyproject.toml`. Use `poetry run` for the
dev loop here; use `pipx install` (or `pipx install --editable`) for the
real workflow.

## Common commands

```bash
# Install the tool (one-time, machine-wide)
pipx install ~/Github/pdfgrabba             # or --editable for dev
pipx reinstall pdfgrabba                    # pull in code changes later

# First-time machine setup
mkdir -p ~/.config/pdfgrabba
cp config_example.yaml ~/.config/pdfgrabba/config.yaml   # set email

# In a project — first run prompts, optionally saves ./pdfgrabba.yaml
cd ~/Github/my-paper
pdfgrabba

# Subsequent runs use ./pdfgrabba.yaml automatically
pdfgrabba

# One-off override
pdfgrabba paper/refs.bib -o /tmp/scratch/

# Force regenerate the manifest from the .bib
pdfgrabba --rebuild-manifest

# Build manifest only (no Chrome)
pdfgrabba --manifest-only

# Specific keys
pdfgrabba --keys autor2003skill acemoglu2020robots

# Dev loop on the tool itself (must be inside this repo)
poetry install
poetry run pdfgrabba --help
```

## Key behaviors to preserve when editing

- **Headed Chrome only.** `undetected-chromedriver` runs with `headless=False` and a persistent user profile at `~/.cache/pdfgrabba-profile/` so logins and Cloudflare cookies survive across sessions. Don't switch to headless.
- **Manifest is state.** `save_manifest(...)` is called inside the per-paper loop after every status change. Crash-safety depends on it.
- **Filesystem reconcile every run.** `reconcile_with_filesystem` runs in `cli.py` after the manifest is built/loaded and before `download.run`. It flips retryable entries (`pending`, `failed`, `skipped_manual`) to `skipped` if their `target_filename` already exists in `output_dir`. This handles the case where the output dir is synced (e.g. Dropbox) but the manifest is not — avoids re-downloading what's already on disk.
- **Filename convention is load-bearing.** `Author_JournalAbbrev_Year.pdf`. Journal abbreviations live in `manifest.py:JOURNAL_ABBREVIATIONS`; extend that table rather than reformatting names elsewhere. CrossRef metadata overrides bib metadata for filename generation when available.
- **Largest-PDF heuristic** picks the main paper when a supplement also downloads (`download.py:wait_for_new_pdf`). Don't replace with "first PDF wins".
- **Email comes from config.** CrossRef User-Agent in `manifest.fetch_crossref_metadata` reads from `Config.email`. Don't hardcode.
- **Downloads dir is parameterized.** `download.run` takes `downloads_dir`; default is `~/Downloads` via `DEFAULT_DOWNLOADS_DIR`. The watcher functions `snapshot_downloads` and `wait_for_new_pdf` both take it explicitly.
- **Interactive controls**: `Enter` = downloaded, `s` = skip (becomes `skipped_manual`, retryable), `q` = quit and save. Ctrl+C also saves.

## Notes

- Both `config.yaml` and `pdfgrabba.yaml` are gitignored — neither should ever land in git.
