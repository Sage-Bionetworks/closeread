"""Tier C: bioRxiv/medRxiv full text from requester-pays buckets. Spec §5.1.

Status: pending. The buckets (s3://biorxiv-src-monthly, s3://medrxiv-src-monthly)
are requester-pays; unsigned access returns AccessDenied, and the `htan-dev`
AWS SSO session must be live (`aws sso login --profile htan-dev`).

Routes tested and rejected by the prototype (§5.1):
- the bioRxiv REST API returns metadata but not full text;
- Europe PMC indexes preprints under PPR identifiers but returns HTTP 404 for
  fullTextXML.

The bucket layout stores .meca packages by month
(Current_Content/<Month_Year>/, Back_Content/...); mapping a DOI to its .meca
requires reading package manifests. Verify the layout with a live session
before building the DOI index — do not guess it. Log bytes transferred: the
account pays for every GET.
"""

from __future__ import annotations

from pathlib import Path

import boto3


def requester_pays_client(profile: str):
    session = boto3.Session(profile_name=profile)
    return session.client("s3")


def fetch_preprint(s3, doi: str, dest_dir: Path) -> tuple[Path, str] | None:
    raise NotImplementedError(
        "Tier C is not yet implemented: run `aws sso login --profile htan-dev`, "
        "verify the .meca layout of s3://biorxiv-src-monthly (requester-pays), "
        "then implement the DOI->package index here. 655 citing preprints are "
        "recorded with oa_status='preprint_requester_pays_pending' and "
        "contribute abstracts meanwhile."
    )
