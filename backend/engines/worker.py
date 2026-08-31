import logging
import time
from sqlalchemy import or_
from sqlalchemy.orm import Session
from models import CertificateLog
from engines.certificate import generate_pdf_from_svg
from engines.mailer import send_certificate_email

logger = logging.getLogger(__name__)

from database import SessionLocal

def process_batch(batch_id: str, send_email: bool = True):
    logger.info(f"Starting background worker for batch: {batch_id}")
    
    # Create an independent database session for this long-running background task
    db = SessionLocal()
    try:
        # Give DB transaction a brief moment to settle across thread boundaries
        records = db.query(CertificateLog).filter(
            CertificateLog.batch_id == batch_id,
            or_(CertificateLog.status == "PENDING", CertificateLog.status == None)
        ).all()
        
        if not records:
            time.sleep(1)
            records = db.query(CertificateLog).filter(
                CertificateLog.batch_id == batch_id,
                or_(CertificateLog.status == "PENDING", CertificateLog.status == None)
            ).all()
            
        logger.info(f"Batch {batch_id}: found {len(records)} pending record(s) to process.")
        
        for idx, record in enumerate(records, 1):
            try:
                # Refresh record to check for mid-way cancellation
                db.refresh(record)
                if record.status == "CANCELLED":
                    logger.info(f"Batch {batch_id} was cancelled. Stopping.")
                    break # Abort the batch processing loop
                
                logger.info(f"[{idx}/{len(records)}] Starting processing for: {record.name}")
                t0 = time.time()
                pdf_path = generate_pdf_from_svg(
                    name=record.name,
                    event_name=record.event,
                    role=record.tier,
                    cert_date=record.date,
                    cert_id=record.cert_id,
                    cert_type=record.cert_type
                )
                t1 = time.time()
                logger.info(f"[{idx}/{len(records)}] PDF generation for '{record.name}' completed in {t1-t0:.2f}s (path: {pdf_path})")
                
                if pdf_path:
                    record.status = "SENT"
                    db.commit()
                    logger.info(f"[{idx}/{len(records)}] Database record for '{record.name}' updated to SENT and committed.")

                    if send_email:
                        try:
                            tm0 = time.time()
                            success, err_msg = send_certificate_email(
                                to_email=record.email,
                                name=record.name,
                                pdf_path=pdf_path,
                                event=record.event,
                                tier=record.tier,
                                cert_id=record.cert_id,
                                cert_type=record.cert_type
                            )
                            tm1 = time.time()
                            if success:
                                logger.info(f"[{idx}/{len(records)}] Email sent to {record.email} in {tm1-tm0:.2f}s")
                            else:
                                logger.warning(f"[{idx}/{len(records)}] Email dispatch warning for {record.email} ({tm1-tm0:.2f}s): {err_msg}")
                        except Exception as mail_err:
                            logger.warning(f"[{idx}/{len(records)}] Email dispatch exception for {record.email}: {mail_err}")
                else:
                    record.status = "FAILED"
                    db.commit()
                    logger.error(f"[{idx}/{len(records)}] PDF generation failed for {record.name}. Marked status as FAILED.")
                    
            except Exception as e:
                logger.error(f"[{idx}/{len(records)}] Error processing {record.name}: {e}")
                record.status = "FAILED"
                db.commit()
        
        logger.info(f"Batch {batch_id} processing complete!")
    finally:
        db.close()
    
    logger.info(f"Batch {batch_id} processing complete.")
