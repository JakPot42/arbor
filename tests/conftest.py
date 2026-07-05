"""conftest.py — point the app at a throwaway test database.

DATABASE_URL must be set before database.py is first imported, because the
engine binds at import time. A file-backed test DB (not :memory:) is used
so multiple sessions in one test see the same data — same pattern as
cfius_screener/tests/conftest.py.
"""
from __future__ import annotations

import os
import pathlib
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_arbor.db"

# Tests run from anywhere; make the project root importable.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from database import Base, engine  # noqa: E402
from database import SessionLocal  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    # Every models module must be imported so its tables register on
    # Base.metadata before create_all() -- same reason database.init_db()
    # imports them all inline rather than relying on some other module
    # having imported them first.
    import models.company  # noqa: F401
    import models.ghosttrace  # noqa: F401
    import models.cfius  # noqa: F401
    import models.dib  # noqa: F401
    import models.debt  # noqa: F401
    import models.brief  # noqa: F401
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)




@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
