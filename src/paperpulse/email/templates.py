"""Email template rendering with Jinja2."""

from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from paperpulse.email.models import Digest


def get_template_env(template_dir: Optional[Path] = None) -> Environment:
    """Create Jinja2 environment for email templates.

    Args:
        template_dir: Directory containing templates (defaults to package templates)

    Returns:
        Configured Jinja2 Environment
    """
    if template_dir is None:
        # Use package templates directory
        template_dir = Path(__file__).parent.parent.parent.parent / "templates" / "email"

    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


# Inline HTML template for digest emails (fallback if file templates not found)
DIGEST_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ digest.subject_line }}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 700px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background-color: #ffffff;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .header {
            text-align: center;
            border-bottom: 2px solid #4a90d9;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        .header h1 {
            color: #4a90d9;
            margin: 0;
            font-size: 28px;
        }
        .header .subtitle {
            color: #666;
            font-size: 14px;
            margin-top: 5px;
        }
        .section {
            margin-bottom: 40px;
            border-left: 4px solid #4a90d9;
            padding-left: 20px;
        }
        .section-header {
            display: flex;
            align-items: center;
            margin-bottom: 15px;
        }
        .section-header h2 {
            color: #2c5282;
            margin: 0;
            font-size: 20px;
        }
        .section-header .count {
            background-color: #4a90d9;
            color: white;
            border-radius: 12px;
            padding: 2px 10px;
            font-size: 12px;
            margin-left: 10px;
        }
        .section-desc {
            color: #666;
            font-size: 13px;
            margin-bottom: 15px;
            font-style: italic;
        }
        .paper {
            background-color: #f8fafc;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 15px;
            border: 1px solid #e2e8f0;
        }
        .paper-title {
            font-weight: 600;
            color: #1a365d;
            font-size: 16px;
            margin-bottom: 8px;
        }
        .paper-title a {
            color: #4a90d9;
            text-decoration: none;
        }
        .paper-title a:hover {
            text-decoration: underline;
        }
        .paper-meta {
            font-size: 13px;
            color: #666;
            margin-bottom: 10px;
        }
        .paper-meta .authors {
            font-style: italic;
        }
        .paper-meta .journal {
            color: #4a90d9;
        }
        .paper-summary {
            font-size: 14px;
            color: #444;
            margin-bottom: 10px;
        }
        .paper-why {
            background-color: #ebf8ff;
            border-left: 3px solid #4a90d9;
            padding: 10px;
            font-size: 13px;
            color: #2c5282;
            margin-bottom: 10px;
        }
        .paper-why strong {
            color: #1a365d;
        }
        .paper-score {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .score-bar {
            flex-grow: 1;
            height: 8px;
            background-color: #e2e8f0;
            border-radius: 4px;
            overflow: hidden;
        }
        .score-fill {
            height: 100%;
            background-color: #48bb78;
            border-radius: 4px;
        }
        .score-text {
            font-size: 12px;
            color: #666;
            min-width: 40px;
        }
        .tags {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin-top: 10px;
        }
        .tag {
            background-color: #edf2f7;
            color: #4a5568;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
        }
        .priority-immediate {
            border-left-color: #e53e3e;
        }
        .priority-immediate .score-fill {
            background-color: #e53e3e;
        }
        .priority-weekly {
            border-left-color: #dd6b20;
        }
        .priority-weekly .score-fill {
            background-color: #dd6b20;
        }
        .footer {
            text-align: center;
            padding-top: 30px;
            border-top: 1px solid #e2e8f0;
            margin-top: 30px;
            font-size: 12px;
            color: #666;
        }
        .footer a {
            color: #4a90d9;
        }
        .no-papers {
            color: #666;
            font-style: italic;
            padding: 20px;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔬 PaperPulse</h1>
            <div class="subtitle">
                {{ digest.digest_type|title }} Digest for {{ digest.user_name }}
                {% if digest.period_start and digest.period_end %}
                <br>{{ digest.period_start.strftime('%B %d') }} - {{ digest.period_end.strftime('%B %d, %Y') }}
                {% endif %}
            </div>
        </div>

        {% for section in digest.sections %}
        <div class="section">
            <div class="section-header">
                <h2>{{ section.interest_name }}</h2>
                <span class="count">{{ section.papers|length }} papers</span>
            </div>
            {% if section.interest_description %}
            <div class="section-desc">{{ section.interest_description }}</div>
            {% endif %}

            {% if section.has_papers %}
                {% for paper in section.top_papers %}
                <div class="paper priority-{{ paper.priority }}">
                    <div class="paper-title">
                        <a href="{{ paper.url }}">{{ paper.title }}</a>
                    </div>
                    <div class="paper-meta">
                        <span class="authors">{{ paper.authors_display }}</span>
                        {% if paper.journal %}
                        · <span class="journal">{{ paper.journal }}</span>
                        {% endif %}
                        {% if paper.published_date %}
                        · {{ paper.published_date.strftime('%b %d, %Y') }}
                        {% endif %}
                    </div>

                    {% if paper.summary %}
                    <div class="paper-summary">{{ paper.summary }}</div>
                    {% endif %}

                    {% if paper.why_relevant %}
                    <div class="paper-why">
                        <strong>Why this matters:</strong> {{ paper.why_relevant }}
                    </div>
                    {% endif %}

                    <div class="paper-score">
                        <span class="score-text">{{ paper.score_percent }}%</span>
                        <div class="score-bar">
                            <div class="score-fill" style="width: {{ paper.score_percent }}%"></div>
                        </div>
                    </div>

                    {% if paper.relevance_tags %}
                    <div class="tags">
                        {% for tag in paper.relevance_tags %}
                        <span class="tag">{{ tag }}</span>
                        {% endfor %}
                    </div>
                    {% endif %}
                </div>
                {% endfor %}
            {% else %}
                <div class="no-papers">No new papers found for this interest this period.</div>
            {% endif %}
        </div>
        {% endfor %}

        <div class="footer">
            <p>
                You're receiving this because you subscribed to PaperPulse digests.<br>
                <a href="#">Manage preferences</a> · <a href="#">Unsubscribe</a>
            </p>
            <p>Generated on {{ digest.generated_at.strftime('%B %d, %Y at %H:%M UTC') }}</p>
        </div>
    </div>
</body>
</html>
"""

DIGEST_TEXT_TEMPLATE = """
================================================================================
🔬 PAPERPULSE {{ digest.digest_type|upper }} DIGEST
================================================================================

Hello {{ digest.user_name }},

{% if digest.period_start and digest.period_end %}
Papers from {{ digest.period_start.strftime('%B %d') }} - {{ digest.period_end.strftime('%B %d, %Y') }}
{% endif %}

{% for section in digest.sections %}
--------------------------------------------------------------------------------
📚 {{ section.interest_name|upper }}
   {{ section.papers|length }} papers found
--------------------------------------------------------------------------------
{% if section.interest_description %}
{{ section.interest_description }}

{% endif %}
{% if section.has_papers %}
{% for paper in section.top_papers %}
{{ loop.index }}. {{ paper.title }}
   Authors: {{ paper.authors_display }}
   {% if paper.journal %}Journal: {{ paper.journal }}{% endif %}
   {% if paper.published_date %}Date: {{ paper.published_date.strftime('%b %d, %Y') }}{% endif %}
   Link: {{ paper.url }}
   Relevance: {{ paper.score_percent }}% match
{% if paper.summary %}
   Summary: {{ paper.summary }}
{% endif %}
{% if paper.why_relevant %}
   Why it matters: {{ paper.why_relevant }}
{% endif %}
{% if paper.relevance_tags %}
   Tags: {{ paper.relevance_tags|join(', ') }}
{% endif %}

{% endfor %}
{% else %}
   No new papers found for this interest this period.

{% endif %}
{% endfor %}
================================================================================
Generated on {{ digest.generated_at.strftime('%B %d, %Y at %H:%M UTC') }}

Manage preferences: [link]
Unsubscribe: [link]
================================================================================
"""


class DigestRenderer:
    """Render digest emails using templates."""

    def __init__(self, template_dir: Optional[Path] = None):
        """Initialize the renderer.

        Args:
            template_dir: Directory containing template files
        """
        self.template_dir = template_dir
        self._env: Optional[Environment] = None

    def _get_env(self) -> Environment:
        """Get or create Jinja2 environment."""
        if self._env is None:
            self._env = Environment(
                autoescape=select_autoescape(["html", "xml"]),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        return self._env

    def render_html(self, digest: Digest) -> str:
        """Render digest as HTML email.

        Args:
            digest: Digest to render

        Returns:
            HTML string
        """
        env = self._get_env()
        template = env.from_string(DIGEST_HTML_TEMPLATE)
        return template.render(digest=digest)

    def render_text(self, digest: Digest) -> str:
        """Render digest as plain text email.

        Args:
            digest: Digest to render

        Returns:
            Plain text string
        """
        env = self._get_env()
        template = env.from_string(DIGEST_TEXT_TEMPLATE)
        return template.render(digest=digest)

    def render(self, digest: Digest) -> tuple[str, str]:
        """Render both HTML and text versions.

        Args:
            digest: Digest to render

        Returns:
            Tuple of (html_content, text_content)
        """
        return self.render_html(digest), self.render_text(digest)
