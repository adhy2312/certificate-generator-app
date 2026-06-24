import logging
import uuid
import os
import re
import zipfile
import tempfile
import time
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, validator, EmailStr
from typing import List, Optional
import html as html_module

import config
from engines.parser import process_source
from engines.certificate import generate_pdf_from_svg
from engines.mailer import send_certificate_email
from engines.worker import process_batch
from database import engine, Base, get_db
from models import CertificateLog

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiting: simple in-memory store (resets on server restart)
# ---------------------------------------------------------------------------
_login_attempts: dict = {}  # ip -> (count, window_start_epoch)
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300  # 5 minutes

def check_rate_limit(ip: str):
    now = time.time()
    entry = _login_attempts.get(ip, (0, now))
    count, window_start = entry
    if now - window_start > LOGIN_WINDOW_SECONDS:
        # Reset window
        _login_attempts[ip] = (1, now)
        return
    count += 1
    _login_attempts[ip] = (count, window_start)
    if count > MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Please wait {LOGIN_WINDOW_SECONDS // 60} minutes."
        )


# ---------------------------------------------------------------------------
# Auto-cleanup background task (remove PDFs older than 2 hours)
# ---------------------------------------------------------------------------
async def cleanup_pdfs_loop():
    while True:
        try:
            now = time.time()
            for filename in os.listdir(config.OUTPUT_DIR):
                if filename.endswith(".pdf"):
                    file_path = os.path.join(config.OUTPUT_DIR, filename)
                    if os.stat(file_path).st_mtime < now - 7200:
                        os.remove(file_path)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Database tables
    Base.metadata.create_all(bind=engine)

    # Safely migrate existing databases to include the new cert_type column
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE certificate_logs ADD COLUMN cert_type VARCHAR DEFAULT 'Certificate of Participation'"
            ))
    except Exception:
        pass  # Column already exists

    # Start auto-cleanup background task
    task = asyncio.create_task(cleanup_pdfs_loop())
    yield
    task.cancel()


# ---------------------------------------------------------------------------
# Allowed origins - tighten CORS to only known frontends
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = [
    "https://certificate-generator-app-dlh6.onrender.com",
    "http://localhost:5173",
    "http://localhost:4173",
    "http://127.0.0.1:5173",
]

app = FastAPI(title="ISTE CertHub API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------------------------
# Request models with strict length/type validation
# ---------------------------------------------------------------------------

MAX_STR = 200  # max length for text fields

class PasswordRequest(BaseModel):
    password: str

    @validator("password")
    def password_length(cls, v):
        if len(v) > 128:
            raise ValueError("Password too long")
        return v


class SingleProcessRequest(BaseModel):
    name: str
    email: str
    event: str
    tier: str
    date: str = ""
    cert_type: str = "Certificate of Participation"
    send_email: bool = True

    @validator("name", "event", "tier", "cert_type")
    def no_oversized_strings(cls, v):
        if len(v) > MAX_STR:
            raise ValueError(f"Field exceeds maximum length of {MAX_STR} characters")
        return v.strip()

    @validator("email")
    def valid_email(cls, v):
        if len(v) > 254 or "@" not in v:
            raise ValueError("Invalid email address")
        return v.strip()

    @validator("date")
    def safe_date(cls, v):
        if len(v) > 50:
            raise ValueError("Date field too long")
        return v.strip()


class BulkProcessRequest(BaseModel):
    records: List[dict]
    event: str
    date: Optional[str] = None
    cert_type: str = "Certificate of Participation"
    send_email: bool = True

    @validator("records")
    def limit_records(cls, v):
        if len(v) > 500:
            raise ValueError("Bulk jobs are limited to 500 records per batch")
        return v

    @validator("event", "cert_type")
    def no_oversized_strings(cls, v):
        if v and len(v) > MAX_STR:
            raise ValueError(f"Field exceeds maximum length of {MAX_STR} characters")
        return v.strip() if v else v


# ---------------------------------------------------------------------------
# Helper: escape user-provided data before injecting into HTML
# ---------------------------------------------------------------------------
def esc(value: str) -> str:
    """HTML-escape a string to prevent XSS in the verify portal."""
    return html_module.escape(str(value or ""))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/api/verify-password")
async def verify_password(req: PasswordRequest, request: Request):
    client_ip = request.client.host
    check_rate_limit(client_ip)
    if req.password == config.GATEKEEPER_PASSWORD:
        return {"success": True, "token": "authenticated"}
    raise HTTPException(status_code=401, detail="Invalid password")


@app.post("/api/parse-preview")
async def parse_preview(url: str = Form(None), file: UploadFile = File(None)):
    # File size guard: 5 MB max
    MAX_UPLOAD_BYTES = 5 * 1024 * 1024
    try:
        if file:
            contents = await file.read(MAX_UPLOAD_BYTES + 1)
            if len(contents) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="File too large. Maximum size is 5 MB.")
            records = process_source(file_data=contents)
        elif url:
            records = process_source(url=url)
        else:
            raise HTTPException(status_code=400, detail="Provide URL or file")

        return {"records": records[:3], "full_records": records}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/jobs/single")
