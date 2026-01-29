#!/usr/bin/env python3
"""Test script for AI-enhanced email digest with real Gemini API."""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Load .env file
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Set the Gemini API key if not in environment
if not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = "AIzaSyAOkP57wd-1RjTeJ6GdebznbzncYFBHwqA"

# Add src to path
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rich.console import Console

from paperpulse.email import (
    DigestRenderer,
    DigestService,
    EmailSender,
    ResearchInterest,
)
from paperpulse.email.summarization import SummarizationService

console = Console()

# Sample papers for testing
SAMPLE_PAPERS = [
    {
        "title": "Machine Learning Collective Variables for Enhanced Sampling of Protein Folding",
        "abstract": "We present a novel deep learning approach to automatically discover collective variables for enhanced sampling molecular dynamics simulations. Our method uses a variational autoencoder to learn low-dimensional representations of protein conformational space, enabling more efficient exploration of free energy landscapes. We demonstrate the approach on protein folding simulations, achieving a 10x speedup in sampling convergence.",
        "authors": ["John Smith", "Jane Doe", "Robert Johnson"],
        "journal": "Journal of Chemical Theory and Computation",
        "url": "https://pubs.acs.org/doi/10.1021/acs.jctc.2024.001",
        "doi": "10.1021/acs.jctc.2024.001",
        "published_date": datetime.now() - timedelta(days=2),
        "citation_count": 15,
        "fields_of_study": ["machine learning", "computational chemistry", "molecular dynamics"],
    },
    {
        "title": "Large Language Models for Scientific Discovery: An Agent-Based Approach",
        "abstract": "We introduce an agentic AI framework that leverages large language models for autonomous scientific discovery. Our multi-agent system can formulate hypotheses, design experiments, analyze results, and iterate on findings. The system integrates with laboratory automation and computational tools, demonstrating successful autonomous optimization of chemical synthesis procedures.",
        "authors": ["Emily Zhang", "Michael Brown"],
        "journal": "Nature Machine Intelligence",
        "url": "https://nature.com/articles/s42256-024-001",
        "doi": "10.1038/s42256-024-001",
        "published_date": datetime.now() - timedelta(days=1),
        "citation_count": 42,
        "fields_of_study": ["artificial intelligence", "scientific discovery", "autonomous systems"],
    },
    {
        "title": "Polymer Chain Dynamics in Confined Geometries: A Molecular Dynamics Study",
        "abstract": "We investigate the dynamics of polymer chains confined in nanopores using extensive all-atom molecular dynamics simulations with GROMACS. Our results reveal anomalous diffusion behavior that deviates significantly from bulk properties. We develop a theoretical model that captures the confinement-induced dynamics.",
        "authors": ["Alice Wang", "Bob Chen"],
        "journal": "Macromolecules",
        "url": "https://pubs.acs.org/doi/10.1021/acs.macromol.2024.001",
        "doi": "10.1021/acs.macromol.2024.001",
        "published_date": datetime.now() - timedelta(days=3),
        "citation_count": 8,
        "fields_of_study": ["polymer science", "molecular dynamics", "nanomaterials"],
    },
]

# User's research interests
INTERESTS = [
    ResearchInterest(
        name="Machine Learning for Molecular Simulations",
        description="Using ML and deep learning for enhanced sampling, collective variables, and force field development in MD simulations.",
        keywords=["machine learning", "deep learning", "molecular dynamics",
                  "enhanced sampling", "collective variables", "neural network"],
        followed_journals=["Journal of Chemical Theory and Computation"],
        fields_of_study=["machine learning", "computational chemistry"],
    ),
    ResearchInterest(
        name="Agentic AI Systems",
        description="Autonomous AI agents, multi-agent systems, and AI-driven scientific discovery.",
        keywords=["agent", "agentic", "autonomous", "LLM", "multi-agent"],
        followed_journals=["Nature Machine Intelligence"],
    ),
]


