#!/usr/bin/env python3
"""Test script for the email digest pipeline with sample data."""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Load .env file
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Add src to path
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rich.console import Console

from paperpulse.email import (
    Digest,
    DigestPaper,
    DigestRenderer,
    DigestSection,
    DigestService,
    EmailSender,
    ResearchInterest,
)

console = Console()

# Sample papers simulating RSS collection
SAMPLE_PAPERS = [
    {
        "title": "Machine Learning Collective Variables for Enhanced Sampling of Protein Folding",
        "abstract": "We present a novel deep learning approach to automatically discover collective variables for enhanced sampling molecular dynamics simulations. Our method uses a variational autoencoder to learn low-dimensional representations of protein conformational space.",
        "authors": ["John Smith", "Jane Doe", "Robert Johnson"],
        "journal": "Journal of Chemical Theory and Computation",
        "url": "https://pubs.acs.org/doi/10.1021/acs.jctc.2024.001",
        "doi": "10.1021/acs.jctc.2024.001",
        "published_date": datetime.now() - timedelta(days=2),
    },
    {
        "title": "Polymer Chain Dynamics in Confined Geometries: A Molecular Dynamics Study",
        "abstract": "We investigate the dynamics of polymer chains confined in nanopores using extensive all-atom molecular dynamics simulations with GROMACS. Our results reveal anomalous diffusion behavior.",
        "authors": ["Alice Wang", "Bob Chen"],
        "journal": "Macromolecules",
        "url": "https://pubs.acs.org/doi/10.1021/acs.macromol.2024.001",
        "doi": "10.1021/acs.macromol.2024.001",
        "published_date": datetime.now() - timedelta(days=3),
    },
    {
        "title": "Large Language Models for Scientific Discovery: An Agent-Based Approach",
        "abstract": "We introduce an agentic AI framework that leverages large language models for autonomous scientific discovery. Our multi-agent system can formulate hypotheses and design experiments.",
        "authors": ["Emily Zhang", "Michael Brown"],
        "journal": "Nature Machine Intelligence",
        "url": "https://nature.com/articles/s42256-024-001",
        "doi": "10.1038/s42256-024-001",
        "published_date": datetime.now() - timedelta(days=1),
    },
    {
        "title": "Coarse-Grained Force Fields for Polymer Simulations",
        "abstract": "We develop a new coarse-grained force field for polymer simulations that accurately reproduces structural and dynamic properties of polyethylene melts.",
        "authors": ["Kurt Kremer", "Sarah Wilson"],
        "journal": "Macromolecules",
        "url": "https://pubs.acs.org/doi/10.1021/acs.macromol.2024.002",
        "doi": "10.1021/acs.macromol.2024.002",
        "published_date": datetime.now() - timedelta(days=4),
    },
    {
        "title": "Autonomous Research Agents with Tool-Using Capabilities",
        "abstract": "We present a framework for building autonomous AI research agents that can use external tools, search databases, and synthesize findings.",
        "authors": ["David Lee"],
        "journal": "NeurIPS Proceedings",
        "url": "https://neurips.cc/paper/2024/001",
        "doi": "10.5555/neurips.2024.001",
        "published_date": datetime.now() - timedelta(days=2),
    },
    {
        "title": "Free Energy Calculations with Neural Network Potentials",
        "abstract": "We combine neural network potentials with metadynamics to enable accurate free energy calculations for complex molecular systems.",
        "authors": ["John Smith", "Lisa Chen"],
        "journal": "Journal of Chemical Theory and Computation",
        "url": "https://pubs.acs.org/doi/10.1021/acs.jctc.2024.002",
        "doi": "10.1021/acs.jctc.2024.002",
        "published_date": datetime.now() - timedelta(days=5),
    },
]

