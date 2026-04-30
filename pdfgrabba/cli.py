"""pdfgrabba — single-command CLI for downloading academic PDFs from a .bib file."""

import argparse
import sys
from pathlib import Path

from pdfgrabba import download
from pdfgrabba.config import (
    PROJECT_CONFIG_NAME,
    load_config,
    write_project_config,
)
from pdfgrabba.manifest import build_manifest, print_summary, save_manifest


def _prompt(question: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        raw = input(f"{question}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\nCancelled.")
    return raw or (default or "")


def main() -> None:
    p = argparse.ArgumentParser(
        prog="pdfgrabba",
        description=(
            "Download academic PDFs from a BibTeX file. Builds a manifest from your .bib, "
            "then opens each DOI in Chrome so you can click the PDF link; the file is "
            "renamed and moved to --output."
        ),
    )
    p.add_argument(
        "bib_file", nargs="?", default=None,
        help="Path to .bib file (or set bib_file in pdfgrabba.yaml)",
    )
    p.add_argument(
        "--output", "-o", default=None,
        help="Output directory for PDFs (or set output_dir in pdfgrabba.yaml)",
    )
    p.add_argument(
        "--config", "-c", default=None,
        help=f"Path to a specific config file (default: ./{PROJECT_CONFIG_NAME} + global)",
    )
    p.add_argument(
        "--downloads-dir", default=None,
        help="Where Chrome saves files before pdfgrabba moves them (default: ~/Downloads)",
    )
    p.add_argument(
        "--rebuild-manifest", action="store_true",
        help="Force rebuild of download_manifest.json even if it exists",
    )
    p.add_argument(
        "--manifest-only", action="store_true",
        help="Build the manifest and exit without launching Chrome",
    )
    p.add_argument("--keys", nargs="*", default=None, help="Only attempt these bib keys")
    p.add_argument("--dry-run", action="store_true", help="List pending papers and exit")
    p.add_argument(
        "--max", "-n", type=int, default=download.MAX_PER_SESSION,
        help=f"Max papers per session (default: {download.MAX_PER_SESSION})",
    )
    p.add_argument(
        "--profile", default=None,
        help="Override Chrome user-data-dir (default: ~/.cache/pdfgrabba-profile)",
    )
    args = p.parse_args()

    config = load_config(Path(args.config) if args.config else None)

    bib_path: Path | None = (
        Path(args.bib_file).expanduser() if args.bib_file else config.bib_file
    )
    output_dir: Path | None = (
        Path(args.output).expanduser() if args.output else config.output_dir
    )
    downloads_dir = (
        Path(args.downloads_dir).expanduser() if args.downloads_dir else config.downloads_dir
    )

    prompted = False
    if bib_path is None:
        raw = _prompt("Path to .bib file")
        if not raw:
            sys.exit("No .bib file specified.")
        bib_path = Path(raw).expanduser()
        prompted = True

    if output_dir is None:
        raw = _prompt("Output directory for PDFs", default="Literature/")
        output_dir = Path(raw).expanduser()
        prompted = True

    if not bib_path.exists():
        sys.exit(f"ERROR: bib file not found: {bib_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "download_manifest.json"

    if prompted:
        project_config_path = Path.cwd() / PROJECT_CONFIG_NAME
        if not project_config_path.exists():
            ans = _prompt(
                f"Save these paths to ./{PROJECT_CONFIG_NAME}? (y/N)", default="N"
            ).lower()
            if ans == "y":
                write_project_config(project_config_path, bib_path, output_dir)
                print(f"  Wrote {project_config_path}")

    if not manifest_path.exists() or args.rebuild_manifest:
        manifest = build_manifest(
            str(bib_path),
            str(output_dir),
            email=config.email,
            skip_existing=True,
        )
        save_manifest(manifest, str(manifest_path))
        print_summary(manifest)
        print(f"\nManifest saved: {manifest_path}")
    else:
        print(f"Using existing manifest: {manifest_path}")
        print("(pass --rebuild-manifest to regenerate)")

    if args.manifest_only:
        return

    download.run(
        manifest_path=str(manifest_path),
        output_dir=str(output_dir),
        downloads_dir=downloads_dir,
        profile_dir=args.profile,
        keys=args.keys,
        dry_run=args.dry_run,
        max_papers=args.max,
    )


if __name__ == "__main__":
    main()