async def process_single(req: SingleProcessRequest, db: Session = Depends(get_db)):
    logger.info(f"Processing single generation for {req.name}")

    cert_log = CertificateLog(
        name=req.name, email=req.email, event=req.event, tier=req.tier,
        date=req.date, cert_type=req.cert_type
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
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"{re.sub(r'[^a-zA-Z0-9_-]', '_', req.name)}_certificate.pdf"
        )

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
async def process_bulk(
    req: BulkProcessRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    batch_id = str(uuid.uuid4())

    for record in req.records:
        name = str(record.get("Name", ""))[:MAX_STR].strip()
        email = str(record.get("Email", ""))[:254].strip()
        tier = str(record.get("Tier", ""))[:MAX_STR].strip()
        rec_type = str(record.get("Type", req.cert_type))[:MAX_STR].strip()

        if not name or not email:
            continue  # Skip malformed records silently

        cert_log = CertificateLog(
            batch_id=batch_id,
            name=name,
            email=email,
            event=req.event,
            tier=tier,
            date=req.date,
            cert_type=rec_type
        )
        db.add(cert_log)

    db.commit()
    background_tasks.add_task(process_batch, batch_id, req.send_email)

    return {"success": True, "batch_id": batch_id, "total": len(req.records)}


@app.get("/api/jobs/{batch_id}")
async def get_job_status(batch_id: str, db: Session = Depends(get_db)):
    # Validate batch_id is a valid UUID format to prevent arbitrary DB probing
    try:
        uuid.UUID(batch_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid batch ID format")

    total = db.query(CertificateLog).filter(CertificateLog.batch_id == batch_id).count()
    if total == 0:
        raise HTTPException(status_code=404, detail="Batch not found")

    sent = db.query(CertificateLog).filter(
        CertificateLog.batch_id == batch_id, CertificateLog.status == "SENT"
    ).count()
    failed = db.query(CertificateLog).filter(
        CertificateLog.batch_id == batch_id, CertificateLog.status == "FAILED"
    ).count()
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
    # Validate cert_id is UUID-shaped to prevent arbitrary DB scanning
    try:
        uuid.UUID(cert_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid certificate ID")

    cert = db.query(CertificateLog).filter(CertificateLog.cert_id == cert_id).first()
    if not cert:
        return HTMLResponse(content="""
        <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
        <title>Invalid Certificate</title>
        <style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#f4f4f0;}
        .box{background:#fff;padding:40px;border:4px solid #1a1a1a;border-radius:16px;box-shadow:8px 8px 0 #1a1a1a;text-align:center;}</style>
        </head><body><div class="box"><h1>⚠️ Invalid Certificate</h1>
        <p>This certificate does not exist in our system.</p></div></body></html>
        """, status_code=404)

    # XSS-safe: escape every database value before injecting into HTML
    safe_cert_type = esc(cert.cert_type)
    safe_name = esc(cert.name)
    safe_event = esc(cert.event)
    safe_tier = esc(cert.tier)
    safe_date = esc(cert.date or cert.created_at.strftime('%B %d, %Y'))
    safe_cert_id = esc(cert.cert_id)

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
                margin: 0; padding: 0; min-height: 100vh;
                background-color: #f4f4f0;
                font-family: 'Space Grotesk', sans-serif;
                display: flex; align-items: center; justify-content: center; color: #1a1a1a;
            }}
            .container {{
                background: #ffffff; padding: 40px;
                border: 4px solid #1a1a1a; border-radius: 16px;
                box-shadow: 8px 8px 0px #1a1a1a;
                max-width: 500px; width: 90%; text-align: left;
            }}
            .badge {{
                display: inline-block; background: #4ade80; color: #064e3b;
                padding: 8px 16px; border: 2px solid #064e3b; border-radius: 99px;
                font-weight: 700; font-size: 14px; margin-bottom: 24px;
                text-transform: uppercase; letter-spacing: 1px;
            }}
            h1 {{ font-size: 28px; font-weight: 700; margin: 0 0 8px 0; letter-spacing: -1px; }}
            p.subtitle {{ color: #666; margin: 0 0 32px 0; font-size: 15px; }}
            .detail-group {{
                margin-bottom: 20px; padding-bottom: 20px;
                border-bottom: 2px dashed #e5e5e5;
            }}
            .detail-group:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
            .label {{
                font-size: 12px; text-transform: uppercase; color: #666;
                font-weight: 700; letter-spacing: 1px; margin-bottom: 4px;
            }}
            .value {{ font-size: 18px; font-weight: 700; color: #1a1a1a; }}
            .footer {{ margin-top: 40px; text-align: center; font-size: 13px; color: #666; font-weight: 700; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="badge">✔ Authentic</div>
            <h1>{safe_cert_type}</h1>
            <p class="subtitle">This official document has been verified in the ISTE MBCET ledger.</p>

            <div class="detail-group">
                <div class="label">Issued To</div>
                <div class="value">{safe_name}</div>
            </div>

            <div class="detail-group">
                <div class="label">Event / Achievement</div>
                <div class="value">{safe_event}</div>
            </div>

            <div class="detail-group">
                <div class="label">Role / Tier</div>
                <div class="value">{safe_tier}</div>
            </div>

            <div class="detail-group">
                <div class="label">Date of Issue</div>
                <div class="value">{safe_date}</div>
            </div>

            <div class="detail-group">
                <div class="label">Ledger ID</div>
                <div class="value" style="font-family: monospace; font-size: 14px;">{safe_cert_id}</div>
            </div>

            <div class="footer">ISTE MBCET Student Chapter</div>
        </div>
    </body>
    </html>
    """


@app.get("/api/jobs/{batch_id}/download")
async def download_batch_zip(batch_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Validate UUID format
    try:
        uuid.UUID(batch_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid batch ID format")

    records = db.query(CertificateLog).filter(CertificateLog.batch_id == batch_id).all()
    if not records:
        raise HTTPException(status_code=404, detail="No certificates found for this batch.")

    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    temp_zip_path = temp_zip.name
    temp_zip.close()

    with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for record in records:
            safe_name = re.sub(r'[\\/*?"<>|]', "", record.name).replace(" ", "_")
            filename = f"{safe_name}_{record.cert_id}.pdf"
            pdf_path = os.path.join(config.OUTPUT_DIR, filename)

            if os.path.exists(pdf_path):
                zip_file.write(pdf_path, arcname=filename)

    background_tasks.add_task(os.remove, temp_zip_path)

    return FileResponse(
        path=temp_zip_path,
        media_type="application/zip",
        filename=f"certificates_batch_{batch_id}.zip"
    )
