import pytest

from pramaan.core.database import init_db


@pytest.fixture(autouse=True)
def _db_ready() -> None:
    init_db()
