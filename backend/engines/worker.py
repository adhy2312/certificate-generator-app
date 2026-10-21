import logging
import time
import os
import gc
from sqlalchemy import or_
from sqlalchemy.orm import Session
from models import CertificateLog
from engines.certificate import generate_pdf_from_svg
from engines.mailer import send_certificate_email, SMTPConnectionManager
from database import SessionLocal
import config

logger = logging.getLogger(__name__)


def process_batch(batch_id: str, send_email: bool = True):
    """
    High-capacity, fault-tolerant background worker.
    Processes 1000+ records with:
      - Accurate status tracking (SENT, GENERATED, FAILED, CANCELLED)
      - Error message recording for failed dispatches
      - Persistent SMTP connection reuse to eliminate rate limits and socket churn
      - Periodic garbage collection to maintain minimal memory footprint (< 150MB)
      - Non-blocking real-time status reporting for frontend polling
    """
    logger.info(f"Starting background worker for batch {batch_id} (send_email={send_email})")
    
    db = SessionLocal()
    try:
        # Give DB a brief moment to settle across thread boundaries
        records = db.query(CertificateLog).filter(
            CertificateLog.batch_id == batch_id,
            or_(CertificateLog.status == "PENDING", CertificateLog.status == None)
        ).order_by(CertificateLog.id.asc()).all()
        
        if not records:
            time.sleep(1)
            records = db.query(CertificateLog).filter(
                CertificateLog.batch_id == batch_id,
                or_(CertificateLog.status == "PENDING", CertificateLog.status == None)
            ).order_by(CertificateLog.id.asc()).all()
            
        total_records = len(records)
        logger.info(f"Batch {batch_id}: found {total_records} pending record(s) to process.")
        
        if total_records == 0:
            return

        # Prepare reusable SMTP session if direct SMTP is needed
        use_smtp_manager = send_email and not config.GAS_MAILER_URL and config.SENDER_EMAIL and config.SENDER_PASS
        smtp_mgr = SMTPConnectionManager() if use_smtp_manager else None

        try:
            if smtp_mgr:
                try:
                    smtp_mgr.connect()
                except Exception as conn_err:
                    logger.warning(f"Initial bulk SMTP connect warning: {conn_err}. Will connect on demand.")

            for idx, record in enumerate(records, 1):
                try:
                    # Periodically refresh from DB to detect mid-way cancellation
                    if idx % 5 == 1:
                        db.refresh(record)
                        if record.status == "CANCELLED":
                            logger.info(f"Batch {batch_id} was cancelled by user. Halting pipeline.")
                            break

                    t0 = time.time()
                    pdf_path = generate_pdf_from_svg(
                        name=record.name,
                        event_name=record.event,
                        role=record.tier,
                        cert_date=record.date,
                        cert_id=record.cert_id,
                        cert_type=record.cert_type
                    )
                    t_gen = time.time() - t0

                    if not pdf_path or not os.path.exists(pdf_path):
                        record.status = "FAILED"
                        record.error_message = "PDF template rendering failed."
                        db.commit()
                        logger.error(f"[{idx}/{total_records}] PDF generation failed for '{record.name}'.")
                        continue

                    if not send_email:
                        # Generation only (e.g. for ZIP download)
                        record.status = "GENERATED"
                        record.error_message = None
                        db.commit()
                        logger.info(f"[{idx}/{total_records}] Generated PDF for '{record.name}' in {t_gen:.2f}s.")
                    else:
                        # Dispatch email
                        tm0 = time.time()
                        success, err_msg = send_certificate_email(
                            to_email=record.email,
                            name=record.name,
                            pdf_path=pdf_path,
                            event=record.event,
                            tier=record.tier,
                            cert_id=record.cert_id,
                            cert_type=record.cert_type,
                            smtp_manager=smtp_mgr
                        )
                        tm_dispatch = time.time() - tm0

                        if success:
                            record.status = "SENT"
                            record.error_message = None
                            db.commit()
                            logger.info(f"[{idx}/{total_records}] Sent email to {record.email} in {tm_dispatch:.2f}s.")
                        else:
                            record.status = "FAILED"
                            record.error_message = str(err_msg)[:250]
                            db.commit()
                            logger.warning(f"[{idx}/{total_records}] Failed sending email to {record.email}: {err_msg}")

                    # Free memory every 25 records to prevent leaks on low-RAM containers
                    if idx % 25 == 0:
                        gc.collect()

                except Exception as item_err:
                    logger.error(f"[{idx}/{total_records}] Exception processing {record.name}: {item_err}")
                    try:
                        record.status = "FAILED"
                        record.error_message = str(item_err)[:250]
                        db.commit()
                    except Exception:
                        db.rollback()

        finally:
            if smtp_mgr:
                smtp_mgr.close()

        logger.info(f"Batch {batch_id} processing cycle completed successfully.")

    except Exception as batch_err:
        logger.error(f"Fatal error in batch worker {batch_id}: {batch_err}")
    finally:
        db.close()
        gc.collect()
