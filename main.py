import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import email_service
import models
import schemas
import security
from database import get_db
from dependencies import get_current_user, require_roles

app = FastAPI(title="CampusCare")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_IMAGES_PER_COMPLAINT = 5

ALLOWED_TRANSITIONS = {
    "Open": ["In Progress"],
    "In Progress": ["Resolved"],
    "Resolved": [],
}


# ---------- Helpers ----------

def get_complaint_or_404(db: Session, complaint_id: int, user: models.User) -> models.Complaint:
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if complaint is None or (user.role == "student" and complaint.user_id != user.id):
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


def detect_image_type(data: bytes):
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def notify_department(background_tasks: BackgroundTasks, db: Session, complaint: models.Complaint, event: str):
    if complaint.department_id is None:
        return
    dept = db.get(models.Department, complaint.department_id)
    if dept is None or not dept.email:
        return
    body = (
        f"{event}\n\n"
        f"Complaint #{complaint.id}: {complaint.title}\n"
        f"Location: {complaint.location}\n"
        f"Status: {complaint.status}\n\n"
        f"{complaint.description or ''}"
    )
    background_tasks.add_task(
        email_service.send_email, dept.email, f"[CampusCare] {event}: #{complaint.id}", body
    )


def notify_reporter(background_tasks: BackgroundTasks, db: Session, complaint: models.Complaint, note: str | None):
    if complaint.user_id is None:
        return
    reporter = db.get(models.User, complaint.user_id)
    if reporter is None:
        return
    body = (
        f"Hi {reporter.name},\n\n"
        f"Your complaint #{complaint.id} ({complaint.title}) is now: {complaint.status}\n"
        f"{('Note: ' + note) if note else ''}"
    )
    background_tasks.add_task(
        email_service.send_email, reporter.email, f"[CampusCare] Complaint #{complaint.id} is {complaint.status}", body
    )


# ---------- Basic ----------

@app.get("/")
def home():
    return {"message": "Welcome to CampusCare"}


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Auth ----------

@app.post("/auth/register", response_model=schemas.UserOut, status_code=201)
def register(data: schemas.UserCreate, db: Session = Depends(get_db)):
    email = data.email.lower()

    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = models.User(
        name=data.name,
        email=email,
        hashed_password=security.hash_password(data.password),
        role="student",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username.lower()).first()

    if user is None or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = security.create_access_token(user.id, user.role)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/auth/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


# ---------- Users (admin only) ----------

@app.patch("/users/{user_id}/role", response_model=schemas.UserOut)
def update_role(
    user_id: int,
    data: schemas.RoleUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_roles("admin")),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = data.role
    db.commit()
    db.refresh(user)
    return user


# ---------- Departments and categories ----------

@app.get("/departments", response_model=list[schemas.DepartmentOut])
def get_departments(db: Session = Depends(get_db)):
    return db.query(models.Department).all()


@app.get("/categories", response_model=list[schemas.CategoryOut])
def get_categories(db: Session = Depends(get_db)):
    return db.query(models.Category).order_by(models.Category.name).all()


# ---------- Complaints ----------

@app.get("/complaints", response_model=list[schemas.ComplaintOut])
def get_complaints(
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Complaint)

    if current_user.role == "student":
        query = query.filter(models.Complaint.user_id == current_user.id)
    if status:
        query = query.filter(models.Complaint.status == status)

    return query.order_by(models.Complaint.created_at.desc()).all()


@app.get("/complaints/{complaint_id}", response_model=schemas.ComplaintOut)
def get_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return get_complaint_or_404(db, complaint_id, current_user)


