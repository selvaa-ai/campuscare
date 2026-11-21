from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    location = Column(String(200))
    status = Column(String(30), default="Open")
    created_at = Column(DateTime, server_default=func.now())
    department_id = Column(Integer, ForeignKey("departments.id"))

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="student")
    created_at = Column(DateTime, server_default=func.now())