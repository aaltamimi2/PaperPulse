# PaperPulse Overhaul - Comprehensive Implementation Plan

## Executive Summary

The PaperPulse codebase is a well-architected Python application for AI-powered academic paper recommendations. The existing foundation includes:

**Current Tech Stack:**
- Python 3.11+ with asyncio
- SQLAlchemy 2.0 with asyncpg for PostgreSQL
- pgvector for embedding storage
- Google Gemini API for embeddings
- Jinja2 for email templates
- Typer/Rich for CLI
- feedparser for RSS collection
- Pydantic for configuration

**Existing Features:**
- RSS feed collection (ACS journals supported)
- Multi-criteria scoring pipeline (semantic, keyword, author, novelty)
- Email digest generation and sending
- User/research profile database models
- Embedding service with Gemini integration

**What Needs to be Built:**
1. Expanded literature discovery APIs (Semantic Scholar, PubMed, arXiv)
2. Enhanced relevance metrics (citation metrics, recency weighting, TF-IDF)
3. User profile management API
4. Automated scheduling system
5. Personalized email campaigns

---

## Architecture Overview

```
paperpulse/
├── api/                    # FastAPI REST endpoints (NEW)
│   ├── __init__.py
│   ├── main.py             # FastAPI app
│   ├── routes/
│   │   ├── users.py        # User management
│   │   ├── profiles.py     # Research profile CRUD
│   │   ├── papers.py       # Paper search/browse
│   │   └── digests.py      # Digest management
│   └── deps.py             # Dependencies
├── collectors/             # Literature discovery (ENHANCED)
│   ├── base.py             # BaseCollector interface
│   ├── rss_collector.py    # Existing RSS
│   ├── semantic_scholar.py # NEW: Semantic Scholar API
│   ├── pubmed.py           # NEW: PubMed/Entrez API
│   ├── arxiv.py            # NEW: arXiv API
│   └── aggregator.py       # NEW: Multi-source aggregation
├── scoring/                # Relevance metrics (ENHANCED)
│   ├── base.py
│   ├── embeddings.py
│   ├── scorers.py          # ENHANCED with new metrics
│   ├── pipeline.py
│   ├── citations.py        # NEW: Citation-based scoring
│   └── tfidf.py            # NEW: TF-IDF scoring
├── email/                  # Email system (ENHANCED)
│   ├── models.py
│   ├── templates.py
│   ├── service.py          # ENHANCED personalization
│   └── campaigns.py        # NEW: Email campaigns
├── scheduler/              # NEW: Scheduling system
│   ├── __init__.py
│   ├── tasks.py            # Celery/APScheduler tasks
│   └── jobs.py             # Job definitions
├── db/
│   └── models/             # ENHANCED with new tables
│       ├── digest_log.py   # NEW: Track sent digests
│       └── paper_score.py  # NEW: Cache paper scores
└── core/
    └── config.py           # ENHANCED settings
```

---

## Phase 1: Literature Discovery APIs

### 1.1 Semantic Scholar Collector

```python
# src/paperpulse/collectors/semantic_scholar.py
"""
Semantic Scholar API integration.
https://api.semanticscholar.org/api-docs/

Key features:
- Paper search by keywords/topics
- Author information
- Citation metrics (influentialCitationCount, citationVelocity)
- References/citations graph
"""

@dataclass
class SemanticScholarConfig:
    api_key: Optional[str] = None  # Optional for higher rate limits
    base_url: str = "https://api.semanticscholar.org/graph/v1"
    rate_limit: int = 100  # requests per 5 minutes (unauthenticated)
    fields: list[str] = field(default_factory=lambda: [
        "paperId", "title", "abstract", "authors", "year",
        "citationCount", "influentialCitationCount", "venue",
        "publicationDate", "externalIds", "s2FieldsOfStudy"
    ])

class SemanticScholarCollector(BaseCollector):
    async def search_papers(
        self,
        query: str,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        limit: int = 100,
    ) -> list[CollectedPaper]:
        """Search papers by query with filters."""

    async def get_author_papers(
        self,
        author_id: str,
        limit: int = 50,
    ) -> list[CollectedPaper]:
        """Get recent papers by a specific author."""

    async def get_recommendations(
        self,
        paper_ids: list[str],
        limit: int = 20,
    ) -> list[CollectedPaper]:
        """Get paper recommendations based on a set of papers."""
```

