"""Topic clustering and trend detection API routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["clustering"])


# ==================== Request/Response Models ====================

class ClusterRequest(BaseModel):
    """Request for clustering papers."""

    papers: list[dict] = Field(..., description="List of papers to cluster")
    n_clusters: Optional[int] = Field(
        default=None,
        description="Number of clusters (auto if not specified)",
    )
    method: str = Field(
        default="embedding",
        description="Clustering method: embedding, lda, hybrid",
    )
    label_clusters: bool = Field(
        default=True,
        description="Whether to generate LLM labels for clusters",
    )


class ClusterResponse(BaseModel):
    """A topic cluster."""

    cluster_id: str
    label: str
    description: str
    paper_count: int
    keywords: list[str]
    coherence_score: float
    paper_ids: list[str]


class ClusteringResultResponse(BaseModel):
    """Full clustering result."""

    method: str
    n_papers: int
    n_clusters: int
    n_unclustered: int
    silhouette_score: Optional[float]
    clusters: list[ClusterResponse]


class TrendingTopicResponse(BaseModel):
    """A trending topic."""

    topic_id: str
    name: str
    description: str
    keywords: list[str]
    paper_count: int
    trend_score: float
    momentum: float
    publication_velocity: float


class RapidlyCitedPaperResponse(BaseModel):
    """A rapidly cited paper."""

    paper_id: str
    title: str
    authors: list[str]
    citation_count: int
    citation_velocity: float
    percentile: float


class TrendReportRequest(BaseModel):
    """Request for generating a trend report."""

    papers: list[dict] = Field(..., description="Papers to analyze")
    user_interests: list[str] = Field(
        default=[],
        description="User's research interests for filtering",
    )
    time_window_days: int = Field(default=30, ge=7, le=365)


class TrendReportResponse(BaseModel):
    """Trend report response."""

    time_window_days: int
    summary: str
    trending_topics: list[TrendingTopicResponse]
    rapidly_cited_papers: list[RapidlyCitedPaperResponse]
    emerging_keywords: list[tuple[str, float]]
    user_relevant_trends: list[TrendingTopicResponse]


# ==================== Clustering Endpoints ====================

@router.post("/cluster", response_model=ClusteringResultResponse)
async def cluster_papers(request: ClusterRequest):
    """Cluster papers into topical groups.

    Methods:
    - **embedding**: K-Means clustering on paper embeddings
    - **lda**: Latent Dirichlet Allocation topic modeling
    - **hybrid**: Combines embedding clusters with LDA keywords
    """
    from paperpulse.clustering import TopicClusteringService

    service = TopicClusteringService()

    try:
        if request.method == "embedding":
            result = await service.cluster_by_embedding(
                papers=request.papers,
                n_clusters=request.n_clusters,
            )
        elif request.method == "lda":
            result = await service.discover_topics_lda(
                papers=request.papers,
                n_topics=request.n_clusters or 10,
            )
        elif request.method == "hybrid":
            result = await service.cluster_hybrid(
                papers=request.papers,
                n_clusters=request.n_clusters,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown clustering method: {request.method}",
            )

        # Optionally generate LLM labels
        if request.label_clusters:
            result = await service.label_clusters(result)

        return ClusteringResultResponse(
            method=result.method,
            n_papers=result.n_papers,
            n_clusters=result.n_clusters,
            n_unclustered=len(result.unclustered_papers),
            silhouette_score=result.silhouette_score,
            clusters=[
                ClusterResponse(
                    cluster_id=c.cluster_id,
                    label=c.label,
                    description=c.description,
                    paper_count=c.size,
                    keywords=c.keywords,
                    coherence_score=c.coherence_score,
                    paper_ids=[
                        p.get("doi") or p.get("arxiv_id") or p.get("title", "")[:50]
                        for p in c.papers
                    ],
                )
                for c in result.clusters
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cluster/assign")
async def assign_to_cluster(
    paper: dict,
    clusters: list[dict],
    threshold: float = Query(default=0.5, ge=0, le=1),
):
    """Assign a new paper to an existing cluster."""
    from paperpulse.clustering import TopicCluster, TopicClusteringService

    service = TopicClusteringService()

    try:
        # Convert cluster dicts to TopicCluster objects
        topic_clusters = [
            TopicCluster(
                cluster_id=c["cluster_id"],
                label=c["label"],
                description=c.get("description", ""),
                papers=[],
                keywords=c.get("keywords", []),
            )
            for c in clusters
        ]

        matched = service.assign_paper_to_cluster(paper, topic_clusters, threshold)

        if matched:
            return {
                "assigned": True,
                "cluster_id": matched.cluster_id,
                "cluster_label": matched.label,
            }
        else:
            return {
                "assigned": False,
                "message": "Paper did not match any cluster above threshold",
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cluster/export/{format}")
async def export_clusters(
    format: str,
    clusters: str = Query(..., description="JSON-encoded clustering result"),
):
    """Export clustering result in various formats.

    Formats:
    - **json**: Full JSON export
    - **csv**: CSV with cluster assignments
    - **d3**: D3.js-compatible nodes and links
    """
    import json

    from fastapi.responses import PlainTextResponse

    from paperpulse.clustering import ClusteringResult, TopicClusteringService

    service = TopicClusteringService()

    try:
        # Parse the clustering result
        data = json.loads(clusters)

        if format == "json":
            return data
        elif format == "csv":
            lines = ["cluster_id,cluster_label,paper_id,paper_title"]
            for cluster in data.get("clusters", []):
                for paper_id in cluster.get("paper_ids", []):
                    lines.append(f"{cluster['cluster_id']},{cluster['label']},{paper_id},")
            return PlainTextResponse(content="\n".join(lines), media_type="text/csv")
        elif format == "d3":
            # Build D3.js format
            nodes = []
            links = []

            for cluster in data.get("clusters", []):
                nodes.append({
                    "id": cluster["cluster_id"],
                    "label": cluster["label"],
                    "type": "cluster",
                    "size": cluster.get("paper_count", 0),
                })

                for paper_id in cluster.get("paper_ids", []):
                    nodes.append({
                        "id": paper_id,
                        "type": "paper",
                    })
                    links.append({
                        "source": cluster["cluster_id"],
                        "target": paper_id,
                    })

            return {"nodes": nodes, "links": links}
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown format: {format}. Use json, csv, or d3.",
            )
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in clusters parameter")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Trend Detection Endpoints ====================

@router.post("/trends", response_model=list[TrendingTopicResponse])
async def detect_trending_topics(
    papers: list[dict],
    time_window_days: int = Query(default=30, ge=7, le=365),
    min_papers: int = Query(default=5, ge=2),
    top_k: int = Query(default=10, ge=1, le=50),
):
    """Detect trending topics from a collection of papers.

    Analyzes publication patterns to identify emerging research areas.
    """
    from paperpulse.clustering import TrendDetectionService

    service = TrendDetectionService()

    try:
        topics = await service.detect_trending_topics(
            papers=papers,
            time_window_days=time_window_days,
            min_papers=min_papers,
            top_k=top_k,
        )

        return [
            TrendingTopicResponse(
                topic_id=t.topic_id,
                name=t.name,
                description=t.description,
                keywords=t.keywords,
                paper_count=len(t.papers),
                trend_score=t.trend_score,
                momentum=t.momentum,
                publication_velocity=t.publication_velocity,
            )
            for t in topics
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trends/citation-velocity", response_model=list[RapidlyCitedPaperResponse])
async def detect_citation_velocity(
    papers: list[dict],
    top_k: int = Query(default=20, ge=1, le=100),
):
    """Identify papers that are gaining citations rapidly.

    Returns papers sorted by citation velocity (citations per day).
    """
    from paperpulse.clustering import TrendDetectionService

    service = TrendDetectionService()

    try:
        rapidly_cited = await service.detect_citation_velocity(papers=papers, top_k=top_k)

        return [
            RapidlyCitedPaperResponse(
                paper_id=p.paper_id,
                title=p.title,
                authors=p.authors,
                citation_count=p.citation_count,
                citation_velocity=p.citation_velocity,
                percentile=p.percentile,
            )
            for p in rapidly_cited
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trends/report", response_model=TrendReportResponse)
async def generate_trend_report(request: TrendReportRequest):
    """Generate a comprehensive trend report.

    Includes:
    - Trending topics
    - Rapidly cited papers
    - Emerging keywords
    - Trends relevant to user's interests
    - AI-generated summary
    """
    from paperpulse.clustering import TrendDetectionService

    service = TrendDetectionService()

    try:
        report = await service.generate_trend_report(
            papers=request.papers,
            user_interests=request.user_interests,
            time_window_days=request.time_window_days,
        )

        return TrendReportResponse(
            time_window_days=report.time_window_days,
            summary=report.summary,
            trending_topics=[
                TrendingTopicResponse(
                    topic_id=t.topic_id,
                    name=t.name,
                    description=t.description,
                    keywords=t.keywords,
                    paper_count=len(t.papers),
                    trend_score=t.trend_score,
                    momentum=t.momentum,
                    publication_velocity=t.publication_velocity,
                )
                for t in report.trending_topics
            ],
            rapidly_cited_papers=[
                RapidlyCitedPaperResponse(
                    paper_id=p.paper_id,
                    title=p.title,
                    authors=p.authors,
                    citation_count=p.citation_count,
                    citation_velocity=p.citation_velocity,
                    percentile=p.percentile,
                )
                for p in report.rapidly_cited_papers
            ],
            emerging_keywords=report.emerging_keywords[:20],
            user_relevant_trends=[
                TrendingTopicResponse(
                    topic_id=t.topic_id,
                    name=t.name,
                    description=t.description,
                    keywords=t.keywords,
                    paper_count=len(t.papers),
                    trend_score=t.trend_score,
                    momentum=t.momentum,
                    publication_velocity=t.publication_velocity,
                )
                for t in report.user_relevant_trends
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trends/topic/{topic_id}/evolution")
async def get_topic_evolution(topic_id: str):
    """Track how a topic has evolved over time.

    Returns historical data on topic scores, paper counts, and momentum.
    """
    from paperpulse.clustering import TrendDetectionService

    service = TrendDetectionService()

    try:
        evolution = await service.track_topic_evolution(topic_id)
        return evolution
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trends/export/{format}")
async def export_trends(
    format: str,
    report: str = Query(..., description="JSON-encoded trend report"),
):
    """Export trend report in various formats.

    Formats:
    - **json**: Full JSON export
    - **csv**: CSV with trending topics
    - **html**: HTML report for viewing
    """
    import json

    from fastapi.responses import HTMLResponse, PlainTextResponse

    from paperpulse.clustering import TrendDetectionService, TrendReport

    try:
        data = json.loads(report)

        if format == "json":
            return data
        elif format == "csv":
            lines = ["topic_id,name,trend_score,momentum,paper_count,keywords"]
            for topic in data.get("trending_topics", []):
                keywords_str = ";".join(topic.get("keywords", [])[:5])
                lines.append(
                    f"{topic['topic_id']},{topic['name']},{topic['trend_score']:.2f},"
                    f"{topic['momentum']:.3f},{topic.get('paper_count', 0)},{keywords_str}"
                )
            return PlainTextResponse(content="\n".join(lines), media_type="text/csv")
        elif format == "html":
            # Build simple HTML report
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Research Trend Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        .topic {{ border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 8px; }}
        .score {{ font-size: 24px; color: #2196F3; }}
        h1 {{ color: #333; }}
    </style>
</head>
<body>
    <h1>Research Trend Report</h1>
    <p><strong>Summary:</strong> {data.get('summary', 'N/A')}</p>
    <h2>Trending Topics</h2>
"""
            for topic in data.get("trending_topics", [])[:10]:
                html += f"""    <div class="topic">
        <h3>{topic['name']}</h3>
        <div class="score">Score: {topic['trend_score']:.1f}</div>
        <p>Keywords: {', '.join(topic.get('keywords', [])[:5])}</p>
    </div>
"""
            html += "</body></html>"
            return HTMLResponse(content=html)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown format: {format}. Use json, csv, or html.",
            )
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in report parameter")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
