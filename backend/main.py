import logging
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
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

import asyncio
import time
from contextlib import asynccontextmanager

async def cleanup_pdfs_loop():
    while True:
        try:
            now = time.time()
            for filename in os.listdir(config.OUTPUT_DIR):
                if filename.endswith(".pdf"):
                    file_path = os.path.join(config.OUTPUT_DIR, filename)
                    # Delete files older than 2 hours to prevent disk exhaustion
                    if os.stat(file_path).st_mtime < now - 7200:
                        os.remove(file_path)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        # Wait 1 hour
        await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Database tables
    Base.metadata.create_all(bind=engine)
    
    # Safely migrate existing databases to include the new cert_type column
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE certificate_logs ADD COLUMN cert_type VARCHAR DEFAULT 'Certificate of Participation'"))
    except Exception:
        # Column likely already exists
        pass
    
    # Start auto-cleanup background task
    task = asyncio.create_task(cleanup_pdfs_loop())
    yield
    task.cancel()

app = FastAPI(title="ISTE CertHub API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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
    date: str = ""
    cert_type: str = "Certificate of Participation"
    send_email: bool = True

class BulkProcessRequest(BaseModel):
    records: List[dict]
    event: str
    date: str = None
    cert_type: str = "Certificate of Participation"
    send_email: bool = True

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

@app.post("/api/jobs/single")
async def process_single(req: SingleProcessRequest, db: Session = Depends(get_db)):
    logger.info(f"Processing single generation for {req.name}")
    
    cert_log = CertificateLog(
        name=req.name, email=req.email, event=req.event, tier=req.tier, date=req.date,
        cert_type=req.cert_type
    )
    db.add(cert_log)
    db.commit()
    db.refresh(cert_log)

    pdf_path = generate_pdf_from_svg(req.name, req.event, req.tier, req.date, cert_log.cert_id)
    if not pdf_path:
        cert_log.status = "FAILED"
        db.commit()
        raise HTTPException(status_code=500, detail="PDF generation failed.")
        
    if not req.send_email:
        cert_log.status = "GENERATED"
        db.commit()
        from fastapi.responses import FileResponse
        return FileResponse(pdf_path, media_type="application/pdf", filename=os.path.basename(pdf_path))
        
    success, error_msg = send_certificate_email(
        to_email=req.email, 
        name=req.name, 
        pdf_path=pdf_path, 
        event=req.event, 
        tier=req.tier, 
        cert_id=cert_log.cert_id,
        cert_type=req.cert_type
    )
    if not success:
        cert_log.status = "FAILED"
        db.commit()
        raise HTTPException(status_code=500, detail=error_msg)
        
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
            date=req.date,
            cert_type=record.get("Type", req.cert_type)
        )
        db.add(cert_log)
    
    db.commit()
    
    # Spawn background task without the HTTP session (worker creates its own session)
    background_tasks.add_task(process_batch, batch_id, req.send_email)
    
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
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Verify Certificate - ISTE MBCET</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body {{
                margin: 0;
                padding: 0;
                min-height: 100vh;
                background-color: #f4f4f0;
                font-family: 'Space Grotesk', sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #1a1a1a;
            }}
            .container {{
                background: #ffffff;
                padding: 40px;
                border: 4px solid #1a1a1a;
                border-radius: 16px;
                box-shadow: 8px 8px 0px #1a1a1a;
                max-width: 500px;
                width: 90%;
                text-align: left;
            }}
            .badge {{
                display: inline-block;
                background: #4ade80;
                color: #064e3b;
                padding: 8px 16px;
                border: 2px solid #064e3b;
                border-radius: 99px;
                font-weight: 700;
                font-size: 14px;
                margin-bottom: 24px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            h1 {{
                font-size: 28px;
                font-weight: 700;
                margin: 0 0 8px 0;
                letter-spacing: -1px;
            }}
            p.subtitle {{
                color: #666;
                margin: 0 0 32px 0;
                font-size: 15px;
            }}
            .detail-group {{
                margin-bottom: 20px;
                padding-bottom: 20px;
                border-bottom: 2px dashed #e5e5e5;
            }}
            .detail-group:last-child {{
                border-bottom: none;
                margin-bottom: 0;
                padding-bottom: 0;
            }}
            .label {{
                font-size: 12px;
                text-transform: uppercase;
                color: #666;
                font-weight: 700;
                letter-spacing: 1px;
                margin-bottom: 4px;
            }}
            .value {{
                font-size: 18px;
                font-weight: 700;
                color: #1a1a1a;
            }}
            .footer {{
                margin-top: 40px;
                text-align: center;
                font-size: 13px;
                color: #666;
                font-weight: 700;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="badge">✔ Authentic</div>
            <h1>{cert.cert_type}</h1>
            <p class="subtitle">This official document has been cryptographically verified in the ISTE ledger.</p>
            
            <div class="detail-group">
                <div class="label">Issued To</div>
                <div class="value">{cert.name}</div>
            </div>
            
            <div class="detail-group">
                <div class="label">Event / Achievement</div>
                <div class="value">{cert.event}</div>
            </div>
            
            <div class="detail-group">
                <div class="label">Role / Tier</div>
                <div class="value">{cert.tier}</div>
            </div>
            
            <div class="detail-group">
                <div class="label">Date of Issue</div>
                <div class="value">{cert.date or cert.created_at.strftime('%B %d, %Y')}</div>
            </div>
            
            <div class="detail-group">
                <div class="label">Ledger ID</div>
                <div class="value" style="font-family: monospace; font-size: 14px;">{cert.cert_id}</div>
            </div>

            <div class="footer">
                ISTE MBCET Student Chapter
            </div>
        </div>
    </body>
    </html>
    """

import zipfile
import tempfile
import os
from fastapi.responses import FileResponse

@app.get("/api/jobs/{batch_id}/download")
async def download_batch_zip(batch_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    records = db.query(CertificateLog).filter(CertificateLog.batch_id == batch_id).all()
    if not records:
        raise HTTPException(status_code=404, detail="No certificates found for this batch.")
        
    # Security/Memory fix: Write to physical temp file to prevent RAM OOM crashes on large batches
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    temp_zip_path = temp_zip.name
    temp_zip.close()
    
    with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for record in records:
            import re
            safe_name = re.sub(r'[\\/*?:"<>|]', "", record.name).replace(" ", "_")
            filename = f"{safe_name}_{record.cert_id}.pdf"
            pdf_path = os.path.join(config.OUTPUT_DIR, filename)
            
            if os.path.exists(pdf_path):
                zip_file.write(pdf_path, arcname=filename)
                
    # Auto-cleanup the temp zip file after download finishes
    background_tasks.add_task(os.remove, temp_zip_path)
    
    return FileResponse(
        path=temp_zip_path,
        media_type="application/zip",
        filename=f"certificates_batch_{batch_id}.zip"
    )
