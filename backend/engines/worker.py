import logging
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
        records = db.query(CertificateLog).filter(CertificateLog.batch_id == batch_id, CertificateLog.status == "PENDING").all()
        
        for record in records:
            try:
                logger.info(f"Processing background record: {record.name}")
                pdf_path = generate_pdf_from_svg(
                    name=record.name,
                    event_name=record.event,
                    role=record.tier,
                    cert_date=record.date,
                    cert_id=record.cert_id
                )
                
                if pdf_path:
                    if send_email:
                        success, err_msg = send_certificate_email(
                            to_email=record.email,
                            name=record.name,
                            pdf_path=pdf_path,
                            event=record.event,
                            tier=record.tier,
                            cert_id=record.cert_id,
                            cert_type=record.cert_type
                        )
                        if success:
                            record.status = "SENT"
                        else:
                            logger.error(f"Failed to email {record.email}: {err_msg}")
                            record.status = "FAILED"
                    else:
                        record.status = "SENT" # Generated successfully
                else:
                    record.status = "FAILED"
                    
            except Exception as e:
                logger.error(f"Error processing {record.name}: {e}")
                record.status = "FAILED"
                
            db.commit()
    finally:
        db.close()
    
    logger.info(f"Batch {batch_id} processing complete.")
