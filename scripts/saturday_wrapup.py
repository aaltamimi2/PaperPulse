#!/usr/bin/env python3
"""Saturday wrap-up: Top unread papers from the week."""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from rich.console import Console

from paperpulse import feedback
from paperpulse.email.models import Digest, DigestSection, DigestPaper
from paperpulse.email.templates import DigestRenderer

console = Console()


async def send_saturday_wrapup(user_email: str, max_papers: int = 10):
    """Send Saturday wrap-up of top unread papers."""
    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    console.print(f"\n[bold magenta]📬 PaperPulse Saturday Wrap-up - {datetime.now().strftime('%Y-%m-%d')}[/bold magenta]")
    console.print("=" * 60)

    # Get unread papers from last 7 days
    unread = feedback.get_unread_papers(days=7)
    console.print(f"[cyan]Unread papers from this week: {len(unread)}[/cyan]")

    if not unread:
        console.print("[green]All caught up! No unread papers this week.[/green]")
        return True

    # Take top N by relevance score
    top_unread = unread[:max_papers]

    # Get feedback stats
    stats = feedback.get_feedback_stats(days=30)
    console.print(f"[dim]Read rate: {stats['read_rate']:.0%}, Positive rate: {stats['positive_rate']:.0%}[/dim]")

    # Create digest
    digest = Digest(
        user_name="Ali",
        user_email=user_email,
        digest_type="weekly",
        feedback_base_url=os.environ.get("FEEDBACK_URL", "http://localhost:8765"),
    )

    # Create single section for top unread
    papers = []
    for p in top_unread:
        paper = DigestPaper(
            title=p.get("title", "Unknown"),
            url=p.get("url", ""),
            relevance_score=p.get("relevance_score", 0),
            feedback_token=feedback.generate_token(p.get("paper_id", "")),
        )
        papers.append(paper)

    section = DigestSection(
        interest_name="📌 Top Unread This Week",
        interest_description=f"Your {len(papers)} highest-relevance papers you haven't read yet",
        papers=papers,
    )
    digest.add_section(section)

    console.print(f"[green]Wrap-up: {len(papers)} papers[/green]")
    for p in papers[:5]:
        console.print(f"  • {p.title[:50]}... ({p.score_percent}%)")

    # Render
    renderer = DigestRenderer()
    html_content, text_content = renderer.render(digest)

    # Custom subject
    subject = f"📌 PaperPulse Weekly Wrap-up: {len(papers)} unread papers to catch up on"

    console.print(f"[cyan]Sending to {user_email}...[/cyan]")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
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
        console.print(f"[bold green]✅ Saturday wrap-up sent![/bold green]")
        return True

    except Exception as e:
        console.print(f"[bold red]❌ Failed: {e}[/bold red]")
        return False


async def main():
    user_email = "altamimialim1@gmail.com"
    success = await send_saturday_wrapup(user_email)
    return 0 if success else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
