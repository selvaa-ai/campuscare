from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Welcome to CampusCare"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/hello/{name}")
def hello(name: str):
    return {"message": f"Hello {name}"}


@app.get("/complaints")
def get_complaints():
    return [
        {"id": 1, "title": "Water leakage", "status": "Open"},
        {"id": 2, "title": "Broken fan", "status": "Resolved"},
    ]


@app.get("/complaints/{complaint_id}")
def get_complaint(complaint_id: int):
    return {"id": complaint_id, "title": "Sample complaint", "status": "Open"}

class Complaint(BaseModel):
    title: str
    description: str
    location: str


@app.post("/complaints")
def create_complaint(complaint: Complaint):
    return {"message": "Complaint received", "data": complaint}