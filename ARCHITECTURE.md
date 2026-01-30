# PaperPulse Architecture & Roadmap

## Current System Overview

PaperPulse is an AI-powered academic paper recommendation system with the following capabilities:

### Tech Stack
| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ with asyncio |
| AI/Embeddings | Google Gemini API |
| Email | Jinja2 templates + SMTP |
| Scheduling | Cron jobs |

### Module Structure
```
src/paperpulse/
├── collectors/        # Paper collection (arXiv, PubMed, Semantic Scholar, RSS)
├── scoring/           # Multi-criteria relevance scoring
├── email/             # Digest generation and delivery
├── api/               # FastAPI feedback server
├── profile.py         # User profile management
├── feedback.py        # Read/rating tracking
└── history.py         # Sent paper deduplication
```

### Data Flow
```
1. COLLECTION: ArXiv + PubMed + RSS → Deduplicate → Paper list

2. SCORING (weighted average):
   ├── Semantic (30%) - Gemini embedding similarity
   ├── Keyword (15%) - Term matching with sqrt scaling
   ├── Author (15%) - Followed author detection
   ├── Citation (15%) - Impact metrics
   ├── Recency (10%) - Publication date decay
   ├── TF-IDF (5%) - Term frequency similarity
   ├── Field of Study (5%) - Field overlap
   └── Novelty (5%) - Novel method indicators

3. DIGEST: Score papers → AI summaries → HTML email → Send

4. FEEDBACK: Read/👍/👎 buttons → feedback.json → Future tuning
```

### Current Features
- ✅ Multi-source paper collection (arXiv, PubMed, Semantic Scholar)
- ✅ AI-powered relevance scoring with 8 weighted scorers
- ✅ Gemini AI summaries and "Why this matters" explanations
- ✅ Beautiful HTML email digests
- ✅ Daily 6am digest + Saturday 9am wrap-up
- ✅ Never-repeat paper deduplication
- ✅ Feedback buttons (Read, 👍, 👎)
- ✅ Followed authors with persistent profiles
- ✅ Suggested authors from relevant papers

---

## Proposed Enhancements

### Priority 1: Paper Similarity & Citation Networks 🔗

**Find Similar Papers**
```python
class PaperSimilarityService:
    async def find_similar_by_embedding(paper_id, limit=20)
    async def find_similar_by_citations(paper_id)  # Papers citing same works
    async def find_similar_by_authors(paper_id)    # Same author papers
    async def find_similar_combined(paper_id, weights)
```

**Citation Network Graph**
```python
class CitationNetworkService:
    async def build_network_from_paper(seed_id, depth=2)
    async def find_influential_papers(graph, algorithm="pagerank")
    async def find_research_fronts(graph)  # Clusters of citing papers
    async def export_for_visualization(graph, format="json")
```

**Data source**: Semantic Scholar API has `references` and `citations` endpoints

### Priority 2: Topic Clustering & Trends 📊

**Cluster Papers by Topic**
```python
class TopicClusteringService:
    async def cluster_by_embedding(paper_ids, n_clusters=10)
    async def discover_topics_lda(paper_ids, n_topics=10)
    async def label_clusters(clusters)  # LLM-generated labels
```

**Detect Emerging Trends**
```python
class TrendDetectionService:
    async def detect_trending_topics(time_window_days=30)
    async def detect_citation_velocity(papers)  # Rapidly cited papers
    async def generate_trend_report(user_interests)
```

### Priority 3: Reading List Management 📚

```python
class ReadingList:
    user_id: str
    name: str
    papers: list[ReadingListItem]  # status: to_read, reading, finished

# API: /api/v1/reading-lists
```

### Priority 4: Reference Manager Integration 📖

```python
class ZoteroIntegration:
    async def export_reading_list(list_id, zotero_api_key)
    async def sync_library(user_id, direction="both")

class BibTeXExporter:
    def export_papers(papers) -> str
```

### Priority 5: Citation Alerts 🔔

```python
class CitationAlertService:
    async def register_user_papers(user_id, dois)  # Your publications
    async def check_new_citations(user_id)
    async def send_citation_alert(user_id, new_citations)
```

### Priority 6: Enhanced Author Following 👤

```python
class AuthorAlertService:
    async def resolve_author_id(name) -> semantic_scholar_id
    async def sync_author_papers(author_id)
    async def check_followed_authors(user_id)  # New papers alert
```

### Priority 7: Semantic Search 🔍

```python
class SemanticSearchService:
    async def search(query, mode="hybrid")  # keyword + semantic
    async def search_by_example(example_text)  # Find similar to paste
```

---

## Implementation Roadmap

### Phase 1: Paper Relationships (High Priority)
1. Add citations table to track paper relationships
2. Implement Semantic Scholar citations fetching
3. Build `PaperSimilarityService`
4. Add `/api/papers/{id}/similar` endpoint
5. Create basic citation graph builder

### Phase 2: Organization (Medium Priority)
1. Implement reading lists
2. Add BibTeX/RIS export
3. Basic Zotero integration

### Phase 3: Discovery (Medium Priority)
1. Topic clustering with embeddings
2. Trend detection
3. Enhanced semantic search

### Phase 4: Alerts (Lower Priority)
1. Citation alerts for user's papers
2. Enhanced author following
3. Conference deadline tracking

---

## File Locations

| Purpose | File |
|---------|------|
| Paper collection | `src/paperpulse/collectors/` |
| Scoring pipeline | `src/paperpulse/scoring/pipeline.py` |
| Embeddings | `src/paperpulse/scoring/embeddings.py` |
| Email templates | `src/paperpulse/email/templates.py` |
| Feedback tracking | `src/paperpulse/feedback.py` |
| Daily digest | `scripts/daily_digest.py` |
| Saturday wrap-up | `scripts/saturday_wrapup.py` |
| Profile management | `scripts/manage_profile.py` |

---

## Configuration

**Environment Variables** (`.env`):
```
GEMINI_API_KEY=...          # For embeddings and summaries
EMAIL_SMTP_USER=...         # Gmail address
EMAIL_SMTP_PASSWORD=...     # Gmail app password
FEEDBACK_URL=...            # Feedback server URL (for email buttons)
```

**User Profile** (`~/.paperpulse/profile.json`):
```json
{
  "followed_authors": ["Author Name", ...],
  "interests": []
}
```

**Tracking Files**:
- `~/.paperpulse/sent_papers.json` - Paper deduplication
- `~/.paperpulse/feedback.json` - Read status and ratings
