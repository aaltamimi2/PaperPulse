#!/usr/bin/env python3
"""Collect REAL papers from academic APIs and send digest email."""

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Configure environment - loads from .env file
# Get a new API key from: https://makersuite.google.com/app/apikey
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from rich.console import Console

from paperpulse.collectors import ArxivCollector, PubMedCollector
from paperpulse.email import DigestRenderer, DigestService, ResearchInterest

console = Console()

# Followed authors (from Google Scholar profiles)
FOLLOWED_AUTHORS = [
    "Steven De Meester",
    "Reid C. Van Lehn",
    "Reid Van Lehn",
    "Siewert J. Marrink",
    "Siewert Marrink",
    "George Huber",
    "George W. Huber",
    "Frank Noé",
    "Frank Noe",
    "Cecilia Clementi",
]

# Your actual research interests
INTERESTS = [
    ResearchInterest(
        name="Machine Learning for Molecular Simulations",
        description="Using ML and deep learning for enhanced sampling, collective variables, and force field development in MD simulations.",
        keywords=["machine learning", "molecular dynamics", "deep learning",
                  "enhanced sampling", "collective variables", "neural network", "GROMACS"],
        followed_authors=FOLLOWED_AUTHORS,
        followed_journals=["Journal of Chemical Theory and Computation", "Journal of Chemical Physics"],
        fields_of_study=["machine learning", "computational chemistry", "molecular dynamics"],
    ),
    ResearchInterest(
        name="Polymer Simulations",
        description="Molecular dynamics simulations of polymer systems, coarse-graining, and polymer physics.",
        keywords=["polymer", "molecular dynamics", "coarse-grained", "GROMACS",
                  "chain dynamics", "diffusion", "melt"],
        followed_authors=FOLLOWED_AUTHORS,
        followed_journals=["Macromolecules", "Soft Matter"],
        fields_of_study=["polymer science", "materials science"],
    ),
]


async def collect_real_papers():
    """Collect real papers from arXiv and PubMed."""
    all_papers = []

    # Collect from arXiv
    console.print("\n[bold cyan]Collecting from arXiv...[/bold cyan]")
    arxiv = ArxivCollector()

    queries = [
        "machine learning molecular dynamics",
        "neural network force field",
        "polymer molecular dynamics simulation",
        "enhanced sampling deep learning",
    ]

    for query in queries:
        try:
            console.print(f"  Searching: {query}")
            papers = await arxiv.search_papers(query, limit=15, days_back=30)
            all_papers.extend(papers)
            console.print(f"    Found {len(papers)} papers")
        except Exception as e:
            console.print(f"    [yellow]Error: {e}[/yellow]")

    await arxiv.close()

    # Collect from PubMed
    console.print("\n[bold cyan]Collecting from PubMed...[/bold cyan]")

    # PubMed requires an email
    os.environ["PUBMED_EMAIL"] = "altamimialim1@gmail.com"

    pubmed = PubMedCollector()

    pubmed_queries = [
        "molecular dynamics machine learning",
        "polymer simulation coarse grained",
    ]

    for query in pubmed_queries:
        try:
            console.print(f"  Searching: {query}")
            papers = await pubmed.search_papers(query, limit=15, days_back=30)
            all_papers.extend(papers)
            console.print(f"    Found {len(papers)} papers")
        except Exception as e:
            console.print(f"    [yellow]Error: {e}[/yellow]")

    await pubmed.close()

    # Deduplicate by title similarity
    seen_titles = set()
    unique_papers = []
    for paper in all_papers:
        title_key = paper.title.lower()[:50]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_papers.append(paper)

    console.print(f"\n[green]Total unique papers collected: {len(unique_papers)}[/green]")

    return unique_papers


async def send_real_digest(papers, user_email: str):
    """Generate and send digest with real papers."""
    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    # Convert CollectedPaper objects to dicts
    paper_dicts = []
    for p in papers:
        paper_dicts.append({
            "title": p.title,
            "abstract": p.abstract,
            "authors": p.authors,
            "journal": p.journal,
            "url": p.url,
            "doi": p.doi,
            "published_date": p.published_date,
            "arxiv_id": p.arxiv_id,
            "citation_count": p.citation_count,
            "fields_of_study": p.fields_of_study,
        })

    console.print(f"\n[bold cyan]Generating AI-enhanced digest...[/bold cyan]")

    # NOTE: Set mock_mode=False once you have a valid Gemini API key
    # Current key was leaked and needs replacement from: https://makersuite.google.com/app/apikey
    use_real_embeddings = os.environ.get("USE_REAL_EMBEDDINGS", "false").lower() == "true"

    service = DigestService(
        mock_mode=not use_real_embeddings,  # Toggle with USE_REAL_EMBEDDINGS=true
        enable_ai_summaries=not use_real_embeddings,  # AI summaries need valid key too
        max_papers_to_summarize=10,
    )

    digest = await service.generate_digest(
        user_name="Ali",
        user_email=user_email,
        interests=INTERESTS,
        papers=paper_dicts,
        digest_type="weekly",
        min_score=0.1,
        max_papers_per_section=10,
    )

    console.print(f"[green]Digest generated: {digest.total_papers} papers[/green]")

    # Show what we're sending with score details
    for section in digest.sections:
        console.print(f"\n[bold]{section.interest_name}[/bold]: {len(section.papers)} papers")
        for p in section.papers[:5]:
            console.print(f"  • {p.title[:55]}... [cyan]{p.score_percent}%[/cyan]")

    # Suggest authors to follow (authors from highly-scored papers not already followed)
    console.print(f"\n[bold yellow]📝 Suggested Authors to Follow:[/bold yellow]")
    author_counts = {}
    for section in digest.sections:
        for p in section.papers:
            if p.relevance_score >= 0.4:  # Only from relevant papers
                for author in (p.authors or [])[:3]:  # First 3 authors per paper
                    # Check if not already followed
                    author_lower = author.lower()
                    already_followed = any(f.lower() in author_lower or author_lower in f.lower()
                                          for f in FOLLOWED_AUTHORS)
                    if not already_followed:
                        author_counts[author] = author_counts.get(author, 0) + 1

    # Show top suggested authors
    suggested = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    for author, count in suggested:
        console.print(f"  • {author} (appears in {count} relevant papers)")

    # Render and send
    renderer = DigestRenderer()
    html_content, text_content = renderer.render(digest)

    console.print(f"\n[bold cyan]Sending email to {user_email}...[/bold cyan]")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = digest.subject_line
    msg["From"] = "PaperPulse <altamimialim1@gmail.com>"
    msg["To"] = user_email

    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            username="altamimialim1@gmail.com",
            password="ykoc mpwo mgnj qvhw",
            start_tls=True,
        )
        console.print(f"\n[bold green]✅ Email sent successfully![/bold green]")
        console.print(f"   Subject: {digest.subject_line}")
        return True
    except Exception as e:
        console.print(f"\n[bold red]❌ Failed: {e}[/bold red]")
        return False


async def main():
    user_email = "altamimialim1@gmail.com"

    console.print("[bold magenta]PaperPulse - Real Papers Digest[/bold magenta]")
    console.print("=" * 60)

    # Collect real papers
    papers = await collect_real_papers()

    if not papers:
        console.print("[red]No papers collected![/red]")
        return 1

    # Send digest
    success = await send_real_digest(papers, user_email)

    return 0 if success else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
