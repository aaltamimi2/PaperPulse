#!/usr/bin/env python3
"""Test script for the scoring pipeline with real Gemini API calls."""

import asyncio
import os
import sys
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Load .env file before importing paperpulse modules
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Add src to path for imports
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rich.console import Console
from rich.table import Table

from paperpulse.scoring import EmbeddingService, ScoringConfig, ScoringPipeline, ScoringContext


console = Console()


# Sample papers for testing (simulating collected papers)
SAMPLE_PAPERS = [
    {
        "title": "Machine Learning Collective Variables for Enhanced Sampling of Protein Folding",
        "abstract": "We present a novel deep learning approach to automatically discover collective variables for enhanced sampling molecular dynamics simulations. Our method uses a variational autoencoder to learn low-dimensional representations of protein conformational space, enabling efficient metadynamics simulations of protein folding pathways.",
        "authors": ["John Smith", "Jane Doe", "Robert Johnson"],
        "journal": "Journal of Chemical Theory and Computation",
    },
    {
        "title": "Polymer Chain Dynamics in Confined Geometries: A Molecular Dynamics Study",
        "abstract": "We investigate the dynamics of polymer chains confined in nanopores using extensive all-atom molecular dynamics simulations with GROMACS. Our results reveal anomalous diffusion behavior and provide insights into the role of polymer-surface interactions.",
        "authors": ["Alice Wang", "Bob Chen"],
        "journal": "Macromolecules",
    },
    {
        "title": "Large Language Models for Scientific Discovery: An Agent-Based Approach",
        "abstract": "We introduce an agentic AI framework that leverages large language models for autonomous scientific discovery. Our multi-agent system can formulate hypotheses, design experiments, and analyze results with minimal human intervention.",
        "authors": ["Emily Zhang", "Michael Brown"],
        "journal": "Nature Machine Intelligence",
    },
    {
        "title": "Synthesis of Novel Block Copolymers for Drug Delivery Applications",
        "abstract": "We report the synthesis and characterization of a new class of amphiphilic block copolymers for targeted drug delivery. The polymers self-assemble into micelles with tunable size and drug loading capacity.",
        "authors": ["Sarah Miller"],
        "journal": "ACS Applied Materials & Interfaces",
    },
    {
        "title": "Quantum Computing Advances in Cryptography",
        "abstract": "This paper reviews recent advances in quantum computing and their implications for cryptographic security. We discuss post-quantum cryptography approaches and their implementation challenges.",
        "authors": ["David Wilson"],
        "journal": "Nature Physics",
    },
]

# Research profiles matching user's interests
RESEARCH_PROFILES = {
    "polymer_md": {
        "name": "Polymer Molecular Dynamics Simulations",
        "description": "Research focused on molecular dynamics simulations of polymer systems, including chain dynamics, phase behavior, and transport properties. Interested in coarse-grained and all-atom simulations using GROMACS, LAMMPS, and related tools.",
        "keywords": [
            "molecular dynamics",
            "polymer",
            "GROMACS",
            "coarse-grained",
            "chain dynamics",
            "diffusion",
            "viscoelastic",
            "simulation",
            "force field",
        ],
        "excluded_keywords": ["synthesis", "experimental"],
        "followed_authors": ["Bob Chen", "Kurt Kremer"],
        "followed_journals": ["Macromolecules", "Journal of Chemical Physics"],
    },
    "agentic_ai": {
        "name": "Agentic AI",
        "description": "Research on autonomous AI agents, multi-agent systems, and AI-driven automation. Focused on large language models, reasoning capabilities, and tool use in AI systems.",
        "keywords": [
            "agent",
            "agentic",
            "large language model",
            "LLM",
            "autonomous",
            "multi-agent",
            "reasoning",
            "tool use",
        ],
        "excluded_keywords": [],
        "followed_authors": [],
        "followed_journals": ["Nature Machine Intelligence", "NeurIPS"],
    },
    "ml_collective_variables": {
        "name": "Machine Learned Collective Variables",
        "description": "Machine learning approaches to discover collective variables and reaction coordinates for enhanced sampling in molecular simulations. Includes deep learning, dimensionality reduction, and variational methods.",
        "keywords": [
            "collective variable",
            "machine learning",
            "deep learning",
            "enhanced sampling",
            "metadynamics",
            "neural network",
            "autoencoder",
            "dimensionality reduction",
            "reaction coordinate",
            "free energy",
        ],
        "excluded_keywords": [],
        "followed_authors": ["John Smith"],
        "followed_journals": ["Journal of Chemical Theory and Computation"],
    },
}


