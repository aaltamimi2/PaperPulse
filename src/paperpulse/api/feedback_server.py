"""Simple FastAPI server for tracking paper interactions from email links."""

import os
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from paperpulse import feedback

app = FastAPI(title="PaperPulse Feedback API")

# HTML response templates
SUCCESS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>PaperPulse - {action}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        .card {{
            background: white;
            padding: 40px 60px;
            border-radius: 16px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            text-align: center;
        }}
        .icon {{ font-size: 48px; margin-bottom: 16px; }}
        h1 {{ color: #1e293b; margin: 0 0 8px 0; font-size: 24px; }}
        p {{ color: #64748b; margin: 0; }}
        .title {{ font-size: 14px; color: #94a3b8; margin-top: 16px; max-width: 300px; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">{icon}</div>
        <h1>{message}</h1>
        <p>{description}</p>
        <p class="title">{title}</p>
    </div>
</body>
</html>
"""


@app.get("/")
async def root():
    """Health check."""
    return {"status": "ok", "service": "PaperPulse Feedback API"}


@app.get("/read/{token}")
async def mark_read(token: str, redirect: str = None):
    """Mark a paper as read via email link."""
    paper_id = feedback.get_paper_from_token(token)
    if not paper_id:
        raise HTTPException(status_code=404, detail="Invalid or expired token")

    feedback.mark_as_read(paper_id)

    # Get paper info for display
    data = feedback.load_feedback()
    paper_info = data.get("papers", {}).get(paper_id, {})
    title = paper_info.get("title", "Unknown paper")[:60]

    if redirect:
        return RedirectResponse(url=redirect)

    return HTMLResponse(SUCCESS_HTML.format(
        action="Marked as Read",
        icon="✅",
        message="Marked as Read!",
        description="This paper won't appear in your Saturday wrap-up.",
        title=title
    ))


@app.get("/rate/{token}/{rating}")
async def rate_paper(token: str, rating: str):
    """Rate a paper (up/down) via email link."""
    if rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="Rating must be 'up' or 'down'")

    paper_id = feedback.get_paper_from_token(token)
    if not paper_id:
        raise HTTPException(status_code=404, detail="Invalid or expired token")

    feedback.rate_paper(paper_id, rating)

    # Get paper info
    data = feedback.load_feedback()
    paper_info = data.get("papers", {}).get(paper_id, {})
    title = paper_info.get("title", "Unknown paper")[:60]

    if rating == "up":
        return HTMLResponse(SUCCESS_HTML.format(
            action="Thumbs Up",
            icon="👍",
            message="Thanks for the feedback!",
            description="We'll show you more papers like this.",
            title=title
        ))
    else:
        return HTMLResponse(SUCCESS_HTML.format(
            action="Thumbs Down",
            icon="👎",
            message="Thanks for the feedback!",
            description="We'll show fewer papers like this.",
            title=title
        ))


@app.get("/stats")
async def get_stats():
    """Get feedback statistics."""
    return feedback.get_feedback_stats(days=30)


@app.get("/unread")
async def get_unread(days: int = 7):
    """Get unread papers from the last N days."""
    return feedback.get_unread_papers(days=days)


def run_server(host: str = "0.0.0.0", port: int = 8765):
    """Run the feedback server."""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
