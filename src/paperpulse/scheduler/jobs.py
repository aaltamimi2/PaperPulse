"""Scheduled job implementations.

This module contains the actual job functions that are executed by the scheduler:
- collect_papers_job: Collect papers from all configured sources
- generate_digests_job: Generate and send digest emails
- send_immediate_alerts_job: Check for high-priority papers and send alerts
- update_embeddings_job: Update paper and profile embeddings
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from paperpulse.core.config import get_settings
from paperpulse.db.models import DigestLog, InterestCategory, JobLog, Paper, ResearchProfile, User
from paperpulse.db.session import get_session

logger = structlog.get_logger(__name__)


async def _log_job_start(job_name: str, job_type: str) -> str:
    """Create a job log entry for a starting job.

    Args:
        job_name: Name of the job
        job_type: Type of job (collect, digest, alert, embedding)

    Returns:
        Job log ID
    """
    async with get_session() as session:
        job_log = JobLog(
            job_name=job_name,
            job_type=job_type,
            started_at=datetime.now(timezone.utc),
            status="running",
        )
        session.add(job_log)
        await session.flush()
        return job_log.id


async def _log_job_complete(
    job_id: str,
    status: str = "completed",
    error_message: Optional[str] = None,
    items_processed: int = 0,
    items_created: int = 0,
    details: Optional[dict] = None,
) -> None:
    """Update a job log entry with completion status.

    Args:
        job_id: Job log ID
        status: Final status (completed, failed)
        error_message: Error message if failed
        items_processed: Number of items processed
        items_created: Number of items created
        details: Additional details
    """
    async with get_session() as session:
        result = await session.execute(
            select(JobLog).where(JobLog.id == job_id)
        )
        job_log = result.scalar_one_or_none()

        if job_log:
            job_log.completed_at = datetime.now(timezone.utc)
            job_log.status = status
            job_log.error_message = error_message
            job_log.items_processed = items_processed
            job_log.items_created = items_created
            job_log.details = details

            if job_log.started_at:
                duration = (job_log.completed_at - job_log.started_at).total_seconds()
                job_log.duration_seconds = duration


async def collect_papers_job() -> dict:
    """Collect papers from all configured sources.

    This job:
    1. Collects papers from RSS feeds, Semantic Scholar, PubMed, arXiv
    2. Deduplicates papers
    3. Stores new papers in the database
    4. Generates embeddings for new papers

    Returns:
        Summary of collection results
    """
    job_id = await _log_job_start("collect_papers", "collect")
    log = logger.bind(job_id=job_id)
    log.info("Starting paper collection job")

    try:
        from paperpulse.collectors import (
            ArxivCollector,
            PaperAggregator,
            PubMedCollector,
            RSSCollector,
            SemanticScholarCollector,
        )

        settings = get_settings()

        # Initialize collectors
        collectors = [RSSCollector()]

        # Add Semantic Scholar if configured
        if settings.semantic_scholar.api_key.get_secret_value():
            collectors.append(SemanticScholarCollector())

        # Add PubMed if email is configured
        if settings.pubmed.email:
            collectors.append(PubMedCollector())

        # Add arXiv (no config needed)
        collectors.append(ArxivCollector())

        aggregator = PaperAggregator(collectors)

        # Get active research profiles to determine what to collect
        async with get_session() as session:
            result = await session.execute(
                select(InterestCategory)
                .join(ResearchProfile)
                .where(ResearchProfile.is_active == True)
            )
            interests = result.scalars().all()

        # Build queries from user interests
        queries = set()
        for interest in interests:
            # Add keywords as queries
            for keyword in interest.keywords[:3]:  # Limit to top 3 keywords
                queries.add(keyword)

        if not queries:
            # Default queries if no user interests
            queries = {"machine learning", "molecular dynamics", "computational chemistry"}

        log.info("Collecting papers", query_count=len(queries))

        total_collected = 0
        total_new = 0

        for query in queries:
            try:
                result = await aggregator.collect_from_query(query, limit=50)
                total_collected += result.total_collected

                # Store new papers
                async with get_session() as session:
                    for paper in result.papers:
                        # Check if paper already exists
                        existing = None
                        if paper.doi:
                            existing = await session.execute(
                                select(Paper).where(Paper.doi == paper.doi)
                            )
                            existing = existing.scalar_one_or_none()

                        if not existing and paper.content_hash():
                            existing = await session.execute(
                                select(Paper).where(Paper.content_hash == paper.content_hash())
                            )
                            existing = existing.scalar_one_or_none()

                        if not existing:
                            db_paper = Paper(
                                title=paper.title,
                                url=paper.url,
                                abstract=paper.abstract,
                                authors=paper.authors,
                                doi=paper.doi,
                                arxiv_id=paper.arxiv_id,
                                pubmed_id=paper.pubmed_id,
                                semantic_scholar_id=paper.semantic_scholar_id,
                                journal=paper.journal,
                                venue=paper.venue,
                                published_date=paper.published_date,
                                year=paper.year,
                                citation_count=paper.citation_count,
                                influential_citation_count=paper.influential_citation_count,
                                fields_of_study=paper.fields_of_study,
                                source_type=paper.source_type,
                                content_hash=paper.content_hash(),
                            )
                            session.add(db_paper)
                            total_new += 1

            except Exception as e:
                log.warning("Query collection failed", query=query, error=str(e))

        # Close collectors
        await aggregator.close()

        summary = {
            "queries_processed": len(queries),
            "total_collected": total_collected,
            "new_papers": total_new,
        }

        await _log_job_complete(
            job_id,
            status="completed",
            items_processed=total_collected,
            items_created=total_new,
            details=summary,
        )

        log.info("Paper collection completed", **summary)
        return summary

    except Exception as e:
        log.error("Paper collection failed", error=str(e))
        await _log_job_complete(job_id, status="failed", error_message=str(e))
        raise


async def generate_digests_job(digest_type: str = "weekly") -> dict:
    """Generate and send digest emails for all eligible users.

    Uses the DigestCampaign system for personalized AI-enhanced email delivery.

    Args:
        digest_type: Type of digest (daily, weekly)

    Returns:
        Summary of digests sent
    """
    job_id = await _log_job_start(f"{digest_type}_digest", "digest")
    log = logger.bind(job_id=job_id, digest_type=digest_type)
    log.info("Starting digest generation job")

    try:
        from paperpulse.email.campaigns import DigestCampaign

        async with get_session() as session:
            # Use the campaign system for digest generation
            campaign = DigestCampaign(
                session=session,
                mock_mode=get_settings().environment == "development",
                enable_ai_summaries=True,
                max_papers_to_summarize=10,
            )

            result = await campaign.run(digest_type=digest_type)

        summary = {
            "users_processed": result.users_processed,
            "digests_sent": result.emails_sent,
            "digests_failed": result.emails_failed,
            "papers_included": result.papers_included,
            "duration_seconds": result.duration_seconds,
            "success_rate": result.success_rate,
        }

        if result.errors:
            summary["errors"] = result.errors[:10]  # Limit stored errors

        status = "completed" if result.emails_failed == 0 else "completed_with_errors"

        await _log_job_complete(
            job_id,
            status=status,
            items_processed=result.users_processed,
            items_created=result.emails_sent,
            details=summary,
        )

        log.info("Digest generation completed", **summary)
        return summary

    except Exception as e:
        log.error("Digest generation failed", error=str(e))
        await _log_job_complete(job_id, status="failed", error_message=str(e))
        raise


async def send_immediate_alerts_job() -> dict:
    """Check for high-priority papers and send immediate alerts.

    Uses the ImmediateAlertCampaign for AI-enhanced alert delivery.

    This job:
    1. Gets papers added since last check
    2. Scores them against user profiles
    3. Sends alerts for immediate-priority matches with AI summaries

    Returns:
        Summary of alerts sent
    """
    job_id = await _log_job_start("immediate_alerts", "alert")
    log = logger.bind(job_id=job_id)
    log.info("Starting immediate alerts job")

    try:
        from paperpulse.email.campaigns import ImmediateAlertCampaign

        async with get_session() as session:
            # Use the campaign system for immediate alerts
            campaign = ImmediateAlertCampaign(
                session=session,
                mock_mode=get_settings().environment == "development",
            )

            result = await campaign.check_and_send_alerts(
                lookback_hours=1,
                min_score=0.7,
            )

        summary = {
            "users_checked": result.users_processed,
            "alerts_sent": result.emails_sent,
            "alerts_failed": result.emails_failed,
            "papers_included": result.papers_included,
            "duration_seconds": result.duration_seconds,
        }

        if result.errors:
            summary["errors"] = result.errors[:10]

        status = "completed" if result.emails_failed == 0 else "completed_with_errors"

        await _log_job_complete(
            job_id,
            status=status,
            items_processed=result.users_processed,
            items_created=result.emails_sent,
            details=summary,
        )

        log.info("Immediate alerts completed", **summary)
        return summary

    except Exception as e:
        log.error("Immediate alerts failed", error=str(e))
        await _log_job_complete(job_id, status="failed", error_message=str(e))
        raise


async def update_embeddings_job() -> dict:
    """Update embeddings for papers and profiles that need them.

    This job:
    1. Finds papers without embeddings
    2. Generates embeddings using the embedding service
    3. Updates profile embeddings that are stale

    Returns:
        Summary of embeddings updated
    """
    job_id = await _log_job_start("update_embeddings", "embedding")
    log = logger.bind(job_id=job_id)
    log.info("Starting embedding update job")

    try:
        from paperpulse.scoring.embeddings import EmbeddingService

        embedding_service = EmbeddingService()

        # Find papers without embeddings (limit batch size)
        async with get_session() as session:
            result = await session.execute(
                select(Paper)
                .where(Paper.embedding == None)
                .limit(100)
            )
            papers = result.scalars().all()

        papers_updated = 0

        for paper in papers:
            try:
                embedding = await embedding_service.embed_paper(
                    paper.title,
                    paper.abstract,
                )

                async with get_session() as session:
                    result = await session.execute(
                        select(Paper).where(Paper.id == paper.id)
                    )
                    db_paper = result.scalar_one_or_none()
                    if db_paper:
                        db_paper.embedding = embedding
                        db_paper.embedding_model = "text-embedding-004"
                        papers_updated += 1

            except Exception as e:
                log.warning("Failed to embed paper", paper_id=paper.id, error=str(e))

        # Find stale profile embeddings (older than 7 days)
        stale_cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        async with get_session() as session:
            result = await session.execute(
                select(InterestCategory)
                .where(
                    (InterestCategory.embedding_updated_at == None) |
                    (InterestCategory.embedding_updated_at < stale_cutoff)
                )
                .limit(50)
            )
            interests = result.scalars().all()

        profiles_updated = 0

        for interest in interests:
            try:
                embedding = await embedding_service.embed_research_profile(
                    interest.name,
                    interest.description,
                    interest.keywords,
                )

                async with get_session() as session:
                    result = await session.execute(
                        select(InterestCategory).where(InterestCategory.id == interest.id)
                    )
                    db_interest = result.scalar_one_or_none()
                    if db_interest:
                        db_interest.profile_embedding = embedding
                        db_interest.embedding_updated_at = datetime.now(timezone.utc)
                        profiles_updated += 1

            except Exception as e:
                log.warning("Failed to embed profile", interest_id=interest.id, error=str(e))

        summary = {
            "papers_without_embedding": len(papers),
            "papers_updated": papers_updated,
            "profiles_stale": len(interests),
            "profiles_updated": profiles_updated,
        }

        await _log_job_complete(
            job_id,
            status="completed",
            items_processed=len(papers) + len(interests),
            items_created=papers_updated + profiles_updated,
            details=summary,
        )

        log.info("Embedding update completed", **summary)
        return summary

    except Exception as e:
        log.error("Embedding update failed", error=str(e))
        await _log_job_complete(job_id, status="failed", error_message=str(e))
        raise
