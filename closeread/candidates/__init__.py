"""Stage 3: candidates."""

from __future__ import annotations

from closeread.candidates.patterns import compile_patterns, find_candidates, uncovered_candidates
from closeread.config import CommunityConfig, Settings
from closeread.jsonl import write_jsonl
from closeread.parse import load_parsed

__all__ = ["run_candidates", "compile_patterns", "find_candidates", "uncovered_candidates"]


def run_candidates(config: CommunityConfig, settings: Settings, log=print) -> int:
    out_dir = settings.community_dir(config.community)
    patterns = compile_patterns(config)
    all_candidates = []
    n_docs = 0
    for path in sorted((out_dir / "parsed").glob("*.json")):
        parsed = load_parsed(path)
        n_docs += 1
        all_candidates.extend(find_candidates(path.stem, parsed, patterns))
    dest = out_dir / "candidates.jsonl"
    n = write_jsonl(dest, all_candidates)
    by_kind: dict[str, int] = {}
    for c in all_candidates:
        by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
    log(f"candidates: {n} from {n_docs} docs {by_kind} -> {dest}")
    return n
