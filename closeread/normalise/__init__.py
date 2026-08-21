"""Stage 6: normalise."""

from __future__ import annotations

from closeread.config import CommunityConfig, Settings


def run_normalise(config: CommunityConfig, settings: Settings, value_set: str, log=print) -> None:
    from closeread.extract.batch import STRONG_MODEL
    from closeread.normalise.vocab import apply_to_silver, generate_mapping

    generate_mapping(settings, config.community, value_set, STRONG_MODEL, log=log)
    apply_to_silver(settings, config.community, log=log)
