"""AI-powered paper summarization using Google Gemini."""

import asyncio
from typing import Optional

import google.generativeai as genai
import structlog

from paperpulse.core.config import get_settings
from paperpulse.email.models import DigestPaper

logger = structlog.get_logger(__name__)


class SummarizationService:
    """Generate AI-powered paper summaries and relevance explanations."""

    def __init__(self, mock_mode: bool = False):
        """Initialize the summarization service.

        Args:
            mock_mode: If True, return placeholder summaries (for testing)
        """
        self.mock_mode = mock_mode
        self.settings = get_settings().gemini
        self._model: Optional[genai.GenerativeModel] = None

        if not mock_mode:
            api_key = self.settings.api_key.get_secret_value()
            if api_key:
                genai.configure(api_key=api_key)
                self._model = genai.GenerativeModel(self.settings.chat_model)
            else:
                logger.warning("No Gemini API key configured, using mock mode")
                self.mock_mode = True

    async def generate_summary(
        self,
        title: str,
        abstract: Optional[str],
        max_sentences: int = 3,
    ) -> str:
        """Generate a concise summary of a paper.

        Args:
            title: Paper title
            abstract: Paper abstract
            max_sentences: Maximum number of sentences in summary

        Returns:
            Generated summary (2-3 sentences)
        """
        if self.mock_mode:
            return self._mock_summary(title)

        if not abstract:
            return f"This paper titled '{title}' explores the topic. No abstract available for detailed summary."

        prompt = f"""Summarize this academic paper in exactly {max_sentences} sentences.
Be concise, focus on the main contribution and findings. Use accessible language.

Title: {title}

Abstract: {abstract}

Summary (exactly {max_sentences} sentences):"""

        try:
            response = await asyncio.to_thread(
                self._model.generate_content,
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=200,
                ),
            )
            summary = response.text.strip()
            logger.debug("Generated summary", title=title[:50])
            return summary

        except Exception as e:
            logger.error("Failed to generate summary", title=title[:50], error=str(e))
            return self._mock_summary(title)

    async def generate_relevance_explanation(
        self,
        title: str,
        abstract: Optional[str],
        interest_name: str,
        interest_description: Optional[str],
        keywords: list[str],
        relevance_score: float,
    ) -> str:
        """Generate a personalized "Why this matters to you" explanation.

        Args:
            title: Paper title
            abstract: Paper abstract
            interest_name: Name of the user's research interest
            interest_description: Description of the interest
            keywords: Keywords associated with the interest
            relevance_score: Computed relevance score (0-1)

        Returns:
            Personalized relevance explanation
        """
        if self.mock_mode:
            return self._mock_relevance(interest_name, relevance_score)

        if not abstract:
            return f"This paper may be relevant to your interest in {interest_name}."

        keywords_str = ", ".join(keywords[:10]) if keywords else "your research topics"
        interest_desc = interest_description or interest_name

        prompt = f"""You are helping a researcher understand why a paper is relevant to their interests.
Write 1-2 sentences explaining why this paper matters for their research.
Be specific and actionable. Focus on how it connects to their work.

Researcher's Interest: {interest_name}
Interest Description: {interest_desc}
Keywords they follow: {keywords_str}
Relevance Score: {int(relevance_score * 100)}%

Paper Title: {title}
Paper Abstract: {abstract}

Why this paper matters (1-2 sentences):"""

        try:
            response = await asyncio.to_thread(
                self._model.generate_content,
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.5,
                    max_output_tokens=150,
                ),
            )
            explanation = response.text.strip()
            logger.debug("Generated relevance explanation", title=title[:50])
            return explanation

        except Exception as e:
            logger.error(
                "Failed to generate relevance explanation",
                title=title[:50],
                error=str(e),
            )
            return self._mock_relevance(interest_name, relevance_score)

    async def enrich_paper(
        self,
        paper: DigestPaper,
        interest_name: str,
        interest_description: Optional[str] = None,
        keywords: Optional[list[str]] = None,
    ) -> DigestPaper:
        """Enrich a DigestPaper with AI-generated summary and relevance explanation.

        Args:
            paper: Paper to enrich
            interest_name: Name of the research interest
            interest_description: Description of the interest
            keywords: Keywords for the interest

        Returns:
            Enriched DigestPaper with summary and why_relevant fields
        """
        keywords = keywords or []

        # Generate both in parallel
        summary_task = self.generate_summary(paper.title, paper.abstract)
        relevance_task = self.generate_relevance_explanation(
            title=paper.title,
            abstract=paper.abstract,
            interest_name=interest_name,
            interest_description=interest_description,
            keywords=keywords,
            relevance_score=paper.relevance_score,
        )

        summary, why_relevant = await asyncio.gather(summary_task, relevance_task)

        paper.summary = summary
        paper.why_relevant = why_relevant

        return paper

    async def enrich_papers_batch(
        self,
        papers: list[DigestPaper],
        interest_name: str,
        interest_description: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        max_concurrent: int = 5,
        max_papers: Optional[int] = None,
    ) -> list[DigestPaper]:
        """Enrich multiple papers with AI summaries (rate-limited).

        Args:
            papers: Papers to enrich
            interest_name: Research interest name
            interest_description: Interest description
            keywords: Interest keywords
            max_concurrent: Maximum concurrent API calls
            max_papers: Maximum papers to enrich (None = all)

        Returns:
            List of enriched papers
        """
        papers_to_enrich = papers[:max_papers] if max_papers else papers

        if not papers_to_enrich:
            return papers

        logger.info(
            "Enriching papers with AI summaries",
            count=len(papers_to_enrich),
            interest=interest_name,
        )

        semaphore = asyncio.Semaphore(max_concurrent)

        async def enrich_with_limit(paper: DigestPaper) -> DigestPaper:
            async with semaphore:
                return await self.enrich_paper(
                    paper,
                    interest_name=interest_name,
                    interest_description=interest_description,
                    keywords=keywords,
                )

        enriched = await asyncio.gather(
            *[enrich_with_limit(p) for p in papers_to_enrich]
        )

        # Combine enriched papers with any remaining non-enriched papers
        if max_papers and max_papers < len(papers):
            return list(enriched) + papers[max_papers:]

        return list(enriched)

    def _mock_summary(self, title: str) -> str:
        """Generate a placeholder summary for testing."""
        return (
            f"This paper presents novel findings in the field. "
            f"The research methodology is rigorous and the results are significant. "
            f"Further investigation may yield important practical applications."
        )

    def _mock_relevance(self, interest_name: str, score: float) -> str:
        """Generate a placeholder relevance explanation for testing."""
        score_pct = int(score * 100)
        if score >= 0.8:
            return f"This paper is highly relevant to your work in {interest_name}, directly addressing key topics you follow."
        elif score >= 0.5:
            return f"This paper connects to your interest in {interest_name} and may offer useful insights."
        else:
            return f"This paper has some overlap with your {interest_name} research area."


class DigestHighlightGenerator:
    """Generate digest-level highlights and insights."""

    def __init__(self, mock_mode: bool = False):
        """Initialize the highlight generator.

        Args:
            mock_mode: If True, return placeholder content
        """
        self.mock_mode = mock_mode
        self.settings = get_settings().gemini
        self._model: Optional[genai.GenerativeModel] = None

        if not mock_mode:
            api_key = self.settings.api_key.get_secret_value()
            if api_key:
                genai.configure(api_key=api_key)
                self._model = genai.GenerativeModel(self.settings.chat_model)
            else:
                self.mock_mode = True

    async def generate_section_highlight(
        self,
        interest_name: str,
        papers: list[DigestPaper],
        max_papers_context: int = 5,
    ) -> str:
        """Generate a highlight summary for a digest section.

        Args:
            interest_name: Research interest name
            papers: Papers in the section
            max_papers_context: Maximum papers to include in context

        Returns:
            Section highlight paragraph
        """
        if self.mock_mode or not papers:
            return self._mock_section_highlight(interest_name, len(papers))

        # Build context from top papers
        top_papers = sorted(papers, key=lambda p: p.relevance_score, reverse=True)[
            :max_papers_context
        ]
        papers_context = "\n".join(
            f"- {p.title} (relevance: {p.score_percent}%)"
            for p in top_papers
        )

        prompt = f"""Write a 2-3 sentence highlight summary for a research digest section.
Mention key themes and any standout papers. Be engaging and informative.

Research Interest: {interest_name}
Number of papers: {len(papers)}

Top papers:
{papers_context}

Section highlight:"""

        try:
            response = await asyncio.to_thread(
                self._model.generate_content,
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.6,
                    max_output_tokens=150,
                ),
            )
            return response.text.strip()

        except Exception as e:
            logger.error(
                "Failed to generate section highlight",
                interest=interest_name,
                error=str(e),
            )
            return self._mock_section_highlight(interest_name, len(papers))

    async def generate_digest_intro(
        self,
        user_name: str,
        digest_type: str,
        sections_summary: list[tuple[str, int]],
    ) -> str:
        """Generate a personalized digest introduction.

        Args:
            user_name: User's name
            digest_type: Type of digest (weekly, daily, immediate)
            sections_summary: List of (interest_name, paper_count) tuples

        Returns:
            Personalized intro paragraph
        """
        if self.mock_mode:
            return self._mock_digest_intro(user_name, digest_type, sections_summary)

        total_papers = sum(count for _, count in sections_summary)
        interests_list = ", ".join(name for name, _ in sections_summary)

        prompt = f"""Write a personalized 2-sentence introduction for a research paper digest email.
Be warm but professional. Mention what the digest contains.

Recipient: {user_name}
Digest type: {digest_type}
Total papers: {total_papers}
Research interests covered: {interests_list}

Introduction:"""

        try:
            response = await asyncio.to_thread(
                self._model.generate_content,
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=100,
                ),
            )
            return response.text.strip()

        except Exception as e:
            logger.error("Failed to generate digest intro", error=str(e))
            return self._mock_digest_intro(user_name, digest_type, sections_summary)

    def _mock_section_highlight(self, interest_name: str, paper_count: int) -> str:
        """Generate placeholder section highlight."""
        return (
            f"This week brings {paper_count} new papers relevant to {interest_name}. "
            f"Several papers show promising advances in key areas of interest."
        )

    def _mock_digest_intro(
        self,
        user_name: str,
        digest_type: str,
        sections_summary: list[tuple[str, int]],
    ) -> str:
        """Generate placeholder digest intro."""
        total = sum(count for _, count in sections_summary)
        interests = len(sections_summary)
        first_name = user_name.split()[0] if user_name else "there"

        return (
            f"Hi {first_name}! Your {digest_type} research digest is ready with "
            f"{total} papers across {interests} research interest{'s' if interests > 1 else ''}. "
            f"Here are the highlights curated just for you."
        )


__all__ = ["SummarizationService", "DigestHighlightGenerator"]
