"""PaperPulse command-line interface."""

import asyncio
from typing import Optional

import structlog
import typer
from rich.console import Console
from rich.table import Table

from paperpulse import __version__

app = typer.Typer(
    name="paperpulse",
    help="AI-powered academic paper recommendation system",
    no_args_is_help=True,
)
console = Console()

# Configure structlog for CLI
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """PaperPulse - AI-powered paper recommendations."""
    import logging

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level)


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"PaperPulse v{__version__}")


# Feed management commands
feeds_app = typer.Typer(help="Manage RSS feeds")
app.add_typer(feeds_app, name="feeds")


@feeds_app.command("list-acs")
def list_acs_feeds(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
) -> None:
    """List available ACS journal feeds."""
    from paperpulse.collectors.acs_feeds import ACS_FEEDS, get_feeds_by_category

    if category:
        feeds = get_feeds_by_category(category)
    else:
        feeds = list(ACS_FEEDS.values())

    if not feeds:
        console.print(f"[yellow]No feeds found for category: {category}[/yellow]")
        return

    table = Table(title="ACS Journal RSS Feeds")
    table.add_column("Code", style="cyan")
    table.add_column("Journal Name", style="green")
    table.add_column("Categories", style="dim")

    for feed in sorted(feeds, key=lambda f: f.journal_code):
        table.add_row(
            feed.journal_code,
            feed.journal_name,
            ", ".join(feed.categories),
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(feeds)} feeds[/dim]")


@feeds_app.command("test")
def test_feed(
    url: str = typer.Argument(..., help="RSS feed URL to test"),
    show_entries: int = typer.Option(5, "--entries", "-n", help="Number of entries to show"),
) -> None:
    """Test an RSS feed URL."""

    async def _test() -> None:
        from paperpulse.collectors.rss_collector import RSSCollector

        collector = RSSCollector()

        console.print(f"[dim]Testing feed: {url}[/dim]\n")

        is_valid, error = await collector.validate_feed(url)

        if not is_valid:
            console.print(f"[red]Feed validation failed: {error}[/red]")
            await collector.close()
            return

        result = await collector.collect(
            feed_id="test",
            feed_url=url,
            feed_name="Test Feed",
        )

        await collector.close()

        if result.error:
            console.print(f"[red]Collection error: {result.error}[/red]")
            return

        console.print(f"[green]Feed is valid![/green]")
        console.print(f"Papers found: {result.total_count}\n")

        if result.papers:
            table = Table(title=f"Recent Papers (showing {min(show_entries, len(result.papers))})")
            table.add_column("Title", style="cyan", max_width=60)
            table.add_column("Authors", style="dim", max_width=30)
            table.add_column("DOI", style="green")

            for paper in result.papers[:show_entries]:
                authors = ", ".join(paper.authors[:2])
                if len(paper.authors) > 2:
                    authors += " et al."
                table.add_row(
                    paper.title[:60] + ("..." if len(paper.title) > 60 else ""),
                    authors or "[dim]N/A[/dim]",
                    paper.doi or "[dim]N/A[/dim]",
                )

            console.print(table)

    asyncio.run(_test())


@feeds_app.command("test-acs")
def test_acs_feed(
    code: str = typer.Argument(..., help="ACS journal code (e.g., 'jctc', 'macromolecules')"),
    show_entries: int = typer.Option(5, "--entries", "-n", help="Number of entries to show"),
) -> None:
    """Test an ACS journal feed by code."""
    from paperpulse.collectors.acs_feeds import get_feed_by_code

    feed_config = get_feed_by_code(code)
    if not feed_config:
        console.print(f"[red]Unknown ACS journal code: {code}[/red]")
        console.print("[dim]Use 'paperpulse feeds list-acs' to see available codes[/dim]")
        raise typer.Exit(1)

    console.print(f"[bold]{feed_config.journal_name}[/bold]")
    console.print(f"[dim]{feed_config.description}[/dim]\n")

    # Reuse test_feed logic
    test_feed(feed_config.feed_url, show_entries)


# Collection commands
collect_app = typer.Typer(help="Collect papers from feeds")
app.add_typer(collect_app, name="collect")


