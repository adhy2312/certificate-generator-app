from sqlalchemy import Column, Integer, String, DateTime
from database import Base
import datetime
import uuid

def generate_uuid():
    return str(uuid.uuid4())

class CertificateLog(Base):
    __tablename__ = "certificate_logs"

    id = Column(Integer, primary_key=True, index=True)
    cert_id = Column(String, unique=True, index=True, default=generate_uuid)
    batch_id = Column(String, index=True, nullable=True)
    name = Column(String, index=True)
    email = Column(String)
    event = Column(String)
    tier = Column(String)
    date = Column(String)
    status = Column(String, default="PENDING") # PENDING, SENT, FAILED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
