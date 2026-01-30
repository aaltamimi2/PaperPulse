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


# Modern, clean HTML template for digest emails
DIGEST_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ digest.subject_line }}</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.65;
            color: #1a1a2e;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }
        .container {
            max-width: 680px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px 30px;
            text-align: center;
        }
        .logo {
            font-size: 32px;
            font-weight: 700;
            color: #ffffff;
            letter-spacing: -0.5px;
            margin-bottom: 8px;
        }
        .logo-icon {
            display: inline-block;
            margin-right: 8px;
        }
        .tagline {
            color: rgba(255, 255, 255, 0.9);
            font-size: 14px;
            font-weight: 400;
        }
        .digest-meta {
            background: rgba(255, 255, 255, 0.15);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            padding: 16px 24px;
            margin-top: 24px;
            display: inline-block;
        }
        .digest-meta-text {
            color: #ffffff;
            font-size: 13px;
        }
        .digest-meta-text strong {
            font-size: 20px;
            display: block;
            margin-bottom: 4px;
        }
        .content {
            padding: 0;
        }
        .intro {
            padding: 32px 30px;
            background: #f8fafc;
            border-bottom: 1px solid #e2e8f0;
        }
        .intro-text {
            font-size: 16px;
            color: #475569;
        }
        .intro-text strong {
            color: #1e293b;
        }
        .section {
            padding: 32px 30px;
            border-bottom: 1px solid #e2e8f0;
        }
        .section:last-of-type {
            border-bottom: none;
        }
        .section-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 12px;
        }
        .section-title {
            font-size: 20px;
            font-weight: 700;
            color: #1e293b;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .section-icon {
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
        }
        .section-count {
            background: #e0e7ff;
            color: #4338ca;
            font-size: 12px;
            font-weight: 600;
            padding: 6px 12px;
            border-radius: 20px;
        }
        .section-desc {
            color: #64748b;
            font-size: 14px;
            margin-bottom: 20px;
            padding-left: 42px;
        }
        .paper {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            transition: all 0.2s ease;
            position: relative;
        }
        .paper:hover {
            border-color: #c7d2fe;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.1);
        }
        .paper:last-child {
            margin-bottom: 0;
        }
        .paper-number {
            position: absolute;
            top: 20px;
            left: -12px;
            width: 24px;
            height: 24px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #ffffff;
            font-size: 11px;
            font-weight: 700;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .paper-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 16px;
            margin-bottom: 12px;
        }
        .paper-title {
            font-size: 16px;
            font-weight: 600;
            color: #1e293b;
            line-height: 1.4;
            flex: 1;
        }
        .paper-title a {
            color: #4f46e5;
            text-decoration: none;
        }
        .paper-title a:hover {
            text-decoration: underline;
        }
        .paper-score {
            flex-shrink: 0;
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: #ffffff;
            font-size: 12px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 6px;
            white-space: nowrap;
        }
        .paper-score.high {
            background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
        }
        .paper-score.very-high {
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        }
        .paper-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 8px 16px;
            font-size: 13px;
            color: #64748b;
            margin-bottom: 14px;
        }
        .paper-meta-item {
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .paper-meta-icon {
            opacity: 0.7;
        }
        .paper-summary {
            font-size: 14px;
            color: #475569;
            line-height: 1.6;
            margin-bottom: 14px;
            padding: 14px 16px;
            background: #f8fafc;
            border-radius: 8px;
            border-left: 3px solid #667eea;
        }
        .paper-why {
            font-size: 13px;
            color: #059669;
            line-height: 1.5;
            padding: 12px 14px;
            background: #ecfdf5;
            border-radius: 8px;
            margin-bottom: 14px;
        }
        .paper-why-label {
            font-weight: 600;
            color: #047857;
            display: block;
            margin-bottom: 4px;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .paper-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }
        .tag {
            background: #f1f5f9;
            color: #475569;
            font-size: 11px;
            font-weight: 500;
            padding: 4px 10px;
            border-radius: 6px;
        }
        .tag.highlight {
            background: #e0e7ff;
            color: #4338ca;
        }
        .paper-cta {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            margin-top: 14px;
            padding: 8px 16px;
            background: #4f46e5;
            color: #ffffff !important;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            border-radius: 8px;
            transition: background 0.2s ease;
        }
        .paper-cta:hover {
            background: #4338ca;
        }
        .paper-actions {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-top: 14px;
            flex-wrap: wrap;
        }
        .feedback-buttons {
            display: flex;
            gap: 8px;
        }
        .btn-read, .btn-up, .btn-down {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 13px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.2s ease;
        }
        .btn-read {
            background: #f1f5f9;
            color: #475569;
        }
        .btn-read:hover {
            background: #e2e8f0;
        }
        .btn-up {
            background: #dcfce7;
            color: #166534;
        }
        .btn-up:hover {
            background: #bbf7d0;
        }
        .btn-down {
            background: #fee2e2;
            color: #991b1b;
        }
        .btn-down:hover {
            background: #fecaca;
        }
        .authors-section {
            padding: 24px 30px;
            background: #f8fafc;
        }
        .authors-box {
            background: #ffffff;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            border: 1px solid #e2e8f0;
        }
        .authors-box.suggested {
            background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
            border-color: #fbbf24;
        }
        .authors-title {
            font-size: 16px;
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 12px;
        }
        .authors-subtitle {
            font-size: 13px;
            color: #64748b;
            margin-bottom: 12px;
        }
        .authors-list {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .author-tag {
            display: inline-block;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 500;
        }
        .author-tag.followed {
            background: #e0e7ff;
            color: #4338ca;
        }
        .author-more {
            padding: 6px 12px;
            color: #64748b;
            font-size: 13px;
        }
        .suggested-authors {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .suggested-author {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 12px;
            background: rgba(255,255,255,0.7);
            border-radius: 8px;
        }
        .suggested-name {
            font-weight: 600;
            color: #1e293b;
        }
        .suggested-count {
            font-size: 12px;
            color: #92400e;
            background: rgba(146, 64, 14, 0.1);
            padding: 4px 8px;
            border-radius: 12px;
        }
        .footer {
            background: #1e293b;
            padding: 32px 30px;
            text-align: center;
        }
        .footer-text {
            color: #94a3b8;
            font-size: 13px;
            margin-bottom: 16px;
        }
        .footer-links {
            display: flex;
            justify-content: center;
            gap: 24px;
            margin-bottom: 20px;
        }
        .footer-links a {
            color: #cbd5e1;
            font-size: 13px;
            text-decoration: none;
        }
        .footer-links a:hover {
            color: #ffffff;
        }
        .footer-brand {
            color: #64748b;
            font-size: 12px;
        }
        .no-papers {
            text-align: center;
            padding: 40px 20px;
            color: #94a3b8;
        }
        .no-papers-icon {
            font-size: 48px;
            margin-bottom: 16px;
        }
        @media (max-width: 600px) {
            body {
                padding: 20px 12px;
            }
            .header {
                padding: 30px 20px;
            }
            .section {
                padding: 24px 20px;
            }
            .paper {
                padding: 16px;
            }
            .paper-number {
                display: none;
            }
            .section-desc {
                padding-left: 0;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">
                <span class="logo-icon">📚</span>PaperPulse
            </div>
            <div class="tagline">Your personalized research digest</div>
            <div class="digest-meta">
                <div class="digest-meta-text">
                    <strong>{{ digest.total_papers }} Papers</strong>
                    {{ digest.digest_type|title }} Digest · {{ digest.sections|length }} Research Areas
                </div>
            </div>
        </div>

        <div class="content">
            <div class="intro">
                <p class="intro-text">
                    Hi <strong>{{ digest.user_name.split()[0] }}</strong>! Here's your curated selection of the latest research papers matching your interests.
                    {% if digest.period_start and digest.period_end %}
                    Covering publications from <strong>{{ digest.period_start.strftime('%b %d') }}</strong> to <strong>{{ digest.period_end.strftime('%b %d, %Y') }}</strong>.
                    {% endif %}
                </p>
            </div>

            {% for section in digest.sections %}
            <div class="section">
                <div class="section-header">
                    <div class="section-title">
                        <span class="section-icon">🔬</span>
                        {{ section.interest_name }}
                    </div>
                    <span class="section-count">{{ section.papers|length }} papers</span>
                </div>
                {% if section.interest_description %}
                <p class="section-desc">{{ section.interest_description }}</p>
                {% endif %}

                {% if section.has_papers %}
                    {% for paper in section.papers %}
                    <div class="paper">
                        <span class="paper-number">{{ loop.index }}</span>
                        <div class="paper-header">
                            <h3 class="paper-title">
                                <a href="{{ paper.url }}">{{ paper.title }}</a>
                            </h3>
                            <span class="paper-score {% if paper.score_percent >= 70 %}very-high{% elif paper.score_percent >= 50 %}high{% endif %}">
                                {{ paper.score_percent }}% match
                            </span>
                        </div>

                        <div class="paper-meta">
                            <span class="paper-meta-item">
                                <span class="paper-meta-icon">👤</span>
                                {{ paper.authors_display }}
                            </span>
                            {% if paper.journal %}
                            <span class="paper-meta-item">
                                <span class="paper-meta-icon">📖</span>
                                {{ paper.journal }}
                            </span>
                            {% endif %}
                            {% if paper.published_date %}
                            <span class="paper-meta-item">
                                <span class="paper-meta-icon">📅</span>
                                {{ paper.published_date.strftime('%b %d, %Y') }}
                            </span>
                            {% endif %}
                        </div>

                        {% if paper.summary %}
                        <div class="paper-summary">
                            {{ paper.summary }}
                        </div>
                        {% endif %}

                        {% if paper.why_relevant %}
                        <div class="paper-why">
                            <span class="paper-why-label">Why this matters to you</span>
                            {{ paper.why_relevant }}
                        </div>
                        {% endif %}

                        {% if paper.relevance_tags %}
                        <div class="paper-tags">
                            {% for tag in paper.relevance_tags %}
                            <span class="tag {% if loop.index <= 2 %}highlight{% endif %}">{{ tag }}</span>
                            {% endfor %}
                        </div>
                        {% endif %}

                        <div class="paper-actions">
                            <a href="{{ paper.url }}" class="paper-cta">
                                Read Paper →
                            </a>
                            {% if paper.feedback_token and feedback_base_url %}
                            <div class="feedback-buttons">
                                <a href="{{ feedback_base_url }}/read/{{ paper.feedback_token }}?redirect={{ paper.url | urlencode }}" class="btn-read" title="Mark as read">
                                    ✓ Read
                                </a>
                                <a href="{{ feedback_base_url }}/rate/{{ paper.feedback_token }}/up" class="btn-up" title="More like this">
                                    👍
                                </a>
                                <a href="{{ feedback_base_url }}/rate/{{ paper.feedback_token }}/down" class="btn-down" title="Less like this">
                                    👎
                                </a>
                            </div>
                            {% endif %}
                        </div>
                    </div>
                    {% endfor %}
                {% else %}
                    <div class="no-papers">
                        <div class="no-papers-icon">📭</div>
                        <p>No new papers found for this interest this period.</p>
                    </div>
                {% endif %}
            </div>
            {% endfor %}
        </div>

        {% if digest.followed_authors or digest.suggested_authors %}
        <div class="authors-section">
            {% if digest.followed_authors %}
            <div class="authors-box">
                <h3 class="authors-title">👥 Authors You Follow</h3>
                <div class="authors-list">
                    {% for author in digest.followed_authors[:6] %}
                    <span class="author-tag followed">{{ author }}</span>
                    {% endfor %}
                    {% if digest.followed_authors|length > 6 %}
                    <span class="author-more">+{{ digest.followed_authors|length - 6 }} more</span>
                    {% endif %}
                </div>
            </div>
            {% endif %}

            {% if digest.suggested_authors %}
            <div class="authors-box suggested">
                <h3 class="authors-title">✨ Suggested Authors to Follow</h3>
                <p class="authors-subtitle">Based on your highly-relevant papers</p>
                <div class="suggested-authors">
                    {% for author in digest.suggested_authors %}
                    <div class="suggested-author">
                        <span class="suggested-name">{{ author.name }}</span>
                        <span class="suggested-count">{{ author.paper_count }} paper{% if author.paper_count > 1 %}s{% endif %}</span>
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endif %}
        </div>
        {% endif %}

        <div class="footer">
            <p class="footer-text">
                You're receiving this digest because you subscribed to PaperPulse research alerts.
            </p>
            <div class="footer-links">
                <a href="#">Manage Preferences</a>
                <a href="#">Unsubscribe</a>
                <a href="#">View Online</a>
            </div>
            <p class="footer-brand">
                Generated on {{ digest.generated_at.strftime('%B %d, %Y at %H:%M UTC') }} · Powered by PaperPulse AI
            </p>
        </div>
    </div>
</body>
</html>
"""

DIGEST_TEXT_TEMPLATE = """
════════════════════════════════════════════════════════════════════════════════
📚 PAPERPULSE {{ digest.digest_type|upper }} DIGEST
════════════════════════════════════════════════════════════════════════════════

Hi {{ digest.user_name.split()[0] }}!

Here's your curated selection of {{ digest.total_papers }} papers across {{ digest.sections|length }} research areas.
{% if digest.period_start and digest.period_end %}
Covering: {{ digest.period_start.strftime('%B %d') }} - {{ digest.period_end.strftime('%B %d, %Y') }}
{% endif %}

{% for section in digest.sections %}
────────────────────────────────────────────────────────────────────────────────
🔬 {{ section.interest_name|upper }}
   {{ section.papers|length }} papers found
────────────────────────────────────────────────────────────────────────────────
{% if section.interest_description %}
{{ section.interest_description }}

{% endif %}
{% if section.has_papers %}
{% for paper in section.papers %}
{{ loop.index }}. {{ paper.title }}
   ├─ Authors: {{ paper.authors_display }}
   {% if paper.journal %}├─ Journal: {{ paper.journal }}{% endif %}
   {% if paper.published_date %}├─ Date: {{ paper.published_date.strftime('%b %d, %Y') }}{% endif %}
   ├─ Match: {{ paper.score_percent }}%
   └─ Link: {{ paper.url }}
{% if paper.summary %}
   📝 SUMMARY
   {{ paper.summary }}
{% endif %}
{% if paper.why_relevant %}
   💡 WHY IT MATTERS
   {{ paper.why_relevant }}
{% endif %}
{% if paper.relevance_tags %}
   🏷️  Tags: {{ paper.relevance_tags|join(' · ') }}
{% endif %}

{% endfor %}
{% else %}
   📭 No new papers found for this interest this period.

{% endif %}
{% endfor %}
════════════════════════════════════════════════════════════════════════════════
Generated: {{ digest.generated_at.strftime('%B %d, %Y at %H:%M UTC') }}
Powered by PaperPulse AI

Manage Preferences: [link]
Unsubscribe: [link]
════════════════════════════════════════════════════════════════════════════════
"""


# Immediate Alert HTML Template - Emphasizes urgency with distinct styling
ALERT_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ digest.subject_line }}</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.65;
            color: #1a1a2e;
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }
        .container {
            max-width: 680px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
        }
        .header {
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
            padding: 40px 30px;
            text-align: center;
        }
        .logo {
            font-size: 32px;
            font-weight: 700;
            color: #ffffff;
            letter-spacing: -0.5px;
            margin-bottom: 8px;
        }
        .alert-badge {
            display: inline-block;
            background: rgba(255, 255, 255, 0.2);
            color: #ffffff;
            font-size: 11px;
            font-weight: 700;
            padding: 6px 14px;
            border-radius: 20px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-top: 12px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        .digest-meta {
            background: rgba(255, 255, 255, 0.15);
            border-radius: 12px;
            padding: 16px 24px;
            margin-top: 20px;
            display: inline-block;
        }
        .digest-meta-text {
            color: #ffffff;
            font-size: 14px;
        }
        .content {
            padding: 32px 30px;
        }
        .intro {
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 16px 20px;
            margin-bottom: 28px;
            border-radius: 0 8px 8px 0;
            font-size: 14px;
            color: #92400e;
        }
        .paper {
            background: #fff7ed;
            border: 2px solid #fed7aa;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
        }
        .paper:last-child {
            margin-bottom: 0;
        }
        .paper-title {
            font-size: 18px;
            font-weight: 700;
            color: #c2410c;
            margin-bottom: 12px;
            line-height: 1.4;
        }
        .paper-title a {
            color: #c2410c;
            text-decoration: none;
        }
        .paper-title a:hover {
            text-decoration: underline;
        }
        .paper-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            font-size: 13px;
            color: #78716c;
            margin-bottom: 16px;
        }
        .paper-summary {
            font-size: 15px;
            color: #44403c;
            line-height: 1.7;
            margin-bottom: 16px;
        }
        .paper-why {
            background: #dcfce7;
            border-left: 4px solid #22c55e;
            padding: 14px 18px;
            border-radius: 0 8px 8px 0;
            font-size: 14px;
            color: #166534;
            margin-bottom: 16px;
        }
        .paper-why strong {
            display: block;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
            color: #14532d;
        }
        .paper-score {
            display: inline-block;
            background: #dc2626;
            color: #ffffff;
            font-size: 13px;
            font-weight: 700;
            padding: 6px 14px;
            border-radius: 8px;
            margin-bottom: 16px;
        }
        .paper-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 16px;
        }
        .tag {
            background: #fee2e2;
            color: #b91c1c;
            font-size: 12px;
            font-weight: 500;
            padding: 4px 12px;
            border-radius: 6px;
        }
        .paper-cta {
            display: inline-block;
            background: #dc2626;
            color: #ffffff !important;
            font-size: 14px;
            font-weight: 600;
            padding: 12px 24px;
            border-radius: 8px;
            text-decoration: none;
        }
        .paper-cta:hover {
            background: #b91c1c;
        }
        .footer {
            background: #1e293b;
            padding: 28px 30px;
            text-align: center;
        }
        .footer-text {
            color: #94a3b8;
            font-size: 13px;
            margin-bottom: 12px;
        }
        .footer-links {
            display: flex;
            justify-content: center;
            gap: 20px;
        }
        .footer-links a {
            color: #cbd5e1;
            font-size: 13px;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">🚨 PaperPulse Alert</div>
            <span class="alert-badge">High-Priority Papers</span>
            <div class="digest-meta">
                <div class="digest-meta-text">
                    {{ digest.total_papers }} paper{% if digest.total_papers != 1 %}s{% endif %} require your attention
                </div>
            </div>
        </div>

        <div class="content">
            <div class="intro">
                <strong>Hi {{ digest.user_name.split()[0] }}!</strong> We found papers that are highly relevant to your research. These scored above your alert threshold and may warrant immediate attention.
            </div>

            {% for section in digest.sections %}
            {% if section.has_papers %}
            {% for paper in section.papers %}
            <div class="paper">
                <h3 class="paper-title">
                    <a href="{{ paper.url }}">{{ paper.title }}</a>
                </h3>

                <div class="paper-meta">
                    <span>👤 {{ paper.authors_display }}</span>
                    {% if paper.journal %}<span>📖 {{ paper.journal }}</span>{% endif %}
                    {% if paper.published_date %}<span>📅 {{ paper.published_date.strftime('%b %d, %Y') }}</span>{% endif %}
                </div>

                <span class="paper-score">{{ paper.score_percent }}% match</span>

                {% if paper.summary %}
                <div class="paper-summary">{{ paper.summary }}</div>
                {% endif %}

                {% if paper.why_relevant %}
                <div class="paper-why">
                    <strong>Why this matters to you</strong>
                    {{ paper.why_relevant }}
                </div>
                {% endif %}

                {% if paper.relevance_tags %}
                <div class="paper-tags">
                    {% for tag in paper.relevance_tags %}
                    <span class="tag">{{ tag }}</span>
                    {% endfor %}
                </div>
                {% endif %}

                <a href="{{ paper.url }}" class="paper-cta">Read Paper →</a>
            </div>
            {% endfor %}
            {% endif %}
            {% endfor %}
        </div>

        <div class="footer">
            <p class="footer-text">
                You're receiving this alert because these papers matched your high-priority criteria.
            </p>
            <div class="footer-links">
                <a href="#">Adjust Alert Settings</a>
                <a href="#">Manage Preferences</a>
            </div>
        </div>
    </div>
</body>
</html>
"""

ALERT_TEXT_TEMPLATE = """
════════════════════════════════════════════════════════════════════════════════
🚨 PAPERPULSE HIGH-PRIORITY ALERT
════════════════════════════════════════════════════════════════════════════════

Hi {{ digest.user_name.split()[0] }},

We found {{ digest.total_papers }} paper{% if digest.total_papers != 1 %}s{% endif %} highly relevant to your research!

{% for section in digest.sections %}
{% if section.has_papers %}
{% for paper in section.papers %}
────────────────────────────────────────────────────────────────────────────────
📌 {{ paper.title }}
────────────────────────────────────────────────────────────────────────────────
├─ Authors: {{ paper.authors_display }}
{% if paper.journal %}├─ Journal: {{ paper.journal }}{% endif %}
{% if paper.published_date %}├─ Date: {{ paper.published_date.strftime('%b %d, %Y') }}{% endif %}
├─ Match: {{ paper.score_percent }}%
└─ Link: {{ paper.url }}

{% if paper.summary %}
📝 SUMMARY
{{ paper.summary }}

{% endif %}
{% if paper.why_relevant %}
💡 WHY THIS MATTERS
{{ paper.why_relevant }}

{% endif %}
{% if paper.relevance_tags %}
🏷️  Tags: {{ paper.relevance_tags|join(' · ') }}
{% endif %}

{% endfor %}
{% endif %}
{% endfor %}
════════════════════════════════════════════════════════════════════════════════
Alert sent: {{ digest.generated_at.strftime('%B %d, %Y at %H:%M UTC') }}

Adjust alert settings: [link]
Manage preferences: [link]
════════════════════════════════════════════════════════════════════════════════
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
        # Use alert template for immediate digests
        if digest.digest_type == "immediate":
            template = env.from_string(ALERT_HTML_TEMPLATE)
        else:
            template = env.from_string(DIGEST_HTML_TEMPLATE)
        return template.render(digest=digest, feedback_base_url=digest.feedback_base_url)

    def render_text(self, digest: Digest) -> str:
        """Render digest as plain text email.

        Args:
            digest: Digest to render

        Returns:
            Plain text string
        """
        env = self._get_env()
        # Use alert template for immediate digests
        if digest.digest_type == "immediate":
            template = env.from_string(ALERT_TEXT_TEMPLATE)
        else:
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