async def test_ai_summarization():
    """Test AI summarization with real Gemini API."""
    console.print("\n[bold cyan]Testing AI Summarization Service[/bold cyan]\n")

    # Initialize summarization service (not mock mode - uses real API)
    summarizer = SummarizationService(mock_mode=False)

    if summarizer.mock_mode:
        console.print("[yellow]Warning: Running in mock mode (no API key)[/yellow]\n")
    else:
        console.print("[green]Using real Gemini API for summaries[/green]\n")

    # Test single paper summary
    paper = SAMPLE_PAPERS[0]
    console.print(f"[bold]Summarizing:[/bold] {paper['title'][:60]}...\n")

    summary = await summarizer.generate_summary(
        title=paper["title"],
        abstract=paper["abstract"],
    )
    console.print(f"[green]Summary:[/green] {summary}\n")

    # Test relevance explanation
    relevance = await summarizer.generate_relevance_explanation(
        title=paper["title"],
        abstract=paper["abstract"],
        interest_name=INTERESTS[0].name,
        interest_description=INTERESTS[0].description,
        keywords=INTERESTS[0].keywords,
        relevance_score=0.85,
    )
    console.print(f"[green]Why it matters:[/green] {relevance}\n")

    return True


async def test_full_ai_digest(user_email: str):
    """Test full digest generation with AI summaries."""
    console.print("\n[bold cyan]Testing Full AI-Enhanced Digest[/bold cyan]\n")

    # Create digest service with AI summaries enabled
    service = DigestService(
        mock_mode=False,  # Use real embeddings if API key available
        enable_ai_summaries=True,
        max_papers_to_summarize=5,
    )

    console.print(f"[dim]Generating digest for {user_email}...[/dim]\n")

    # Generate digest
    digest = await service.generate_digest(
        user_name="Alim Altamimi",
        user_email=user_email,
        interests=INTERESTS,
        papers=SAMPLE_PAPERS,
        digest_type="weekly",
        min_score=0.05,
        max_papers_per_section=5,
    )

    console.print(f"[green]Digest generated![/green]")
    console.print(f"  Subject: {digest.subject_line}")
    console.print(f"  Total papers: {digest.total_papers}")
    console.print(f"  Sections: {len(digest.sections)}\n")

    # Show papers with AI summaries
    for section in digest.sections:
        console.print(f"\n[bold magenta]{section.interest_name}[/bold magenta]")
        console.print(f"Papers: {len(section.papers)}\n")

        for paper in section.papers[:3]:  # Show top 3
            console.print(f"  [bold]{paper.title[:60]}...[/bold]")
            console.print(f"  Score: {paper.score_percent}%")
            if paper.summary:
                console.print(f"  [green]Summary:[/green] {paper.summary[:150]}...")
            if paper.why_relevant:
                console.print(f"  [blue]Why it matters:[/blue] {paper.why_relevant[:150]}...")
            console.print()

    return digest


async def test_email_delivery(digest, user_email: str):
    """Test email rendering and delivery (console mode)."""
    console.print("\n[bold cyan]Testing Email Delivery[/bold cyan]\n")

    renderer = DigestRenderer()
    sender = EmailSender(mock_mode=True)  # Console output

    # Render
    html_content, text_content = renderer.render(digest)

    console.print(f"HTML: {len(html_content)} chars, Text: {len(text_content)} chars")

    # Save HTML for viewing
    output_path = PROJECT_ROOT / "ai_digest_output.html"
    with open(output_path, "w") as f:
        f.write(html_content)
    console.print(f"[bold]HTML saved to: {output_path}[/bold]\n")

    # Send (console mode)
    success = await sender.send(
        to_email=user_email,
        subject=digest.subject_line,
        html_content=html_content,
        text_content=text_content,
    )

    return success


async def main():
    """Run all tests."""
    user_email = "altamimialim1@gmail.com"

    console.print("[bold magenta]PaperPulse AI-Enhanced Email Test[/bold magenta]")
    console.print("=" * 60)
    console.print(f"[dim]Target email: {user_email}[/dim]\n")

    try:
        # Test AI summarization
        await test_ai_summarization()

        # Test full digest
        digest = await test_full_ai_digest(user_email)

        # Test email delivery
        await test_email_delivery(digest, user_email)

        console.print("\n[bold green]All tests passed![/bold green]")

    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
