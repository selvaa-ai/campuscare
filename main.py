from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
import security
from database import get_db

app = FastAPI(title="CampusCare")


@app.get("/")
def home():
    return {"message": "Welcome to CampusCare"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/departments", response_model=list[schemas.DepartmentOut])
def get_departments(db: Session = Depends(get_db)):
    return db.query(models.Department).all()


@app.get("/complaints", response_model=list[schemas.ComplaintOut])
def get_complaints(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.Complaint)
    if status:
        query = query.filter(models.Complaint.status == status)
    return query.order_by(models.Complaint.created_at.desc()).all()


@app.get("/complaints/{complaint_id}", response_model=schemas.ComplaintOut)
def get_complaint(complaint_id: int, db: Session = Depends(get_db)):
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


@app.post("/complaints", response_model=schemas.ComplaintOut, status_code=201)
def create_complaint(data: schemas.ComplaintCreate, db: Session = Depends(get_db)):
    if data.department_id is not None:
        dept = db.query(models.Department).filter(models.Department.id == data.department_id).first()
        if dept is None:
            raise HTTPException(status_code=400, detail="Invalid department_id")

    complaint = models.Complaint(**data.model_dump())
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return complaint


@app.patch("/complaints/{complaint_id}/status", response_model=schemas.ComplaintOut)
def update_status(complaint_id: int, data: schemas.StatusUpdate, db: Session = Depends(get_db)):
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")

    complaint.status = data.status
    db.commit()
    db.refresh(complaint)
    return complaint



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