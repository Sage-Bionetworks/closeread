"""Typed settings: paths, credentials, community configuration (spec §9.3)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent


class CorpusConfig(BaseModel):
    seed: str
    group_by: str


class CommunityConfig(BaseModel):
    """One community's YAML under communities/. Spec §9.3."""

    community: str
    display_name: str
    corpus: CorpusConfig
    identity_strings: list[str]
    accession_patterns: dict[str, str] = Field(default_factory=dict)
    portals: list[str] = Field(default_factory=list)
    passes: list[str] = Field(default_factory=list)
    aws_profile_requester_pays: str | None = None

    def compiled_patterns(self) -> dict[str, re.Pattern[str]]:
        return {kind: re.compile(pat) for kind, pat in self.accession_patterns.items()}

    def seed_path(self) -> Path:
        p = Path(self.corpus.seed)
        return p if p.is_absolute() else REPO_ROOT / p


class Settings(BaseModel):
    """Runtime settings. Paths are laid out per spec §4.3 layers."""

    repo_root: Path = REPO_ROOT
    out_dir: Path = REPO_ROOT / "out"
    window_chars: int = 30_000
    window_overlap: int = 1_500
    openalex_mailto: str = "adam.taylor@sagebase.org"
    pmc_bucket: str = "pmc-oa-opendata"
    biorxiv_bucket: str = "biorxiv-src-monthly"
    medrxiv_bucket: str = "medrxiv-src-monthly"

    @property
    def raw_dir(self) -> Path:
        return self.out_dir / "raw"

    @property
    def bronze_dir(self) -> Path:
        return self.out_dir / "bronze"

    @property
    def silver_dir(self) -> Path:
        return self.out_dir / "silver"

    @property
    def gold_dir(self) -> Path:
        return self.out_dir / "gold"

    @property
    def report_dir(self) -> Path:
        return self.out_dir / "report"

    def community_dir(self, community: str) -> Path:
        return self.out_dir / community


def load_env(env_path: Path | None = None) -> None:
    """Load KEY=VALUE lines from .env into os.environ (no dependency on python-dotenv)."""
    path = env_path or REPO_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def gemini_api_key() -> str:
    load_env()
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set (env or .env)")
    return key


def load_community(name_or_path: str) -> CommunityConfig:
    path = Path(name_or_path)
    if not path.exists():
        path = REPO_ROOT / "communities" / f"{name_or_path}.yaml"
    with open(path) as fh:
        return CommunityConfig.model_validate(yaml.safe_load(fh))
