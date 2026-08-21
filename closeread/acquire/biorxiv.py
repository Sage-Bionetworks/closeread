"""Tier C: bioRxiv/medRxiv full text from requester-pays buckets. Spec §5.1.

Verified layout (2026-08-21): s3://biorxiv-src-monthly/Current_Content/<Month_Year>/
holds one .meca zip per posted version, named by UUID, with the JATS at
content/<article_id>.xml where article_id is the last dot-segment of the DOI
(10.1101/2023.11.05.565674 -> 565674). There is no DOI index, so the month
folder implied by the posting date is scanned by reading each package's zip
central directory with a suffix-range GET (~16 KB), and the matched JATS entry
is extracted with a second ranged GET — no full-package downloads.

Routes tested and rejected: the bioRxiv REST API's jatsxml URL is
Cloudflare-blocked (HTTP 429/1015); Europe PMC returns 404 for preprint
fullTextXML. Requester pays: every GET is billed to the profile; bytes
transferred are counted and logged (spec §5.1).
"""

from __future__ import annotations

import datetime as dt
import re
import struct
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import boto3

BIORXIV_BUCKET = "biorxiv-src-monthly"
MEDRXIV_BUCKET = "medrxiv-src-monthly"
TAIL_BYTES = 16_384
TAIL_BYTES_RETRY = 131_072

_CONTENT_XML = re.compile(rb"content/(\d+)\.xml$")


def requester_pays_client(profile: str):
    return boto3.Session(profile_name=profile).client("s3")


def article_id_from_doi(doi: str) -> str:
    return doi.split("/")[-1].split(".")[-1]


def month_prefix(pub_date: str) -> str:
    d = dt.date.fromisoformat(pub_date)
    return f"Current_Content/{d:%B_%Y}/"


@dataclass
class MecaEntry:
    key: str
    name: str
    method: int
    comp_size: int
    local_offset: int


class TransferMeter:
    def __init__(self) -> None:
        self.bytes = 0
        self.requests = 0

    def add(self, n: int) -> None:
        self.bytes += n
        self.requests += 1


def _list_keys(s3, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    pager = s3.get_paginator("list_objects_v2")
    for page in pager.paginate(Bucket=bucket, Prefix=prefix, RequestPayer="requester"):
        keys.extend(o["Key"] for o in page.get("Contents") or [] if o["Key"].endswith(".meca"))
    return keys


def _central_directory_entries(tail: bytes) -> list[tuple[str, int, int, int]]:
    """(name, method, comp_size, local_offset) for entries visible in the tail."""
    out = []
    i = tail.find(b"PK\x01\x02")
    while i != -1 and i + 46 <= len(tail):
        method, = struct.unpack("<H", tail[i + 10 : i + 12])
        comp_size, = struct.unpack("<I", tail[i + 20 : i + 24])
        nlen, elen, clen = struct.unpack("<HHH", tail[i + 28 : i + 34])
        local_offset, = struct.unpack("<I", tail[i + 42 : i + 46])
        name = tail[i + 46 : i + 46 + nlen]
        out.append((name.decode("utf8", "replace"), method, comp_size, local_offset))
        i = tail.find(b"PK\x01\x02", i + 46 + nlen + elen + clen)
    return out


def _index_package(s3, bucket: str, key: str, meter: TransferMeter) -> list[tuple[str, int, int, int]]:
    for span in (TAIL_BYTES, TAIL_BYTES_RETRY):
        resp = s3.get_object(Bucket=bucket, Key=key, RequestPayer="requester", Range=f"bytes=-{span}")
        tail = resp["Body"].read()
        meter.add(len(tail))
        if tail.find(b"PK\x05\x06") == -1:
            continue
        entries = _central_directory_entries(tail)
        if entries:
            return entries
    return []


def scan_month(
    s3, bucket: str, prefix: str, wanted_ids: set[str], meter: TransferMeter, log=print, workers: int = 24
) -> dict[str, MecaEntry]:
    """Map article_id -> JATS entry for wanted ids found in one month folder."""
    keys = _list_keys(s3, bucket, prefix)
    found: dict[str, MecaEntry] = {}

    def probe(key: str):
        try:
            for name, method, comp_size, local_offset in _index_package(s3, bucket, key, meter):
                m = _CONTENT_XML.search(name.encode())
                if m and m.group(1).decode() in wanted_ids:
                    return m.group(1).decode(), MecaEntry(key, name, method, comp_size, local_offset)
        except Exception as exc:  # noqa: BLE001 — one bad package must not kill the scan
            log(f"  probe failed {key}: {exc}")
        return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(probe, keys):
            if result:
                found[result[0]] = result[1]
    log(f"  {prefix}: {len(keys)} packages scanned, {len(found)}/{len(wanted_ids)} wanted ids found")
    return found


def fetch_entry_xml(s3, bucket: str, entry: MecaEntry, meter: TransferMeter) -> bytes:
    """Extract one JATS entry with a ranged GET at its local header."""
    end = entry.local_offset + 30 + len(entry.name) + 2_048 + entry.comp_size
    resp = s3.get_object(
        Bucket=bucket, Key=entry.key, RequestPayer="requester",
        Range=f"bytes={entry.local_offset}-{end}",
    )
    blob = resp["Body"].read()
    meter.add(len(blob))
    if blob[:4] != b"PK\x03\x04":
        raise ValueError(f"no local header at offset for {entry.key}")
    nlen, elen = struct.unpack("<HH", blob[26:30])
    start = 30 + nlen + elen
    data = blob[start : start + entry.comp_size]
    if entry.method == 8:
        return zlib.decompress(data, -15)
    if entry.method == 0:
        return data
    raise ValueError(f"unsupported compression method {entry.method}")
