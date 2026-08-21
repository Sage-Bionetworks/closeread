"""closeread command line. Spec §9.4."""

from __future__ import annotations

import click

from closeread.config import Settings, load_community


@click.group()
def main() -> None:
    """closeread: grounded, evidence-linked fact extraction from publications."""


@main.command()
@click.option("--community", required=True)
@click.option("--citing", is_flag=True, help="Acquire the citing corpus (tiers A-D) instead of the seed corpus.")
def acquire(community: str, citing: bool) -> None:
    """Stage 1: OpenAlex metadata, then full text."""
    from closeread.acquire import acquire_citing, acquire_corpus

    if citing:
        acquire_citing(load_community(community), Settings())
    else:
        acquire_corpus(load_community(community), Settings())


@main.command()
@click.option("--community", required=True)
def parse(community: str) -> None:
    """Stage 2: JATS to plain text plus a section index."""
    from closeread.parse import run_parse

    run_parse(load_community(community), Settings())


@main.command()
@click.option("--community", required=True)
def candidates(community: str) -> None:
    """Stage 3: regular-expression candidates. Candidates never decide meaning."""
    from closeread.candidates import run_candidates

    run_candidates(load_community(community), Settings())


@main.command()
@click.option("--community", required=True)
@click.option("--pass", "pass_name", required=True)
@click.option("--dry-run", is_flag=True, help="Print request count and cost estimate; submit nothing.")
@click.option("--model", default=None, help="Override the pass model.")
@click.option("--skip-canary", is_flag=True, hidden=True)
def extract(community: str, pass_name: str, dry_run: bool, model: str | None, skip_canary: bool) -> None:
    """Stage 4: submit one batch job for one pass. Canary gates the fan-out."""
    from closeread.extract import run_extract

    run_extract(
        load_community(community),
        Settings(),
        pass_name,
        dry_run=dry_run,
        model_override=model,
        skip_canary=skip_canary,
    )


@main.command()
@click.option("--run", "run_id", required=True)
def status(run_id: str) -> None:
    """Check the state of a submitted batch job."""
    from closeread.extract.batch import print_status

    print_status(run_id, Settings())


@main.command()
@click.option("--run", "run_id", required=True)
def collect(run_id: str) -> None:
    """Stage 5: harvest responses, align spans, write records."""
    from closeread.collect import run_collect

    run_collect(run_id, Settings())


@main.command()
@click.option("--value-set", required=True)
@click.option("--community", default="htan")
def normalise(value_set: str, community: str) -> None:
    """Stage 6: generate and apply a vocabulary mapping table."""
    from closeread.normalise import run_normalise

    run_normalise(load_community(community), Settings(), value_set)


@main.command()
@click.option("--run", "run_id", required=True)
@click.option("--model", default=None, help="Judge model; must differ from the extractor.")
def judge(run_id: str, model: str | None) -> None:
    """Stage 7: adjudicate records (submits a canary-gated batch job)."""
    from closeread.judge import run_judge

    run_judge(run_id, Settings(), judge_model=model)


@main.command("judge-collect")
@click.option("--run", "run_id", required=True)
@click.option("--job-tag", required=True)
def judge_collect(run_id: str, job_tag: str) -> None:
    """Harvest judge verdicts and rebuild silver."""
    from closeread.judge import collect_judge

    collect_judge(run_id, job_tag, Settings())


@main.command()
@click.option("--runs", multiple=True, required=True)
@click.option("--community", default="htan")
def report(runs: tuple[str, ...], community: str) -> None:
    """Stage 8: build gold tables, figures, and REPORT.md."""
    from closeread.report import run_report

    run_report(load_community(community), Settings(), list(runs))


if __name__ == "__main__":
    main()