### 1.2 PubMed Collector

```python
# src/paperpulse/collectors/pubmed.py
"""
PubMed/NCBI Entrez API integration.
Uses Biopython's Entrez module.

Key features:
- MeSH term search
- Date-range filtering
- Abstract retrieval
"""

class PubMedCollector(BaseCollector):
    async def search_papers(
        self,
        query: str,
        mesh_terms: Optional[list[str]] = None,
        days_back: int = 30,
        limit: int = 100,
    ) -> list[CollectedPaper]:
        """Search PubMed with Entrez."""
```

### 1.3 arXiv Collector

```python
# src/paperpulse/collectors/arxiv.py
"""
arXiv API integration using the arxiv package.

Key features:
- Category-based search (cs.AI, physics.chem-ph, etc.)
- Date filtering
- Full text PDF access
"""

class ArxivCollector(BaseCollector):
    async def search_papers(
        self,
        query: str,
        categories: Optional[list[str]] = None,
        days_back: int = 30,
        limit: int = 100,
    ) -> list[CollectedPaper]:
        """Search arXiv by query and categories."""
```

### 1.4 Multi-Source Aggregator

```python
# src/paperpulse/collectors/aggregator.py
"""
Aggregate papers from multiple sources with deduplication.
"""

class PaperAggregator:
    def __init__(
        self,
        collectors: list[BaseCollector],
        deduplication_strategy: str = "doi_first",
    ):
        self.collectors = collectors

    async def collect_all(
        self,
        query: str,
        **filters,
    ) -> list[CollectedPaper]:
        """Collect from all sources and deduplicate."""

    def deduplicate(
        self,
        papers: list[CollectedPaper],
    ) -> list[CollectedPaper]:
        """Remove duplicate papers using DOI, title similarity."""
```

---

## Phase 2: Enhanced Relevance Metrics

### 2.1 Citation-Based Scorer

```python
# src/paperpulse/scoring/citations.py
"""
Citation-based relevance scoring.
"""

class CitationScorer(BaseScorer):
    name = "citation"
    default_weight = 0.15

    # Impact factor ranges for normalization
    HIGH_CITATION_THRESHOLD = 50
    VELOCITY_BOOST = 2.0  # Papers cited frequently in recent years

    async def score(self, context: ScoringContext) -> ScoreResult:
        """
        Score based on:
        - Total citation count (normalized by field average)
        - Influential citation count (highly weighted)
        - Citation velocity (recent citations)
        - H-index of authors
        """
```

### 2.2 Recency Scorer

```python
# src/paperpulse/scoring/recency.py
"""
Recency-based scoring with exponential decay.
"""

class RecencyScorer(BaseScorer):
    name = "recency"
    default_weight = 0.1

    def __init__(
        self,
        decay_half_life_days: int = 30,
        max_age_days: int = 365,
    ):
        self.decay_half_life = decay_half_life_days

    async def score(self, context: ScoringContext) -> ScoreResult:
        """
        Score with exponential decay:
        score = exp(-0.693 * age_days / half_life)
        """
```

### 2.3 TF-IDF Scorer

```python
# src/paperpulse/scoring/tfidf.py
"""
TF-IDF based keyword matching for better precision.
"""

from sklearn.feature_extraction.text import TfidfVectorizer

class TFIDFScorer(BaseScorer):
    name = "tfidf"
    default_weight = 0.15

    def __init__(self, corpus_size: int = 10000):
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2),
            stop_words="english",
        )
        self._fitted = False

    async def fit_corpus(self, papers: list[dict]) -> None:
        """Fit TF-IDF on paper corpus."""

    async def score(self, context: ScoringContext) -> ScoreResult:
        """Score using TF-IDF cosine similarity."""
```

### 2.4 Updated Scoring Pipeline

```python
# Update src/paperpulse/scoring/pipeline.py

@dataclass
class ScoringConfig:
    # Updated weights (must sum to 1.0)
    weight_semantic: float = 0.30      # Reduced from 0.4
    weight_keyword: float = 0.15       # Reduced from 0.3
    weight_author: float = 0.15        # Reduced from 0.2
    weight_novelty: float = 0.10       # Same
    weight_citation: float = 0.15      # NEW
    weight_recency: float = 0.10       # NEW
    weight_tfidf: float = 0.05         # NEW
```