@app.post("/complaints", response_model=schemas.ComplaintOut, status_code=201)
def create_complaint(
    data: schemas.ComplaintCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    department_id = data.department_id

    if data.category_id is not None:
        category = db.query(models.Category).filter(models.Category.id == data.category_id).first()
        if category is None:
            raise HTTPException(status_code=400, detail="Invalid category_id")
        department_id = category.department_id  # routing: category -> department
    elif department_id is not None:
        dept = db.query(models.Department).filter(models.Department.id == department_id).first()
        if dept is None:
            raise HTTPException(status_code=400, detail="Invalid department_id")

    complaint = models.Complaint(
        title=data.title,
        description=data.description,
        location=data.location,
        category_id=data.category_id,
        department_id=department_id,
        user_id=current_user.id,
    )
    db.add(complaint)
    db.flush()

    db.add(models.StatusHistory(
        complaint_id=complaint.id,
        old_status=None,
        new_status="Open",
        changed_by=current_user.id,
        note="Complaint created",
    ))
    db.commit()
    db.refresh(complaint)

    notify_department(background_tasks, db, complaint, "New complaint")
    return complaint


@app.patch("/complaints/{complaint_id}/status", response_model=schemas.ComplaintOut)
def update_status(
    complaint_id: int,
    data: schemas.StatusUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    staff: models.User = Depends(require_roles("team", "admin")),
):
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")

    old_status = complaint.status
    if data.status not in ALLOWED_TRANSITIONS.get(old_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot change status from '{old_status}' to '{data.status}'",
        )

    complaint.status = data.status
    db.add(models.StatusHistory(
        complaint_id=complaint.id,
        old_status=old_status,
        new_status=data.status,
        changed_by=staff.id,
        note=data.note,
    ))
    db.commit()
    db.refresh(complaint)

    notify_reporter(background_tasks, db, complaint, data.note)
    return complaint


@app.post("/complaints/{complaint_id}/reopen", response_model=schemas.ComplaintOut)
def reopen_complaint(
    complaint_id: int,
    data: schemas.NoteIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    complaint = get_complaint_or_404(db, complaint_id, current_user)

    if complaint.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the reporter can reopen a complaint")
    if complaint.status != "Resolved":
        raise HTTPException(status_code=400, detail="Only resolved complaints can be reopened")

    complaint.status = "Open"
    db.add(models.StatusHistory(
        complaint_id=complaint.id,
        old_status="Resolved",
        new_status="Open",
        changed_by=current_user.id,
        note=data.note or "Reopened by reporter",
    ))
    db.commit()
    db.refresh(complaint)

    notify_department(background_tasks, db, complaint, "Complaint reopened")
    return complaint


@app.get("/complaints/{complaint_id}/history", response_model=list[schemas.StatusHistoryOut])
def get_history(
    complaint_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_complaint_or_404(db, complaint_id, current_user)
    return (
        db.query(models.StatusHistory)
        .filter(models.StatusHistory.complaint_id == complaint_id)
        .order_by(models.StatusHistory.changed_at.asc(), models.StatusHistory.id.asc())
        .all()
    )


# ---------- Images ----------

@app.post("/complaints/{complaint_id}/images", response_model=schemas.ImageOut, status_code=201)
def upload_image(
    complaint_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_complaint_or_404(db, complaint_id, current_user)

    count = (
        db.query(models.ComplaintImage)
        .filter(models.ComplaintImage.complaint_id == complaint_id)
        .count()
    )
    if count >= MAX_IMAGES_PER_COMPLAINT:
        raise HTTPException(status_code=400, detail="Maximum 5 images per complaint")

    data = file.file.read(MAX_IMAGE_SIZE + 1)
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="Image too large (max 5 MB)")

    detected = detect_image_type(data)
    if detected is None:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG or WEBP images are allowed")
    content_type, ext = detected

    stored_name = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / stored_name).write_bytes(data)

    image = models.ComplaintImage(
        complaint_id=complaint_id,
        stored_name=stored_name,
        original_name=file.filename,
        content_type=content_type,
        uploaded_by=current_user.id,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


@app.get("/complaints/{complaint_id}/images", response_model=list[schemas.ImageOut])
def list_images(
    complaint_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_complaint_or_404(db, complaint_id, current_user)
    return (
        db.query(models.ComplaintImage)
        .filter(models.ComplaintImage.complaint_id == complaint_id)
        .order_by(models.ComplaintImage.id.asc())
        .all()
    )


@app.get("/images/{image_id}")
def get_image(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    image = db.query(models.ComplaintImage).filter(models.ComplaintImage.id == image_id).first()
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    get_complaint_or_404(db, image.complaint_id, current_user)

    path = UPLOAD_DIR / image.stored_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file missing")
    return FileResponse(path, media_type=image.content_type)