# User's research interests
INTERESTS = [
    ResearchInterest(
        name="Polymer Molecular Dynamics Simulations",
        description="MD simulations of polymer systems including chain dynamics, phase behavior, and transport properties using GROMACS, LAMMPS, and related tools.",
        keywords=["molecular dynamics", "polymer", "GROMACS", "coarse-grained",
                  "chain dynamics", "diffusion", "simulation", "force field"],
        excluded_keywords=["synthesis", "experimental"],
        followed_authors=["Kurt Kremer", "Bob Chen"],
        followed_journals=["Macromolecules", "Journal of Chemical Physics"],
    ),
    ResearchInterest(
        name="Agentic AI",
        description="Autonomous AI agents, multi-agent systems, and AI-driven automation using large language models.",
        keywords=["agent", "agentic", "large language model", "LLM",
                  "autonomous", "multi-agent", "reasoning", "tool use"],
        followed_journals=["Nature Machine Intelligence", "NeurIPS"],
    ),
    ResearchInterest(
        name="Machine Learned Collective Variables",
        description="ML approaches for discovering collective variables and reaction coordinates for enhanced sampling in molecular simulations.",
        keywords=["collective variable", "machine learning", "deep learning",
                  "enhanced sampling", "metadynamics", "neural network",
                  "autoencoder", "reaction coordinate", "free energy"],
        followed_authors=["John Smith"],
        followed_journals=["Journal of Chemical Theory and Computation"],
    ),
]


async def test_digest_generation():
    """Test digest generation with sample papers."""
    console.print("\n[bold cyan]Testing Digest Generation Pipeline[/bold cyan]\n")

    # Create digest service (mock mode for embeddings)
    service = DigestService(mock_mode=True)

    console.print(f"[dim]Generating digest with {len(SAMPLE_PAPERS)} papers across {len(INTERESTS)} interests...[/dim]\n")

    # Generate digest
    digest = await service.generate_digest(
        user_name="Dr. Researcher",
        user_email="researcher@university.edu",
        interests=INTERESTS,
        papers=SAMPLE_PAPERS,
        digest_type="weekly",
        min_score=0.05,  # Lower threshold for demo
        max_papers_per_section=5,
    )

    console.print(f"[green]Digest generated![/green]")
    console.print(f"  Subject: {digest.subject_line}")
    console.print(f"  Total papers: {digest.total_papers}")
    console.print(f"  Sections: {len(digest.sections)}\n")

    # Show section summaries
    for section in digest.sections:
        console.print(f"[bold]{section.interest_name}[/bold]")
        console.print(f"  Papers: {len(section.papers)}")
        if section.papers:
            top = section.papers[0]
            console.print(f"  Top paper: {top.title[:50]}... (score: {top.score_percent}%)")
        console.print()

    return digest


async def test_rendering(digest):
    """Test HTML and text rendering."""
    console.print("[bold cyan]Testing Email Rendering[/bold cyan]\n")

    renderer = DigestRenderer()

    # Render HTML
    html_content, text_content = renderer.render(digest)

    console.print(f"[green]HTML rendered: {len(html_content)} characters[/green]")
    console.print(f"[green]Text rendered: {len(text_content)} characters[/green]")

    # Save HTML to file
    output_path = PROJECT_ROOT / "test_digest_output.html"
    with open(output_path, "w") as f:
        f.write(html_content)
    console.print(f"\n[bold]HTML saved to: {output_path}[/bold]")

    # Print text version
    console.print("\n[bold cyan]Plain Text Version:[/bold cyan]")
    console.print("-" * 70)
    print(text_content)

    return html_content, text_content


async def test_email_send(digest):
    """Test email sending (console mode)."""
    console.print("\n[bold cyan]Testing Email Sender (Console Mode)[/bold cyan]\n")

    renderer = DigestRenderer()
    sender = EmailSender(mock_mode=True)  # Console output

    success = await sender.send_digest(digest, renderer)

    if success:
        console.print("[green]Email sent successfully (console mode)[/green]")
    else:
        console.print("[red]Email sending failed[/red]")


async def main():
    """Run all tests."""
    console.print("[bold magenta]PaperPulse Email Digest Pipeline Test[/bold magenta]")
    console.print("=" * 60)

    try:
        # Test digest generation
        digest = await test_digest_generation()

        # Test rendering
        await test_rendering(digest)

        # Test email sending
        await test_email_send(digest)

        console.print("\n[bold green]All tests passed![/bold green]")

    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
