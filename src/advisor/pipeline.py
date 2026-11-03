"""Local end-to-end build: PDFs → products/chunks → KG → compatibility matrix → artifacts.

Skeleton only. Each step delegates to its module contract; fill them in per backlog item.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable

from advisor.config import Settings, get_settings

log = logging.getLogger(__name__)

STEPS: tuple[str, ...] = (
    "discover",  # ingestion.discover_documents
    "parse",  # parsing.parse_document / parse_catalog
    "extract",  # extraction.extract_product
    "enrich",  # enrichment.join_catalog
    "chunk",  # chunking.chunk_document
    "kg",  # kg.build_graph + kg.save
    "compat_matrix",  # compatibility.evaluate over every (discontinued, active) pair
    "export",  # repository.ArtifactRepository
)


def _not_implemented(step: str) -> Callable[[Settings], None]:
    def run(_: Settings) -> None:
        raise NotImplementedError(f"pipeline step '{step}' is not implemented yet")

    return run


RUNNERS: dict[str, Callable[[Settings], None]] = {step: _not_implemented(step) for step in STEPS}


def run(steps: tuple[str, ...] = STEPS, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    for step in steps:
        log.info("pipeline step", extra={"step": step})
        RUNNERS[step](settings)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", nargs="*", choices=STEPS, default=list(STEPS))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    run(tuple(args.steps))


if __name__ == "__main__":
    main()
