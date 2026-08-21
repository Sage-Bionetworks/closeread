"""Tier B full-text acquisition: PubMed Central open-access bucket. Spec §5.1.

Bucket layout: s3://pmc-oa-opendata/PMC<id>.<v>/PMC<id>.<v>.xml, unsigned.
"""

from __future__ import annotations

import re
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config

PMC_BUCKET = "pmc-oa-opendata"


def unsigned_client():
    return boto3.client("s3", region_name="us-east-1", config=Config(signature_version=UNSIGNED))


def latest_version(s3, pmcid: str) -> int | None:
    """Highest available version for a PMCID, or None if absent."""
    versions: list[int] = []
    pager = s3.get_paginator("list_objects_v2")
    for page in pager.paginate(Bucket=PMC_BUCKET, Prefix=f"{pmcid}.", Delimiter="/"):
        for cp in page.get("CommonPrefixes") or []:
            m = re.match(rf"{re.escape(pmcid)}\.(\d+)/$", cp["Prefix"])
            if m:
                versions.append(int(m.group(1)))
    return max(versions) if versions else None


def fetch_jats(s3, pmcid: str, dest_dir: Path) -> tuple[Path, str] | None:
    """Download the latest JATS XML for a PMCID. Returns (path, version) or None.

    Idempotent: an already-downloaded file is returned without refetching.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    cached = sorted(
        dest_dir.glob(f"{pmcid}.*.xml"),
        key=lambda p: int(p.stem.split(".")[-1]),
    )
    if cached:
        path = cached[-1]
        return path, path.stem.split(".")[-1]

    version = latest_version(s3, pmcid)
    if version is None:
        return None
    key = f"{pmcid}.{version}/{pmcid}.{version}.xml"
    path = dest_dir / f"{pmcid}.{version}.xml"
    obj = s3.get_object(Bucket=PMC_BUCKET, Key=key)
    path.write_bytes(obj["Body"].read())
    return path, str(version)
