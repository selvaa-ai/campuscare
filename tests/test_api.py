import email_service

SAMPLE = {
    "title": "Fan not working",
    "description": "Room 204 fan is off",
    "location": "Block A, Room 204",
}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def create_complaint(client, headers, **extra):
    r = client.post("/complaints", json={**SAMPLE, **extra}, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


def test_register_and_duplicate(client):
    body = {"name": "A", "email": "a@example.com", "password": "Secret123"}
    r = client.post("/auth/register", json=body)
    assert r.status_code == 201
    assert "password" not in r.json()
    assert "hashed_password" not in r.json()
    assert client.post("/auth/register", json=body).status_code == 409


def test_login_wrong_password(client):
    client.post("/auth/register", json={"name": "A", "email": "a@example.com", "password": "Secret123"})
    r = client.post("/auth/login", data={"username": "a@example.com", "password": "wrong"})
    assert r.status_code == 401


def test_complaints_require_login(client):
    assert client.get("/complaints").status_code == 401


def test_complaint_is_routed_to_department(client, make_user, seed):
    h = make_user("s1@example.com")
    r = client.post("/complaints", json={**SAMPLE, "category_id": seed["category_id"]}, headers=h)
    assert r.status_code == 201
    assert r.json()["department_id"] == seed["department_id"]


def test_invalid_category_rejected(client, make_user, seed):
    h = make_user("s1@example.com")
    r = client.post("/complaints", json={**SAMPLE, "category_id": 9999}, headers=h)
    assert r.status_code == 400


def test_student_sees_only_own_complaints(client, make_user):
    h1 = make_user("s1@example.com")
    h2 = make_user("s2@example.com")
    create_complaint(client, h1)
    assert len(client.get("/complaints", headers=h1).json()) == 1
    assert client.get("/complaints", headers=h2).json() == []


def test_student_cannot_change_status(client, make_user):
    h = make_user("s1@example.com")
    cid = create_complaint(client, h)
    r = client.patch(f"/complaints/{cid}/status", json={"status": "In Progress"}, headers=h)
    assert r.status_code == 403


def test_status_workflow_and_history(client, make_user):
    student = make_user("s1@example.com")
    admin = make_user("admin@example.com", role="admin")
    cid = create_complaint(client, student)

    r = client.patch(f"/complaints/{cid}/status", json={"status": "Resolved"}, headers=admin)
    assert r.status_code == 400  # Open -> Resolved allowed illa

    assert client.patch(f"/complaints/{cid}/status", json={"status": "In Progress"}, headers=admin).status_code == 200
    assert client.patch(f"/complaints/{cid}/status", json={"status": "Resolved"}, headers=admin).status_code == 200

    history = client.get(f"/complaints/{cid}/history", headers=student).json()
    assert [h["new_status"] for h in history] == ["Open", "In Progress", "Resolved"]


def test_reopen_only_by_reporter(client, make_user):
    student = make_user("s1@example.com")
    admin = make_user("admin@example.com", role="admin")
    cid = create_complaint(client, student)
    client.patch(f"/complaints/{cid}/status", json={"status": "In Progress"}, headers=admin)
    client.patch(f"/complaints/{cid}/status", json={"status": "Resolved"}, headers=admin)

    assert client.post(f"/complaints/{cid}/reopen", json={}, headers=admin).status_code == 403
    r = client.post(f"/complaints/{cid}/reopen", json={"note": "Still broken"}, headers=student)
    assert r.status_code == 200
    assert r.json()["status"] == "Open"


def test_fake_image_rejected(client, make_user):
    h = make_user("s1@example.com")
    cid = create_complaint(client, h)
    files = {"file": ("fake.jpg", b"this is not an image", "image/jpeg")}
    assert client.post(f"/complaints/{cid}/images", files=files, headers=h).status_code == 400


def test_image_upload_and_privacy(client, make_user):
    owner = make_user("s1@example.com")
    other = make_user("s2@example.com")
    cid = create_complaint(client, owner)

    files = {"file": ("photo.png", PNG, "image/png")}
    r = client.post(f"/complaints/{cid}/images", files=files, headers=owner)
    assert r.status_code == 201
    image_id = r.json()["id"]

    assert client.get(f"/images/{image_id}", headers=owner).status_code == 200
    assert client.get(f"/images/{image_id}", headers=other).status_code == 404


def test_department_gets_email(client, make_user, seed, monkeypatch):
    sent = []
    monkeypatch.setattr(email_service, "send_email", lambda to, subject, body: sent.append(to))
    h = make_user("s1@example.com")
    create_complaint(client, h, category_id=seed["category_id"])
    assert sent == ["maint@example.com"]


def test_reporter_gets_email_on_status_change(client, make_user, monkeypatch):
    sent = []
    monkeypatch.setattr(email_service, "send_email", lambda to, subject, body: sent.append(to))
    student = make_user("s1@example.com")
    admin = make_user("admin@example.com", role="admin")
    cid = create_complaint(client, student)
    client.patch(f"/complaints/{cid}/status", json={"status": "In Progress"}, headers=admin)
    assert sent == ["s1@example.com"]