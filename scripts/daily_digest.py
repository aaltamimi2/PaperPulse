#!/usr/bin/env python3
"""Daily digest script for cron - filters out previously sent papers."""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Load environment
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from rich.console import Console

from paperpulse.collectors import ArxivCollector, PubMedCollector
from paperpulse.email import DigestRenderer, DigestService, ResearchInterest
from paperpulse.email.models import SuggestedAuthor
from paperpulse import profile, history

console = Console()

# Load followed authors from profile
profile.init_default_authors([
    "Steven De Meester", "Reid C. Van Lehn", "Siewert J. Marrink",
    "George Huber", "Frank Noé", "Cecilia Clementi",
])
FOLLOWED_AUTHORS = profile.get_followed_authors()

# Research interests
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
    ResearchInterest(
        name="AI & Foundation Models",
        description="Advances in agentic AI, large language models, foundation models, reasoning, and AI systems.",
        keywords=["large language model", "LLM", "foundation model", "agentic",
                  "transformer", "GPT", "reasoning", "AI agent", "prompt"],
        followed_journals=["Nature Machine Intelligence", "NeurIPS", "ICML"],
        fields_of_study=["artificial intelligence", "machine learning", "natural language processing"],
    ),
]


async def collect_papers(days_back: int = 2):
    """Collect papers from the last N days."""
    all_papers = []

    # Collect from arXiv
    console.print("[cyan]Collecting from arXiv...[/cyan]")
    arxiv = ArxivCollector()

    queries = [
        "machine learning molecular dynamics",
        "neural network force field",
        "polymer molecular dynamics simulation",
        "enhanced sampling deep learning",
        "large language model reasoning",
        "agentic AI systems",
        "foundation model",
    ]

    for query in queries:
        try:
            papers = await arxiv.search_papers(query, limit=10, days_back=days_back)
            all_papers.extend(papers)
        except Exception as e:
            console.print(f"[yellow]arXiv error for '{query}': {e}[/yellow]")

    await arxiv.close()

    # Collect from PubMed
    console.print("[cyan]Collecting from PubMed...[/cyan]")
    pubmed = PubMedCollector()

    pubmed_queries = [
        "molecular dynamics machine learning",
        "polymer simulation coarse grained",
    ]

    for query in pubmed_queries:
        try:
            papers = await pubmed.search_papers(query, limit=10, days_back=days_back)
            all_papers.extend(papers)
        except Exception as e:
            console.print(f"[yellow]PubMed error for '{query}': {e}[/yellow]")

    await pubmed.close()

    # Deduplicate by title
    seen_titles = set()
    unique_papers = []
    for paper in all_papers:
        title_key = paper.title.lower()[:50]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_papers.append(paper)

    console.print(f"[green]Collected {len(unique_papers)} unique papers[/green]")
    return unique_papers


async def send_daily_digest(user_email: str):
    """Generate and send the daily digest, filtering out previously sent papers."""
    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    console.print(f"\n[bold magenta]📬 PaperPulse Daily Digest - {datetime.now().strftime('%Y-%m-%d')}[/bold magenta]")
    console.print("=" * 60)

    # Check last run
    last_run = history.get_last_run()
    if last_run:
        console.print(f"Last run: {last_run.strftime('%Y-%m-%d %H:%M')}")

    # Collect papers from last 2 days (to catch any we missed)
    papers = await collect_papers(days_back=2)

    if not papers:
        console.print("[yellow]No papers collected, exiting.[/yellow]")
        return False

    # Convert to dicts
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

    # Filter out previously sent papers
    unsent_papers = history.filter_unsent_papers(paper_dicts, days_to_check=7)
    console.print(f"[cyan]New papers (not sent in last 7 days): {len(unsent_papers)}[/cyan]")

    if not unsent_papers:
        console.print("[yellow]No new papers to send today.[/yellow]")
        return True  # Success, just nothing new

    # Generate digest
    console.print("[cyan]Generating digest with AI summaries...[/cyan]")
    service = DigestService(
        mock_mode=False,
        enable_ai_summaries=True,
        max_papers_to_summarize=5,
    )

    digest = await service.generate_digest(
        user_name="Ali",
        user_email=user_email,
        interests=INTERESTS,
        papers=unsent_papers,
        digest_type="daily",
        min_score=0.1,
        max_papers_per_section=5,
    )

    # Add followed/suggested authors
    digest.followed_authors = FOLLOWED_AUTHORS

    # Generate suggested authors
    author_counts = {}
    author_papers = {}
    for section in digest.sections:
        for p in section.papers:
            if p.relevance_score >= 0.4:
                for author in (p.authors or [])[:3]:
                    author_lower = author.lower()
                    already_followed = any(f.lower() in author_lower or author_lower in f.lower()
                                          for f in FOLLOWED_AUTHORS)
                    if not already_followed:
                        author_counts[author] = author_counts.get(author, 0) + 1
                        if author not in author_papers:
                            author_papers[author] = p.title

    suggested = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    digest.suggested_authors = [
        SuggestedAuthor(name=author, paper_count=count, sample_paper=author_papers.get(author))
        for author, count in suggested
    ]

    console.print(f"[green]Digest: {digest.total_papers} papers across {len(digest.sections)} sections[/green]")

    if digest.total_papers == 0:
        console.print("[yellow]No relevant papers found today.[/yellow]")
        return True

    # Show summary
    for section in digest.sections:
        console.print(f"  {section.interest_name}: {len(section.papers)} papers")

    # Render and send
    renderer = DigestRenderer()
    html_content, text_content = renderer.render(digest)

    console.print(f"[cyan]Sending to {user_email}...[/cyan]")

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
            username=os.environ.get("EMAIL_SMTP_USER", "altamimialim1@gmail.com"),
            password=os.environ.get("EMAIL_SMTP_PASSWORD", ""),
            start_tls=True,
        )
        console.print(f"[bold green]✅ Email sent![/bold green]")

        # Mark papers as sent
        sent_paper_dicts = []
        for section in digest.sections:
            for p in section.papers:
                sent_paper_dicts.append({
                    "title": p.title,
                    "doi": p.doi,
                    "arxiv_id": getattr(p, 'arxiv_id', None),
                })
        history.mark_papers_sent(sent_paper_dicts)
        console.print(f"[dim]Marked {len(sent_paper_dicts)} papers as sent[/dim]")

        # Cleanup old history
        removed = history.cleanup_old_history(days_to_keep=30)
        if removed:
            console.print(f"[dim]Cleaned up {removed} old history entries[/dim]")

        return True

    except Exception as e:
        console.print(f"[bold red]❌ Failed: {e}[/bold red]")
        return False


async def main():
    user_email = "altamimialim1@gmail.com"
    success = await send_daily_digest(user_email)
    return 0 if success else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
