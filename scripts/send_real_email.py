#!/usr/bin/env python3
"""Send a real AI-enhanced digest email."""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Configure environment
os.environ["GEMINI_API_KEY"] = "AIzaSyAOkP57wd-1RjTeJ6GdebznbzncYFBHwqA"
os.environ["EMAIL_PROVIDER"] = "smtp"
os.environ["EMAIL_SMTP_HOST"] = "smtp.gmail.com"
os.environ["EMAIL_SMTP_PORT"] = "587"
os.environ["EMAIL_SMTP_USER"] = "altamimialim1@gmail.com"
os.environ["EMAIL_SMTP_PASSWORD"] = "ykoc mpwo mgnj qvhw"
os.environ["EMAIL_FROM_ADDRESS"] = "altamimialim1@gmail.com"
os.environ["EMAIL_FROM_NAME"] = "PaperPulse"
os.environ["EMAIL_SMTP_USE_TLS"] = "true"

from paperpulse.email import DigestRenderer, DigestService, ResearchInterest
from paperpulse.email.models import Digest

# Sample papers
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


async def send_email():
    """Generate and send a real email."""
    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    user_email = "altamimialim1@gmail.com"
    user_name = "Alim"

    print(f"Generating AI-enhanced digest for {user_email}...")

    # Generate digest with AI summaries
    service = DigestService(
        mock_mode=False,
        enable_ai_summaries=True,
        max_papers_to_summarize=5,
    )

    digest = await service.generate_digest(
        user_name=user_name,
        user_email=user_email,
        interests=INTERESTS,
        papers=SAMPLE_PAPERS,
        digest_type="weekly",
        min_score=0.05,
        max_papers_per_section=5,
    )

    print(f"Digest generated: {digest.total_papers} papers")

    # Render email
    renderer = DigestRenderer()
    html_content, text_content = renderer.render(digest)

    print(f"Rendering complete: {len(html_content)} chars HTML")

    # Send via SMTP
    print(f"Sending email to {user_email}...")

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
        print(f"\n✅ Email sent successfully to {user_email}!")
        print(f"   Subject: {digest.subject_line}")
        return True
    except Exception as e:
        print(f"\n❌ Failed to send email: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(send_email())
    exit(0 if success else 1)
