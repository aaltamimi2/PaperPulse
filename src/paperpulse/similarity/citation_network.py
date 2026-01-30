"""Citation network service - build and analyze paper relationship graphs."""

import asyncio
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CitationNode:
    """A node in the citation graph representing a paper."""
    paper_id: str
    title: str
    authors: list[str]
    year: Optional[int] = None
    citation_count: int = 0
    url: str = ""
    abstract: Optional[str] = None

    # Graph metrics (computed after graph is built)
    in_degree: int = 0  # Number of papers citing this one
    out_degree: int = 0  # Number of papers this one cites
    pagerank: float = 0.0
    betweenness: float = 0.0

    # Relationships
    references: list[str] = field(default_factory=list)  # Papers this cites
    cited_by: list[str] = field(default_factory=list)  # Papers citing this


@dataclass
class CitationEdge:
    """An edge representing a citation relationship."""
    source_id: str  # Citing paper
    target_id: str  # Cited paper
    context: Optional[str] = None  # Citation context snippet


@dataclass
class CitationGraph:
    """A citation network graph."""
    seed_paper_id: str
    nodes: dict[str, CitationNode] = field(default_factory=dict)
    edges: list[CitationEdge] = field(default_factory=list)

    # Graph statistics
    total_nodes: int = 0
    total_edges: int = 0
    depth_reached: int = 0

    @property
    def papers(self) -> list[CitationNode]:
        """Get all papers in the graph."""
        return list(self.nodes.values())

    def get_paper(self, paper_id: str) -> Optional[CitationNode]:
        """Get a paper by ID."""
        return self.nodes.get(paper_id)

    def add_node(self, node: CitationNode) -> None:
        """Add a node to the graph."""
        if node.paper_id not in self.nodes:
            self.nodes[node.paper_id] = node
            self.total_nodes = len(self.nodes)

    def add_edge(self, source_id: str, target_id: str, context: Optional[str] = None) -> None:
        """Add a citation edge (source cites target)."""
        edge = CitationEdge(source_id=source_id, target_id=target_id, context=context)
        self.edges.append(edge)
        self.total_edges = len(self.edges)

        # Update node relationships
        if source_id in self.nodes:
            if target_id not in self.nodes[source_id].references:
                self.nodes[source_id].references.append(target_id)
                self.nodes[source_id].out_degree += 1

        if target_id in self.nodes:
            if source_id not in self.nodes[target_id].cited_by:
                self.nodes[target_id].cited_by.append(source_id)
                self.nodes[target_id].in_degree += 1

    def to_dict(self) -> dict:
        """Convert graph to dictionary for JSON serialization."""
        return {
            "seed_paper_id": self.seed_paper_id,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "depth_reached": self.depth_reached,
            "nodes": [
                {
                    "id": node.paper_id,
                    "title": node.title,
                    "authors": node.authors,
                    "year": node.year,
                    "citation_count": node.citation_count,
                    "url": node.url,
                    "in_degree": node.in_degree,
                    "out_degree": node.out_degree,
                    "pagerank": node.pagerank,
                }
                for node in self.nodes.values()
            ],
            "edges": [
                {"source": edge.source_id, "target": edge.target_id}
                for edge in self.edges
            ],
        }

    def export_gexf(self) -> str:
        """Export graph in GEXF format for Gephi."""
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<gexf xmlns="http://www.gexf.net/1.2draft" version="1.2">',
            '  <graph mode="static" defaultedgetype="directed">',
            '    <attributes class="node">',
            '      <attribute id="0" title="year" type="integer"/>',
            '      <attribute id="1" title="citations" type="integer"/>',
            '      <attribute id="2" title="pagerank" type="float"/>',
            '    </attributes>',
            '    <nodes>',
        ]

        for node in self.nodes.values():
            title_escaped = node.title.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
            lines.append(f'      <node id="{node.paper_id}" label="{title_escaped}">')
            lines.append('        <attvalues>')
            lines.append(f'          <attvalue for="0" value="{node.year or 0}"/>')
            lines.append(f'          <attvalue for="1" value="{node.citation_count}"/>')
            lines.append(f'          <attvalue for="2" value="{node.pagerank:.6f}"/>')
            lines.append('        </attvalues>')
            lines.append('      </node>')

        lines.append('    </nodes>')
        lines.append('    <edges>')

        for i, edge in enumerate(self.edges):
            lines.append(f'      <edge id="{i}" source="{edge.source_id}" target="{edge.target_id}"/>')

        lines.append('    </edges>')
        lines.append('  </graph>')
        lines.append('</gexf>')

        return '\n'.join(lines)


