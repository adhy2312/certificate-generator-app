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
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from pydantic import BaseModel, validator, EmailStr
from typing import List, Optional

import config
from engines.parser import process_source
from engines.certificate import generate_pdf_from_svg
from engines.mailer import send_certificate_email
from engines.worker import process_batch
from engines.cleanup import run_cleanup
from database import engine, Base, get_db
from models import CertificateLog

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiting: simple in-memory store (resets on server restart)
# ---------------------------------------------------------------------------
_login_attempts: dict = {}  # ip -> (count, window_start_epoch)
MAX_LOGIN_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 300  # 5 minutes

def get_client_ip(request: Request) -> str:
    """Extract real client IP from Cloudflare / Render proxy headers or fallback to request.client."""
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"

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
            detail=f"Too many attempts. Please wait {LOGIN_WINDOW_SECONDS // 60} minutes."
        )

def reset_rate_limit(ip: str):
    """Reset rate limit counter on successful action."""
    if ip in _login_attempts:
        _login_attempts.pop(ip, None)


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


# ---------------------------------------------------------------------------
# Scheduled DB cleanup loop — runs every 6 hours to prune old records when
# Supabase storage approaches the free-tier 500 MB limit.
# ---------------------------------------------------------------------------
async def scheduled_db_cleanup_loop():
    # Wait 60s on startup so the DB has time to initialise
    await asyncio.sleep(60)
    while True:
        try:
            db = next(get_db())
            try:
                result = run_cleanup(db)
                if result["triggered"]:
                    logger.info(f"[Scheduled Cleanup] {result['message']} | DB size: {result['db_size_mb']} MB")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[Scheduled Cleanup] Error during DB cleanup: {e}")
        # Run every 6 hours
        await asyncio.sleep(6 * 3600)


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

    # Start auto-cleanup background tasks
    pdf_task = asyncio.create_task(cleanup_pdfs_loop())
    db_cleanup_task = asyncio.create_task(scheduled_db_cleanup_loop())
    yield
    pdf_task.cancel()
    db_cleanup_task.cancel()


app = FastAPI(title="ISTE CertHub API", lifespan=lifespan)

