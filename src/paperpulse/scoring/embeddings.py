"""Gemini embedding service for semantic similarity."""

import asyncio
import hashlib
import math
from typing import Optional

import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from paperpulse.core.config import GeminiSettings, get_settings

logger = structlog.get_logger(__name__)

# Try to import Google AI SDK
GENAI_AVAILABLE = False
GENAI_TYPE = None

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
    GENAI_TYPE = "generativeai"
except ImportError:
    pass


def _deterministic_embedding(text: str, dimensions: int = 768) -> list[float]:
    """Generate a deterministic pseudo-embedding based on word presence.

    This is a fallback for testing when the API is unavailable.
    It produces consistent embeddings where texts with common words
    have higher cosine similarity.

    Args:
        text: Text to embed
        dimensions: Number of dimensions

    Returns:
        Pseudo-embedding vector
    """
    import re

    # Extract words and normalize
    text_lower = text.lower().strip()
    words = set(re.findall(r'\b[a-z]{3,}\b', text_lower))

    # Create embedding based on word hashes
    # Each word contributes to specific dimensions based on its hash
    embedding = [0.0] * dimensions

    for word in words:
        # Hash word to get deterministic dimension indices
        word_hash = hashlib.md5(word.encode()).digest()

        # Each word affects multiple dimensions
        for i in range(4):
            # Get dimension index from hash bytes
            dim_idx = (word_hash[i * 2] * 256 + word_hash[i * 2 + 1]) % dimensions
            # Get contribution sign and magnitude from hash
            sign = 1 if word_hash[i + 8] > 127 else -1
            magnitude = 0.5 + (word_hash[i + 12] / 512.0)  # 0.5 to 1.0
            embedding[dim_idx] += sign * magnitude

    # Add small noise based on full text hash (for uniqueness)
    text_hash = hashlib.sha256(text_lower.encode()).digest()
    for i in range(min(32, dimensions)):
        noise = (text_hash[i % len(text_hash)] / 2550.0) - 0.05  # Small noise
        embedding[i] += noise

    # Normalize to unit length
    norm = math.sqrt(sum(x * x for x in embedding))
    if norm > 0:
        embedding = [x / norm for x in embedding]
    else:
        # Fallback: create a random unit vector
        for i in range(dimensions):
            embedding[i] = (hashlib.md5(f"{i}:{text_lower}".encode()).digest()[0] / 127.5) - 1
        norm = math.sqrt(sum(x * x for x in embedding))
        embedding = [x / norm for x in embedding]

    return embedding


class EmbeddingService:
    """Service for generating text embeddings using Google Gemini.

    Falls back to deterministic pseudo-embeddings when API is unavailable.
    """

    def __init__(
        self,
        settings: Optional[GeminiSettings] = None,
        mock_mode: bool = False,
    ):
        """Initialize the embedding service.

        Args:
            settings: Gemini API configuration
            mock_mode: If True, use deterministic pseudo-embeddings
        """
        self.settings = settings or get_settings().gemini
        self._configured = False
        self._mock_mode = mock_mode

        if not mock_mode and GENAI_AVAILABLE:
            try:
                genai.configure(api_key=self.settings.api_key.get_secret_value())
                self._configured = True
                logger.info("Gemini API configured successfully")
            except Exception as e:
                logger.warning(f"Failed to configure Gemini API: {e}, using mock mode")
                self._mock_mode = True
        else:
            self._mock_mode = True
            if not GENAI_AVAILABLE:
                logger.warning("google-generativeai not installed, using mock embeddings")

    @property
    def is_mock(self) -> bool:
        """Check if using mock embeddings."""
        return self._mock_mode

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats
        """
        if self._mock_mode:
            return _deterministic_embedding(text, self.settings.embedding_dimensions)

        return await self._embed_with_api(text)

    @retry(
        retry=retry_if_exception_type((Exception,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _embed_with_api(self, text: str) -> list[float]:
        """Generate embedding using the Gemini API."""
        loop = asyncio.get_event_loop()

        def _call_api():
            result = genai.embed_content(
                model=f"models/{self.settings.embedding_model}",
                content=text,
                task_type="semantic_similarity",
            )
            return result["embedding"]

        embedding = await loop.run_in_executor(None, _call_api)
        return list(embedding)

    async def embed_texts(
        self,
        texts: list[str],
        batch_size: int = 100,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call

        Returns:
            List of embedding vectors
        """
        if self._mock_mode:
            return [
                _deterministic_embedding(text, self.settings.embedding_dimensions)
                for text in texts
            ]

        # For API, process in batches
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            logger.debug("Embedding batch", batch_start=i, batch_size=len(batch))

            for text in batch:
                embedding = await self._embed_with_api(text)
                all_embeddings.append(embedding)

        return all_embeddings

    async def embed_paper(
        self,
        title: str,
        abstract: Optional[str] = None,
    ) -> list[float]:
        """Generate embedding for a paper.

        Combines title and abstract for better semantic representation.

        Args:
            title: Paper title
            abstract: Paper abstract (optional)

        Returns:
            Embedding vector
        """
        if abstract:
            text = f"{title}\n\n{abstract}"
        else:
            text = title

        return await self.embed_text(text)

    async def embed_research_profile(
        self,
        name: str,
        description: Optional[str] = None,
        keywords: Optional[list[str]] = None,
    ) -> list[float]:
        """Generate embedding for a research interest category.

        Combines name, description, and keywords for comprehensive representation.

        Args:
            name: Category name (e.g., "Polymer Molecular Dynamics")
            description: Detailed description of the research interest
            keywords: List of relevant keywords

        Returns:
            Embedding vector
        """
        parts = [name]

        if description:
            parts.append(description)

        if keywords:
            parts.append("Keywords: " + ", ".join(keywords))

        text = "\n\n".join(parts)
        return await self.embed_text(text)


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors.

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Cosine similarity score (0 to 1 for normalized vectors)
    """
    if len(vec1) != len(vec2):
        raise ValueError(f"Vector dimensions must match: {len(vec1)} != {len(vec2)}")

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)
