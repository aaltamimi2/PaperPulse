"""Email campaign orchestration for personalized digest delivery."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from paperpulse.core.config import get_settings
from paperpulse.db.models import DigestLog, InterestCategory, Paper, ResearchProfile, User
from paperpulse.email.models import Digest, DigestPaper, DigestSection
from paperpulse.email.service import DigestService, EmailSender
from paperpulse.email.summarization import DigestHighlightGenerator, SummarizationService
from paperpulse.email.templates import DigestRenderer
from paperpulse.scoring import EmbeddingService, ScoringPipeline

logger = structlog.get_logger(__name__)


@dataclass
class CampaignResult:
    """Result of a campaign execution."""

    campaign_type: str
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    # Metrics
    users_processed: int = 0
    emails_sent: int = 0
    emails_failed: int = 0
    papers_included: int = 0

    # Errors
    errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate email delivery success rate."""
        total = self.emails_sent + self.emails_failed
        if total == 0:
            return 0.0
        return self.emails_sent / total

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get campaign duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class DigestCampaign:
    """Orchestrate digest email campaigns for all users."""

    def __init__(
        self,
        session: AsyncSession,
        mock_mode: bool = False,
        enable_ai_summaries: bool = True,
        max_papers_to_summarize: int = 10,
    ):
        """Initialize the digest campaign.

        Args:
            session: Database session
            mock_mode: Use mock mode for testing
            enable_ai_summaries: Generate AI summaries for papers
            max_papers_to_summarize: Max papers per section to summarize
        """
        self.session = session
        self.mock_mode = mock_mode
        self.enable_ai_summaries = enable_ai_summaries
        self.max_papers_to_summarize = max_papers_to_summarize

        # Initialize services
        embedding_service = EmbeddingService(mock_mode=mock_mode)
        self.scoring_pipeline = ScoringPipeline(embedding_service=embedding_service)
        self.digest_service = DigestService(
            scoring_pipeline=self.scoring_pipeline,
            mock_mode=mock_mode,
        )
        self.renderer = DigestRenderer()
        self.email_sender = EmailSender(mock_mode=mock_mode)
        self.summarization = SummarizationService(mock_mode=mock_mode)
        self.highlight_generator = DigestHighlightGenerator(mock_mode=mock_mode)

    async def get_eligible_users(
        self,
        digest_type: str,
        current_hour: Optional[int] = None,
        current_day: Optional[int] = None,
    ) -> list[User]:
        """Get users eligible for a digest based on their preferences.

        Args:
            digest_type: Type of digest (weekly, daily)
            current_hour: Current hour (0-23), uses system time if None
            current_day: Current day of week (0=Mon, 6=Sun)

        Returns:
            List of eligible users
        """
        now = datetime.now()
        current_hour = current_hour if current_hour is not None else now.hour
        current_day = current_day if current_day is not None else now.weekday()

        query = (
            select(User)
            .options(selectinload(User.research_profiles).selectinload(ResearchProfile.interest_categories))
            .where(User.digest_enabled == True)  # noqa: E712
        )

        if digest_type == "weekly":
            query = query.where(User.digest_frequency == "weekly")
            query = query.where(User.digest_day == current_day)
            query = query.where(User.digest_hour == current_hour)
        elif digest_type == "daily":
            query = query.where(User.digest_frequency == "daily")
            query = query.where(User.digest_hour == current_hour)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_papers_for_period(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict]:
        """Get papers collected within a time period.

        Args:
            start_date: Start of period
            end_date: End of period

        Returns:
            List of paper dictionaries for scoring
        """
        query = (
            select(Paper)
            .where(Paper.collected_at >= start_date)
            .where(Paper.collected_at <= end_date)
        )

        result = await self.session.execute(query)
        papers = result.scalars().all()

        return [
            {
                "title": p.title,
                "abstract": p.abstract,
                "authors": p.authors or [],
                "journal": p.journal,
                "url": p.url,
                "doi": p.doi,
                "published_date": p.published_date,
                "citation_count": p.citation_count,
                "influential_citation_count": p.influential_citation_count,
                "fields_of_study": p.fields_of_study or [],
                "venue": p.venue,
                "year": p.year,
            }
            for p in papers
        ]

    async def generate_user_digest(
        self,
        user: User,
        papers: list[dict],
        digest_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Optional[Digest]:
        """Generate a digest for a single user.

        Args:
            user: User to generate digest for
            papers: Available papers for the period
            digest_type: Type of digest
            period_start: Start of period
            period_end: End of period

        Returns:
            Generated Digest or None if no relevant papers
        """
        if not user.research_profiles:
            logger.warning("User has no profiles", user_id=user.id)
            return None

        # Get primary profile
        profile = user.research_profiles[0]
        if not profile.interest_categories:
            logger.warning("Profile has no interests", user_id=user.id)
            return None

        digest = Digest(
            user_name=user.name or user.email,
            user_email=user.email,
            digest_type=digest_type,
            period_start=period_start,
            period_end=period_end,
        )

        # Process each interest category
        for interest in profile.interest_categories:
            # Build profile dict for scoring
            profile_dict = {
                "name": interest.name,
                "description": interest.description,
                "keywords": interest.keywords or [],
                "excluded_keywords": interest.excluded_keywords or [],
                "followed_authors": interest.followed_authors or [],
                "followed_journals": interest.followed_journals or [],
            }

            # Score papers
            scored_papers = await self.scoring_pipeline.score_papers(papers, profile_dict)

            # Filter and create digest papers
            section_papers: list[DigestPaper] = []
            min_score = 0.1

            for paper_dict, score in scored_papers:
                if score.total_score >= min_score:
                    # Generate tags from score
                    tags = self._extract_relevance_tags(score)

                    digest_paper = DigestPaper(
                        title=paper_dict.get("title", ""),
                        url=paper_dict.get("url", ""),
                        authors=paper_dict.get("authors", []),
                        journal=paper_dict.get("journal"),
                        published_date=paper_dict.get("published_date"),
                        abstract=paper_dict.get("abstract"),
                        doi=paper_dict.get("doi"),
                        relevance_score=score.total_score,
                        priority=score.priority,
                        relevance_tags=tags,
                    )
                    section_papers.append(digest_paper)

                    if len(section_papers) >= 10:  # Max papers per section
                        break

            # Enrich with AI summaries if enabled
            if self.enable_ai_summaries and section_papers:
                section_papers = await self.summarization.enrich_papers_batch(
                    papers=section_papers,
                    interest_name=interest.name,
                    interest_description=interest.description,
                    keywords=interest.keywords or [],
                    max_papers=self.max_papers_to_summarize,
                )

            # Create section
            immediate_count = sum(1 for p in section_papers if p.priority == "immediate")
            weekly_count = sum(1 for p in section_papers if p.priority == "weekly")

            section = DigestSection(
                interest_name=interest.name,
                interest_description=interest.description,
                papers=section_papers,
                total_papers_found=len(section_papers),
                immediate_count=immediate_count,
                weekly_count=weekly_count,
            )

            digest.add_section(section)

        if not digest.has_content:
            logger.info("No relevant papers for user", user_id=user.id)
            return None

        return digest

    def _extract_relevance_tags(self, score) -> list[str]:
        """Extract relevance tags from scoring breakdown."""
        tags = []
        for component in score.component_scores:
            if component.score >= 0.5:
                if component.scorer_name == "keyword":
                    matched = component.details.get("matched_keywords", [])
                    tags.extend(matched[:3])
                elif component.scorer_name == "author":
                    matched = component.details.get("matched_authors", [])
                    if matched:
                        tags.append(f"Author: {matched[0]}")
                elif component.scorer_name == "novelty" and component.score >= 0.5:
                    tags.append("Novel method")
                elif component.scorer_name == "citation" and component.score >= 0.7:
                    tags.append("Highly cited")
                elif component.scorer_name == "recency" and component.score >= 0.8:
                    tags.append("Recent")
        return list(set(tags))[:5]

    async def log_digest_sent(
        self,
        user_id: int,
        digest_type: str,
        papers_count: int,
        period_start: datetime,
        period_end: datetime,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Log a digest delivery attempt.

        Args:
            user_id: User ID
            digest_type: Type of digest
            papers_count: Number of papers included
            period_start: Period start
            period_end: Period end
            success: Whether delivery succeeded
            error_message: Error message if failed
        """
        log = DigestLog(
            user_id=user_id,
            digest_type=digest_type,
            papers_count=papers_count,
            period_start=period_start,
            period_end=period_end,
            sent_at=datetime.now() if success else None,
            status="sent" if success else "failed",
            error_message=error_message,
        )
        self.session.add(log)
        await self.session.commit()

    async def run(
        self,
        digest_type: str = "weekly",
        force_users: Optional[list[int]] = None,
    ) -> CampaignResult:
        """Run a digest campaign.

        Args:
            digest_type: Type of digest (weekly, daily)
            force_users: Specific user IDs to send to (overrides schedule)

        Returns:
            Campaign result with metrics
        """
        result = CampaignResult(campaign_type=f"{digest_type}_digest")

        logger.info("Starting digest campaign", type=digest_type)

        # Calculate period
        period_end = datetime.now()
        if digest_type == "weekly":
            period_start = period_end - timedelta(days=7)
        else:
            period_start = period_end - timedelta(days=1)

        # Get papers
        papers = await self.get_papers_for_period(period_start, period_end)
        if not papers:
            logger.warning("No papers found for period")
            result.completed_at = datetime.now()
            return result

        logger.info("Found papers for period", count=len(papers))

        # Get eligible users
        if force_users:
            query = (
                select(User)
                .options(selectinload(User.research_profiles).selectinload(ResearchProfile.interest_categories))
                .where(User.id.in_(force_users))
            )
            users_result = await self.session.execute(query)
            users = list(users_result.scalars().all())
        else:
            users = await self.get_eligible_users(digest_type)

        if not users:
            logger.info("No eligible users for digest")
            result.completed_at = datetime.now()
            return result

        logger.info("Processing users", count=len(users))
        result.users_processed = len(users)

        # Process each user
        for user in users:
            try:
                digest = await self.generate_user_digest(
                    user=user,
                    papers=papers,
                    digest_type=digest_type,
                    period_start=period_start,
                    period_end=period_end,
                )

                if digest is None:
                    continue

                # Render and send
                html_content, text_content = self.renderer.render(digest)
                success = await self.email_sender.send(
                    to_email=user.email,
                    subject=digest.subject_line,
                    html_content=html_content,
                    text_content=text_content,
                )

                if success:
                    result.emails_sent += 1
                    result.papers_included += digest.total_papers
                    await self.log_digest_sent(
                        user_id=user.id,
                        digest_type=digest_type,
                        papers_count=digest.total_papers,
                        period_start=period_start,
                        period_end=period_end,
                        success=True,
                    )
                else:
                    result.emails_failed += 1
                    await self.log_digest_sent(
                        user_id=user.id,
                        digest_type=digest_type,
                        papers_count=digest.total_papers,
                        period_start=period_start,
                        period_end=period_end,
                        success=False,
                        error_message="Email delivery failed",
                    )

            except Exception as e:
                logger.error(
                    "Failed to process user digest",
                    user_id=user.id,
                    error=str(e),
                )
                result.emails_failed += 1
                result.errors.append(f"User {user.id}: {str(e)}")

        result.completed_at = datetime.now()
        logger.info(
            "Digest campaign completed",
            type=digest_type,
            sent=result.emails_sent,
            failed=result.emails_failed,
            duration=result.duration_seconds,
        )

        return result


class ImmediateAlertCampaign:
    """Send immediate alerts for high-priority papers."""

    def __init__(
        self,
        session: AsyncSession,
        mock_mode: bool = False,
    ):
        """Initialize the alert campaign.

        Args:
            session: Database session
            mock_mode: Use mock mode for testing
        """
        self.session = session
        self.mock_mode = mock_mode

        embedding_service = EmbeddingService(mock_mode=mock_mode)
        self.scoring_pipeline = ScoringPipeline(embedding_service=embedding_service)
        self.renderer = DigestRenderer()
        self.email_sender = EmailSender(mock_mode=mock_mode)
        self.summarization = SummarizationService(mock_mode=mock_mode)

    async def get_users_with_immediate_alerts(self) -> list[User]:
        """Get users who have immediate alerts enabled."""
        query = (
            select(User)
            .options(selectinload(User.research_profiles).selectinload(ResearchProfile.interest_categories))
            .where(User.immediate_alerts_enabled == True)  # noqa: E712
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_new_papers_since(
        self,
        since: datetime,
    ) -> list[dict]:
        """Get papers collected since a given time.

        Args:
            since: Cutoff datetime

        Returns:
            List of paper dictionaries
        """
        query = select(Paper).where(Paper.collected_at >= since)
        result = await self.session.execute(query)
        papers = result.scalars().all()

        return [
            {
                "title": p.title,
                "abstract": p.abstract,
                "authors": p.authors or [],
                "journal": p.journal,
                "url": p.url,
                "doi": p.doi,
                "published_date": p.published_date,
                "citation_count": p.citation_count,
                "influential_citation_count": p.influential_citation_count,
                "fields_of_study": p.fields_of_study or [],
            }
            for p in papers
        ]

    async def check_and_send_alerts(
        self,
        lookback_hours: int = 1,
        min_score: float = 0.7,
    ) -> CampaignResult:
        """Check for high-priority papers and send immediate alerts.

        Args:
            lookback_hours: Hours to look back for new papers
            min_score: Minimum score for immediate alert

        Returns:
            Campaign result
        """
        result = CampaignResult(campaign_type="immediate_alert")

        since = datetime.now() - timedelta(hours=lookback_hours)
        papers = await self.get_new_papers_since(since)

        if not papers:
            result.completed_at = datetime.now()
            return result

        users = await self.get_users_with_immediate_alerts()
        result.users_processed = len(users)

        for user in users:
            try:
                if not user.research_profiles:
                    continue

                profile = user.research_profiles[0]
                if not profile.interest_categories:
                    continue

                # Check each interest for high-priority matches
                alert_papers: list[DigestPaper] = []

                for interest in profile.interest_categories:
                    profile_dict = {
                        "name": interest.name,
                        "description": interest.description,
                        "keywords": interest.keywords or [],
                        "excluded_keywords": interest.excluded_keywords or [],
                        "followed_authors": interest.followed_authors or [],
                        "followed_journals": interest.followed_journals or [],
                    }

                    scored_papers = await self.scoring_pipeline.score_papers(
                        papers, profile_dict
                    )

                    for paper_dict, score in scored_papers:
                        if score.total_score >= min_score:
                            digest_paper = DigestPaper(
                                title=paper_dict.get("title", ""),
                                url=paper_dict.get("url", ""),
                                authors=paper_dict.get("authors", []),
                                journal=paper_dict.get("journal"),
                                abstract=paper_dict.get("abstract"),
                                relevance_score=score.total_score,
                                priority="immediate",
                            )

                            # Enrich with AI summary
                            await self.summarization.enrich_paper(
                                digest_paper,
                                interest_name=interest.name,
                                interest_description=interest.description,
                                keywords=interest.keywords or [],
                            )

                            alert_papers.append(digest_paper)

                if not alert_papers:
                    continue

                # Create and send alert
                digest = Digest(
                    user_name=user.name or user.email,
                    user_email=user.email,
                    digest_type="immediate",
                    period_start=since,
                    period_end=datetime.now(),
                )

                section = DigestSection(
                    interest_name="High-Priority Alerts",
                    papers=alert_papers,
                    total_papers_found=len(alert_papers),
                    immediate_count=len(alert_papers),
                )
                digest.add_section(section)

                html_content, text_content = self.renderer.render(digest)
                success = await self.email_sender.send(
                    to_email=user.email,
                    subject=digest.subject_line,
                    html_content=html_content,
                    text_content=text_content,
                )

                if success:
                    result.emails_sent += 1
                    result.papers_included += len(alert_papers)
                else:
                    result.emails_failed += 1

            except Exception as e:
                logger.error(
                    "Failed to process user alert",
                    user_id=user.id,
                    error=str(e),
                )
                result.emails_failed += 1
                result.errors.append(f"User {user.id}: {str(e)}")

        result.completed_at = datetime.now()
        logger.info(
            "Immediate alert campaign completed",
            sent=result.emails_sent,
            failed=result.emails_failed,
        )

        return result


__all__ = ["DigestCampaign", "ImmediateAlertCampaign", "CampaignResult"]
