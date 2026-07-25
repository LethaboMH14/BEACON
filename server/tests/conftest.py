"""
Pytest configuration and fixtures.
VUKA pattern: clean DB per test, real HTTP client.
"""
import json
import pytest
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Add server/ to path so `src` resolves as a package (its modules use
# package-relative imports — adding src/ itself to the path breaks them)
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.main import app
from src.db.models import Base
from src.db.database import get_db


# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///:memory:"

# Test operator roster (src/auth/operators.py) — every operator_id used
# across the test suite maps to this one fixed token.
TEST_OPERATOR_TOKEN = "test-token"


@pytest.fixture(autouse=True)
def operator_roster(monkeypatch):
    roster = {op: TEST_OPERATOR_TOKEN for op in
              ["op_001", "op_002", "op_003", "op_004", "op_005", "op_x", "ops"]}
    monkeypatch.setenv("OPERATOR_TOKENS", json.dumps(roster))

@pytest.fixture(scope="function")
def db_engine():
    """Create a fresh database engine for each test."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        # StaticPool: share the ONE in-memory connection across threads —
        # without it the TestClient's app thread gets a fresh, EMPTY :memory: db
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a database session for a test."""
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with dependency override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_camera(db_session):
    """Create a sample camera for tests."""
    from src.db.models import Camera
    from datetime import datetime
    
    camera = Camera(
        id="cam_test_001",
        name="Test Camera 1",
        location="Test Street",
        lat=-26.1234,
        lng=28.5678,
        hex_id="881f1d4a9ffffff",
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(camera)
    db_session.commit()
    return camera
