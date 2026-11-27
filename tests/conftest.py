import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL or not TEST_DATABASE_URL.rsplit("/", 1)[-1].endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must point to a database whose name ends with '_test'")

os.environ["EMAIL_ENABLED"] = "false"

import main  # noqa: E402
import models  # noqa: E402
from database import Base, get_db  # noqa: E402

engine = create_engine(TEST_DATABASE_URL)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db_session():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session, tmp_path, monkeypatch):
    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


@pytest.fixture()
def seed(db_session):
    dept = models.Department(name="Maintenance", email="maint@example.com")
    db_session.add(dept)
    db_session.flush()
    cat = models.Category(name="Electrical", department_id=dept.id)
    db_session.add(cat)
    db_session.commit()
    return {"department_id": dept.id, "category_id": cat.id}


@pytest.fixture()
def make_user(client, db_session):
    def _make(email, role="student"):
        password = "Test@1234"
        client.post("/auth/register", json={"name": "Test User", "email": email, "password": password})
        if role != "student":
            user = db_session.query(models.User).filter(models.User.email == email).first()
            user.role = role
            db_session.commit()
        r = client.post("/auth/login", data={"username": email, "password": password})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _make