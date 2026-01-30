"""Trend detection service for identifying emerging research topics.

This module provides production-level trend detection including:
- Emerging topic detection based on publication velocity
- Citation velocity tracking (rapidly cited papers)
- Trend forecasting and momentum scoring
- Personalized trend reports based on user interests
"""

import asyncio
import hashlib
import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import aiohttp
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TrendingTopic:
    """A trending research topic."""

    topic_id: str
    name: str
    description: str
    keywords: list[str]
    papers: list[dict]  # Representative papers
    trend_score: float  # Overall trend score (0-100)
    momentum: float  # Rate of change (positive = growing)
    first_seen: datetime
    peak_date: Optional[datetime] = None
    publication_velocity: float = 0.0  # Papers per day
    citation_velocity: float = 0.0  # Citations per day
    related_topics: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "topic_id": self.topic_id,
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords,
            "paper_count": len(self.papers),
            "representative_papers": [
                {"title": p.get("title"), "doi": p.get("doi")}
                for p in self.papers[:5]
            ],
            "trend_score": self.trend_score,
            "momentum": self.momentum,
            "first_seen": self.first_seen.isoformat(),
            "peak_date": self.peak_date.isoformat() if self.peak_date else None,
            "publication_velocity": self.publication_velocity,
            "citation_velocity": self.citation_velocity,
            "related_topics": self.related_topics,
        }


@dataclass
class RapidlyCitedPaper:
    """A paper that is gaining citations rapidly."""

    paper_id: str
    title: str
    authors: list[str]
    published_date: datetime
    citation_count: int
    citation_velocity: float  # Citations per day
    citation_acceleration: float  # Change in velocity
    percentile: float  # How fast compared to similar papers
    paper_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": self.authors[:5],
            "published_date": self.published_date.isoformat(),
            "citation_count": self.citation_count,
            "citation_velocity": self.citation_velocity,
            "citation_acceleration": self.citation_acceleration,
            "percentile": self.percentile,
        }


@dataclass
class TrendReport:
    """A comprehensive trend report."""

    generated_at: datetime
    time_window_days: int
    trending_topics: list[TrendingTopic]
    rapidly_cited_papers: list[RapidlyCitedPaper]
    emerging_keywords: list[tuple[str, float]]  # (keyword, growth_rate)
    declining_topics: list[TrendingTopic]
    user_relevant_trends: list[TrendingTopic]  # Filtered by user interests
    summary: str

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "time_window_days": self.time_window_days,
            "trending_topics": [t.to_dict() for t in self.trending_topics],
            "rapidly_cited_papers": [p.to_dict() for p in self.rapidly_cited_papers],
            "emerging_keywords": self.emerging_keywords[:20],
            "declining_topics": [t.to_dict() for t in self.declining_topics],
            "user_relevant_trends": [t.to_dict() for t in self.user_relevant_trends],
            "summary": self.summary,
        }


class TrendDetectionService:
    """Service for detecting emerging research trends.

    This service analyzes paper publication patterns and citation data to identify:
    1. Emerging topics: New research areas with growing publication rates
    2. Hot papers: Recently published papers gaining citations rapidly
    3. Declining topics: Areas with decreasing publication activity
    4. Keyword emergence: New terminology gaining popularity

    Features:
    - Time-series analysis of publication and citation data
    - Momentum and acceleration scoring
    - Personalized trend filtering based on user interests
    - LLM-powered trend summaries
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        semantic_scholar_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
    ):
        """Initialize the trend detection service.

        Args:
            gemini_api_key: API key for Gemini (summaries)
            semantic_scholar_key: API key for Semantic Scholar (citation data)
            cache_dir: Directory for caching trend data
        """
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.semantic_scholar_key = semantic_scholar_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        self.cache_dir = cache_dir or Path.home() / ".paperpulse" / "cache" / "trends"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Historical trend data
        self._trend_history: dict[str, list[dict]] = {}
        self._load_trend_history()

    def _load_trend_history(self) -> None:
        """Load historical trend data from disk."""
        history_file = self.cache_dir / "trend_history.json"
        if history_file.exists():
            try:
                with open(history_file, "r") as f:
                    self._trend_history = json.load(f)
                logger.info(f"Loaded trend history with {len(self._trend_history)} topics")
            except Exception as e:
                logger.warning(f"Failed to load trend history: {e}")

    def _save_trend_history(self) -> None:
        """Save trend history to disk."""
        history_file = self.cache_dir / "trend_history.json"
        try:
            with open(history_file, "w") as f:
                json.dump(self._trend_history, f)
        except Exception as e:
            logger.warning(f"Failed to save trend history: {e}")

    def _get_paper_id(self, paper: dict) -> str:
        """Get a unique identifier for a paper."""
        if paper.get("doi"):
            return f"doi:{paper['doi']}"
        if paper.get("arxiv_id"):
            return f"arxiv:{paper['arxiv_id']}"
        title = paper.get("title", "")
        return f"title:{hashlib.md5(title.encode()).hexdigest()[:12]}"

    def _parse_date(self, paper: dict) -> datetime:
        """Parse publication date from paper metadata."""
        date_str = paper.get("published_date") or paper.get("publication_date") or paper.get("date")

        if isinstance(date_str, datetime):
            return date_str

        if isinstance(date_str, str):
            for fmt in ["%Y-%m-%d", "%Y-%m", "%Y", "%Y/%m/%d"]:
                try:
                    return datetime.strptime(date_str[:len("2024-01-01")], fmt)
                except ValueError:
                    continue

        # Default to recent date if unparseable
        return datetime.now() - timedelta(days=30)

    async def detect_trending_topics(
        self,
        papers: list[dict],
        time_window_days: int = 30,
        min_papers: int = 5,
        top_k: int = 10,
    ) -> list[TrendingTopic]:
        """Detect trending topics from a collection of papers.

        Args:
            papers: List of paper dictionaries with publication dates
            time_window_days: Time window for trend analysis
            min_papers: Minimum papers required for a topic
            top_k: Number of trending topics to return

        Returns:
            List of trending topics sorted by trend score
        """
        if not papers:
            return []

        now = datetime.now()
        cutoff = now - timedelta(days=time_window_days)

        # Filter to recent papers
        recent_papers = [p for p in papers if self._parse_date(p) >= cutoff]

        if len(recent_papers) < min_papers:
            logger.warning(f"Only {len(recent_papers)} recent papers, need {min_papers}")
            recent_papers = papers[:100]  # Use whatever we have

        # Extract keywords and track their frequency over time
        keyword_timeline = self._build_keyword_timeline(recent_papers, time_window_days)

        # Identify trending keywords
        trending_keywords = self._identify_trending_keywords(keyword_timeline)

        # Cluster papers by trending keywords
        topics = self._cluster_by_keywords(recent_papers, trending_keywords, min_papers)

        # Calculate trend scores
        for topic in topics:
            topic.trend_score = self._calculate_trend_score(topic, keyword_timeline)
            topic.momentum = self._calculate_momentum(topic, keyword_timeline)
            topic.publication_velocity = len(topic.papers) / time_window_days

        # Sort by trend score
        topics.sort(key=lambda t: t.trend_score, reverse=True)

        # Update history
        self._update_trend_history(topics)
        self._save_trend_history()

        return topics[:top_k]

    def _build_keyword_timeline(
        self,
        papers: list[dict],
        time_window_days: int,
    ) -> dict[str, dict[int, int]]:
        """Build a timeline of keyword frequencies.

        Returns:
            Dict mapping keywords to {day_offset: count}
        """
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
            "be", "have", "has", "had", "do", "does", "did", "will", "would",
            "this", "that", "these", "those", "it", "its", "we", "our", "their",
            "using", "based", "new", "novel", "propose", "proposed", "paper",
            "study", "method", "approach", "results", "show", "data", "model",
        }

        keyword_timeline: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        now = datetime.now()

        for paper in papers:
            pub_date = self._parse_date(paper)
            day_offset = (now - pub_date).days

            if day_offset < 0 or day_offset > time_window_days:
                continue

            # Extract keywords from title and abstract
            text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
            words = [w.strip(".,;:!?()[]{}\"'") for w in text.split()]
            words = [w for w in words if len(w) > 3 and w not in stopwords and w.isalpha()]

            # Also extract bigrams
            bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]

            for word in words + bigrams:
                keyword_timeline[word][day_offset] += 1

        return dict(keyword_timeline)

    def _identify_trending_keywords(
        self,
        keyword_timeline: dict[str, dict[int, int]],
        min_total: int = 3,
    ) -> list[tuple[str, float]]:
        """Identify keywords with increasing frequency.

        Returns:
            List of (keyword, growth_rate) sorted by growth rate
        """
        trending = []

        for keyword, timeline in keyword_timeline.items():
            total = sum(timeline.values())
            if total < min_total:
                continue

            # Compare first half to second half
            days = sorted(timeline.keys())
            if not days:
                continue

            mid = len(days) // 2 if len(days) > 1 else 0

            first_half = sum(timeline.get(d, 0) for d in days[:mid]) if mid > 0 else 0
            second_half = sum(timeline.get(d, 0) for d in days[mid:])

            # Calculate growth rate
            if first_half > 0:
                growth_rate = (second_half - first_half) / first_half
            elif second_half > 0:
                growth_rate = 1.0  # New keyword
            else:
                growth_rate = 0

            # Weight by recency (more recent = higher weight)
            recency_bonus = sum(timeline.get(d, 0) * (1 - d/30) for d in timeline.keys()) / total

            score = growth_rate * (1 + recency_bonus)

            if score > 0:
                trending.append((keyword, score))

        return sorted(trending, key=lambda x: x[1], reverse=True)

    def _cluster_by_keywords(
        self,
        papers: list[dict],
        trending_keywords: list[tuple[str, float]],
        min_papers: int,
    ) -> list[TrendingTopic]:
        """Cluster papers around trending keywords to form topics."""
        topics = []
        used_papers: set[str] = set()
        now = datetime.now()

        # Take top keywords as potential topic seeds
        for keyword, growth_rate in trending_keywords[:30]:
            # Find papers containing this keyword
            matching_papers = []
            for paper in papers:
                paper_id = self._get_paper_id(paper)
                if paper_id in used_papers:
                    continue

                text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
                if keyword in text:
                    matching_papers.append(paper)

            if len(matching_papers) < min_papers:
                continue

            # Mark papers as used
            for p in matching_papers:
                used_papers.add(self._get_paper_id(p))

            # Find related keywords
            related_keywords = self._find_related_keywords(matching_papers, keyword)

            # Find first publication date
            dates = [self._parse_date(p) for p in matching_papers]
            first_seen = min(dates) if dates else now

            # Create topic
            topic_id = f"trend_{hashlib.md5(keyword.encode()).hexdigest()[:8]}"

            topic = TrendingTopic(
                topic_id=topic_id,
                name=keyword.title(),
                description=f"Emerging research on {keyword}",
                keywords=[keyword] + related_keywords[:9],
                papers=matching_papers,
                trend_score=0,  # Calculated later
                momentum=growth_rate,
                first_seen=first_seen,
            )
            topics.append(topic)

        return topics

    def _find_related_keywords(
        self,
        papers: list[dict],
        seed_keyword: str,
        top_k: int = 10,
    ) -> list[str]:
        """Find keywords related to a seed keyword within papers."""
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
            "using", "based", "new", "novel", "propose", "proposed", seed_keyword.lower(),
        }

        word_freq: dict[str, int] = defaultdict(int)

        for paper in papers:
            text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
            words = [w.strip(".,;:!?()[]{}\"'") for w in text.split()]
            words = [w for w in words if len(w) > 3 and w not in stopwords and w.isalpha()]

            for word in set(words):
                word_freq[word] += 1

        # Sort by frequency
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)

        return [w for w, _ in sorted_words[:top_k]]

    def _calculate_trend_score(
        self,
        topic: TrendingTopic,
        keyword_timeline: dict[str, dict[int, int]],
    ) -> float:
        """Calculate overall trend score (0-100).

        Score is based on:
        - Publication volume (40%)
        - Growth rate / momentum (30%)
        - Recency of publications (20%)
        - Keyword diversity (10%)
        """
        # Volume score (log-scaled, capped at 50 papers)
        volume_score = min(1.0, np.log1p(len(topic.papers)) / np.log1p(50)) * 40

        # Growth score
        momentum = max(0, min(1, topic.momentum))  # Clamp to [0, 1]
        growth_score = momentum * 30

        # Recency score
        now = datetime.now()
        days_old = [(now - self._parse_date(p)).days for p in topic.papers]
        avg_age = np.mean(days_old) if days_old else 30
        recency_score = max(0, (1 - avg_age / 30)) * 20

        # Keyword diversity score
        diversity_score = min(1.0, len(topic.keywords) / 10) * 10

        return volume_score + growth_score + recency_score + diversity_score

    def _calculate_momentum(
        self,
        topic: TrendingTopic,
        keyword_timeline: dict[str, dict[int, int]],
    ) -> float:
        """Calculate momentum (rate of change in publication frequency)."""
        main_keyword = topic.keywords[0] if topic.keywords else ""
        timeline = keyword_timeline.get(main_keyword, {})

        if len(timeline) < 2:
            return 0.0

        # Linear regression on timeline
        days = sorted(timeline.keys())
        counts = [timeline[d] for d in days]

        if len(days) < 2:
            return 0.0

        # Simple slope calculation
        x = np.array(days)
        y = np.array(counts)

        slope = np.polyfit(x, y, 1)[0]

        # Normalize by average count
        avg = np.mean(y)
        if avg > 0:
            return -slope / avg  # Negative because days are offset from now
        return 0.0

    def _update_trend_history(self, topics: list[TrendingTopic]) -> None:
        """Update trend history with current snapshot."""
        timestamp = datetime.now().isoformat()

        for topic in topics:
            topic_id = topic.topic_id
            if topic_id not in self._trend_history:
                self._trend_history[topic_id] = []

            self._trend_history[topic_id].append({
                "timestamp": timestamp,
                "trend_score": topic.trend_score,
                "paper_count": len(topic.papers),
                "momentum": topic.momentum,
            })

            # Keep only last 30 snapshots
            self._trend_history[topic_id] = self._trend_history[topic_id][-30:]

    async def detect_citation_velocity(
        self,
        papers: list[dict],
        top_k: int = 20,
    ) -> list[RapidlyCitedPaper]:
        """Identify papers gaining citations rapidly.

        Args:
            papers: List of papers with citation counts
            top_k: Number of papers to return

        Returns:
            List of rapidly cited papers sorted by velocity
        """
        results = []
        now = datetime.now()

        for paper in papers:
            pub_date = self._parse_date(paper)
            days_since_pub = max(1, (now - pub_date).days)

            citation_count = paper.get("citation_count", 0) or paper.get("citationCount", 0) or 0

            if citation_count == 0 or days_since_pub > 365:
                continue

            # Calculate velocity (citations per day)
            velocity = citation_count / days_since_pub

            # Get historical velocity if available
            paper_id = self._get_paper_id(paper)
            prev_velocity = self._get_previous_velocity(paper_id)
            acceleration = velocity - prev_velocity if prev_velocity else 0

            # Calculate percentile (simplified - compare against mean velocity)
            # In production, this would use actual percentile data

            result = RapidlyCitedPaper(
                paper_id=paper_id,
                title=paper.get("title", ""),
                authors=[a.get("name", str(a)) if isinstance(a, dict) else str(a)
                         for a in paper.get("authors", [])[:5]],
                published_date=pub_date,
                citation_count=citation_count,
                citation_velocity=velocity,
                citation_acceleration=acceleration,
                percentile=0,  # Calculated below
                paper_data=paper,
            )
            results.append(result)

        # Calculate percentiles
        if results:
            velocities = [r.citation_velocity for r in results]
            for result in results:
                result.percentile = sum(1 for v in velocities if v <= result.citation_velocity) / len(velocities) * 100

        # Sort by velocity
        results.sort(key=lambda x: x.citation_velocity, reverse=True)

        return results[:top_k]

    def _get_previous_velocity(self, paper_id: str) -> Optional[float]:
        """Get previous velocity from history for acceleration calculation."""
        # In production, this would query historical citation data
        return None

    async def generate_trend_report(
        self,
        papers: list[dict],
        user_interests: list[str] = None,
        time_window_days: int = 30,
    ) -> TrendReport:
        """Generate a comprehensive trend report.

        Args:
            papers: List of papers to analyze
            user_interests: User's research interests for filtering
            time_window_days: Analysis time window

        Returns:
            Comprehensive trend report
        """
        user_interests = user_interests or []

        # Detect trending topics
        trending_topics = await self.detect_trending_topics(
            papers, time_window_days=time_window_days
        )

        # Detect rapidly cited papers
        rapidly_cited = await self.detect_citation_velocity(papers)

        # Identify emerging keywords
        keyword_timeline = self._build_keyword_timeline(papers, time_window_days)
        emerging_keywords = self._identify_trending_keywords(keyword_timeline)[:20]

        # Identify declining topics (negative momentum)
        all_topics = await self.detect_trending_topics(papers, min_papers=3, top_k=50)
        declining_topics = [t for t in all_topics if t.momentum < -0.2]
        declining_topics.sort(key=lambda t: t.momentum)

        # Filter topics relevant to user interests
        user_relevant = []
        if user_interests:
            interest_set = set(w.lower() for interest in user_interests for w in interest.split())
            for topic in trending_topics:
                topic_keywords = set(kw.lower() for kw in topic.keywords)
                if interest_set & topic_keywords:
                    user_relevant.append(topic)

        # Generate summary
        summary = await self._generate_trend_summary(
            trending_topics[:5],
            rapidly_cited[:5],
            emerging_keywords[:10],
            user_relevant[:3],
        )

        return TrendReport(
            generated_at=datetime.now(),
            time_window_days=time_window_days,
            trending_topics=trending_topics,
            rapidly_cited_papers=rapidly_cited,
            emerging_keywords=emerging_keywords,
            declining_topics=declining_topics[:5],
            user_relevant_trends=user_relevant,
            summary=summary,
        )

    async def _generate_trend_summary(
        self,
        trending_topics: list[TrendingTopic],
        rapidly_cited: list[RapidlyCitedPaper],
        emerging_keywords: list[tuple[str, float]],
        user_relevant: list[TrendingTopic],
    ) -> str:
        """Generate a natural language summary of trends using LLM."""
        if not self.gemini_api_key:
            # Generate simple summary without LLM
            parts = []

            if trending_topics:
                topics_str = ", ".join(t.name for t in trending_topics[:3])
                parts.append(f"Top trending topics: {topics_str}.")

            if rapidly_cited:
                parts.append(f"Found {len(rapidly_cited)} rapidly-cited papers.")

            if emerging_keywords:
                keywords_str = ", ".join(kw for kw, _ in emerging_keywords[:5])
                parts.append(f"Emerging keywords: {keywords_str}.")

            if user_relevant:
                relevant_str = ", ".join(t.name for t in user_relevant[:3])
                parts.append(f"Relevant to your interests: {relevant_str}.")

            return " ".join(parts) or "No significant trends detected."

        # Use Gemini for summary
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_api_key}"

        prompt = f"""Summarize these research trends in 2-3 sentences for a researcher:

