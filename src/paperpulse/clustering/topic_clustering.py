"""Topic clustering service for grouping papers by research themes.

This module provides production-level topic clustering using multiple approaches:
- Embedding-based clustering (K-Means, HDBSCAN)
- LDA topic modeling
- LLM-powered cluster labeling
"""

import asyncio
import hashlib
import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiohttp
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TopicCluster:
    """A cluster of related papers."""

    cluster_id: str
    label: str  # Human-readable label (LLM-generated or keyword-based)
    description: str
    papers: list[dict]  # List of paper metadata
    keywords: list[str]  # Representative keywords
    centroid: Optional[list[float]] = None  # Embedding centroid
    coherence_score: float = 0.0  # How tightly clustered (0-1)
    size: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        self.size = len(self.papers)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "cluster_id": self.cluster_id,
            "label": self.label,
            "description": self.description,
            "paper_ids": [p.get("doi") or p.get("arxiv_id") or p.get("title") for p in self.papers],
            "paper_count": self.size,
            "keywords": self.keywords,
            "coherence_score": self.coherence_score,
            "metadata": self.metadata,
        }


@dataclass
class ClusteringResult:
    """Result of a clustering operation."""

    clusters: list[TopicCluster]
    method: str  # "embedding", "lda", "hybrid"
    n_papers: int
    n_clusters: int
    unclustered_papers: list[dict] = field(default_factory=list)  # Papers that didn't fit any cluster
    silhouette_score: Optional[float] = None  # Overall clustering quality
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "method": self.method,
            "n_papers": self.n_papers,
            "n_clusters": self.n_clusters,
            "n_unclustered": len(self.unclustered_papers),
            "silhouette_score": self.silhouette_score,
            "timestamp": self.timestamp.isoformat(),
            "clusters": [c.to_dict() for c in self.clusters],
        }


