"""Test helpers. `AsyncMongoMock` wraps mongomock so service code written against the PyMongo
Async API (`await coll.find_one(...)`, `async for d in coll.find(...)`) runs in unit tests
without a database. Integration tests use a real replica set (testcontainers / dev compose).

Not imported by production code; requires `mongomock` (dev dependency).
"""

from __future__ import annotations

from typing import Any


class _AsyncCursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def sort(self, *args: Any, **kwargs: Any) -> _AsyncCursor:
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def limit(self, n: int) -> _AsyncCursor:
        self._cursor = self._cursor.limit(n)
        return self

    def skip(self, n: int) -> _AsyncCursor:
        self._cursor = self._cursor.skip(n)
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        docs = list(self._cursor)
        return docs if length is None else docs[:length]

    def __aiter__(self) -> _AsyncCursor:
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            doc: dict[str, Any] = next(self._cursor)
            return doc
        except StopIteration:
            raise StopAsyncIteration from None


class AsyncCollection:
    def __init__(self, coll: Any) -> None:
        self._c = coll
        self.name = coll.name

    async def find_one(self, *a: Any, **kw: Any) -> Any:
        return self._c.find_one(*a, **kw)

    def find(self, *a: Any, **kw: Any) -> _AsyncCursor:
        return _AsyncCursor(self._c.find(*a, **kw))

    async def insert_one(self, doc: dict[str, Any], **kw: Any) -> Any:
        return self._c.insert_one(doc)

    async def insert_many(self, docs: list[dict[str, Any]], **kw: Any) -> Any:
        return self._c.insert_many(docs)

    async def update_one(self, *a: Any, **kw: Any) -> Any:
        return self._c.update_one(*a, **kw)

    async def update_many(self, *a: Any, **kw: Any) -> Any:
        return self._c.update_many(*a, **kw)

    async def find_one_and_update(self, *a: Any, **kw: Any) -> Any:
        return self._c.find_one_and_update(*a, **kw)

    async def delete_one(self, *a: Any, **kw: Any) -> Any:
        return self._c.delete_one(*a, **kw)

    async def delete_many(self, *a: Any, **kw: Any) -> Any:
        return self._c.delete_many(*a, **kw)

    async def count_documents(self, *a: Any, **kw: Any) -> int:
        return int(self._c.count_documents(*a, **kw))

    async def aggregate(self, pipeline: list[dict[str, Any]], **kw: Any) -> _AsyncCursor:
        # PyMongo Async: `await coll.aggregate(...)` returns a cursor.
        return _AsyncCursor(iter(list(self._c.aggregate(pipeline))))

    async def create_index(self, keys: Any, **kw: Any) -> str:
        kw.pop("collation", None)  # mongomock doesn't support collations
        kw.pop("partialFilterExpression", None)
        return str(self._c.create_index(keys, **kw))


class AsyncMongoMock:
    """Stand-in for `AsyncMongoClient(...)[db]`."""

    def __init__(self, name: str = "inventory") -> None:
        import mongomock

        self._db: Any = mongomock.MongoClient(tz_aware=True)[name]

    def __getitem__(self, name: str) -> AsyncCollection:
        return AsyncCollection(self._db[name])

    async def command(self, *a: Any, **kw: Any) -> dict[str, Any]:
        return {"ok": 1}
