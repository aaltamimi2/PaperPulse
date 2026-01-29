"""Background job scheduler using APScheduler.

This module provides scheduled execution of:
- Paper collection from all configured sources
- Digest generation and email delivery
- Immediate alert checks
- Embedding updates

The scheduler can run:
1. As a standalone process (paperpulse scheduler start)
2. Embedded in the API server
3. With jobs triggered manually (paperpulse scheduler run-job)
"""

from datetime import datetime
from typing import Optional

import structlog
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from paperpulse.core.config import SchedulerSettings, get_settings

logger = structlog.get_logger(__name__)

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance.

    Returns:
        AsyncIOScheduler instance
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            timezone="UTC",
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 3600,
            },
        )
    return _scheduler


def _job_listener(event: JobExecutionEvent) -> None:
    """Handle job execution events for logging.

    Args:
        event: Job execution event
    """
    if event.exception:
        logger.error(
            "Job failed",
            job_id=event.job_id,
            error=str(event.exception),
            traceback=event.traceback,
        )
    else:
        logger.info(
            "Job completed",
            job_id=event.job_id,
            return_value=str(event.retval)[:100] if event.retval else None,
        )


def _get_day_of_week(day_name: str) -> str:
    """Convert day name to cron day of week.

    Args:
        day_name: Day name (monday, tuesday, etc.)

    Returns:
        Cron day of week (mon, tue, etc.)
    """
    day_map = {
        "monday": "mon",
        "tuesday": "tue",
        "wednesday": "wed",
        "thursday": "thu",
        "friday": "fri",
        "saturday": "sat",
        "sunday": "sun",
    }
    return day_map.get(day_name.lower(), "sun")


def init_scheduler(settings: Optional[SchedulerSettings] = None) -> AsyncIOScheduler:
    """Initialize and configure the scheduler with all jobs.

    Args:
        settings: Scheduler settings (uses defaults if not provided)

    Returns:
        Configured AsyncIOScheduler
    """
    settings = settings or get_settings().scheduler

    if not settings.enabled:
        logger.warning("Scheduler is disabled in settings")
        return get_scheduler()

    scheduler = get_scheduler()

    # Add job listener for logging
    scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    # Import jobs here to avoid circular imports
    from paperpulse.scheduler.jobs import (
        collect_papers_job,
        generate_digests_job,
        send_immediate_alerts_job,
        update_embeddings_job,
    )

    # Paper collection job (every N hours)
    scheduler.add_job(
        collect_papers_job,
        IntervalTrigger(hours=settings.collect_interval_hours),
        id="collect_papers",
        name="Collect papers from all sources",
        replace_existing=True,
    )
    logger.info(
        "Registered job: collect_papers",
        interval_hours=settings.collect_interval_hours,
    )

    # Weekly digest job
    day_of_week = _get_day_of_week(settings.digest_weekly_day)
    scheduler.add_job(
        generate_digests_job,
        CronTrigger(
            day_of_week=day_of_week,
            hour=settings.digest_weekly_hour,
        ),
        id="weekly_digest",
        name="Generate weekly digests",
        kwargs={"digest_type": "weekly"},
        replace_existing=True,
    )
    logger.info(
        "Registered job: weekly_digest",
        day=settings.digest_weekly_day,
        hour=settings.digest_weekly_hour,
    )

    # Daily digest job (for users who prefer daily)
    scheduler.add_job(
        generate_digests_job,
        CronTrigger(hour=settings.digest_daily_hour),
        id="daily_digest",
        name="Generate daily digests",
        kwargs={"digest_type": "daily"},
        replace_existing=True,
    )
    logger.info(
        "Registered job: daily_digest",
        hour=settings.digest_daily_hour,
    )

    # Immediate alerts check
    scheduler.add_job(
        send_immediate_alerts_job,
        IntervalTrigger(minutes=settings.alerts_interval_minutes),
        id="immediate_alerts",
        name="Check and send immediate alerts",
        replace_existing=True,
    )
    logger.info(
        "Registered job: immediate_alerts",
        interval_minutes=settings.alerts_interval_minutes,
    )

    # Embedding updates (daily)
    scheduler.add_job(
        update_embeddings_job,
        CronTrigger(hour=settings.embedding_update_hour),
        id="update_embeddings",
        name="Update paper and profile embeddings",
        replace_existing=True,
    )
    logger.info(
        "Registered job: update_embeddings",
        hour=settings.embedding_update_hour,
    )

    logger.info("Scheduler initialized with all jobs")
    return scheduler


def start_scheduler() -> None:
    """Start the scheduler.

    Call init_scheduler() first to register jobs.
    """
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")
    else:
        logger.warning("Scheduler already running")


def stop_scheduler() -> None:
    """Stop the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")
    _scheduler = None


def get_job_status() -> list[dict]:
    """Get status of all scheduled jobs.

    Returns:
        List of job status dictionaries
    """
    scheduler = get_scheduler()
    jobs = []

    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": next_run.isoformat() if next_run else None,
            "trigger": str(job.trigger),
        })

    return jobs


__all__ = [
    "get_scheduler",
    "init_scheduler",
    "start_scheduler",
    "stop_scheduler",
    "get_job_status",
]