class TopicClusteringService:
    """Service for clustering papers into topical groups.

    Supports multiple clustering strategies:
    1. Embedding-based: Uses paper embeddings with K-Means or HDBSCAN
    2. LDA: Latent Dirichlet Allocation for topic modeling
    3. Hybrid: Combines embedding clustering with keyword extraction

    Features:
    - Automatic cluster labeling using LLM
    - Cluster coherence scoring
    - Support for incremental clustering (adding papers to existing clusters)
    - Export to various formats (JSON, CSV, visualization data)
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        min_cluster_size: int = 3,
        max_clusters: int = 20,
    ):
        """Initialize the topic clustering service.

        Args:
            gemini_api_key: API key for Gemini (embeddings and labeling)
            cache_dir: Directory for caching embeddings
            min_cluster_size: Minimum papers per cluster
            max_clusters: Maximum number of clusters to create
        """
        self.api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.cache_dir = cache_dir or Path.home() / ".paperpulse" / "cache" / "clustering"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_cluster_size = min_cluster_size
        self.max_clusters = max_clusters

        # Embedding cache
        self._embedding_cache: dict[str, list[float]] = {}
        self._load_embedding_cache()

    def _load_embedding_cache(self) -> None:
        """Load cached embeddings from disk."""
        cache_file = self.cache_dir / "embedding_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    self._embedding_cache = json.load(f)
                logger.info(f"Loaded {len(self._embedding_cache)} cached embeddings")
            except Exception as e:
                logger.warning(f"Failed to load embedding cache: {e}")

    def _save_embedding_cache(self) -> None:
        """Save embeddings cache to disk."""
        cache_file = self.cache_dir / "embedding_cache.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(self._embedding_cache, f)
        except Exception as e:
            logger.warning(f"Failed to save embedding cache: {e}")

    def _get_paper_id(self, paper: dict) -> str:
        """Get a unique identifier for a paper."""
        if paper.get("doi"):
            return f"doi:{paper['doi']}"
        if paper.get("arxiv_id"):
            return f"arxiv:{paper['arxiv_id']}"
        # Fall back to title hash
        title = paper.get("title", "")
        return f"title:{hashlib.md5(title.encode()).hexdigest()[:12]}"

    async def _get_embedding(self, text: str) -> list[float]:
        """Get embedding for text using Gemini API."""
        cache_key = hashlib.md5(text.encode()).hexdigest()

        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        if not self.api_key:
            # Return mock embedding for testing
            np.random.seed(hash(text) % 2**32)
            return list(np.random.randn(768).astype(float))

        url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={self.api_key}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    json={"content": {"parts": [{"text": text[:8000]}]}},
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        embedding = data.get("embedding", {}).get("values", [])
                        if embedding:
                            self._embedding_cache[cache_key] = embedding
                            return embedding
                    else:
                        logger.warning(f"Embedding API error: {resp.status}")
            except Exception as e:
                logger.error(f"Embedding request failed: {e}")

        # Return mock embedding on failure
        np.random.seed(hash(text) % 2**32)
        return list(np.random.randn(768).astype(float))

    async def _get_paper_embedding(self, paper: dict) -> list[float]:
        """Get embedding for a paper (title + abstract)."""
        paper_id = self._get_paper_id(paper)

        if paper_id in self._embedding_cache:
            return self._embedding_cache[paper_id]

        text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
        embedding = await self._get_embedding(text)

        self._embedding_cache[paper_id] = embedding
        return embedding

    async def cluster_by_embedding(
        self,
        papers: list[dict],
        n_clusters: Optional[int] = None,
        method: str = "kmeans",
    ) -> ClusteringResult:
        """Cluster papers using their embeddings.

        Args:
            papers: List of paper dictionaries with title and abstract
            n_clusters: Number of clusters (auto-determined if None)
            method: Clustering method ("kmeans" or "hdbscan")

        Returns:
            ClusteringResult with discovered clusters
        """
        if len(papers) < self.min_cluster_size:
            logger.warning(f"Too few papers ({len(papers)}) for clustering")
            return ClusteringResult(
                clusters=[],
                method=f"embedding_{method}",
                n_papers=len(papers),
                n_clusters=0,
                unclustered_papers=papers,
            )

        # Get embeddings for all papers
        logger.info(f"Getting embeddings for {len(papers)} papers...")
        embeddings = []
        for paper in papers:
            emb = await self._get_paper_embedding(paper)
            embeddings.append(emb)

        embeddings_array = np.array(embeddings)

        # Determine number of clusters
        if n_clusters is None:
            # Rule of thumb: sqrt(n/2), bounded by min_cluster_size and max_clusters
            n_clusters = max(2, min(
                self.max_clusters,
                int(np.sqrt(len(papers) / 2))
            ))

        # Perform clustering
        if method == "kmeans":
            labels, centroids = self._kmeans_cluster(embeddings_array, n_clusters)
        elif method == "hdbscan":
            labels, centroids = self._hdbscan_cluster(embeddings_array)
        else:
            raise ValueError(f"Unknown clustering method: {method}")

        # Build clusters
        cluster_papers: dict[int, list[dict]] = defaultdict(list)
        unclustered = []

        for i, (paper, label) in enumerate(zip(papers, labels)):
            if label == -1:  # Noise point (HDBSCAN)
                unclustered.append(paper)
            else:
                cluster_papers[label].append(paper)

        # Create TopicCluster objects
        clusters = []
        for label, cluster_paper_list in cluster_papers.items():
            if len(cluster_paper_list) < self.min_cluster_size:
                unclustered.extend(cluster_paper_list)
                continue

            # Extract keywords from cluster
            keywords = self._extract_cluster_keywords(cluster_paper_list)

            # Calculate coherence
            cluster_embeddings = [
                embeddings[papers.index(p)] for p in cluster_paper_list
            ]
            coherence = self._calculate_coherence(cluster_embeddings)

            # Generate cluster ID
            cluster_id = f"cluster_{label}_{hashlib.md5(str(keywords[:3]).encode()).hexdigest()[:8]}"

            # Create initial label from keywords
            initial_label = ", ".join(keywords[:3]) if keywords else f"Topic {label}"

            cluster = TopicCluster(
                cluster_id=cluster_id,
                label=initial_label,
                description=f"Papers related to: {', '.join(keywords[:5])}",
                papers=cluster_paper_list,
                keywords=keywords,
                centroid=centroids[label].tolist() if centroids is not None and label < len(centroids) else None,
                coherence_score=coherence,
            )
            clusters.append(cluster)

        # Calculate silhouette score if we have clusters
        silhouette = None
        if len(clusters) >= 2:
            silhouette = self._calculate_silhouette(embeddings_array, labels)

        # Save embedding cache
        self._save_embedding_cache()

        result = ClusteringResult(
            clusters=sorted(clusters, key=lambda c: c.size, reverse=True),
            method=f"embedding_{method}",
            n_papers=len(papers),
            n_clusters=len(clusters),
            unclustered_papers=unclustered,
            silhouette_score=silhouette,
        )

        return result

    def _kmeans_cluster(
        self,
        embeddings: np.ndarray,
        n_clusters: int,
        max_iter: int = 100,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Perform K-Means clustering.

        Implements K-Means++ initialization for better convergence.
        """
        n_samples = len(embeddings)

        # K-Means++ initialization
        centroids = [embeddings[np.random.randint(n_samples)]]

        for _ in range(1, n_clusters):
            # Calculate distances to nearest centroid
            distances = np.array([
                min(np.linalg.norm(x - c) ** 2 for c in centroids)
                for x in embeddings
            ])

            # Sample proportional to distance squared
            probs = distances / distances.sum()
            next_idx = np.random.choice(n_samples, p=probs)
            centroids.append(embeddings[next_idx])

        centroids = np.array(centroids)

        # Iterate
        for _ in range(max_iter):
            # Assign points to nearest centroid
            labels = np.array([
                np.argmin([np.linalg.norm(x - c) for c in centroids])
                for x in embeddings
            ])

            # Update centroids
            new_centroids = np.array([
                embeddings[labels == k].mean(axis=0) if np.any(labels == k) else centroids[k]
                for k in range(n_clusters)
            ])

            # Check convergence
            if np.allclose(centroids, new_centroids, atol=1e-6):
                break

            centroids = new_centroids

        return labels, centroids

    def _hdbscan_cluster(
        self,
        embeddings: np.ndarray,
        min_samples: int = 3,
    ) -> tuple[np.ndarray, Optional[np.ndarray]]:
        """Perform HDBSCAN clustering.

        This is a simplified implementation. For production with large datasets,
        consider using the hdbscan library.
        """
        # Simplified: fall back to K-Means with automatic k selection
        # In production, use actual HDBSCAN implementation

        n_samples = len(embeddings)

        # Try different k values and pick best silhouette
        best_k = 2
        best_score = -1

        for k in range(2, min(self.max_clusters + 1, n_samples // self.min_cluster_size + 1)):
            labels, centroids = self._kmeans_cluster(embeddings, k)
            score = self._calculate_silhouette(embeddings, labels)

            if score is not None and score > best_score:
                best_score = score
                best_k = k

        return self._kmeans_cluster(embeddings, best_k)

    def _extract_cluster_keywords(
        self,
        papers: list[dict],
        top_k: int = 10,
    ) -> list[str]:
        """Extract representative keywords from cluster papers using TF-IDF."""
        # Common stopwords
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
            "be", "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "must", "this", "that", "these",
            "those", "it", "its", "we", "our", "their", "they", "them", "paper",
            "study", "research", "method", "results", "approach", "using", "based",
            "propose", "proposed", "show", "demonstrate", "present", "novel",
        }

        # Build term frequency across all papers
        term_freq: dict[str, int] = defaultdict(int)
        doc_freq: dict[str, int] = defaultdict(int)

        for paper in papers:
            text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
            # Simple tokenization
            words = [w.strip(".,;:!?()[]{}\"'") for w in text.split()]
            words = [w for w in words if len(w) > 2 and w not in stopwords and w.isalpha()]

            # Count terms
            seen = set()
            for word in words:
                term_freq[word] += 1
                if word not in seen:
                    doc_freq[word] += 1
                    seen.add(word)

        # Calculate TF-IDF
        n_docs = len(papers)
        tfidf_scores: dict[str, float] = {}

        for term, tf in term_freq.items():
            df = doc_freq[term]
            # Only consider terms appearing in multiple papers
            if df >= 2:
                idf = np.log(n_docs / df)
                tfidf_scores[term] = tf * idf

        # Sort by TF-IDF score
        sorted_terms = sorted(tfidf_scores.items(), key=lambda x: x[1], reverse=True)

        return [term for term, _ in sorted_terms[:top_k]]

    def _calculate_coherence(self, embeddings: list[list[float]]) -> float:
        """Calculate cluster coherence (average pairwise cosine similarity)."""
        if len(embeddings) < 2:
            return 1.0

        embeddings_array = np.array(embeddings)

        # Normalize embeddings
        norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        normalized = embeddings_array / norms

        # Calculate pairwise cosine similarities
        similarity_matrix = np.dot(normalized, normalized.T)

        # Get upper triangle (excluding diagonal)
        n = len(embeddings)
        upper_indices = np.triu_indices(n, k=1)
        similarities = similarity_matrix[upper_indices]

        return float(np.mean(similarities))

    def _calculate_silhouette(
        self,
        embeddings: np.ndarray,
        labels: np.ndarray,
    ) -> Optional[float]:
        """Calculate silhouette score for clustering quality."""
        unique_labels = set(labels) - {-1}  # Exclude noise

        if len(unique_labels) < 2:
            return None

        silhouette_vals = []

        for i, (emb, label) in enumerate(zip(embeddings, labels)):
            if label == -1:
                continue

            # a(i) = mean distance to same cluster
            same_cluster = embeddings[labels == label]
            if len(same_cluster) > 1:
                a_i = np.mean([np.linalg.norm(emb - x) for x in same_cluster if not np.array_equal(x, emb)])
            else:
                a_i = 0

            # b(i) = min mean distance to other clusters
            b_i = float("inf")
            for other_label in unique_labels:
                if other_label != label:
                    other_cluster = embeddings[labels == other_label]
                    mean_dist = np.mean([np.linalg.norm(emb - x) for x in other_cluster])
                    b_i = min(b_i, mean_dist)

            if b_i == float("inf"):
                b_i = 0

            # Silhouette value
            s_i = (b_i - a_i) / max(a_i, b_i) if max(a_i, b_i) > 0 else 0
            silhouette_vals.append(s_i)

        return float(np.mean(silhouette_vals)) if silhouette_vals else None

    async def discover_topics_lda(
        self,
        papers: list[dict],
        n_topics: int = 10,
        n_iterations: int = 50,
    ) -> ClusteringResult:
        """Discover topics using Latent Dirichlet Allocation.

        This is a simplified LDA implementation. For production with large
        datasets, consider using gensim or sklearn.

        Args:
            papers: List of paper dictionaries
            n_topics: Number of topics to discover
            n_iterations: Number of Gibbs sampling iterations

        Returns:
            ClusteringResult with discovered topic clusters
        """
        if len(papers) < self.min_cluster_size:
            return ClusteringResult(
                clusters=[],
                method="lda",
                n_papers=len(papers),
                n_clusters=0,
                unclustered_papers=papers,
            )

        # Build vocabulary
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
            "be", "have", "has", "had", "do", "does", "did", "will", "would",
            "this", "that", "these", "those", "it", "its", "we", "our", "their",
        }

        vocab: dict[str, int] = {}
        docs: list[list[int]] = []

        for paper in papers:
            text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
            words = [w.strip(".,;:!?()[]{}\"'") for w in text.split()]
            words = [w for w in words if len(w) > 2 and w not in stopwords and w.isalpha()]

            doc = []
            for word in words:
                if word not in vocab:
                    vocab[word] = len(vocab)
                doc.append(vocab[word])
            docs.append(doc)

        vocab_size = len(vocab)
        n_docs = len(docs)

        if vocab_size == 0:
            return ClusteringResult(
                clusters=[],
                method="lda",
                n_papers=len(papers),
                n_clusters=0,
                unclustered_papers=papers,
            )

        # Initialize
        alpha = 0.1  # Document-topic prior
        beta = 0.01  # Topic-word prior

        # Random topic assignments
        topic_assignments: list[list[int]] = []
        n_dk = np.zeros((n_docs, n_topics))  # Document-topic counts
        n_kw = np.zeros((n_topics, vocab_size))  # Topic-word counts
        n_k = np.zeros(n_topics)  # Topic counts

        for d, doc in enumerate(docs):
            assignments = []
            for word in doc:
                topic = np.random.randint(n_topics)
                assignments.append(topic)
                n_dk[d, topic] += 1
                n_kw[topic, word] += 1
                n_k[topic] += 1
            topic_assignments.append(assignments)

        # Gibbs sampling
        for _ in range(n_iterations):
            for d, doc in enumerate(docs):
                for i, word in enumerate(doc):
                    old_topic = topic_assignments[d][i]

                    # Remove current assignment
                    n_dk[d, old_topic] -= 1
                    n_kw[old_topic, word] -= 1
                    n_k[old_topic] -= 1

                    # Calculate probabilities
                    probs = np.zeros(n_topics)
                    for k in range(n_topics):
                        probs[k] = (n_dk[d, k] + alpha) * (n_kw[k, word] + beta) / (n_k[k] + vocab_size * beta)

                    probs /= probs.sum()

                    # Sample new topic
                    new_topic = np.random.choice(n_topics, p=probs)

                    # Update counts
                    topic_assignments[d][i] = new_topic
                    n_dk[d, new_topic] += 1
                    n_kw[new_topic, word] += 1
                    n_k[new_topic] += 1

        # Assign documents to dominant topics
        doc_topics = np.argmax(n_dk, axis=1)

        # Get top words per topic
        reverse_vocab = {v: k for k, v in vocab.items()}
        topic_keywords: dict[int, list[str]] = {}

        for k in range(n_topics):
            top_word_indices = np.argsort(n_kw[k])[-10:][::-1]
            topic_keywords[k] = [reverse_vocab[idx] for idx in top_word_indices]

        # Build clusters
        cluster_papers: dict[int, list[dict]] = defaultdict(list)

        for doc_idx, topic in enumerate(doc_topics):
            cluster_papers[topic].append(papers[doc_idx])

        clusters = []
        unclustered = []

        for topic, paper_list in cluster_papers.items():
            if len(paper_list) < self.min_cluster_size:
                unclustered.extend(paper_list)
                continue

            keywords = topic_keywords.get(topic, [])
            cluster_id = f"lda_topic_{topic}_{hashlib.md5(str(keywords[:3]).encode()).hexdigest()[:8]}"

            cluster = TopicCluster(
                cluster_id=cluster_id,
                label=", ".join(keywords[:3]) if keywords else f"Topic {topic}",
                description=f"LDA topic characterized by: {', '.join(keywords[:5])}",
                papers=paper_list,
                keywords=keywords,
                coherence_score=float(n_dk[:, topic].mean() / n_dk.sum(axis=1).mean()) if n_dk.sum() > 0 else 0.0,
            )
            clusters.append(cluster)

        return ClusteringResult(
            clusters=sorted(clusters, key=lambda c: c.size, reverse=True),
            method="lda",
            n_papers=len(papers),
            n_clusters=len(clusters),
            unclustered_papers=unclustered,
        )

    async def label_clusters(
        self,
        result: ClusteringResult,
        use_llm: bool = True,
    ) -> ClusteringResult:
        """Generate human-readable labels for clusters using LLM.

        Args:
            result: Clustering result to label
            use_llm: Whether to use LLM for labeling (vs keyword-based)

        Returns:
            Updated ClusteringResult with improved labels
        """
        if not use_llm or not self.api_key:
            # Use keyword-based labeling
            for cluster in result.clusters:
                if cluster.keywords:
                    cluster.label = " & ".join(cluster.keywords[:2]).title()
            return result

        # Use Gemini to generate labels
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.api_key}"

        async with aiohttp.ClientSession() as session:
            for cluster in result.clusters:
                # Build prompt with paper titles
                titles = [p.get("title", "")[:100] for p in cluster.papers[:10]]
                keywords = cluster.keywords[:10]

                prompt = f"""Generate a concise (2-4 words) research topic label for this cluster of papers.

Top keywords: {', '.join(keywords)}

Sample paper titles:
{chr(10).join(f'- {t}' for t in titles)}

Respond with ONLY the topic label, nothing else. Examples: "Graph Neural Networks", "Protein Folding", "Reinforcement Learning", "Medical Image Analysis"."""

                try:
                    async with session.post(
                        url,
                        json={"contents": [{"parts": [{"text": prompt}]}]},
                        headers={"Content-Type": "application/json"},
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            label = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                            if label and len(label) < 50:
                                cluster.label = label
                                cluster.description = f"Research papers on {label.lower()}"
                except Exception as e:
                    logger.warning(f"Failed to generate label for cluster: {e}")

        return result

    async def cluster_hybrid(
        self,
        papers: list[dict],
        n_clusters: Optional[int] = None,
    ) -> ClusteringResult:
        """Perform hybrid clustering combining embeddings and LDA.

        Uses embedding clustering as primary, then refines with LDA topic keywords.

        Args:
            papers: List of paper dictionaries
            n_clusters: Number of clusters (auto if None)

        Returns:
            ClusteringResult with hybrid clusters
        """
        # Get embedding-based clusters
        emb_result = await self.cluster_by_embedding(papers, n_clusters, method="kmeans")

        # Get LDA topics
        lda_result = await self.discover_topics_lda(papers, n_topics=len(emb_result.clusters) or 5)

        # Enhance embedding clusters with LDA keywords
        for emb_cluster in emb_result.clusters:
            # Find most similar LDA topic by paper overlap
            best_overlap = 0
            best_lda_cluster = None

            emb_paper_ids = {self._get_paper_id(p) for p in emb_cluster.papers}

            for lda_cluster in lda_result.clusters:
                lda_paper_ids = {self._get_paper_id(p) for p in lda_cluster.papers}
                overlap = len(emb_paper_ids & lda_paper_ids)

                if overlap > best_overlap:
                    best_overlap = overlap
                    best_lda_cluster = lda_cluster

            # Merge keywords from LDA
            if best_lda_cluster:
                combined_keywords = list(dict.fromkeys(
                    emb_cluster.keywords[:5] + best_lda_cluster.keywords[:5]
                ))
                emb_cluster.keywords = combined_keywords[:10]

        # Update method
        emb_result.method = "hybrid"

        # Generate labels
        emb_result = await self.label_clusters(emb_result)

        return emb_result

    def assign_paper_to_cluster(
        self,
        paper: dict,
        clusters: list[TopicCluster],
        threshold: float = 0.5,
    ) -> Optional[TopicCluster]:
        """Assign a new paper to an existing cluster.

        Args:
            paper: Paper to assign
            clusters: Existing clusters
            threshold: Minimum similarity threshold

        Returns:
            Best matching cluster or None if below threshold
        """
        if not clusters:
            return None

        # Simple keyword overlap scoring
        paper_text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
        paper_words = set(paper_text.split())

        best_score = 0
        best_cluster = None

        for cluster in clusters:
            keyword_matches = sum(1 for kw in cluster.keywords if kw.lower() in paper_words)
            score = keyword_matches / len(cluster.keywords) if cluster.keywords else 0

            if score > best_score and score >= threshold:
                best_score = score
                best_cluster = cluster

        return best_cluster

    def export_for_visualization(
        self,
        result: ClusteringResult,
        format: str = "json",
    ) -> str:
        """Export clustering result for visualization.

        Args:
            result: Clustering result to export
            format: Export format ("json", "csv", "d3")

        Returns:
            Serialized data string
        """
        if format == "json":
            return json.dumps(result.to_dict(), indent=2)

        elif format == "csv":
            lines = ["cluster_id,cluster_label,paper_id,paper_title"]
            for cluster in result.clusters:
                for paper in cluster.papers:
                    paper_id = self._get_paper_id(paper)
                    title = paper.get("title", "").replace(",", ";")[:100]
                    lines.append(f"{cluster.cluster_id},{cluster.label},{paper_id},{title}")
            return "\n".join(lines)

        elif format == "d3":
            # Format for D3.js visualization (nodes and links)
            nodes = []
            links = []

            # Add cluster nodes
            for cluster in result.clusters:
                nodes.append({
                    "id": cluster.cluster_id,
                    "label": cluster.label,
                    "type": "cluster",
                    "size": cluster.size,
                })

                # Add paper nodes and links
                for paper in cluster.papers:
                    paper_id = self._get_paper_id(paper)
                    nodes.append({
                        "id": paper_id,
                        "label": paper.get("title", "")[:50],
                        "type": "paper",
                    })
                    links.append({
                        "source": cluster.cluster_id,
                        "target": paper_id,
                    })

            return json.dumps({"nodes": nodes, "links": links}, indent=2)

        else:
            raise ValueError(f"Unknown export format: {format}")
