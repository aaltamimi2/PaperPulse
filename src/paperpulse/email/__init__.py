"""Email digest generation and delivery."""

from paperpulse.email.campaigns import (
    CampaignResult,
    DigestCampaign,
    ImmediateAlertCampaign,
)
from paperpulse.email.models import Digest, DigestPaper, DigestSection
from paperpulse.email.service import DigestService, EmailSender, ResearchInterest
from paperpulse.email.summarization import DigestHighlightGenerator, SummarizationService
from paperpulse.email.templates import DigestRenderer

__all__ = [
    # Models
    "Digest",
    "DigestPaper",
    "DigestSection",
    # Services
    "DigestService",
    "EmailSender",
    "ResearchInterest",
    # Campaigns
    "CampaignResult",
    "DigestCampaign",
    "ImmediateAlertCampaign",
    # AI Summarization
    "SummarizationService",
    "DigestHighlightGenerator",
    # Templates
    "DigestRenderer",
]
