from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import models
import schemas
import security
from database import get_db
from dependencies import get_current_user, require_roles

app = FastAPI(title="CampusCare")


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


# ---------- Departments ----------

@app.get("/departments", response_model=list[schemas.DepartmentOut])
def get_departments(db: Session = Depends(get_db)):
    return db.query(models.Department).all()


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
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()

    if complaint is None or (
        current_user.role == "student" and complaint.user_id != current_user.id
    ):
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


@app.post("/complaints", response_model=schemas.ComplaintOut, status_code=201)
def create_complaint(
    data: schemas.ComplaintCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if data.department_id is not None:
        dept = db.query(models.Department).filter(models.Department.id == data.department_id).first()
        if dept is None:
            raise HTTPException(status_code=400, detail="Invalid department_id")

    complaint = models.Complaint(**data.model_dump(), user_id=current_user.id)
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return complaint


@app.patch("/complaints/{complaint_id}/status", response_model=schemas.ComplaintOut)
def update_status(
    complaint_id: int,
    data: schemas.StatusUpdate,
    db: Session = Depends(get_db),
    staff: models.User = Depends(require_roles("team", "admin")),
):
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")

    complaint.status = data.status
    db.commit()
    db.refresh(complaint)
    return complaint