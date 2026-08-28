"""Pydantic models for every table in spec §8."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def _sha1_16(payload: str) -> str:
    # Not a security primitive: SHA-1 is used only as a short, stable, deterministic
    # ID generator for record/edge keys. usedforsecurity=False silences Bandit B324.
    return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def make_record_id(doc_id: str, extraction_class: str, char_start: int, char_end: int, run_id: str) -> str:
    return _sha1_16(f"{doc_id}{extraction_class}{char_start}{char_end}{run_id}")


def make_edge_id(citing_doc_id: str, cited_doc_id: str) -> str:
    return _sha1_16(f"{citing_doc_id}{cited_doc_id}")


class AlignmentStatus(StrEnum):
    match_exact = "match_exact"
    match_fuzzy = "match_fuzzy"
    match_lesser = "match_lesser"


class JudgeVerdict(StrEnum):
    confirmed = "confirmed"
    rejected = "rejected"
    uncertain = "uncertain"


class AuthorOverlap(StrEnum):
    is_corpus_document = "is_corpus_document"
    shared_senior_author = "shared_senior_author"
    shared_author = "shared_author"
    external = "external"


class EvidenceScope(StrEnum):
    full_text = "full_text"
    abstract_only = "abstract_only"


class Record(BaseModel):
    """One extracted fact. Spec §8.3."""

    record_id: str
    run_id: str
    doc_id: str
    community: str
    pass_name: str
    extraction_class: str
    source_quote: str
    char_start: int
    char_end: int
    source_section: str = "unknown"
    alignment_status: AlignmentStatus
    attributes: dict[str, Any]
    attributes_canonical: dict[str, Any] | None = None
    enum_drift: list[str] = Field(default_factory=list)
    candidate_support: bool = False
    judge_verdict: JudgeVerdict | None = None
    judge_confidence: float | None = None
    judge_reason: str | None = None
    extractor_model: str
    prompt_version: str
    schema_version: str
    evidence_scope: EvidenceScope = EvidenceScope.full_text


class RejectedRecord(Record):
    """A record that failed alignment or validation. Never shipped. Rule 6.6."""

    alignment_status: AlignmentStatus | None = None  # type: ignore[assignment]
    char_start: int | None = None  # type: ignore[assignment]
    char_end: int | None = None  # type: ignore[assignment]
    reject_reason: str


class Document(BaseModel):
    """Spec §8.4."""

    doc_id: str
    doc_type: str  # "corpus" or "citing"
    community: str
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    title: str | None = None
    pub_date: str | None = None
    venue: str | None = None
    oa_status: str | None = None
    source_version: str | None = None
    group_key: str | None = None
    merged_from: list[str] = Field(default_factory=list)
    snapshot_date: str | None = None
    author_ids: list[str] = Field(default_factory=list)
    institution_ids: list[str] = Field(default_factory=list)
    author_overlap: AuthorOverlap | None = None
    n_shared_authors: int | None = None
    shared_author_ids: list[str] = Field(default_factory=list)
    is_preprint: bool = False
    abstract: str | None = None


class CitationEdge(BaseModel):
    edge_id: str
    citing_doc_id: str
    cited_doc_id: str


class Candidate(BaseModel):
    """A regex match. Locates text; never decides meaning. Spec §5.4, §3.2."""

    doc_id: str
    kind: str
    value: str
    char_start: int
    char_end: int
    section: str = "unknown"


class VocabMapEntry(BaseModel):
    value_set: str
    surface_form: str
    canonical_form: str
    mapping_version: str


class Run(BaseModel):
    """Spec §8.4. One execution of one pass over one community."""

    run_id: str
    community: str
    pass_name: str
    model: str
    prompt_version: str
    schema_version: str
    submitted_at: str
    n_requests: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_estimate: float | None = None
    canary_passed: bool = False
    sections_read: list[str] | None = None  # None = whole document (§4.2.1)
    batch_job_name: str | None = None
    status: str = "submitted"


class GoldLabel(BaseModel):
    """Separate table so human labels survive re-extraction. Spec §8.4."""

    record_id: str
    human_label: str
    labeller: str
    labelled_at: str
