"""Paper similarity and citation network API routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["papers"])


# ==================== Request/Response Models ====================

class SimilarPaperRequest(BaseModel):
    """Request for finding similar papers."""

    paper_id: str = Field(..., description="Paper ID (DOI or arXiv ID)")
    limit: int = Field(default=20, ge=1, le=100)
    method: str = Field(
        default="combined",
        description="Similarity method: embedding, citations, authors, combined",
    )
    weights: Optional[dict[str, float]] = Field(
        default=None,
        description="Custom weights for combined method",
    )


class SimilarPaperResponse(BaseModel):
    """A similar paper in the response."""

    paper_id: str
    title: str
    authors: list[str]
    similarity_score: float
    similarity_sources: dict[str, float]
    abstract: Optional[str] = None
    url: Optional[str] = None


class CitationNetworkRequest(BaseModel):
    """Request for building a citation network."""

    seed_paper_id: str = Field(..., description="Starting paper ID")
    depth: int = Field(default=2, ge=1, le=3, description="Network depth")
    max_nodes: int = Field(default=100, ge=10, le=500)


class CitationNodeResponse(BaseModel):
    """A node in the citation network."""

    paper_id: str
    title: str
    authors: list[str]
    citation_count: int
    pagerank_score: float
    depth: int
    is_seed: bool


class CitationNetworkResponse(BaseModel):
    """Citation network response."""

    nodes: list[CitationNodeResponse]
    edges: list[dict]  # {source, target, weight}
    influential_papers: list[CitationNodeResponse]
    research_fronts: list[dict]  # Clusters of citing papers


# ==================== Endpoints ====================

@router.post("/similar", response_model=list[SimilarPaperResponse])
async def find_similar_papers(request: SimilarPaperRequest):
    """Find papers similar to a given paper.

    Uses multiple similarity measures:
    - **embedding**: Semantic similarity using paper embeddings
    - **citations**: Papers citing the same works (bibliographic coupling)
    - **authors**: Other papers by the same authors
    - **combined**: Weighted combination of all methods
    """
    from paperpulse.similarity import PaperSimilarityService

    service = PaperSimilarityService()

    try:
        result = await service.find_similar(
            paper_id=request.paper_id,
            limit=request.limit,
            method=request.method,
            weights=request.weights,
        )

        return [
            SimilarPaperResponse(
                paper_id=p.paper_id,
                title=p.title,
                authors=p.authors,
                similarity_score=p.similarity_score,
                similarity_sources=p.similarity_sources,
                abstract=p.abstract,
                url=p.url,
            )
            for p in result.similar_papers
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{paper_id}/similar", response_model=list[SimilarPaperResponse])
async def get_similar_papers(
    paper_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    method: str = Query(default="combined"),
):
    """Get papers similar to the specified paper (GET version)."""
    from paperpulse.similarity import PaperSimilarityService

    service = PaperSimilarityService()

    try:
        result = await service.find_similar(
            paper_id=paper_id,
            limit=limit,
            method=method,
        )

        return [
            SimilarPaperResponse(
                paper_id=p.paper_id,
                title=p.title,
                authors=p.authors,
                similarity_score=p.similarity_score,
                similarity_sources=p.similarity_sources,
                abstract=p.abstract,
                url=p.url,
            )
            for p in result.similar_papers
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/citation-network", response_model=CitationNetworkResponse)
async def build_citation_network(request: CitationNetworkRequest):
    """Build a citation network starting from a seed paper.

    Returns a graph of papers connected by citations, including:
    - Influential papers (by PageRank)
    - Research fronts (clusters of related citing papers)
    """
    from paperpulse.similarity import CitationNetworkService

    service = CitationNetworkService()

    try:
        graph = await service.build_network(
            seed_paper_id=request.seed_paper_id,
            depth=request.depth,
            max_nodes=request.max_nodes,
        )

        # Get influential papers
        influential = await service.find_influential_papers(graph, top_k=10)

        # Get research fronts
        fronts = await service.find_research_fronts(graph)

        # Convert to response format
        nodes = [
            CitationNodeResponse(
                paper_id=node.paper_id,
                title=node.title,
                authors=node.authors,
                citation_count=node.citation_count,
                pagerank_score=node.pagerank_score,
                depth=node.depth,
                is_seed=node.is_seed,
            )
            for node in graph.nodes.values()
        ]

        edges = [
            {"source": edge.source, "target": edge.target, "weight": edge.weight}
            for edge in graph.edges
        ]

        influential_response = [
            CitationNodeResponse(
                paper_id=node.paper_id,
                title=node.title,
                authors=node.authors,
                citation_count=node.citation_count,
                pagerank_score=node.pagerank_score,
                depth=node.depth,
                is_seed=node.is_seed,
            )
            for node in influential
        ]

        return CitationNetworkResponse(
            nodes=nodes,
            edges=edges,
            influential_papers=influential_response,
            research_fronts=[
                {
                    "cluster_id": f.cluster_id,
                    "label": f.label,
                    "paper_count": len(f.papers),
                    "keywords": f.keywords[:5],
                }
                for f in fronts
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{paper_id}/citations")
async def get_paper_citations(
    paper_id: str,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Get papers that cite this paper."""
    from paperpulse.similarity import CitationNetworkService

    service = CitationNetworkService()

    try:
        citations = await service._fetch_citations(paper_id, limit=limit)
        return {
            "paper_id": paper_id,
            "citation_count": len(citations),
            "citations": citations,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{paper_id}/references")
async def get_paper_references(
    paper_id: str,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Get papers that this paper cites."""
    from paperpulse.similarity import CitationNetworkService

    service = CitationNetworkService()

    try:
        references = await service._fetch_references(paper_id, limit=limit)
        return {
            "paper_id": paper_id,
            "reference_count": len(references),
            "references": references,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{paper_id}/network/export")
async def export_citation_network(
    paper_id: str,
    depth: int = Query(default=2, ge=1, le=3),
    format: str = Query(default="gexf", description="Export format: gexf, json"),
):
    """Export citation network in GEXF format (for Gephi) or JSON (for D3.js)."""
    from fastapi.responses import PlainTextResponse

    from paperpulse.similarity import CitationNetworkService

    service = CitationNetworkService()

    try:
        graph = await service.build_network(seed_paper_id=paper_id, depth=depth)
        exported = service.export_for_visualization(graph, format=format)

        content_type = "application/xml" if format == "gexf" else "application/json"
        return PlainTextResponse(content=exported, media_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
