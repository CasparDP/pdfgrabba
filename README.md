# pdfgrabba

A small CLI for downloading academic PDFs from a BibTeX file.

For each entry, pdfgrabba opens the DOI page in a real Chrome window. If a
PDF auto-downloads, it grabs it. Otherwise you click the publisher's PDF
link yourself; the script watches your Downloads folder, picks up the new
file, renames it to `Author_JournalAbbrev_Year.pdf`, and moves it into the
project's literature folder.

It is deliberately semi-interactive: most academic publishers block
headless tools, and proxy-based scraping invites IP bans. Letting a human
click "Download PDF" once per paper is the simplest thing that works.

## Install

Requires Python 3.10+ and Google Chrome installed at the standard macOS
location (`/Applications/Google Chrome.app`). For paywalled journals you
also need a network with subscription access (e.g. a university VPN).

The recommended install is [pipx](https://pipx.pypa.io/), which puts
`pdfgrabba` on your `$PATH` in an isolated venv so you can invoke it from
any project directory:

```bash
git clone https://github.com/yourusername/pdfgrabba.git
pipx install ./pdfgrabba
```

To pull in code changes later: `pipx reinstall pdfgrabba`. For active
development on the tool itself, use `pipx install --editable ./pdfgrabba`
so edits take effect without reinstalling.

Set up the global config once per machine:

```bash
mkdir -p ~/.config/pdfgrabba
cp pdfgrabba/config_example.yaml ~/.config/pdfgrabba/config.yaml
# edit it and set your email
```

The email is used in the CrossRef User-Agent header (CrossRef etiquette).

### Dev-loop alternative

If you're hacking on pdfgrabba and don't want to reinstall, `poetry run
pdfgrabba` works *from inside the pdfgrabba repo* (Poetry refuses to run
from elsewhere because it's tied to the local `pyproject.toml`).

## Workflow

The tool lives in one place; the PDFs route to whichever project you're
working in. There are two layers of config:

| Layer | File | What goes here |
|---|---|---|
| Global (per machine) | `~/.config/pdfgrabba/config.yaml` | `email`, optional `downloads_dir` |
| Project (per repo) | `./pdfgrabba.yaml` | `bib_file`, `output_dir` |

Both are gitignored in this repo. CLI flags override either.

### First time in a new project

```bash
cd ~/Github/my-paper
pdfgrabba
# pdfgrabba prompts:
#   Path to .bib file: paper/references.bib
#   Output directory for PDFs [Literature/]:
#   Save these paths to ./pdfgrabba.yaml? (y/N): y
```

### Subsequent runs in that project

```bash
cd ~/Github/my-paper
pdfgrabba          # uses pdfgrabba.yaml, picks up where it left off
```

### One-off override

```bash
pdfgrabba paper/refs.bib -o /tmp/scratch/
```

## What the tool does

1. Builds `<output>/download_manifest.json` from the `.bib` (CrossRef-enriched
   metadata, target filenames, statuses).
2. Opens Chrome and walks each `pending` entry. For each: navigate to the
   DOI, wait for an auto-download or for you to click the PDF link, then
   rename and move the file.

Re-running picks up where it left off. PDFs already in the output directory
are marked `skipped` and not re-attempted.

### Controls during a session

- **Enter** — "I clicked the PDF, the download is starting"
- **s** — skip this paper (status: `skipped_manual`, retried next run)
- **q** — quit, save progress
- **Ctrl+C** — emergency quit, progress still saved

### Flags

| Flag | Purpose |
|---|---|
| `bib_file` (positional, optional) | Path to the .bib (or set in pdfgrabba.yaml) |
| `-o, --output DIR` | Output directory for PDFs |
| `-c, --config PATH` | Use a specific config file in place of the project layer |
| `--downloads-dir PATH` | Where Chrome saves files (default: `~/Downloads`) |
| `--rebuild-manifest` | Force rebuild of the manifest from the .bib |
| `--manifest-only` | Build the manifest and exit (skip Chrome) |
| `--keys KEY1 KEY2` | Only attempt these bib keys |
| `--dry-run` | List pending papers and exit |
| `-n, --max N` | Max papers per session (default: 25) |
| `--profile DIR` | Override the Chrome user-data-dir |

### Manifest statuses

| Status | Retried? |
|---|---|
| `pending` | Yes |
| `failed` | Yes |
| `skipped_manual` | Yes |
| `downloaded` | No |
| `skipped` (file already exists) | No |
| `no_doi` | No |

## How it works under the hood

- **Chrome via undetected-chromedriver.** A persistent user-data-dir lives
  at `~/.cache/pdfgrabba-profile/`, so logins and Cloudflare cookies
  survive across sessions.
- **Headed only.** Headless Chrome is detected and blocked by most
  publishers' bot protection.
- **Manifest as state.** Rewritten after every paper, so a crash or a `q`
  loses at most the current paper.
- **Largest-PDF heuristic.** When publishers ship a supplement alongside
  the main paper, the script picks the larger file.

## License

MIT