---

## Phase 3: User Profile Management

### 3.1 FastAPI Application

```python
# src/paperpulse/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="PaperPulse API",
    description="AI-powered academic paper recommendations",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
from paperpulse.api.routes import users, profiles, papers, digests

app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(profiles.router, prefix="/api/v1/profiles", tags=["profiles"])
app.include_router(papers.router, prefix="/api/v1/papers", tags=["papers"])
app.include_router(digests.router, prefix="/api/v1/digests", tags=["digests"])
```

### 3.2 User Management Routes

```python
# src/paperpulse/api/routes/users.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

router = APIRouter()

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    email_verified: bool
    digest_enabled: bool
    immediate_alerts_enabled: bool

@router.post("/", response_model=UserResponse)
async def create_user(user: UserCreate):
    """Create a new user account."""

@router.get("/me", response_model=UserResponse)
async def get_current_user(user = Depends(get_current_user)):
    """Get current user profile."""

@router.patch("/me/preferences")
async def update_preferences(
    digest_enabled: Optional[bool] = None,
    immediate_alerts_enabled: Optional[bool] = None,
):
    """Update email preferences."""
```

### 3.3 Research Profile Routes

```python
# src/paperpulse/api/routes/profiles.py
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class InterestCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    keywords: list[str] = []
    excluded_keywords: list[str] = []
    followed_authors: list[str] = []
    followed_journals: list[str] = []
    weight_semantic: float = 0.3
    weight_keyword: float = 0.15
    weight_citation: float = 0.15
    weight_recency: float = 0.1

class ResearchProfileCreate(BaseModel):
    name: str
    description: Optional[str] = None
    interests: list[InterestCategoryCreate] = []

@router.post("/", response_model=ResearchProfileResponse)
async def create_profile(profile: ResearchProfileCreate):
    """Create a new research profile."""

@router.get("/", response_model=list[ResearchProfileResponse])
async def list_profiles():
    """List all research profiles for current user."""

@router.put("/{profile_id}/interests/{interest_id}")
async def update_interest(
    profile_id: str,
    interest_id: str,
    interest: InterestCategoryCreate,
):
    """Update an interest category."""

@router.post("/{profile_id}/generate-embedding")
async def generate_profile_embedding(profile_id: str):
    """Generate/update embeddings for a research profile."""
```

---

## Phase 4: Scheduling System

### 4.1 APScheduler Integration

```python
# src/paperpulse/scheduler/__init__.py
"""
Scheduling system using APScheduler.
Alternative: Celery + Redis for distributed workloads.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

scheduler = AsyncIOScheduler()

def init_scheduler():
    """Initialize and start the scheduler."""
    from paperpulse.scheduler.jobs import (
        collect_papers_job,
        generate_digests_job,
        send_immediate_alerts_job,
        update_embeddings_job,
    )

    # Collect papers every 6 hours
    scheduler.add_job(
        collect_papers_job,
        IntervalTrigger(hours=6),
        id="collect_papers",
        name="Collect papers from all sources",
    )

    # Generate and send weekly digests (Sunday 8am)
    scheduler.add_job(
        generate_digests_job,
        CronTrigger(day_of_week="sun", hour=8),
        id="weekly_digest",
        name="Generate weekly digests",
        kwargs={"digest_type": "weekly"},
    )

    # Check for immediate alerts every hour
    scheduler.add_job(
        send_immediate_alerts_job,
        IntervalTrigger(hours=1),
        id="immediate_alerts",
        name="Check and send immediate alerts",
    )

    # Update embeddings daily
    scheduler.add_job(
        update_embeddings_job,
        CronTrigger(hour=2),
        id="update_embeddings",
        name="Update paper and profile embeddings",
    )

    scheduler.start()
```

### 4.2 Job Definitions

