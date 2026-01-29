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


# API commands (Phase 3)
api_app = typer.Typer(help="API server operations")
app.add_typer(api_app, name="api")


@api_app.command("serve")
def serve_api(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to listen on"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
) -> None:
    """Start the FastAPI server."""
    from paperpulse.api import run_server

    console.print(f"[bold]Starting PaperPulse API server[/bold]")
    console.print(f"[dim]Host: {host}, Port: {port}, Reload: {reload}[/dim]")
    console.print(f"[green]API docs: http://{host}:{port}/api/docs[/green]\n")

    run_server(host=host, port=port, reload=reload)


@api_app.command("routes")
def list_routes() -> None:
    """List all API routes."""
    table = Table(title="PaperPulse API Routes")
    table.add_column("Method", style="cyan")
    table.add_column("Path", style="green")
    table.add_column("Description", style="dim")

    routes = [
        ("POST", "/api/v1/auth/register", "Register new user"),
        ("POST", "/api/v1/auth/token", "Get access token"),
        ("GET", "/api/v1/users/me", "Get current user profile"),
        ("PATCH", "/api/v1/users/me", "Update user profile"),
        ("PATCH", "/api/v1/users/me/preferences", "Update preferences"),
        ("POST", "/api/v1/users/me/change-password", "Change password"),
        ("DELETE", "/api/v1/users/me", "Delete account"),
        ("GET", "/api/v1/profiles", "List research profiles"),
        ("POST", "/api/v1/profiles", "Create research profile"),
        ("GET", "/api/v1/profiles/{id}", "Get profile details"),
        ("PATCH", "/api/v1/profiles/{id}", "Update profile"),
        ("DELETE", "/api/v1/profiles/{id}", "Delete profile"),
        ("GET", "/api/v1/profiles/{id}/interests", "List interest categories"),
        ("POST", "/api/v1/profiles/{id}/interests", "Create interest category"),
        ("PATCH", "/api/v1/profiles/{id}/interests/{id}", "Update interest"),
        ("DELETE", "/api/v1/profiles/{id}/interests/{id}", "Delete interest"),
        ("POST", "/api/v1/profiles/{id}/interests/{id}/generate-embedding", "Generate embedding"),
    ]

    for method, path, description in routes:
        table.add_row(method, path, description)

    console.print(table)


# Scheduler commands (Phase 4)
scheduler_app = typer.Typer(help="Background job scheduler operations")
app.add_typer(scheduler_app, name="scheduler")


@scheduler_app.command("start")
def start_scheduler(
    foreground: bool = typer.Option(True, "--foreground/--background", "-f/-b", help="Run in foreground"),
) -> None:
    """Start the background job scheduler.

    This runs the scheduler with all configured jobs:
    - Paper collection (every 6 hours)
    - Weekly digest generation (Sunday 8am)
    - Daily digest generation (7am)
    - Immediate alert checks (every hour)
    - Embedding updates (daily at 2am)
    """
    from paperpulse.scheduler import get_job_status, init_scheduler, start_scheduler

    console.print("[bold]Starting PaperPulse Scheduler[/bold]\n")

    # Initialize scheduler with jobs
    init_scheduler()

    # Show registered jobs
    jobs = get_job_status()
    table = Table(title="Registered Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Next Run", style="dim")
    table.add_column("Trigger", style="dim")

    for job in jobs:
        table.add_row(
            job["id"],
            job["name"],
            job["next_run"] or "Not scheduled",
            job["trigger"],
        )

    console.print(table)
    console.print()

    # Start scheduler
    start_scheduler()

    if foreground:
        console.print("[green]Scheduler running. Press Ctrl+C to stop.[/green]\n")
        try:
            # Keep the process running
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down scheduler...[/yellow]")
            from paperpulse.scheduler import stop_scheduler
            stop_scheduler()
            console.print("[green]Scheduler stopped.[/green]")


@scheduler_app.command("status")
def scheduler_status() -> None:
    """Show status of all scheduled jobs."""
    from paperpulse.scheduler import get_job_status, get_scheduler, init_scheduler

    # Initialize to get job info (doesn't start scheduler)
    init_scheduler()

    jobs = get_job_status()

    if not jobs:
        console.print("[yellow]No jobs registered[/yellow]")
        return

    table = Table(title="Scheduled Jobs Status")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Next Run", style="yellow")
    table.add_column("Trigger")

    for job in jobs:
        table.add_row(
            job["id"],
            job["name"],
            job["next_run"] or "[dim]Not scheduled[/dim]",
            job["trigger"],
        )

    console.print(table)


@scheduler_app.command("run-job")
def run_job(
    job_name: str = typer.Argument(
        ...,
        help="Job to run: collect, weekly-digest, daily-digest, alerts, embeddings",
    ),
) -> None:
    """Manually run a scheduled job.

    Available jobs:
    - collect: Collect papers from all sources
    - weekly-digest: Generate weekly digest emails
    - daily-digest: Generate daily digest emails
    - alerts: Check and send immediate alerts
    - embeddings: Update paper and profile embeddings
    """
    from paperpulse.scheduler.jobs import (
        collect_papers_job,
        generate_digests_job,
        send_immediate_alerts_job,
        update_embeddings_job,
    )

    job_map = {
        "collect": collect_papers_job,
        "weekly-digest": lambda: generate_digests_job("weekly"),
        "daily-digest": lambda: generate_digests_job("daily"),
        "alerts": send_immediate_alerts_job,
        "embeddings": update_embeddings_job,
    }

    if job_name not in job_map:
        console.print(f"[red]Unknown job: {job_name}[/red]")
        console.print(f"[dim]Available jobs: {', '.join(job_map.keys())}[/dim]")
        raise typer.Exit(1)

    async def _run() -> None:
        console.print(f"[dim]Running job: {job_name}...[/dim]\n")

        try:
            result = await job_map[job_name]()

            console.print("[green]Job completed successfully![/green]")

            if result:
                table = Table(title="Job Results")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")

                for key, value in result.items():
                    table.add_row(key.replace("_", " ").title(), str(value))

                console.print(table)

        except Exception as e:
            console.print(f"[red]Job failed: {e}[/red]")
            raise typer.Exit(1)

    asyncio.run(_run())


@scheduler_app.command("history")
def job_history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of entries to show"),
    job_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by job type"),
) -> None:
    """Show recent job execution history."""

    async def _history() -> None:
        from sqlalchemy import select

        from paperpulse.db.models import JobLog
        from paperpulse.db.session import get_session

        async with get_session() as session:
            query = select(JobLog).order_by(JobLog.started_at.desc()).limit(limit)

            if job_type:
                query = query.where(JobLog.job_type == job_type)

            result = await session.execute(query)
            logs = result.scalars().all()

        if not logs:
            console.print("[yellow]No job history found[/yellow]")
            return

        table = Table(title="Job Execution History")
        table.add_column("Job", style="cyan")
        table.add_column("Type", style="dim")
        table.add_column("Started", style="green")
        table.add_column("Duration", style="yellow")
        table.add_column("Status")
        table.add_column("Items")

        for log in logs:
            status_style = "green" if log.status == "completed" else "red"
            duration = f"{log.duration_seconds:.1f}s" if log.duration_seconds else "-"

            table.add_row(
                log.job_name,
                log.job_type,
                log.started_at.strftime("%Y-%m-%d %H:%M") if log.started_at else "-",
                duration,
                f"[{status_style}]{log.status}[/{status_style}]",
                f"{log.items_processed}/{log.items_created}",
            )

        console.print(table)

    asyncio.run(_history())


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
