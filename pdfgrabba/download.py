"""Navigate to papers, watch ~/Downloads, rename and move PDFs."""

import random
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, WebDriverException

from pdfgrabba.manifest import load_manifest, save_manifest


DEFAULT_PROFILE_DIR = Path.home() / ".cache" / "pdfgrabba-profile"
DEFAULT_DOWNLOADS_DIR = Path.home() / "Downloads"
MAX_PER_SESSION = 25
PAGE_LOAD_TIMEOUT = 30
WATCH_TIMEOUT = 120
MIN_PDF_SIZE = 10_000
DELAY_BETWEEN = (10, 30)


def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    sym = {"INFO": "ℹ", "OK": "✓", "WARN": "⚠", "ERR": "✗", "WAIT": "⏳"}.get(level, "·")
    print(f"  [{ts}] {sym} {msg}")


def detect_chrome_version() -> int | None:
    try:
        result = subprocess.run(
            ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        match = re.search(r"(\d+)\.", result.stdout)
        return int(match.group(1)) if match else None
    except Exception:
        return None


def make_driver(profile_dir: Path) -> uc.Chrome:
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--window-size=1366,900")

    prefs = {
        "plugins.always_open_pdf_externally": True,
        "download.prompt_for_download": False,
    }
    options.add_experimental_option("prefs", prefs)

    chrome_version = detect_chrome_version()
    if chrome_version:
        log(f"Chrome version: {chrome_version}")

    driver = uc.Chrome(
        options=options,
        headless=False,
        use_subprocess=True,
        version_main=chrome_version,
    )
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver


def snapshot_downloads(downloads_dir: Path) -> dict[str, float]:
    snap = {}
    for f in downloads_dir.glob("*.pdf"):
        try:
            snap[str(f)] = f.stat().st_mtime
        except OSError:
            pass
    return snap


def wait_for_new_pdf(
    before: dict[str, float],
    downloads_dir: Path,
    timeout: int = WATCH_TIMEOUT,
) -> Path | None:
    start = time.time()
    last_msg = 0.0

    while time.time() - start < timeout:
        partials = list(downloads_dir.glob("*.crdownload"))

        new_pdfs = []
        for f in downloads_dir.glob("*.pdf"):
            path_str = str(f)
            try:
                mtime = f.stat().st_mtime
                size = f.stat().st_size
            except OSError:
                continue
            if size < MIN_PDF_SIZE:
                continue
            if path_str not in before or mtime > before[path_str]:
                new_pdfs.append(f)

        if new_pdfs and not partials:
            return max(new_pdfs, key=lambda p: p.stat().st_size)

        elapsed = time.time() - start
        if elapsed - last_msg >= 15:
            status = "downloading..." if partials else "waiting..."
            log(f"Watching ~/Downloads ({elapsed:.0f}s) — {status}", "WAIT")
            last_msg = elapsed

        time.sleep(1)

    return None


def run(
    manifest_path: str,
    output_dir: str,
    downloads_dir: Path | None = None,
    profile_dir: str | None = None,
    keys: list[str] | None = None,
    dry_run: bool = False,
    max_papers: int = MAX_PER_SESSION,
) -> None:
    manifest = load_manifest(manifest_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    dl_dir = Path(downloads_dir).expanduser() if downloads_dir else DEFAULT_DOWNLOADS_DIR
    if not dl_dir.exists():
        raise SystemExit(f"Downloads dir does not exist: {dl_dir}")

    pending = [
        e for e in manifest
        if e.get("status") in ("pending", "failed", "skipped_manual")
        and (not keys or e.get("bib_key") in keys)
    ]

    if not pending:
        print("\nNo pending downloads.")
        return

    pending = pending[:max_papers]
    profile = Path(profile_dir) if profile_dir else DEFAULT_PROFILE_DIR
    profile.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  pdfgrabba — {len(pending)} papers")
    print(f"  Output:    {out}")
    print(f"  Downloads: {dl_dir}")
    print(f"{'='*60}")
    print("  For each paper: browser opens the page, you click PDF.")
    print("  Script watches ~/Downloads, renames & moves the file.")
    print("  Controls: [Enter] = done  [s] = skip  [q] = quit")
    print()

    if dry_run:
        for e in pending:
            print(f"  [{e['bib_key']}] {e['target_filename']}")
        return

    downloaded = 0
    failed = 0
    driver = None

    try:
        driver = make_driver(profile)

        for i, entry in enumerate(pending):
            bib_key = entry.get("bib_key", "unknown")
            target = entry.get("target_filename", "unknown.pdf")
            title = entry.get("title", "")
            doi = entry.get("doi")
            url = entry.get("url") or (f"https://doi.org/{doi}" if doi else "")

            if not url:
                log(f"No URL for {bib_key}, skipping", "ERR")
                entry["status"] = "failed"
                entry["notes"] = "No URL or DOI"
                save_manifest(manifest, manifest_path)
                failed += 1
                continue

            print(f"{'─'*60}")
            print(f"  [{i+1}/{len(pending)}] {target}")
            print(f"  {title[:70]}")

            snap = snapshot_downloads(dl_dir)

            log(f"Opening {url[:70]}...")
            try:
                driver.get(url)
                time.sleep(3)
            except TimeoutException:
                log("Page load timeout, continuing...", "WARN")
            except WebDriverException as e:
                log(f"Navigation error: {str(e)[:100]}", "ERR")
                entry["status"] = "failed"
                entry["notes"] = "Navigation error"
                save_manifest(manifest, manifest_path)
                failed += 1
                continue

            log(f"On: {driver.current_url[:70]}")

            auto = wait_for_new_pdf(snap, dl_dir, timeout=5)
            if auto:
                dest = out / target
                shutil.move(str(auto), str(dest))
                size_kb = dest.stat().st_size // 1024
                log(f"Auto-downloaded → {target} ({size_kb} KB)", "OK")
                entry["status"] = "downloaded"
                entry["notes"] = f"Auto ({size_kb} KB)"
                entry["last_attempt"] = datetime.now().isoformat()
                save_manifest(manifest, manifest_path)
                downloaded += 1

                if i < len(pending) - 1:
                    d = random.uniform(*DELAY_BETWEEN)
                    log(f"Next paper in {d:.0f}s...", "WAIT")
                    time.sleep(d)
                continue

            print()
            print("    → Click the PDF download link in the browser.")
            print("    → Then press Enter. (s=skip, q=quit)")
            try:
                user = input("    ▸ ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                save_manifest(manifest, manifest_path)
                break

            if user == "q":
                save_manifest(manifest, manifest_path)
                break
            if user == "s":
                entry["status"] = "skipped_manual"
                entry["notes"] = "User skipped"
                entry["last_attempt"] = datetime.now().isoformat()
                save_manifest(manifest, manifest_path)
                continue

            pdf = wait_for_new_pdf(snap, dl_dir, timeout=WATCH_TIMEOUT)

            if pdf:
                dest = out / target
                shutil.move(str(pdf), str(dest))
                size_kb = dest.stat().st_size // 1024
                log(f"Downloaded → {target} ({size_kb} KB)", "OK")
                entry["status"] = "downloaded"
                entry["notes"] = f"Manual ({size_kb} KB)"
                downloaded += 1
            else:
                log("No PDF detected in ~/Downloads", "ERR")
                entry["status"] = "failed"
                entry["notes"] = "No PDF appeared in Downloads"
                failed += 1

            entry["last_attempt"] = datetime.now().isoformat()
            save_manifest(manifest, manifest_path)

            if i < len(pending) - 1 and pdf:
                d = random.uniform(*DELAY_BETWEEN)
                log(f"Next paper in {d:.0f}s...", "WAIT")
                time.sleep(d)

    except KeyboardInterrupt:
        print("\n  Interrupted. Progress saved.")
        save_manifest(manifest, manifest_path)
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    remaining = sum(
        1 for e in manifest
        if e.get("status") in ("pending", "failed", "skipped_manual")
    )

    print(f"\n{'='*60}")
    print(f"  Done: {downloaded} downloaded, {failed} failed, {remaining} remaining")
    print(f"{'='*60}")