Trending Topics:
{chr(10).join(f"- {t.name}: {len(t.papers)} papers, score {t.trend_score:.1f}" for t in trending_topics[:5])}

Rapidly Cited Papers:
{chr(10).join(f"- {p.title[:60]}... ({p.citation_velocity:.1f} citations/day)" for p in rapidly_cited[:3])}

Emerging Keywords: {', '.join(kw for kw, _ in emerging_keywords[:10])}

Provide a brief, actionable summary highlighting the most important trends and what they mean for research direction."""

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        summary = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if summary:
                            return summary.strip()
            except Exception as e:
                logger.warning(f"Failed to generate trend summary: {e}")

        return "Unable to generate trend summary."

    async def track_topic_evolution(
        self,
        topic_id: str,
        time_range_days: int = 90,
    ) -> dict:
        """Track how a topic has evolved over time.

        Args:
            topic_id: Topic identifier
            time_range_days: Historical range to analyze

        Returns:
            Evolution data including score history and key events
        """
        history = self._trend_history.get(topic_id, [])

        if not history:
            return {
                "topic_id": topic_id,
                "status": "not_found",
                "message": "No historical data for this topic",
            }

        # Extract time series
        timestamps = [h["timestamp"] for h in history]
        scores = [h["trend_score"] for h in history]
        paper_counts = [h["paper_count"] for h in history]
        momentums = [h["momentum"] for h in history]

        # Calculate statistics
        current_score = scores[-1] if scores else 0
        avg_score = np.mean(scores)
        max_score = max(scores)
        min_score = min(scores)

        # Detect peak
        peak_idx = np.argmax(scores)
        peak_date = timestamps[peak_idx]

        # Determine current phase
        if len(scores) >= 3:
            recent_trend = np.mean(scores[-3:]) - np.mean(scores[:3])
            if recent_trend > 5:
                phase = "growing"
            elif recent_trend < -5:
                phase = "declining"
            else:
                phase = "stable"
        else:
            phase = "emerging"

        return {
            "topic_id": topic_id,
            "current_score": current_score,
            "average_score": avg_score,
            "peak_score": max_score,
            "peak_date": peak_date,
            "min_score": min_score,
            "phase": phase,
            "data_points": len(history),
            "score_history": list(zip(timestamps, scores)),
            "paper_count_history": list(zip(timestamps, paper_counts)),
        }

    def find_related_trends(
        self,
        topic: TrendingTopic,
        all_topics: list[TrendingTopic],
        top_k: int = 5,
    ) -> list[TrendingTopic]:
        """Find topics related to a given topic.

        Args:
            topic: Source topic
            all_topics: All available topics
            top_k: Number of related topics to return

        Returns:
            List of related topics
        """
        if not all_topics:
            return []

        source_keywords = set(kw.lower() for kw in topic.keywords)
        scored_topics = []

        for other_topic in all_topics:
            if other_topic.topic_id == topic.topic_id:
                continue

            other_keywords = set(kw.lower() for kw in other_topic.keywords)

            # Calculate Jaccard similarity
            intersection = len(source_keywords & other_keywords)
            union = len(source_keywords | other_keywords)
            similarity = intersection / union if union > 0 else 0

            if similarity > 0:
                scored_topics.append((other_topic, similarity))

        # Sort by similarity
        scored_topics.sort(key=lambda x: x[1], reverse=True)

        return [t for t, _ in scored_topics[:top_k]]

    def export_trends(
        self,
        report: TrendReport,
        format: str = "json",
    ) -> str:
        """Export trend report in various formats.

        Args:
            report: Trend report to export
            format: Export format ("json", "csv", "html")

        Returns:
            Serialized report
        """
        if format == "json":
            return json.dumps(report.to_dict(), indent=2)

        elif format == "csv":
            lines = ["topic_id,name,trend_score,momentum,paper_count,keywords"]
            for topic in report.trending_topics:
                keywords_str = ";".join(topic.keywords[:5])
                lines.append(f"{topic.topic_id},{topic.name},{topic.trend_score:.2f},{topic.momentum:.3f},{len(topic.papers)},{keywords_str}")
            return "\n".join(lines)

        elif format == "html":
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Research Trend Report - {report.generated_at.strftime('%Y-%m-%d')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        .topic {{ border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 8px; }}
        .score {{ font-size: 24px; color: #2196F3; }}
        .keywords {{ color: #666; }}
        h1 {{ color: #333; }}
        h2 {{ color: #555; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
    </style>
</head>
<body>
    <h1>Research Trend Report</h1>
    <p>Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M')}</p>
    <p><strong>Summary:</strong> {report.summary}</p>

    <h2>Trending Topics</h2>
"""
            for topic in report.trending_topics[:10]:
                html += f"""    <div class="topic">
        <h3>{topic.name}</h3>
        <div class="score">Score: {topic.trend_score:.1f}</div>
        <p>{len(topic.papers)} papers | Momentum: {topic.momentum:+.2f}</p>
        <p class="keywords">Keywords: {', '.join(topic.keywords[:5])}</p>
    </div>
"""

            html += """
    <h2>Rapidly Cited Papers</h2>
    <ul>
"""
            for paper in report.rapidly_cited_papers[:10]:
                html += f"""        <li><strong>{paper.title[:80]}...</strong><br>
            {paper.citation_velocity:.1f} citations/day | {paper.citation_count} total</li>
"""
            html += """    </ul>
</body>
</html>"""
            return html

        else:
            raise ValueError(f"Unknown export format: {format}")
