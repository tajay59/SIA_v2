"""Every service app, built with in-memory fakes, for `check_matrix.py --app apps:<name>`.

CI runs the gate against each one, so an endpoint that is served but missing from
tests/authz/matrix.yaml fails the build.
"""

from __future__ import annotations

from typing import Any


def _identity() -> Any:
    import fakeredis.aioredis

    from cimh_common.testing import AsyncMongoMock
    from identity_svc.config import Settings
    from identity_svc.main import build_app

    return build_app(Settings(), db=AsyncMongoMock(), redis=fakeredis.aioredis.FakeRedis(), configure_logs=False)


def _hello() -> Any:
    from hello_svc.main import app

    return app


identity = _identity()
hello = _hello()