class CitationNetworkService:
    """Build and analyze citation networks."""

    def __init__(self, semantic_scholar_api_key: Optional[str] = None):
        """Initialize the citation network service.

        Args:
            semantic_scholar_api_key: Optional API key for higher rate limits
        """
        self.s2_api_key = semantic_scholar_api_key
        self._rate_limit_delay = 0.1  # Seconds between API calls

    async def build_network(
        self,
        seed_paper: dict,
        depth: int = 2,
        max_nodes: int = 100,
        include_references: bool = True,
        include_citations: bool = True,
    ) -> CitationGraph:
        """Build a citation network starting from a seed paper.

        Args:
            seed_paper: Starting paper dict with title, doi, or s2_id
            depth: How many levels of citations to traverse
                   1 = direct references and citations only
                   2 = references of references, etc.
            max_nodes: Maximum number of papers in the graph
            include_references: Include papers the seed cites
            include_citations: Include papers that cite the seed

        Returns:
            CitationGraph with nodes and edges
        """
        paper_id = await self._resolve_paper_id(seed_paper)
        if not paper_id:
            logger.error("Could not resolve paper ID", title=seed_paper.get("title"))
            return CitationGraph(seed_paper_id="unknown")

        graph = CitationGraph(seed_paper_id=paper_id)
        visited = set()
        queue = [(paper_id, 0)]  # (paper_id, current_depth)

        logger.info("Building citation network", seed_id=paper_id, depth=depth, max_nodes=max_nodes)

        while queue and len(graph.nodes) < max_nodes:
            current_id, current_depth = queue.pop(0)

            if current_id in visited:
                continue
            visited.add(current_id)

            # Fetch paper details
            paper_data = await self._fetch_paper_details(current_id)
            if not paper_data:
                continue

            # Add node
            node = CitationNode(
                paper_id=current_id,
                title=paper_data.get("title", "Unknown"),
                authors=[a.get("name", "") for a in paper_data.get("authors", [])],
                year=paper_data.get("year"),
                citation_count=paper_data.get("citationCount", 0),
                url=paper_data.get("url", ""),
                abstract=paper_data.get("abstract"),
            )
            graph.add_node(node)

            # Only expand if within depth limit
            if current_depth < depth:
                # Fetch references
                if include_references:
                    references = await self._fetch_references(current_id)
                    for ref in references:
                        ref_id = ref.get("paperId")
                        if ref_id and len(graph.nodes) < max_nodes:
                            # Add minimal node for reference
                            ref_node = CitationNode(
                                paper_id=ref_id,
                                title=ref.get("title", "Unknown"),
                                authors=[a.get("name", "") for a in ref.get("authors", [])],
                                year=ref.get("year"),
                                citation_count=ref.get("citationCount", 0),
                                url=ref.get("url", ""),
                            )
                            graph.add_node(ref_node)
                            graph.add_edge(current_id, ref_id)

                            if ref_id not in visited:
                                queue.append((ref_id, current_depth + 1))

                # Fetch citations
                if include_citations:
                    citations = await self._fetch_citations(current_id)
                    for cit in citations:
                        cit_id = cit.get("paperId")
                        if cit_id and len(graph.nodes) < max_nodes:
                            cit_node = CitationNode(
                                paper_id=cit_id,
                                title=cit.get("title", "Unknown"),
                                authors=[a.get("name", "") for a in cit.get("authors", [])],
                                year=cit.get("year"),
                                citation_count=cit.get("citationCount", 0),
                                url=cit.get("url", ""),
                            )
                            graph.add_node(cit_node)
                            graph.add_edge(cit_id, current_id)

                            if cit_id not in visited:
                                queue.append((cit_id, current_depth + 1))

            graph.depth_reached = max(graph.depth_reached, current_depth)

            await asyncio.sleep(self._rate_limit_delay)

        # Compute graph metrics
        self._compute_pagerank(graph)

        logger.info(
            "Citation network built",
            nodes=graph.total_nodes,
            edges=graph.total_edges,
            depth=graph.depth_reached,
        )

        return graph

    def find_influential_papers(
        self,
        graph: CitationGraph,
        method: str = "pagerank",
        limit: int = 10,
    ) -> list[tuple[CitationNode, float]]:
        """Find the most influential papers in the network.

        Args:
            graph: Citation graph to analyze
            method: Ranking method - "pagerank", "citations", "in_degree"
            limit: Number of papers to return

        Returns:
            List of (paper, score) tuples sorted by influence
        """
        papers = list(graph.nodes.values())

        if method == "pagerank":
            papers.sort(key=lambda x: x.pagerank, reverse=True)
            return [(p, p.pagerank) for p in papers[:limit]]
        elif method == "citations":
            papers.sort(key=lambda x: x.citation_count, reverse=True)
            return [(p, float(p.citation_count)) for p in papers[:limit]]
        elif method == "in_degree":
            papers.sort(key=lambda x: x.in_degree, reverse=True)
            return [(p, float(x.in_degree)) for p in papers[:limit]]
        else:
            raise ValueError(f"Unknown method: {method}")

    def find_research_fronts(
        self,
        graph: CitationGraph,
        min_cluster_size: int = 3,
    ) -> list[list[CitationNode]]:
        """Identify research fronts (clusters of recent highly-connected papers).

        Research fronts are groups of recent papers that cite similar foundational work.

        Args:
            graph: Citation graph to analyze
            min_cluster_size: Minimum papers to form a research front

        Returns:
            List of paper clusters representing research fronts
        """
        # Find recent papers (last 3 years)
        import datetime
        current_year = datetime.datetime.now().year
        recent_papers = [
            p for p in graph.nodes.values()
            if p.year and p.year >= current_year - 3
        ]

        if len(recent_papers) < min_cluster_size:
            return []

        # Group by shared references (bibliographic coupling)
        reference_sets = {}
        for paper in recent_papers:
            reference_sets[paper.paper_id] = set(paper.references)

        # Cluster papers with high reference overlap
        clusters = []
        used = set()

        for paper in recent_papers:
            if paper.paper_id in used:
                continue

            cluster = [paper]
            used.add(paper.paper_id)

            for other in recent_papers:
                if other.paper_id in used:
                    continue

                # Calculate Jaccard similarity of references
                refs1 = reference_sets.get(paper.paper_id, set())
                refs2 = reference_sets.get(other.paper_id, set())

                if refs1 and refs2:
                    intersection = len(refs1 & refs2)
                    union = len(refs1 | refs2)
                    similarity = intersection / union if union > 0 else 0

                    if similarity >= 0.3:  # 30% overlap threshold
                        cluster.append(other)
                        used.add(other.paper_id)

            if len(cluster) >= min_cluster_size:
                clusters.append(cluster)

        # Sort clusters by average citation count (most impactful first)
        clusters.sort(
            key=lambda c: sum(p.citation_count for p in c) / len(c),
            reverse=True
        )

        return clusters

    def find_bridge_papers(
        self,
        graph: CitationGraph,
        limit: int = 10,
    ) -> list[CitationNode]:
        """Find papers that bridge different research areas.

        Bridge papers connect otherwise disconnected parts of the citation network.

        Args:
            graph: Citation graph to analyze
            limit: Number of papers to return

        Returns:
            List of bridge papers sorted by bridging importance
        """
        # Simple heuristic: papers with diverse references and citations
        # (connected to papers from different years/areas)
        bridge_scores = {}

        for paper in graph.nodes.values():
            # Calculate year diversity of connections
            connected_years = []
            for ref_id in paper.references:
                if ref_id in graph.nodes:
                    ref_year = graph.nodes[ref_id].year
                    if ref_year:
                        connected_years.append(ref_year)

            for cit_id in paper.cited_by:
                if cit_id in graph.nodes:
                    cit_year = graph.nodes[cit_id].year
                    if cit_year:
                        connected_years.append(cit_year)

            if connected_years:
                year_range = max(connected_years) - min(connected_years)
                connectivity = len(paper.references) + len(paper.cited_by)
                # Bridge score: connectivity * year diversity
                bridge_scores[paper.paper_id] = connectivity * (1 + year_range / 10)
            else:
                bridge_scores[paper.paper_id] = 0

        # Sort by bridge score
        sorted_papers = sorted(
            graph.nodes.values(),
            key=lambda p: bridge_scores.get(p.paper_id, 0),
            reverse=True
        )

        return sorted_papers[:limit]

    def _compute_pagerank(
        self,
        graph: CitationGraph,
        damping: float = 0.85,
        iterations: int = 100,
        tolerance: float = 1e-6,
    ) -> None:
        """Compute PageRank scores for all nodes in the graph."""
        n = len(graph.nodes)
        if n == 0:
            return

        # Initialize scores
        scores = {node_id: 1.0 / n for node_id in graph.nodes}

        # Build adjacency list (who cites whom)
        cited_by = defaultdict(list)
        out_degree = defaultdict(int)

        for edge in graph.edges:
            cited_by[edge.target_id].append(edge.source_id)
            out_degree[edge.source_id] += 1

        # Iterate
        for _ in range(iterations):
            new_scores = {}
            max_diff = 0

            for node_id in graph.nodes:
                # Sum contributions from citing papers
                rank_sum = 0
                for citing_id in cited_by.get(node_id, []):
                    if out_degree[citing_id] > 0:
                        rank_sum += scores[citing_id] / out_degree[citing_id]

                new_score = (1 - damping) / n + damping * rank_sum
                max_diff = max(max_diff, abs(new_score - scores[node_id]))
                new_scores[node_id] = new_score

            scores = new_scores

            if max_diff < tolerance:
                break

        # Update node pagerank values
        for node_id, score in scores.items():
            graph.nodes[node_id].pagerank = score

    async def _resolve_paper_id(self, paper: dict) -> Optional[str]:
        """Resolve paper to Semantic Scholar ID."""
        if paper.get("s2_id"):
            return paper["s2_id"]

        # Try DOI
        if paper.get("doi"):
            return f"DOI:{paper['doi']}"

        # Try arXiv
        if paper.get("arxiv_id"):
            return f"ARXIV:{paper['arxiv_id']}"

        # Search by title
        import httpx

        title = paper.get("title", "")
        if not title:
            return None

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {}
            if self.s2_api_key:
                headers["x-api-key"] = self.s2_api_key

            try:
                resp = await client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    headers=headers,
                    params={"query": title, "limit": 1, "fields": "paperId"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data"):
                        return data["data"][0]["paperId"]
            except Exception as e:
                logger.warning("Failed to resolve paper ID", error=str(e))

        return None

    async def _fetch_paper_details(self, paper_id: str) -> Optional[dict]:
        """Fetch paper details from Semantic Scholar."""
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {}
            if self.s2_api_key:
                headers["x-api-key"] = self.s2_api_key

            try:
                url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
                resp = await client.get(
                    url,
                    headers=headers,
                    params={"fields": "paperId,title,authors,year,citationCount,url,abstract"}
                )
                if resp.status_code == 200:
                    return resp.json()
            except Exception as e:
                logger.warning("Failed to fetch paper details", paper_id=paper_id, error=str(e))

        return None

    async def _fetch_references(self, paper_id: str, limit: int = 50) -> list[dict]:
        """Fetch papers that this paper cites."""
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {}
            if self.s2_api_key:
                headers["x-api-key"] = self.s2_api_key

            try:
                url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/references"
                resp = await client.get(
                    url,
                    headers=headers,
                    params={
                        "fields": "paperId,title,authors,year,citationCount,url",
                        "limit": limit
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return [r["citedPaper"] for r in data.get("data", []) if r.get("citedPaper")]
            except Exception as e:
                logger.warning("Failed to fetch references", paper_id=paper_id, error=str(e))

        return []

    async def _fetch_citations(self, paper_id: str, limit: int = 50) -> list[dict]:
        """Fetch papers that cite this paper."""
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {}
            if self.s2_api_key:
                headers["x-api-key"] = self.s2_api_key

            try:
                url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations"
                resp = await client.get(
                    url,
                    headers=headers,
                    params={
                        "fields": "paperId,title,authors,year,citationCount,url",
                        "limit": limit
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return [c["citingPaper"] for c in data.get("data", []) if c.get("citingPaper")]
            except Exception as e:
                logger.warning("Failed to fetch citations", paper_id=paper_id, error=str(e))

        return []
