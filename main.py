from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
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

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="student")
    created_at = Column(DateTime, server_default=func.now())