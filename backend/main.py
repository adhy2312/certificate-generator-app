import logging
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

import config
from engines.parser import process_source
from engines.certificate import generate_pdf_from_svg
from engines.mailer import send_certificate_email
from engines.worker import process_batch
from database import engine, Base, get_db
from models import CertificateLog

# Initialize Database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="ISTE CertHub API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PasswordRequest(BaseModel):
    password: str

class SingleProcessRequest(BaseModel):
    name: str
    email: str
    event: str
    tier: str
    date: str = None

class BulkProcessRequest(BaseModel):
    records: List[dict]
    event: str
    date: str = None

@app.post("/api/verify-password")
async def verify_password(req: PasswordRequest):
    if req.password == config.GATEKEEPER_PASSWORD:
        return {"success": True, "token": "authenticated"}
    raise HTTPException(status_code=401, detail="Invalid password")

@app.post("/api/parse-preview")
async def parse_preview(url: str = Form(None), file: UploadFile = File(None)):
    try:
        if file:
            contents = await file.read()
            records = process_source(file_data=contents)
        elif url:
            records = process_source(url=url)
        else:
            raise HTTPException(status_code=400, detail="Provide URL or file")
            
        return {"records": records[:3], "full_records": records}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/process-single")
async def process_single(req: SingleProcessRequest, db: Session = Depends(get_db)):
    logger.info(f"Processing single generation for {req.name}")
    
    cert_log = CertificateLog(
        name=req.name, email=req.email, event=req.event, tier=req.tier, date=req.date
    )
    db.add(cert_log)
    db.commit()
    db.refresh(cert_log)

    pdf_path = generate_pdf_from_svg(req.name, req.event, req.tier, req.date, cert_log.cert_id)
    if not pdf_path:
        cert_log.status = "FAILED"
        db.commit()
        raise HTTPException(status_code=500, detail="PDF generation failed.")
        
    success = send_certificate_email(req.email, req.name, pdf_path, req.event, req.tier, cert_log.cert_id)
    if not success:
        cert_log.status = "FAILED"
        db.commit()
        raise HTTPException(status_code=500, detail="Email dispatch failed.")
        
    cert_log.status = "SENT"
    db.commit()
    return {"success": True, "message": "Certificate generated and sent"}

@app.post("/api/jobs/bulk")
async def process_bulk(req: BulkProcessRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    batch_id = str(uuid.uuid4())
    
    for record in req.records:
        cert_log = CertificateLog(
            batch_id=batch_id,
            name=record.get("Name"),
            email=record.get("Email"),
            event=req.event,
            tier=record.get("Tier"),
            date=req.date
        )
        db.add(cert_log)
    
    db.commit()
    
    # Spawn background task
    background_tasks.add_task(process_batch, batch_id, db)
    
    return {"success": True, "batch_id": batch_id, "total": len(req.records)}

@app.get("/api/jobs/{batch_id}")
async def get_job_status(batch_id: str, db: Session = Depends(get_db)):
    total = db.query(CertificateLog).filter(CertificateLog.batch_id == batch_id).count()
    sent = db.query(CertificateLog).filter(CertificateLog.batch_id == batch_id, CertificateLog.status == "SENT").count()
    failed = db.query(CertificateLog).filter(CertificateLog.batch_id == batch_id, CertificateLog.status == "FAILED").count()
    pending = total - sent - failed
    
    return {
        "batch_id": batch_id,
        "total": total,
        "sent": sent,
        "failed": failed,
        "pending": pending,
        "completed": pending == 0
    }

@app.get("/verify/{cert_id}", response_class=HTMLResponse)
async def verify_certificate(cert_id: str, db: Session = Depends(get_db)):
    cert = db.query(CertificateLog).filter(CertificateLog.cert_id == cert_id).first()
    if not cert:
        return "<h1>Invalid Certificate</h1><p>This certificate does not exist in our system.</p>"
    
    return f"""
    <html>
        <head><title>Verify Certificate</title></head>
        <body style="font-family: sans-serif; text-align: center; padding: 50px;">
            <h1 style="color: green;">✔ Authentic Certificate</h1>
            <p><strong>Name:</strong> {cert.name}</p>
            <p><strong>Event:</strong> {cert.event}</p>
            <p><strong>Tier:</strong> {cert.tier}</p>
            <p><strong>Date:</strong> {cert.date or cert.created_at.strftime('%Y-%m-%d')}</p>
            <p style="color: gray; font-size: 12px; margin-top: 30px;">ISTE MBCET Student Chapter Official Ledger</p>
        </body>
    </html>
    """

import zipfile
import io
import os

@app.get("/api/jobs/{batch_id}/download")
async def download_batch_zip(batch_id: str, db: Session = Depends(get_db)):
    records = db.query(CertificateLog).filter(CertificateLog.batch_id == batch_id).all()
    if not records:
        raise HTTPException(status_code=404, detail="No certificates found for this batch.")
        
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for record in records:
            import re
            safe_name = re.sub(r'[\\/*?:"<>|]', "", record.name).replace(" ", "_")
            filename = f"{safe_name}_{record.cert_id}.pdf"
            pdf_path = os.path.join(config.OUTPUT_DIR, filename)
            
            if os.path.exists(pdf_path):
                zip_file.write(pdf_path, arcname=filename)
                
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=certificates_batch_{batch_id}.zip"
        }
    )