```python
# src/paperpulse/scheduler/jobs.py

async def collect_papers_job():
    """Collect papers from all configured sources."""
    from paperpulse.collectors.aggregator import PaperAggregator
    from paperpulse.db import get_session

    aggregator = PaperAggregator([
        RSSCollector(),
        SemanticScholarCollector(),
        ArxivCollector(),
    ])

    # Get active feeds and queries
    async with get_session() as session:
        feeds = await get_active_feeds(session)

    for feed in feeds:
        papers = await aggregator.collect_all(feed.query)
        await save_papers(papers)

async def generate_digests_job(digest_type: str = "weekly"):
    """Generate digests for all users with enabled preferences."""
    from paperpulse.db import get_session

    async with get_session() as session:
        users = await get_users_with_digest_enabled(session, digest_type)

    for user in users:
        digest = await generate_user_digest(user)
        await send_digest_email(user, digest)
        await log_digest_sent(user, digest)

async def send_immediate_alerts_job():
    """Check for high-priority papers and send alerts."""
    from paperpulse.scoring import ScoringPipeline

    # Get papers from last hour
    recent_papers = await get_recent_papers(hours=1)

    for user in await get_alert_enabled_users():
        for profile in user.research_profiles:
            scored = await score_papers_for_profile(recent_papers, profile)
            immediate = [p for p in scored if p.priority == "immediate"]

            if immediate:
                await send_immediate_alert(user, immediate)
```

### 4.3 Database Models for Tracking

```python
# src/paperpulse/db/models/digest_log.py
"""Track sent digests for analytics and debugging."""

class DigestLog(Base, UUIDMixin, TimestampMixin):
    """Log of sent digest emails."""

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    digest_type: Mapped[str] = mapped_column(String(20))  # weekly, daily, immediate
    papers_included: Mapped[int] = mapped_column(Integer)
    sections_included: Mapped[int] = mapped_column(Integer)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    email_status: Mapped[str] = mapped_column(String(20))  # sent, failed, bounced
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    clicked_links: Mapped[int] = mapped_column(Integer, default=0)
```

---

## Phase 5: Personalized Email Campaigns

### 5.1 Enhanced Email Service

```python
# src/paperpulse/email/campaigns.py
"""
Email campaign management for personalized communications.
"""

class EmailCampaign:
    """Manage email campaigns with personalization."""

    async def create_personalized_digest(
        self,
        user: User,
        papers: list[Paper],
    ) -> Digest:
        """Create a fully personalized digest."""

        # Score papers for each interest
        scored_papers = {}
        for profile in user.research_profiles:
            for interest in profile.interest_categories:
                scored = await self.scoring_pipeline.score_papers(
                    papers, interest.to_profile_dict()
                )
                scored_papers[interest.name] = scored

        # Generate AI summaries for top papers
        for interest_name, papers in scored_papers.items():
            for paper, score in papers[:5]:  # Top 5
                if paper.get("summary") is None:
                    paper["summary"] = await self.generate_summary(paper)
                    paper["why_relevant"] = await self.generate_relevance_explanation(
                        paper, interest_name
                    )

        return self.build_digest(user, scored_papers)

    async def generate_summary(self, paper: dict) -> str:
        """Generate AI summary using Gemini."""
        prompt = f"""
        Summarize this academic paper in 2-3 sentences for a researcher:

        Title: {paper['title']}
        Abstract: {paper.get('abstract', 'N/A')}
        """
        return await self.gemini_client.generate(prompt)

    async def generate_relevance_explanation(
        self,
        paper: dict,
        interest_name: str,
    ) -> str:
        """Explain why paper is relevant to user's interest."""
        prompt = f"""
        Explain in 1-2 sentences why this paper is relevant to someone
        interested in "{interest_name}":

        Title: {paper['title']}
        Abstract: {paper.get('abstract', 'N/A')}
        """
        return await self.gemini_client.generate(prompt)
```

### 5.2 Email Templates Enhancement

Add new templates for:
- Welcome email
- Immediate alerts
- Weekly digest (enhanced with AI summaries)
- Profile setup guide
- Unsubscribe confirmation

---

## Database Migrations

