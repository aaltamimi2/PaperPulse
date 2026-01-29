"""Digest generation and email delivery service."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import structlog

from paperpulse.collectors.base import CollectedPaper
from paperpulse.core.config import get_settings
from paperpulse.email.models import Digest, DigestPaper, DigestSection
from paperpulse.email.templates import DigestRenderer
from paperpulse.scoring import AggregatedScore, EmbeddingService, ScoringPipeline

logger = structlog.get_logger(__name__)


@dataclass
class ResearchInterest:
    """User's research interest for digest generation."""

    name: str
    description: Optional[str] = None
    keywords: list[str] = None
    excluded_keywords: list[str] = None
    followed_authors: list[str] = None
    followed_journals: list[str] = None

    def __post_init__(self):
        self.keywords = self.keywords or []
        self.excluded_keywords = self.excluded_keywords or []
        self.followed_authors = self.followed_authors or []
        self.followed_journals = self.followed_journals or []

    def to_profile_dict(self) -> dict:
        """Convert to profile dictionary for scoring pipeline."""
        return {
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords,
            "excluded_keywords": self.excluded_keywords,
            "followed_authors": self.followed_authors,
            "followed_journals": self.followed_journals,
        }


class DigestService:
    """Service for generating paper digests."""

    def __init__(
        self,
        scoring_pipeline: Optional[ScoringPipeline] = None,
        renderer: Optional[DigestRenderer] = None,
        mock_mode: bool = False,
    ):
        """Initialize the digest service.

        Args:
            scoring_pipeline: Pipeline for scoring papers
            renderer: Template renderer for emails
            mock_mode: Use mock embeddings for testing
        """
        if scoring_pipeline is None:
            embedding_service = EmbeddingService(mock_mode=mock_mode)
            scoring_pipeline = ScoringPipeline(embedding_service=embedding_service)

        self.scoring_pipeline = scoring_pipeline
        self.renderer = renderer or DigestRenderer()

    def _collected_to_dict(self, paper: CollectedPaper) -> dict:
        """Convert CollectedPaper to dict for scoring."""
        return {
            "title": paper.title,
            "abstract": paper.abstract,
            "authors": paper.authors,
            "journal": paper.journal,
            "url": paper.url,
            "doi": paper.doi,
            "published_date": paper.published_date,
        }

    def _create_digest_paper(
        self,
        paper_dict: dict,
        score: AggregatedScore,
    ) -> DigestPaper:
        """Create a DigestPaper from paper dict and score."""
        # Generate relevance tags from score breakdown
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

        return DigestPaper(
            title=paper_dict.get("title", ""),
            url=paper_dict.get("url", ""),
            authors=paper_dict.get("authors", []),
            journal=paper_dict.get("journal"),
            published_date=paper_dict.get("published_date"),
            abstract=paper_dict.get("abstract"),
            doi=paper_dict.get("doi"),
            relevance_score=score.total_score,
            priority=score.priority,
            relevance_tags=list(set(tags))[:5],  # Dedupe and limit
        )

    async def generate_digest(
        self,
        user_name: str,
        user_email: str,
        interests: list[ResearchInterest],
        papers: list[CollectedPaper | dict],
        digest_type: str = "weekly",
        min_score: float = 0.1,
        max_papers_per_section: int = 10,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> Digest:
        """Generate a digest for a user with multiple research interests.

        Args:
            user_name: User's display name
            user_email: User's email address
            interests: List of research interests to create sections for
            papers: Papers to score and include
            digest_type: Type of digest (weekly, daily, immediate)
            min_score: Minimum score to include a paper
            max_papers_per_section: Max papers per interest section
            period_start: Start of the digest period
            period_end: End of the digest period

        Returns:
            Generated Digest object
        """
        logger.info(
            "Generating digest",
            user=user_email,
            interests=len(interests),
            papers=len(papers),
        )

        # Set default period
        if period_end is None:
            period_end = datetime.now()
        if period_start is None:
            if digest_type == "weekly":
                period_start = period_end - timedelta(days=7)
            elif digest_type == "daily":
                period_start = period_end - timedelta(days=1)
            else:
                period_start = period_end - timedelta(hours=24)

        # Convert papers to dicts if needed
        paper_dicts = []
        for paper in papers:
            if isinstance(paper, CollectedPaper):
                paper_dicts.append(self._collected_to_dict(paper))
            else:
                paper_dicts.append(paper)

        # Create digest
        digest = Digest(
            user_name=user_name,
            user_email=user_email,
            digest_type=digest_type,
            period_start=period_start,
            period_end=period_end,
        )

        # Score papers for each interest and create sections
        for interest in interests:
            logger.debug("Scoring for interest", interest=interest.name)

            profile = interest.to_profile_dict()
            scored_papers = await self.scoring_pipeline.score_papers(paper_dicts, profile)

            # Filter by minimum score and create digest papers
            section_papers = []
            immediate_count = 0
            weekly_count = 0

            for paper_dict, score in scored_papers:
                if score.total_score >= min_score:
                    digest_paper = self._create_digest_paper(paper_dict, score)
                    section_papers.append(digest_paper)

                    if score.priority == "immediate":
                        immediate_count += 1
                    elif score.priority == "weekly":
                        weekly_count += 1

                    if len(section_papers) >= max_papers_per_section:
                        break

            section = DigestSection(
                interest_name=interest.name,
                interest_description=interest.description,
                papers=section_papers,
                total_papers_found=len([p for p, s in scored_papers if s.total_score >= min_score]),
                immediate_count=immediate_count,
                weekly_count=weekly_count,
            )

            digest.add_section(section)

            logger.debug(
                "Section created",
                interest=interest.name,
                papers=len(section_papers),
                immediate=immediate_count,
                weekly=weekly_count,
            )

        logger.info(
            "Digest generated",
            user=user_email,
            sections=len(digest.sections),
            total_papers=digest.total_papers,
        )

        return digest

    def render_digest(self, digest: Digest) -> tuple[str, str]:
        """Render digest to HTML and text.

        Args:
            digest: Digest to render

        Returns:
            Tuple of (html_content, text_content)
        """
        return self.renderer.render(digest)


class EmailSender:
    """Send emails via SMTP or console output."""

    def __init__(self, mock_mode: bool = False):
        """Initialize the email sender.

        Args:
            mock_mode: If True, print to console instead of sending
        """
        self.settings = get_settings().email
        self.mock_mode = mock_mode or self.settings.provider == "console"

    async def send(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        """Send an email.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML version of email
            text_content: Plain text version

        Returns:
            True if sent successfully
        """
        if self.mock_mode:
            return await self._send_console(to_email, subject, html_content, text_content)
        else:
            return await self._send_smtp(to_email, subject, html_content, text_content)

    async def _send_console(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        """Print email to console (for testing)."""
        logger.info(
            "Email sent (console mode)",
            to=to_email,
            subject=subject,
        )

        print("\n" + "=" * 70)
        print(f"TO: {to_email}")
        print(f"FROM: {self.settings.from_name} <{self.settings.from_address}>")
        print(f"SUBJECT: {subject}")
        print("=" * 70)
        print(text_content)
        print("=" * 70 + "\n")

        return True

    async def _send_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        """Send email via SMTP."""
        try:
            import aiosmtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.settings.from_name} <{self.settings.from_address}>"
            msg["To"] = to_email

            # Attach both plain text and HTML versions
            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            await aiosmtplib.send(
                msg,
                hostname=self.settings.smtp_host,
                port=self.settings.smtp_port,
                username=self.settings.smtp_user,
                password=self.settings.smtp_password.get_secret_value(),
                use_tls=self.settings.smtp_use_tls,
            )

            logger.info("Email sent via SMTP", to=to_email, subject=subject)
            return True

        except Exception as e:
            logger.error("Failed to send email", to=to_email, error=str(e))
            return False

    async def send_digest(self, digest: Digest, renderer: DigestRenderer) -> bool:
        """Render and send a digest email.

        Args:
            digest: Digest to send
            renderer: Template renderer

        Returns:
            True if sent successfully
        """
        html_content, text_content = renderer.render(digest)
        return await self.send(
            to_email=digest.user_email,
            subject=digest.subject_line,
            html_content=html_content,
            text_content=text_content,
        )
