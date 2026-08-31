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
        
        for record in records:
            try:
                # Refresh record to check for mid-way cancellation
                db.refresh(record)
                if record.status == "CANCELLED":
                    logger.info(f"Batch {batch_id} was cancelled. Stopping.")
                    break # Abort the batch processing loop
                
                logger.info(f"Processing background record: {record.name}")
                pdf_path = generate_pdf_from_svg(
                    name=record.name,
                    event_name=record.event,
                    role=record.tier,
                    cert_date=record.date,
                    cert_id=record.cert_id,
                    cert_type=record.cert_type
                )
                
                if pdf_path:
                    record.status = "SENT"
                    db.commit()
                    logger.info(f"Successfully generated PDF for {record.name}. Marked status as SENT.")

                    if send_email:
                        try:
                            success, err_msg = send_certificate_email(
                                to_email=record.email,
                                name=record.name,
                                pdf_path=pdf_path,
                                event=record.event,
                                tier=record.tier,
                                cert_id=record.cert_id,
                                cert_type=record.cert_type
                            )
                            if not success:
                                logger.warning(f"Email dispatch warning for {record.email}: {err_msg}")
                        except Exception as mail_err:
                            logger.warning(f"Email dispatch exception for {record.email}: {mail_err}")
                else:
                    record.status = "FAILED"
                    db.commit()
                    
            except Exception as e:
                logger.error(f"Error processing {record.name}: {e}")
                record.status = "FAILED"
                db.commit()
    finally:
        db.close()
    
    logger.info(f"Batch {batch_id} processing complete.")