@collect_app.command("acs")
def collect_acs(
    codes: list[str] = typer.Argument(
        None,
        help="ACS journal codes to collect (defaults to all)",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't save to database"),
) -> None:
    """Collect papers from ACS journal feeds."""
    from paperpulse.collectors.acs_feeds import ACS_FEEDS, get_feed_by_code

    async def _collect() -> None:
        from paperpulse.collectors.rss_collector import RSSCollector

        if codes:
            feeds = []
            for code in codes:
                feed = get_feed_by_code(code)
                if feed:
                    feeds.append(feed)
                else:
                    console.print(f"[yellow]Unknown code: {code}, skipping[/yellow]")
        else:
            feeds = list(ACS_FEEDS.values())

        if not feeds:
            console.print("[red]No valid feeds to collect[/red]")
            return

        collector = RSSCollector()
        total_papers = 0
        results_table = Table(title="Collection Results")
        results_table.add_column("Journal", style="cyan")
        results_table.add_column("Papers", justify="right")
        results_table.add_column("Status", style="green")

        for feed in feeds:
            console.print(f"[dim]Collecting from {feed.journal_name}...[/dim]")

            result = await collector.collect(
                feed_id=feed.journal_code,
                feed_url=feed.feed_url,
                feed_name=feed.display_name,
                journal_name=feed.journal_name,
            )

            status = "[green]OK[/green]" if result.success else f"[red]{result.error}[/red]"
            results_table.add_row(
                feed.journal_name,
                str(result.total_count),
                status,
            )
            total_papers += result.total_count

            if not dry_run and result.success and result.papers:
                # TODO: Save to database
                pass

        await collector.close()

        console.print()
        console.print(results_table)
        console.print(f"\n[bold]Total papers collected: {total_papers}[/bold]")

        if dry_run:
            console.print("[yellow]Dry run - papers not saved to database[/yellow]")

    asyncio.run(_collect())


# Database commands
db_app = typer.Typer(help="Database operations")
app.add_typer(db_app, name="db")


@db_app.command("init")
def init_database() -> None:
    """Initialize database tables."""

    async def _init() -> None:
        from paperpulse.db import init_db

        console.print("[dim]Initializing database...[/dim]")
        await init_db()
        console.print("[green]Database initialized successfully![/green]")

    asyncio.run(_init())


# Digest commands
digest_app = typer.Typer(help="Generate and send paper digests")
app.add_typer(digest_app, name="digest")


@digest_app.command("preview")
def preview_digest(
    journals: list[str] = typer.Option(
        ["jctc", "macromolecules"],
        "--journal", "-j",
        help="ACS journal codes to collect from",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="Output HTML file (prints text to console if not specified)",
    ),
) -> None:
    """Generate a preview digest with sample research interests."""

    async def _preview() -> None:
        from paperpulse.collectors.acs_feeds import get_feed_by_code
        from paperpulse.collectors.rss_collector import RSSCollector
        from paperpulse.email import DigestRenderer, DigestService, ResearchInterest

        # Define sample research interests (user's interests)
        interests = [
            ResearchInterest(
                name="Polymer Molecular Dynamics Simulations",
                description="MD simulations of polymer systems using GROMACS, LAMMPS",
                keywords=["molecular dynamics", "polymer", "GROMACS", "coarse-grained",
                         "chain dynamics", "diffusion", "simulation", "force field"],
                excluded_keywords=["synthesis", "experimental"],
                followed_journals=["Macromolecules", "Journal of Chemical Physics"],
            ),
            ResearchInterest(
                name="Agentic AI",
                description="Autonomous AI agents and LLM-based systems",
                keywords=["agent", "agentic", "large language model", "LLM",
                         "autonomous", "multi-agent", "reasoning"],
                followed_journals=["Nature Machine Intelligence"],
            ),
            ResearchInterest(
                name="Machine Learned Collective Variables",
                description="ML approaches for enhanced sampling in molecular simulations",
                keywords=["collective variable", "machine learning", "deep learning",
                         "enhanced sampling", "metadynamics", "neural network",
                         "autoencoder", "reaction coordinate", "free energy"],
                followed_journals=["Journal of Chemical Theory and Computation"],
            ),
        ]

        # Collect papers from specified journals
        collector = RSSCollector()
        all_papers = []

        for code in journals:
            feed = get_feed_by_code(code)
            if not feed:
                console.print(f"[yellow]Unknown journal code: {code}[/yellow]")
                continue

            console.print(f"[dim]Collecting from {feed.journal_name}...[/dim]")
            result = await collector.collect(
                feed_id=feed.journal_code,
                feed_url=feed.feed_url,
                feed_name=feed.display_name,
                journal_name=feed.journal_name,
            )

            if result.success:
                all_papers.extend(result.papers)
                console.print(f"  Found {len(result.papers)} papers")

        await collector.close()

        if not all_papers:
            console.print("[red]No papers collected![/red]")
            return

        console.print(f"\n[bold]Total papers: {len(all_papers)}[/bold]")
        console.print("[dim]Generating digest...[/dim]\n")

        # Generate digest
        service = DigestService(mock_mode=True)
        digest = await service.generate_digest(
            user_name="Researcher",
            user_email="researcher@example.com",
            interests=interests,
            papers=all_papers,
            digest_type="weekly",
        )

        # Render
        renderer = DigestRenderer()
        html_content, text_content = renderer.render(digest)

        if output:
            with open(output, "w") as f:
                f.write(html_content)
            console.print(f"[green]HTML digest saved to: {output}[/green]")
        else:
            # Print text version to console
            console.print(text_content)

    asyncio.run(_preview())


@digest_app.command("send")
def send_digest(
    email: str = typer.Argument(..., help="Recipient email address"),
    journals: list[str] = typer.Option(
        ["jctc", "macromolecules"],
        "--journal", "-j",
        help="ACS journal codes to collect from",
    ),
    console_only: bool = typer.Option(
        True,
        "--console/--smtp",
        help="Print to console instead of sending via SMTP",
    ),
) -> None:
    """Generate and send a digest email."""

    async def _send() -> None:
        from paperpulse.collectors.acs_feeds import get_feed_by_code
        from paperpulse.collectors.rss_collector import RSSCollector
        from paperpulse.email import (
            DigestRenderer,
            DigestService,
            EmailSender,
            ResearchInterest,
        )

        # Same interests as preview
        interests = [
            ResearchInterest(
                name="Polymer Molecular Dynamics Simulations",
                description="MD simulations of polymer systems",
                keywords=["molecular dynamics", "polymer", "GROMACS", "simulation"],
            ),
            ResearchInterest(
                name="Agentic AI",
                description="Autonomous AI agents and LLM systems",
                keywords=["agent", "LLM", "autonomous", "multi-agent"],
            ),
            ResearchInterest(
                name="Machine Learned Collective Variables",
                description="ML for enhanced sampling",
                keywords=["collective variable", "machine learning", "enhanced sampling"],
            ),
        ]

        # Collect papers
        collector = RSSCollector()
        all_papers = []

        for code in journals:
            feed = get_feed_by_code(code)
            if not feed:
                continue

            console.print(f"[dim]Collecting from {feed.journal_name}...[/dim]")
            result = await collector.collect(
                feed_id=feed.journal_code,
                feed_url=feed.feed_url,
                feed_name=feed.display_name,
                journal_name=feed.journal_name,
            )

            if result.success:
                all_papers.extend(result.papers)

        await collector.close()

        if not all_papers:
            console.print("[red]No papers collected![/red]")
            return

        # Generate and send
        service = DigestService(mock_mode=True)
        digest = await service.generate_digest(
            user_name=email.split("@")[0],
            user_email=email,
            interests=interests,
            papers=all_papers,
        )

        renderer = DigestRenderer()
        sender = EmailSender(mock_mode=console_only)

        success = await sender.send_digest(digest, renderer)

        if success:
            console.print("[green]Digest sent successfully![/green]")
        else:
            console.print("[red]Failed to send digest[/red]")

    asyncio.run(_send())


if __name__ == "__main__":
    app()
