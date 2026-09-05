import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
from app.config import settings
from app import models
from app.job_sources import fetch_jobs
from app.email_service import send_email, build_digest_text

log = logging.getLogger("scheduler")
scheduler = BackgroundScheduler()


def refresh_jobs_job():
    """Runs daily: pulls fresh listings from Adzuna based on the saved
    profile's role/location prefs and upserts them into the local DB."""
    db = SessionLocal()
    try:
        profile = db.query(models.Profile).first()
        query = (profile.prefs or {}).get("role", "") if profile else ""
        location = (profile.prefs or {}).get("location", "") if profile else ""
        if location == "Any":
            location = ""

        jobs = asyncio.run(fetch_jobs(query=query, location=location))
        added, updated = 0, 0
        for j in jobs:
            existing = db.query(models.Job).filter_by(external_id=j["external_id"]).first()
            if existing:
                for k, v in j.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                db.add(models.Job(**j))
                added += 1
        db.commit()
        log.info(f"Job refresh: {added} added, {updated} updated")
    except Exception as e:
        log.error(f"Job refresh failed: {e}")
    finally:
        db.close()


def send_digest_job():
    """Runs weekly: builds the digest from current tracker entries and emails it."""
    db = SessionLocal()
    try:
        entries = db.query(models.TrackerEntry).all()
        payload = [{
            "status": e.status,
            "job": {"role": e.job.role, "company": e.job.company, "location": e.job.location},
        } for e in entries]
        text = build_digest_text(payload)
        send_email("Your weekly Apply Assist digest", text)
        log.info("Digest email sent")
    except Exception as e:
        log.error(f"Digest send failed: {e}")
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        refresh_jobs_job,
        CronTrigger(hour=settings.job_fetch_cron_hour, minute=0),
        id="refresh_jobs",
        replace_existing=True,
    )
    scheduler.add_job(
        send_digest_job,
        CronTrigger(day_of_week=settings.digest_cron_day_of_week, hour=settings.digest_cron_hour, minute=0),
        id="send_digest",
        replace_existing=True,
    )
    scheduler.start()
    log.info("Scheduler started: daily job refresh + weekly digest email")