```python
# alembic/versions/002_overhaul_schema.py
"""
Add new tables and columns for the overhaul.
"""

def upgrade() -> None:
    # Add citation metrics to papers
    op.add_column("papers", sa.Column("citation_count", sa.Integer()))
    op.add_column("papers", sa.Column("influential_citations", sa.Integer()))
    op.add_column("papers", sa.Column("semantic_scholar_id", sa.String(20)))
    op.add_column("papers", sa.Column("pubmed_id", sa.String(20)))
    op.add_column("papers", sa.Column("arxiv_id", sa.String(20)))
    op.add_column("papers", sa.Column("source_type", sa.String(20)))  # rss, semantic_scholar, pubmed, arxiv

    # Create digest_logs table
    op.create_table(
        "digest_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("digest_type", sa.String(20), nullable=False),
        sa.Column("papers_included", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email_status", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create paper_scores cache table
    op.create_table(
        "paper_scores",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("paper_id", sa.UUID(), nullable=False),
        sa.Column("interest_category_id", sa.UUID(), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=False),
        sa.Column("component_scores", sa.JSON(), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.ForeignKeyConstraint(["interest_category_id"], ["interest_categorys.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_scores_paper_interest", "paper_scores", ["paper_id", "interest_category_id"])

    # Add digest schedule preferences to users
    op.add_column("users", sa.Column("digest_frequency", sa.String(20), server_default="weekly"))
    op.add_column("users", sa.Column("digest_day", sa.Integer(), server_default="0"))  # 0=Sunday
    op.add_column("users", sa.Column("digest_hour", sa.Integer(), server_default="8"))
    op.add_column("users", sa.Column("timezone", sa.String(50), server_default="UTC"))
```

---

## Configuration Updates

```bash
# Update .env.example

# Semantic Scholar API (optional, increases rate limits)
SEMANTIC_SCHOLAR_API_KEY=

# PubMed/NCBI (required for PubMed access)
NCBI_EMAIL=your-email@example.com
NCBI_API_KEY=your-ncbi-api-key

# arXiv (no key needed, but configure)
ARXIV_MAX_RESULTS=100

# Scheduling
SCHEDULER_ENABLED=true
DIGEST_WEEKLY_DAY=sunday
DIGEST_WEEKLY_HOUR=8

# Google API (existing, with new key)
GEMINI_API_KEY=AIzaSyAOkP57wd-1RjTeJ6GdebznbzncYFBHwqA
```

---

## New Dependencies

```toml
# Add to pyproject.toml

dependencies = [
    # Existing...

    # New collectors
    "arxiv>=2.1.0",        # arXiv API client
    "biopython>=1.83",      # PubMed/Entrez access

    # Enhanced scoring
    "scikit-learn>=1.4.0",  # TF-IDF vectorization

    # Scheduling
    "apscheduler>=3.10.0",  # Task scheduling

    # API
    "fastapi>=0.109.0",
    "uvicorn>=0.27.0",
    "python-jose[cryptography]>=3.3.0",  # JWT tokens
    "passlib[bcrypt]>=1.7.4",            # Password hashing
]
```

---

## CLI Updates

```python
# Add to src/paperpulse/cli.py

# Scheduler commands
scheduler_app = typer.Typer(help="Scheduler operations")
app.add_typer(scheduler_app, name="scheduler")

@scheduler_app.command("start")
def start_scheduler():
    """Start the background scheduler."""
    from paperpulse.scheduler import init_scheduler
    init_scheduler()
    # Keep running
    asyncio.get_event_loop().run_forever()

@scheduler_app.command("run-job")
def run_job(job_name: str):
    """Manually run a scheduled job."""
    jobs = {
        "collect": collect_papers_job,
        "digest": generate_digests_job,
        "alerts": send_immediate_alerts_job,
    }
    if job_name in jobs:
        asyncio.run(jobs[job_name]())

# API commands
api_app = typer.Typer(help="API server")
app.add_typer(api_app, name="api")

@api_app.command("serve")
def serve_api(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
):
    """Start the FastAPI server."""
    import uvicorn
    uvicorn.run(
        "paperpulse.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )
```

---

## Implementation Phases

| Phase | Deliverables |
|-------|--------------|
| 1 | Semantic Scholar, PubMed, arXiv collectors + aggregator |
| 2 | Citation, recency, TF-IDF scorers + updated pipeline |
| 3 | FastAPI app + user/profile management endpoints |
| 4 | APScheduler integration + job definitions |
| 5 | Enhanced email campaigns + AI summaries |
| 6 | Testing, documentation, deployment |

---

## Critical Files for Implementation

- `src/paperpulse/collectors/base.py` - Base collector interface to extend for new APIs
- `src/paperpulse/scoring/pipeline.py` - Scoring pipeline to integrate new scorers
- `src/paperpulse/email/service.py` - Email service to enhance with personalization
- `src/paperpulse/db/models/user.py` - User models to extend with new preferences
- `src/paperpulse/core/config.py` - Configuration to add new API keys and settings
