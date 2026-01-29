"""Email digest generation and delivery."""

from paperpulse.email.models import Digest, DigestPaper, DigestSection
from paperpulse.email.service import DigestService, EmailSender, ResearchInterest
from paperpulse.email.templates import DigestRenderer

__all__ = [
    "Digest",
    "DigestPaper",
    "DigestRenderer",
    "DigestSection",
    "DigestService",
    "EmailSender",
    "ResearchInterest",
]
