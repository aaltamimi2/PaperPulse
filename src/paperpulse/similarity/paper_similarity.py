"""Paper similarity service - find papers similar to a given paper."""

import asyncio
from dataclasses import dataclass, field
from typing import Optional
import structlog

from paperpulse.scoring.embeddings import EmbeddingService, cosine_similarity

logger = structlog.get_logger(__name__)


@dataclass
class SimilarPaper:
    """A paper similar to the query paper."""
    paper_id: str
    title: str
    authors: list[str]
    url: str
    abstract: Optional[str] = None
    doi: Optional[str] = None
    year: Optional[int] = None

    # Similarity scores
    similarity_score: float = 0.0
    embedding_similarity: float = 0.0
    citation_similarity: float = 0.0
    author_similarity: float = 0.0

    # Source information
    similarity_reasons: list[str] = field(default_factory=list)


@dataclass
class SimilarityResult:
    """Result of a similarity search."""
    query_paper_id: str
    query_paper_title: str
    similar_papers: list[SimilarPaper]
    total_found: int
    method_used: str


class PaperSimilarityService:
    """Find papers similar to a given paper using multiple methods.

    Methods:
    1. Embedding similarity - cosine similarity of paper embeddings
    2. Citation overlap - papers citing or cited by the same papers
    3. Author overlap - other papers by the same authors
    4. Combined - weighted combination of all methods
    """

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        semantic_scholar_api_key: Optional[str] = None,
    ):
        """Initialize the similarity service.

        Args:
            embedding_service: Service for generating embeddings
            semantic_scholar_api_key: API key for Semantic Scholar (optional, for higher rate limits)
        """
        self.embedding_service = embedding_service or EmbeddingService()
        self.s2_api_key = semantic_scholar_api_key
        self._paper_cache: dict[str, dict] = {}
        self._embedding_cache: dict[str, list[float]] = {}

    async def find_similar(
        self,
        paper: dict,
        method: str = "combined",
        limit: int = 20,
        weights: Optional[dict] = None,
    ) -> SimilarityResult:
        """Find papers similar to the given paper.

        Args:
            paper: Paper dict with title, abstract, authors, etc.
            method: Similarity method - "embedding", "citation", "author", "combined"
            limit: Maximum number of similar papers to return
            weights: Custom weights for combined method (default: embedding=0.5, citation=0.3, author=0.2)

        Returns:
            SimilarityResult with list of similar papers
        """
        weights = weights or {"embedding": 0.5, "citation": 0.3, "author": 0.2}

        paper_id = self._get_paper_id(paper)
        title = paper.get("title", "Unknown")

        logger.info("Finding similar papers", paper_id=paper_id, method=method, limit=limit)

        if method == "embedding":
            similar = await self._find_similar_by_embedding(paper, limit)
        elif method == "citation":
            similar = await self._find_similar_by_citations(paper, limit)
        elif method == "author":
            similar = await self._find_similar_by_authors(paper, limit)
        elif method == "combined":
            similar = await self._find_similar_combined(paper, limit, weights)
        else:
            raise ValueError(f"Unknown similarity method: {method}")

        return SimilarityResult(
            query_paper_id=paper_id,
            query_paper_title=title,
            similar_papers=similar,
            total_found=len(similar),
            method_used=method,
        )

    async def _find_similar_by_embedding(
        self,
        paper: dict,
        limit: int,
        candidate_papers: Optional[list[dict]] = None,
    ) -> list[SimilarPaper]:
        """Find similar papers using embedding cosine similarity.

        Args:
            paper: Query paper
            limit: Max results
            candidate_papers: If provided, search within these papers only
        """
        # Get query paper embedding
        query_embedding = await self._get_paper_embedding(paper)

        if candidate_papers is None:
            # Use Semantic Scholar recommendations as candidates
            candidate_papers = await self._get_s2_recommendations(paper)

        # Score all candidates
        scored_papers = []
        for candidate in candidate_papers:
            if self._get_paper_id(candidate) == self._get_paper_id(paper):
                continue  # Skip the query paper itself

            candidate_embedding = await self._get_paper_embedding(candidate)
            similarity = cosine_similarity(query_embedding, candidate_embedding)

            scored_papers.append(SimilarPaper(
                paper_id=self._get_paper_id(candidate),
                title=candidate.get("title", "Unknown"),
                authors=candidate.get("authors", []),
                url=candidate.get("url", ""),
                abstract=candidate.get("abstract"),
                doi=candidate.get("doi"),
                year=candidate.get("year"),
                similarity_score=similarity,
                embedding_similarity=similarity,
                similarity_reasons=["High semantic similarity"],
            ))

        # Sort by similarity and return top results
        scored_papers.sort(key=lambda x: x.similarity_score, reverse=True)
        return scored_papers[:limit]

    async def _find_similar_by_citations(
        self,
        paper: dict,
        limit: int,
    ) -> list[SimilarPaper]:
        """Find similar papers through citation relationships.

        Papers are similar if they:
        - Cite the same papers (bibliographic coupling)
        - Are cited by the same papers (co-citation)
        """
        import httpx

        paper_id = paper.get("s2_id") or paper.get("doi")
        if not paper_id:
            # Try to resolve via title search
            paper_id = await self._resolve_s2_id(paper.get("title", ""))

        if not paper_id:
            logger.warning("Cannot find paper in Semantic Scholar", title=paper.get("title"))
            return []

        similar_papers = []
        seen_ids = {paper_id}

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {}
            if self.s2_api_key:
                headers["x-api-key"] = self.s2_api_key

            # Get references (papers this paper cites)
            try:
                refs_url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/references"
                refs_resp = await client.get(
                    refs_url,
                    headers=headers,
                    params={"fields": "paperId,title,authors,year,url,abstract,citationCount"}
                )
                if refs_resp.status_code == 200:
                    refs_data = refs_resp.json()
                    reference_ids = [r["citedPaper"]["paperId"] for r in refs_data.get("data", [])
                                    if r.get("citedPaper", {}).get("paperId")]
                else:
                    reference_ids = []
            except Exception as e:
                logger.warning("Failed to fetch references", error=str(e))
                reference_ids = []

            # Get citations (papers that cite this paper)
            try:
                cites_url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations"
                cites_resp = await client.get(
                    cites_url,
                    headers=headers,
                    params={"fields": "paperId,title,authors,year,url,abstract,citationCount", "limit": 100}
                )
                if cites_resp.status_code == 200:
                    cites_data = cites_resp.json()
                    for citation in cites_data.get("data", [])[:limit]:
                        citing_paper = citation.get("citingPaper", {})
                        if citing_paper.get("paperId") and citing_paper["paperId"] not in seen_ids:
                            seen_ids.add(citing_paper["paperId"])
                            similar_papers.append(SimilarPaper(
                                paper_id=citing_paper["paperId"],
                                title=citing_paper.get("title", "Unknown"),
                                authors=[a.get("name", "") for a in citing_paper.get("authors", [])],
                                url=citing_paper.get("url", ""),
                                abstract=citing_paper.get("abstract"),
                                year=citing_paper.get("year"),
                                similarity_score=0.8,  # Base score for direct citations
                                citation_similarity=1.0,
                                similarity_reasons=["Cites this paper"],
                            ))
            except Exception as e:
                logger.warning("Failed to fetch citations", error=str(e))

            # Find papers citing the same references (bibliographic coupling)
            if reference_ids:
                # Get papers that also cite these references
                for ref_id in reference_ids[:10]:  # Limit to avoid rate limits
                    try:
                        await asyncio.sleep(0.1)  # Rate limiting
                        ref_cites_url = f"https://api.semanticscholar.org/graph/v1/paper/{ref_id}/citations"
                        ref_cites_resp = await client.get(
                            ref_cites_url,
                            headers=headers,
                            params={"fields": "paperId,title,authors,year,url,abstract", "limit": 20}
                        )
                        if ref_cites_resp.status_code == 200:
                            ref_cites_data = ref_cites_resp.json()
                            for citation in ref_cites_data.get("data", []):
                                citing = citation.get("citingPaper", {})
                                if citing.get("paperId") and citing["paperId"] not in seen_ids:
                                    seen_ids.add(citing["paperId"])
                                    similar_papers.append(SimilarPaper(
                                        paper_id=citing["paperId"],
                                        title=citing.get("title", "Unknown"),
                                        authors=[a.get("name", "") for a in citing.get("authors", [])],
                                        url=citing.get("url", ""),
                                        abstract=citing.get("abstract"),
                                        year=citing.get("year"),
                                        similarity_score=0.6,
                                        citation_similarity=0.7,
                                        similarity_reasons=["Cites same references"],
                                    ))
                    except Exception as e:
                        logger.debug("Failed to fetch co-citations", ref_id=ref_id, error=str(e))

        # Sort by similarity score
        similar_papers.sort(key=lambda x: x.similarity_score, reverse=True)
        return similar_papers[:limit]

    async def _find_similar_by_authors(
        self,
        paper: dict,
        limit: int,
    ) -> list[SimilarPaper]:
        """Find other papers by the same authors."""
        import httpx

        authors = paper.get("authors", [])
        if not authors:
            return []

        similar_papers = []
        seen_ids = {self._get_paper_id(paper)}

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {}
            if self.s2_api_key:
                headers["x-api-key"] = self.s2_api_key

            for author_name in authors[:3]:  # Check first 3 authors
                # Search for author
                try:
                    search_url = "https://api.semanticscholar.org/graph/v1/author/search"
                    search_resp = await client.get(
                        search_url,
                        headers=headers,
                        params={"query": author_name, "limit": 1}
                    )

                    if search_resp.status_code != 200:
                        continue

                    search_data = search_resp.json()
                    if not search_data.get("data"):
                        continue

                    author_id = search_data["data"][0]["authorId"]

                    # Get author's papers
                    await asyncio.sleep(0.1)  # Rate limiting
                    papers_url = f"https://api.semanticscholar.org/graph/v1/author/{author_id}/papers"
                    papers_resp = await client.get(
                        papers_url,
                        headers=headers,
                        params={
                            "fields": "paperId,title,authors,year,url,abstract,citationCount",
                            "limit": 50
                        }
                    )

                    if papers_resp.status_code != 200:
                        continue

                    papers_data = papers_resp.json()
                    for author_paper in papers_data.get("data", []):
                        if author_paper.get("paperId") and author_paper["paperId"] not in seen_ids:
                            seen_ids.add(author_paper["paperId"])
                            similar_papers.append(SimilarPaper(
                                paper_id=author_paper["paperId"],
                                title=author_paper.get("title", "Unknown"),
                                authors=[a.get("name", "") for a in author_paper.get("authors", [])],
                                url=author_paper.get("url", ""),
                                abstract=author_paper.get("abstract"),
                                year=author_paper.get("year"),
                                similarity_score=0.7,
                                author_similarity=1.0,
                                similarity_reasons=[f"Same author: {author_name}"],
                            ))

                except Exception as e:
                    logger.warning("Failed to fetch author papers", author=author_name, error=str(e))

                await asyncio.sleep(0.1)  # Rate limiting between authors

        # Sort by year (most recent first) then citation count
        similar_papers.sort(key=lambda x: (x.year or 0), reverse=True)
        return similar_papers[:limit]

    async def _find_similar_combined(
        self,
        paper: dict,
        limit: int,
        weights: dict,
    ) -> list[SimilarPaper]:
        """Combine multiple similarity methods with weights."""
        # Run all methods in parallel
        embedding_task = self._find_similar_by_embedding(paper, limit * 2)
        citation_task = self._find_similar_by_citations(paper, limit * 2)
        author_task = self._find_similar_by_authors(paper, limit)

        embedding_results, citation_results, author_results = await asyncio.gather(
            embedding_task, citation_task, author_task,
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(embedding_results, Exception):
            logger.warning("Embedding similarity failed", error=str(embedding_results))
            embedding_results = []
        if isinstance(citation_results, Exception):
            logger.warning("Citation similarity failed", error=str(citation_results))
            citation_results = []
        if isinstance(author_results, Exception):
            logger.warning("Author similarity failed", error=str(author_results))
            author_results = []

        # Merge results
        paper_scores: dict[str, SimilarPaper] = {}

        for sp in embedding_results:
            paper_scores[sp.paper_id] = sp
            sp.similarity_score = sp.embedding_similarity * weights.get("embedding", 0.5)

        for sp in citation_results:
            if sp.paper_id in paper_scores:
                existing = paper_scores[sp.paper_id]
                existing.citation_similarity = sp.citation_similarity
                existing.similarity_score += sp.citation_similarity * weights.get("citation", 0.3)
                existing.similarity_reasons.extend(sp.similarity_reasons)
            else:
                sp.similarity_score = sp.citation_similarity * weights.get("citation", 0.3)
                paper_scores[sp.paper_id] = sp

        for sp in author_results:
            if sp.paper_id in paper_scores:
                existing = paper_scores[sp.paper_id]
                existing.author_similarity = sp.author_similarity
                existing.similarity_score += sp.author_similarity * weights.get("author", 0.2)
                existing.similarity_reasons.extend(sp.similarity_reasons)
            else:
                sp.similarity_score = sp.author_similarity * weights.get("author", 0.2)
                paper_scores[sp.paper_id] = sp

        # Deduplicate reasons
        for sp in paper_scores.values():
            sp.similarity_reasons = list(set(sp.similarity_reasons))

        # Sort and return
        results = list(paper_scores.values())
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results[:limit]

    async def _get_paper_embedding(self, paper: dict) -> list[float]:
        """Get or compute embedding for a paper."""
        paper_id = self._get_paper_id(paper)

        if paper_id in self._embedding_cache:
            return self._embedding_cache[paper_id]

        embedding = await self.embedding_service.embed_paper(
            title=paper.get("title", ""),
            abstract=paper.get("abstract"),
        )

        self._embedding_cache[paper_id] = embedding
        return embedding

    async def _get_s2_recommendations(self, paper: dict) -> list[dict]:
        """Get paper recommendations from Semantic Scholar."""
        import httpx

        paper_id = paper.get("s2_id") or paper.get("doi")
        if not paper_id:
            paper_id = await self._resolve_s2_id(paper.get("title", ""))

        if not paper_id:
            return []

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {}
            if self.s2_api_key:
                headers["x-api-key"] = self.s2_api_key

            try:
                url = f"https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{paper_id}"
                resp = await client.get(
                    url,
                    headers=headers,
                    params={"fields": "paperId,title,authors,year,url,abstract,citationCount", "limit": 100}
                )

                if resp.status_code == 200:
                    data = resp.json()
                    return [
                        {
                            "s2_id": p["paperId"],
                            "title": p.get("title", ""),
                            "authors": [a.get("name", "") for a in p.get("authors", [])],
                            "year": p.get("year"),
                            "url": p.get("url", ""),
                            "abstract": p.get("abstract"),
                            "citation_count": p.get("citationCount"),
                        }
                        for p in data.get("recommendedPapers", [])
                    ]
            except Exception as e:
                logger.warning("Failed to get S2 recommendations", error=str(e))

        return []

    async def _resolve_s2_id(self, title: str) -> Optional[str]:
        """Resolve a paper title to Semantic Scholar ID."""
        import httpx

        if not title:
            return None

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {}
            if self.s2_api_key:
                headers["x-api-key"] = self.s2_api_key

            try:
                url = "https://api.semanticscholar.org/graph/v1/paper/search"
                resp = await client.get(
                    url,
                    headers=headers,
                    params={"query": title, "limit": 1, "fields": "paperId"}
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data"):
                        return data["data"][0]["paperId"]
            except Exception as e:
                logger.warning("Failed to resolve S2 ID", title=title[:50], error=str(e))

        return None

    def _get_paper_id(self, paper: dict) -> str:
        """Get a unique identifier for a paper."""
        if paper.get("s2_id"):
            return f"s2:{paper['s2_id']}"
        if paper.get("doi"):
            return f"doi:{paper['doi']}"
        if paper.get("arxiv_id"):
            return f"arxiv:{paper['arxiv_id']}"
        # Fallback to title hash
        import hashlib
        title = paper.get("title", "").lower().strip()
        return f"title:{hashlib.md5(title.encode()).hexdigest()[:16]}"
