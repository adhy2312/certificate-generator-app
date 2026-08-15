"""
Cleanup Agent — Certificate Log Pruner
======================================
Handles automatic deletion of old certificate records from the database
when Supabase storage approaches its free-tier limit (500 MB).

Strategy:
  1. Check current database size via pg_database_size().
  2. If usage is above the configured threshold (default: 80% of 500 MB),
     delete the oldest SENT / FAILED / CANCELLED records in batches.
  3. Always keep a configurable minimum of the most recent records per status.
  4. Returns a summary dict for use in the API response or scheduled task logs.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# --- Tuning knobs (all overridable via environment variables) -----------------

# Free-tier Supabase hard cap in bytes  (500 MB)
SUPABASE_FREE_LIMIT_BYTES: int = int(os.getenv("SUPABASE_FREE_LIMIT_BYTES", str(500 * 1024 * 1024)))

# Trigger cleanup when database is >= this percentage of the cap
CLEANUP_THRESHOLD_PCT: float = float(os.getenv("CLEANUP_THRESHOLD_PCT", "80"))

# Always keep this many recent records regardless of age
KEEP_MINIMUM_RECORDS: int = int(os.getenv("KEEP_MINIMUM_RECORDS", "200"))

# Delete records older than this many days (only SENT / FAILED / CANCELLED)
PRUNE_OLDER_THAN_DAYS: int = int(os.getenv("PRUNE_OLDER_THAN_DAYS", "60"))

# Emergency mode: delete records older than this if still over threshold after normal prune
EMERGENCY_PRUNE_DAYS: int = int(os.getenv("EMERGENCY_PRUNE_DAYS", "14"))

# -----------------------------------------------------------------------------


def _get_db_size_bytes(db: Session) -> Optional[int]:
    """Return current database size in bytes using pg_database_size().
    Returns None if running on SQLite (local dev) — no cleanup needed there.
    """
    try:
        result = db.execute(text("SELECT pg_database_size(current_database())")).scalar()
        return int(result)
    except Exception:
        # SQLite or query failure — skip size check
        return None


def _get_record_count(db: Session) -> int:
    from models import CertificateLog
    return db.query(CertificateLog).count()


def _prune_old_records(db: Session, older_than_days: int, keep_minimum: int) -> int:
    """
    Delete SENT / FAILED / CANCELLED records older than `older_than_days`,
    but always preserve the most recent `keep_minimum` records globally.
    Returns the number of rows deleted.
    """
    from models import CertificateLog

    cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
    deletable_statuses = ("SENT", "FAILED", "CANCELLED")

    total = db.query(CertificateLog).count()
    if total <= keep_minimum:
        logger.info(f"[Cleanup] Only {total} records exist — below minimum ({keep_minimum}). Skipping prune.")
        return 0

    # Find IDs of the `keep_minimum` most recent records so we never delete them
    recent_ids_query = (
        db.query(CertificateLog.id)
        .order_by(CertificateLog.created_at.desc())
        .limit(keep_minimum)
        .subquery()
    )

    # Delete old records that are not in the protected recent set
    to_delete = (
        db.query(CertificateLog)
        .filter(
            CertificateLog.status.in_(deletable_statuses),
            CertificateLog.created_at < cutoff_date,
            ~CertificateLog.id.in_(db.query(recent_ids_query.c.id)),
        )
    )

    count = to_delete.count()
    if count == 0:
        logger.info("[Cleanup] No records eligible for deletion.")
        return 0

    to_delete.delete(synchronize_session=False)
    db.commit()
    logger.info(f"[Cleanup] Pruned {count} records older than {older_than_days} days.")
    return count


def run_cleanup(db: Session, force: bool = False) -> dict:
    """
    Main cleanup entry point.

    Args:
        db:    SQLAlchemy database session.
        force: If True, bypass the size threshold check and prune regardless.

    Returns:
        A summary dict with keys:
          - triggered (bool): whether cleanup actually ran
          - db_size_mb (float | None): current DB size in MB
          - threshold_mb (float): configured threshold in MB
          - records_before (int): total records before cleanup
          - records_deleted (int): how many rows were removed
          - records_after (int): total records remaining
          - emergency_mode (bool): whether emergency pruning was also applied
          - message (str): human-readable summary
    """
    threshold_bytes = SUPABASE_FREE_LIMIT_BYTES * (CLEANUP_THRESHOLD_PCT / 100)
    threshold_mb = round(threshold_bytes / 1024 / 1024, 1)

    db_size_bytes = _get_db_size_bytes(db)
    db_size_mb = round(db_size_bytes / 1024 / 1024, 2) if db_size_bytes is not None else None

    records_before = _get_record_count(db)

    summary = {
        "triggered": False,
        "db_size_mb": db_size_mb,
        "threshold_mb": threshold_mb,
        "records_before": records_before,
        "records_deleted": 0,
        "records_after": records_before,
        "emergency_mode": False,
        "message": "Database size is within safe limits. No cleanup needed.",
    }

    # --- Decide whether to run ---
    should_run = force
    if db_size_bytes is not None and db_size_bytes >= threshold_bytes:
        should_run = True
        logger.warning(
            f"[Cleanup] DB size {db_size_mb} MB >= threshold {threshold_mb} MB. Triggering cleanup."
        )

    if not should_run:
        logger.info(
            f"[Cleanup] DB size {db_size_mb} MB is below threshold {threshold_mb} MB. Skipping."
        )
        return summary

    summary["triggered"] = True

    # --- Normal prune: records older than PRUNE_OLDER_THAN_DAYS ---
    deleted = _prune_old_records(db, PRUNE_OLDER_THAN_DAYS, KEEP_MINIMUM_RECORDS)
    summary["records_deleted"] += deleted

    # --- Re-check size; if still over threshold, apply emergency prune ---
    db_size_bytes_after = _get_db_size_bytes(db)
    if db_size_bytes_after is not None and db_size_bytes_after >= threshold_bytes:
        logger.warning("[Cleanup] Still over threshold after normal prune — applying emergency prune.")
        summary["emergency_mode"] = True
        emergency_deleted = _prune_old_records(db, EMERGENCY_PRUNE_DAYS, KEEP_MINIMUM_RECORDS // 2)
        summary["records_deleted"] += emergency_deleted
        summary["db_size_mb"] = round(db_size_bytes_after / 1024 / 1024, 2)

    summary["records_after"] = _get_record_count(db)
    summary["message"] = (
        f"Cleanup complete. Removed {summary['records_deleted']} record(s). "
        f"{'Emergency mode was activated.' if summary['emergency_mode'] else ''}"
    ).strip()

    logger.info(f"[Cleanup] {summary['message']}")
    return summary