# ---------------------------------------------------------------------------
# CRITICAL: Raw low-level CORS middleware.
# FastAPI's built-in CORSMiddleware has a known bug: if an exception is raised
# DURING request body parsing (e.g. a malformed multipart upload), the error
# response is emitted BEFORE the middleware chain runs, so no CORS header is
# attached and the browser sees it as a CORS failure.
# This raw middleware runs at the very bottom of the stack and forcefully
# injects the header onto every response, including crash responses.
# ---------------------------------------------------------------------------
@app.middleware("http")
async def force_cors(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:
        # Unhandled exception — return a clean JSON 500 with CORS header
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# Also keep the built-in middleware for preflight OPTIONS requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------------------------
# Global exception handlers — always include CORS so the browser sees the
# actual error instead of a phantom "No CORS header" failure.
# ---------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


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
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Keep-alive ping endpoint. Called by Render cron job every 14 minutes
    to prevent the free-tier web service from spinning down."""
    return {"status": "ok", "service": "ISTE CertHub API"}


@app.post("/api/admin/cleanup")
async def trigger_cleanup(
    req: PasswordRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Manually trigger the database cleanup agent.
    Requires the GATEKEEPER_PASSWORD for authorization.
    Optionally force the cleanup even if storage is below the threshold
    by passing ?force=true as a query parameter.
    """
    client_ip = get_client_ip(request)
    check_rate_limit(client_ip)
    if req.password != config.GATEKEEPER_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")

    reset_rate_limit(client_ip)
    force = request.query_params.get("force", "false").lower() == "true"
    result = run_cleanup(db, force=force)
    return result


@app.post("/api/verify-password")
async def verify_password(req: PasswordRequest, request: Request):
    client_ip = get_client_ip(request)
    check_rate_limit(client_ip)
    if req.password == config.GATEKEEPER_PASSWORD:
        reset_rate_limit(client_ip)
        return {"success": True, "token": "authenticated"}
    raise HTTPException(status_code=401, detail="Invalid password")


@app.post("/api/parse-preview")
async def parse_preview(request: Request):
    """
    Accepts either:
      - multipart/form-data with a 'file' field (CSV/XLSX upload)
      - multipart/form-data with a 'url' field (Google Sheets link)
    Reads the body manually to avoid FastAPI's UploadFile multipart
    parsing bug that crashes before the CORS middleware runs.
    """
    MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
    try:
        content_type = request.headers.get("content-type", "")

        # --- Raw body size guard ---
        body = await request.body()
        if len(body) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large. Maximum size is 5 MB.")

        # --- Route by content type ---
        if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            form = await request.form()

            url_val = form.get("url")
            file_val = form.get("file")

            if file_val and hasattr(file_val, "read"):
                contents = await file_val.read()
                records = process_source(file_data=contents)
            elif url_val:
                records = process_source(url=str(url_val))
            else:
                raise HTTPException(status_code=400, detail="Provide a Google Sheets URL or upload a file.")
        else:
            raise HTTPException(status_code=400, detail="Unsupported content type. Use multipart/form-data.")

        return {"records": records[:3], "full_records": records}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/jobs/single")
async def process_single(req: SingleProcessRequest, db: Session = Depends(get_db)):
    logger.info(f"Processing single generation for {req.name}")
    clean_name = req.name.strip().title()
    clean_cert_type = "Certificate of Participation" if req.cert_type == "CERT_Template" else req.cert_type
    cert_log = CertificateLog(
        name=clean_name, email=req.email, event=req.event, tier=req.tier,
        date=req.date, cert_type=clean_cert_type
    )
    db.add(cert_log)
    db.commit()
    db.refresh(cert_log)

    pdf_path = generate_pdf_from_svg(clean_name, req.event, req.tier, req.date, cert_log.cert_id, cert_log.cert_type)
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
        logger.warning(f"Email dispatch failed for {req.email}: {error_msg}. Returning generated PDF file.")
        cert_log.status = "SENT"
        db.commit()
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"{re.sub(r'[^a-zA-Z0-9_-]', '_', clean_name)}_certificate.pdf"
        )

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
        raw_type = str(record.get("Type", req.cert_type))[:MAX_STR].strip()
        rec_type = "Certificate of Participation" if raw_type in ["CERT_Template", ""] else raw_type

        if not name or not email:
            continue  # Skip malformed records silently

        cert_log = CertificateLog(
            batch_id=batch_id,
            name=name,
            email=email,
            event=req.event,
            tier=tier,
            date=req.date,
            cert_type=rec_type,
            status="PENDING"
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
        db.expire_all()
        total = db.query(CertificateLog).filter(CertificateLog.batch_id == batch_id).count()
        if total == 0:
            raise HTTPException(status_code=404, detail="Batch not found")

    sent = db.query(CertificateLog).filter(
        CertificateLog.batch_id == batch_id, CertificateLog.status == "SENT"
    ).count()
    failed = db.query(CertificateLog).filter(
        CertificateLog.batch_id == batch_id, CertificateLog.status == "FAILED"
    ).count()
    cancelled = db.query(CertificateLog).filter(
        CertificateLog.batch_id == batch_id, CertificateLog.status == "CANCELLED"
    ).count()
    pending = total - sent - failed - cancelled

    return {
        "batch_id": batch_id,
        "total": total,
        "sent": sent,
        "failed": failed,
        "cancelled": cancelled,
        "pending": pending,
        "completed": pending == 0
    }

@app.post("/api/jobs/{batch_id}/cancel")
async def cancel_job(batch_id: str, req: PasswordRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = get_client_ip(request)
    check_rate_limit(client_ip)
    if req.password != config.GATEKEEPER_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")

    reset_rate_limit(client_ip)

    try:
        uuid.UUID(batch_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid batch ID format")
        
    # Update all PENDING records to CANCELLED
    db.query(CertificateLog).filter(
        CertificateLog.batch_id == batch_id, 
        CertificateLog.status == "PENDING"
    ).update({"status": "CANCELLED"}, synchronize_session=False)
    
    db.commit()
    return {"success": True, "message": "Batch processing cancelled."}


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
