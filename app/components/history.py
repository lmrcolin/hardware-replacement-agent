"""Search history and trends for the agent chat.

Every question sent to the agent is appended to a local JSON Lines log (default
``.cache/advisor/searches.jsonl``, git-ignored; override with ``ADVISOR_SEARCH_LOG``). Ratings
("¿Te fue útil?") go to the same file. Trends group searches by the part the agent resolved, or by
category when it searched by requirements, so "E810", "Intel E810" and "E810-CQDA2" count as one.
Presentation only: nothing here feeds the agent.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from advisor.config import REPO_ROOT
from advisor.models import RecommendationResponse

LOG_ENV = "ADVISOR_SEARCH_LOG"
DEFAULT_LOG = REPO_ROOT / ".cache" / "advisor" / "searches.jsonl"
OUTCOME_LABEL = {
    "recommended": "con sustituto",
    "risky": "solo opciones con riesgo",
    "unverified": "sin datos suficientes",
    "none": "sin sustituto",
    "clarify": "pidió aclaración",
}


def log_path() -> Path:
    return Path(os.environ.get(LOG_ENV) or DEFAULT_LOG)


def outcome(response: RecommendationResponse) -> str:
    if response.clarification_question:
        return "clarify"
    if response.recommendations:
        return "recommended"
    if response.risky_options:
        return "risky"
    if response.unverified_options:
        return "unverified"
    return "none"


def search_record(
    turn_id: str, shown: str, sent: str, response: RecommendationResponse, source: str
) -> dict[str, Any]:
    parsed = response.parsed_query
    return {
        "type": "search",
        "id": turn_id,
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "text": shown,
        "sent": sent,
        "part": response.original.part_number if response.original else None,
        "category": parsed.category.value if parsed and parsed.category else None,
        "outcome": outcome(response),
        "source": source,
    }


class SearchLog:
    """Append-only JSONL log; unreadable lines are skipped, never fatal for the UI."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or log_path()

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def rate(self, turn_id: str, useful: bool) -> None:
        self.append(
            {
                "type": "feedback",
                "id": turn_id,
                "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                "useful": useful,
            }
        )

    def read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows


def searches(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("type") == "search" and r.get("text")]


def topic(record: dict[str, Any]) -> str:
    """What the search was about: resolved part > category > the text itself."""
    return str(record.get("part") or record.get("category") or record["text"]).strip()


def recent(rows: Iterable[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    """Latest distinct questions, newest first."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for record in reversed(searches(rows)):
        key = record["text"].casefold()
        if key not in seen:
            seen.add(key)
            out.append(record)
        if len(out) == limit:
            break
    return out


@dataclass(frozen=True)
class Trend:
    topic: str
    total: int  # searches in the window
    previous: int  # searches in the window before it
    example: str  # latest question about this topic (to re-ask it)

    @property
    def direction(self) -> str:
        if self.total > self.previous:
            return "up"
        if self.total < self.previous:
            return "down"
        return "flat"


def trending(
    rows: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
    days: int = 7,
    limit: int = 5,
) -> list[Trend]:
    """Most searched topics in the last ``days``, compared with the ``days`` before."""
    now = now or datetime.now(UTC)
    start, before = now - timedelta(days=days), now - timedelta(days=2 * days)
    current: Counter[str] = Counter()
    previous: Counter[str] = Counter()
    example: dict[str, str] = {}
    for record in searches(rows):
        try:
            ts = datetime.fromisoformat(record["ts"])
        except (KeyError, ValueError):
            continue
        name = topic(record)
        if ts >= start:
            current[name] += 1
            example[name] = record["sent"] if record.get("sent") else record["text"]
        elif ts >= before:
            previous[name] += 1
    ranked = sorted(current.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return [Trend(name, count, previous[name], example[name]) for name, count in ranked]


def satisfaction(rows: Iterable[dict[str, Any]]) -> tuple[int, int]:
    """(useful, rated) over the latest rating per answer."""
    latest: dict[str, bool] = {}
    for record in rows:
        if record.get("type") == "feedback" and "id" in record:
            latest[record["id"]] = bool(record.get("useful"))
    return sum(latest.values()), len(latest)
