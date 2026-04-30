"""Two-tier YAML config for pdfgrabba: global (user-wide) + project (per-repo)."""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ValidationError


GLOBAL_CONFIG_PATH = (
    Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    / "pdfgrabba"
    / "config.yaml"
)
PROJECT_CONFIG_NAME = "pdfgrabba.yaml"


class Config(BaseModel):
    email: str
    downloads_dir: Path = Path.home() / "Downloads"
    bib_file: Optional[Path] = None
    output_dir: Optional[Path] = None


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(config_override: Optional[Path] = None) -> Config:
    """Merge global config with project (or override) config. Project wins on conflict."""
    global_data = _read_yaml(GLOBAL_CONFIG_PATH)

    if config_override is not None:
        if not config_override.exists():
            raise SystemExit(f"Config file not found: {config_override}")
        project_data = _read_yaml(config_override)
    else:
        project_data = _read_yaml(Path.cwd() / PROJECT_CONFIG_NAME)

    merged = {**global_data, **project_data}

    if "email" not in merged or not merged["email"]:
        raise SystemExit(
            "No email configured. pdfgrabba sends it to CrossRef in the User-Agent.\n"
            f"\nCreate {GLOBAL_CONFIG_PATH} with:\n"
            "  email: you@example.com\n"
            "\nSee config_example.yaml for the full schema."
        )

    try:
        return Config(**merged)
    except ValidationError as e:
        raise SystemExit(f"Invalid config:\n{e}")


def write_project_config(path: Path, bib_file: Path, output_dir: Path) -> None:
    """Write a minimal project config so `pdfgrabba` from the project root just works."""
    data = {
        "bib_file": str(bib_file),
        "output_dir": str(output_dir),
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)