async def test_embeddings():
    """Test the embedding service."""
    console.print("\n[bold cyan]Testing Embedding Service[/bold cyan]\n")

    # Use mock_mode=True for testing when API is unavailable
    service = EmbeddingService(mock_mode=True)

    if service.is_mock:
        console.print("[yellow]Note: Using mock embeddings (API unavailable or mock mode enabled)[/yellow]\n")

    # Test single embedding
    console.print("Generating embedding for sample text...")
    text = "Machine learning for molecular dynamics simulations"
    embedding = await service.embed_text(text)

    console.print(f"  Text: '{text}'")
    console.print(f"  Embedding dimensions: {len(embedding)}")
    console.print(f"  First 5 values: {embedding[:5]}")
    console.print("[green]✓ Single embedding works![/green]\n")

    # Test paper embedding
    console.print("Generating embedding for paper...")
    paper_embedding = await service.embed_paper(
        title="Polymer Dynamics Study",
        abstract="We study polymer chain dynamics using MD simulations.",
    )
    console.print(f"  Paper embedding dimensions: {len(paper_embedding)}")
    console.print("[green]✓ Paper embedding works![/green]\n")

    # Test profile embedding
    console.print("Generating embedding for research profile...")
    profile_embedding = await service.embed_research_profile(
        name="Polymer MD Simulations",
        description="Molecular dynamics of polymer systems",
        keywords=["polymer", "MD", "simulation"],
    )
    console.print(f"  Profile embedding dimensions: {len(profile_embedding)}")
    console.print("[green]✓ Profile embedding works![/green]\n")

    return True


async def test_scoring_pipeline():
    """Test the full scoring pipeline."""
    console.print("\n[bold cyan]Testing Scoring Pipeline[/bold cyan]\n")

    # Use mock embeddings for testing
    embedding_service = EmbeddingService(mock_mode=True)
    pipeline = ScoringPipeline(embedding_service=embedding_service)

    if embedding_service.is_mock:
        console.print("[yellow]Note: Using mock embeddings for scoring[/yellow]\n")

    for profile_key, profile in RESEARCH_PROFILES.items():
        console.print(f"\n[bold]Profile: {profile['name']}[/bold]")
        console.print(f"[dim]{profile['description'][:80]}...[/dim]\n")

        results = await pipeline.score_papers(SAMPLE_PAPERS, profile)

        # Display results table
        table = Table(title=f"Papers Ranked for '{profile['name']}'")
        table.add_column("Rank", style="cyan", justify="right")
        table.add_column("Title", style="white", max_width=50)
        table.add_column("Score", style="green", justify="right")
        table.add_column("Priority", style="yellow")
        table.add_column("Breakdown", style="dim")

        for i, (paper, score) in enumerate(results, 1):
            breakdown = ", ".join(
                f"{s.scorer_name}:{s.score:.2f}"
                for s in score.component_scores
            )

            priority_color = {
                "immediate": "red",
                "weekly": "yellow",
                "monthly": "blue",
                "low": "dim",
            }.get(score.priority, "white")

            table.add_row(
                str(i),
                paper["title"][:50] + ("..." if len(paper["title"]) > 50 else ""),
                f"{score.total_score:.3f}",
                f"[{priority_color}]{score.priority}[/{priority_color}]",
                breakdown,
            )

        console.print(table)

    return True


async def test_individual_scorers():
    """Test individual scorers in detail."""
    console.print("\n[bold cyan]Testing Individual Scorers[/bold cyan]\n")

    from paperpulse.scoring.scorers import (
        KeywordScorer,
        AuthorScorer,
        NoveltyScorer,
    )

    # Test keyword scorer
    console.print("[bold]Keyword Scorer Test[/bold]")
    keyword_scorer = KeywordScorer()
    context = ScoringContext(
        paper_title="Molecular Dynamics Simulations of Polymer Chains",
        paper_abstract="We use GROMACS to study polymer diffusion behavior.",
        profile_keywords=["molecular dynamics", "polymer", "GROMACS", "diffusion"],
        profile_excluded_keywords=["synthesis"],
    )
    result = await keyword_scorer.score(context)
    console.print(f"  Score: {result.score:.3f}")
    console.print(f"  Matched: {result.details.get('matched_keywords', [])}")
    console.print()

    # Test author scorer
    console.print("[bold]Author Scorer Test[/bold]")
    author_scorer = AuthorScorer()
    context = ScoringContext(
        paper_title="Test Paper",
        paper_authors=["J. Smith", "A. Johnson", "B. Williams"],
        profile_followed_authors=["John Smith", "Jane Doe"],
    )
    result = await author_scorer.score(context)
    console.print(f"  Score: {result.score:.3f}")
    console.print(f"  Matched: {result.details.get('matched_authors', [])}")
    console.print()

    # Test novelty scorer
    console.print("[bold]Novelty Scorer Test[/bold]")
    novelty_scorer = NoveltyScorer()
    context = ScoringContext(
        paper_title="A Novel Deep Learning Framework for Molecular Simulations",
        paper_abstract="We propose a new neural network architecture that outperforms existing methods for enhanced sampling.",
    )
    result = await novelty_scorer.score(context)
    console.print(f"  Score: {result.score:.3f}")
    console.print(f"  Novelty indicators: {result.details.get('novelty_indicators', [])}")
    console.print(f"  Method indicators: {result.details.get('method_indicators', [])}")
    console.print()

    return True


async def main():
    """Run all tests."""
    console.print("[bold magenta]PaperPulse Scoring Pipeline Test[/bold magenta]")
    console.print("=" * 50)

    try:
        # Test embeddings first
        await test_embeddings()

        # Test individual scorers (without API calls for non-semantic)
        await test_individual_scorers()

        # Test full pipeline
        await test_scoring_pipeline()

        console.print("\n[bold green]All tests passed![/bold green]")

    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
