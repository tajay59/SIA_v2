"""Record the MongoDB reads a service really issues, then `explain` each one (TRD TR-DATA-5).

Wrap a service's async collections with `RecordingCollection`; call the service methods as usual; every
`find`/`find_one` is executed for real and its shape (filter, projection, sort, skip, limit) is kept, so the
check can't drift from the code. `explain_all` runs `explain` with executionStats and grades each plan:

- FAIL  a collection scan (COLLSCAN) anywhere in the plan
- WARN  an in-memory SORT, or more than `ratio` documents examined per document returned
- OK    with a note: a relevance sort over `$text` matches (MongoDB can't rank from an index)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Query:
    label: str
    collection: str
    filter: dict[str, Any]
    projection: dict[str, Any] | None = None
    sort: list[tuple[str, Any]] | None = None
    skip: int = 0
    limit: int = 0


@dataclass
class QueryLog:
    label: str = "?"
    queries: list[Query] = field(default_factory=list)


class _Cursor:
    def __init__(self, real: Any, log: QueryLog, q: Query, kw: dict[str, Any]) -> None:
        self._real, self._log, self._q, self._kw = real, log, q, kw

    def sort(self, spec: Any, direction: Any = None) -> _Cursor:
        self._q.sort = [(spec, direction)] if isinstance(spec, str) else list(spec)
        return self

    def skip(self, n: int) -> _Cursor:
        self._q.skip = n
        return self

    def limit(self, n: int) -> _Cursor:
        self._q.limit = n
        return self

    def max_time_ms(self, ms: int) -> _Cursor:
        self._max_ms = ms
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        self._log.queries.append(self._q)
        cur = self._real.find(self._q.filter, self._q.projection, **self._kw)  # keeps the transaction session
        if self._q.sort:
            cur = cur.sort(self._q.sort)
        if self._q.skip:
            cur = cur.skip(self._q.skip)
        if self._q.limit:
            cur = cur.limit(self._q.limit)
        if getattr(self, "_max_ms", None):
            cur = cur.max_time_ms(self._max_ms)
        return list(await cur.to_list(length))


class RecordingCollection:
    def __init__(self, real: Any, log: QueryLog) -> None:
        self._real, self._log = real, log

    def find(self, filter: dict[str, Any] | None = None, projection: Any = None, **kw: Any) -> _Cursor:
        q = Query(self._log.label, self._real.name, dict(filter or {}), projection)
        return _Cursor(self._real, self._log, q, kw)

    async def find_one(self, filter: dict[str, Any] | None = None, projection: Any = None, **kw: Any) -> Any:
        self._log.queries.append(Query(self._log.label, self._real.name, dict(filter or {}), projection, limit=1))
        return await self._real.find_one(filter, projection, **kw)

    async def count_documents(self, filter: dict[str, Any], **kw: Any) -> int:
        # Explained as a find on the same filter: the planner picks the index the same way.
        self._log.queries.append(Query(f"{self._log.label} (count)", self._real.name, dict(filter)))
        return int(await self._real.count_documents(filter, **kw))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _stages(node: dict[str, Any]) -> list[str]:
    out = [node.get("stage", "?")]
    for key in ("inputStage", "outerStage", "innerStage"):
        if key in node:
            out += _stages(node[key])
    for child in node.get("inputStages", []):
        out += _stages(child)
    return out


@dataclass
class Graded:
    query: Query
    grade: str
    stages: list[str]
    returned: int
    docs: int
    keys: int
    millis: int
    note: str


async def explain_all(db: Any, queries: list[Query], ratio: int = 100) -> list[Graded]:
    graded: list[Graded] = []
    for q in queries:
        cmd: dict[str, Any] = {"find": q.collection, "filter": q.filter}
        if q.projection:
            cmd["projection"] = q.projection
        if q.sort:
            cmd["sort"] = dict(q.sort)
        if q.skip:
            cmd["skip"] = q.skip
        if q.limit:
            cmd["limit"] = q.limit
        res = await db.command({"explain": cmd, "verbosity": "executionStats"})
        st = res["executionStats"]
        stages = _stages(st["executionStages"])
        returned, docs = st["nReturned"], st["totalDocsExamined"]
        grade, note = "OK", ""
        if "COLLSCAN" in stages:
            grade, note = "FAIL", "collection scan"
        elif "SORT" in stages and "TEXT_MATCH" in stages:
            # $text can only rank in memory; cost grows with the number of matches (reported, not graded).
            note = f"text-score sort over {st['totalKeysExamined']} matches"
        elif "SORT" in stages:
            grade, note = "WARN", "in-memory sort"
        elif docs > ratio * max(returned, 1):
            grade, note = "WARN", f"{docs} docs examined for {returned} returned"
        graded.append(
            Graded(q, grade, stages, returned, docs, st["totalKeysExamined"], st["executionTimeMillis"], note)
        )
    return graded


def report(graded: list[Graded]) -> str:
    lines = [f"{'grade':5} {'ms':>5} {'ret':>5} {'docs':>8} {'keys':>8}  query  [plan]"]
    for g in graded:
        plan = ">".join(dict.fromkeys(g.stages))
        note = f"  <- {g.note}" if g.note else ""
        lines.append(f"{g.grade:5} {g.millis:5} {g.returned:5} {g.docs:8} {g.keys:8}  {g.query.label}  [{plan}]{note}")
    return "\n".join(lines)
