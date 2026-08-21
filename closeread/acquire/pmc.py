"""Tier B full-text acquisition: PubMed Central open-access bucket. Spec §5.1.

Bucket layout: s3://pmc-oa-opendata/PMC<id>.<v>/PMC<id>.<v>.xml, unsigned.
OpenAlex does not return PMCIDs, so they are resolved from PMIDs via the NCBI
ID converter.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable
from pathlib import Path

import boto3
import httpx
from botocore import UNSIGNED
from botocore.config import Config

PMC_BUCKET = "pmc-oa-opendata"
IDCONV_URL = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"


def pmids_to_pmcids(pmids: Iterable[str], mailto: str, log=print) -> dict[str, str]:
    """PMID -> PMCID via the NCBI ID converter, 200 ids per request."""
    pmids = [p for p in pmids if p]
    out: dict[str, str] = {}
    with httpx.Client(
        headers={"User-Agent": f"closeread (mailto:{mailto})"}, follow_redirects=True
    ) as client:
        for i in range(0, len(pmids), 200):
            batch = pmids[i : i + 200]
            delay = 1.0
            for attempt in range(5):
                try:
                    resp = client.get(
                        IDCONV_URL,
                        params={
                            "ids": ",".join(batch),
                            "format": "json",
                            "tool": "closeread",
                            "email": mailto,
                        },
                        timeout=60,
                    )
                except httpx.TransportError:
                    if attempt == 4:
                        raise
                    time.sleep(delay)
                    delay *= 2
                    continue
                if resp.status_code in (429, 500, 502, 503, 504):
                    if attempt == 4:
                        resp.raise_for_status()
                    time.sleep(delay)
                    delay *= 2
                    continue
                resp.raise_for_status()
                for rec in resp.json().get("records", []):
                    if rec.get("pmcid") and rec.get("pmid"):
                        out[str(rec["pmid"])] = rec["pmcid"]
                break
            time.sleep(0.34)  # NCBI rate limit: 3 req/s
            if (i // 200) % 10 == 9:
                log(f"idconv: {min(i + 200, len(pmids))}/{len(pmids)} pmids, {len(out)} pmcids")
    return out


EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def fetch_abstracts(pmids: Iterable[str], mailto: str, log=print) -> dict[str, str]:
    """PMID -> abstract text via PubMed E-utilities, for works where neither
    full text nor an OpenAlex abstract exists (§5.1 step 5)."""
    from lxml import etree

    pmids = [p for p in pmids if p]
    out: dict[str, str] = {}
    with httpx.Client(timeout=90, headers={"User-Agent": f"closeread (mailto:{mailto})"}) as client:
        for i in range(0, len(pmids), 200):
            batch = pmids[i : i + 200]
            delay = 2.0
            for attempt in range(5):
                try:
                    resp = client.get(
                        EFETCH_URL,
                        params={"db": "pubmed", "id": ",".join(batch), "retmode": "xml",
                                "tool": "closeread", "email": mailto},
                    )
                    if resp.status_code in (429, 500, 502, 503, 504):
                        raise httpx.TransportError("retryable status")
                    resp.raise_for_status()
                    break
                except httpx.TransportError:
                    if attempt == 4:
                        raise
                    time.sleep(delay)
                    delay *= 2
            root = etree.fromstring(resp.content)
            for art in root.iter("PubmedArticle"):
                pmid = art.findtext(".//PMID")
                abstract = " ".join(
                    " ".join(a.itertext()).strip() for a in art.findall(".//Abstract/AbstractText")
                ).strip()
                if pmid and abstract:
                    out[pmid] = abstract
            time.sleep(0.4)  # NCBI rate limit
    return out


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


def _versioned(dir_: Path, pmcid: str) -> list[Path]:
    return sorted(
        (p for p in dir_.glob(f"{pmcid}.*.xml") if p.stem.split(".")[-1].isdigit()),
        key=lambda p: int(p.stem.split(".")[-1]),
    )


def fetch_jats(
    s3, pmcid: str, dest_dir: Path, reference_cache: Path | None = None
) -> tuple[Path, str] | None:
    """Download the latest JATS XML for a PMCID. Returns (path, version) or None.

    Idempotent: an already-downloaded file is returned without refetching.
    reference_cache is a read-only directory of previously fetched
    PMC<id>.<v>.xml files; a hit is copied in instead of refetched.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    cached = _versioned(dest_dir, pmcid)
    if cached:
        path = cached[-1]
        return path, path.stem.split(".")[-1]

    if reference_cache is not None:
        ref_hits = _versioned(reference_cache, pmcid)
        if ref_hits:
            src = ref_hits[-1]
            path = dest_dir / src.name
            path.write_bytes(src.read_bytes())
            return path, src.stem.split(".")[-1]

    version = latest_version(s3, pmcid)
    if version is None:
        return None
    key = f"{pmcid}.{version}/{pmcid}.{version}.xml"
    path = dest_dir / f"{pmcid}.{version}.xml"
    obj = s3.get_object(Bucket=PMC_BUCKET, Key=key)
    path.write_bytes(obj["Body"].read())
    return path, str(version)
