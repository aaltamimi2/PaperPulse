# PaperPulse

AI-powered academic paper recommendation and digest system.

## Features

- **RSS Feed Collection**: Automatically collect papers from ACS journals and other academic sources
- **AI-Powered Scoring**: Multi-criteria relevance scoring using semantic similarity, keyword matching, author tracking, and novelty detection
- **Personalized Digests**: Customized email newsletters based on your research interests
- **Multiple Interest Categories**: Support for different research areas (e.g., Polymer MD, Agentic AI, ML Collective Variables)

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/PaperPulse.git
cd PaperPulse

# Install in development mode
pip install -e ".[dev]"

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings
```

## Quick Start

```bash
# List available ACS journal feeds
paperpulse feeds list-acs

# Test an ACS feed
paperpulse feeds test-acs jctc

# Collect papers from specific journals
paperpulse collect acs jctc macromolecules

# Initialize the database
paperpulse db init
```

## Configuration

Key environment variables:

- `GEMINI_API_KEY`: Google Gemini API key for embeddings and summarization
- `DB_*`: PostgreSQL database configuration
- `EMAIL_*`: Email delivery settings

## Architecture

### Scoring Pipeline

Papers are scored using a weighted combination of:
- **Semantic Similarity (40%)**: Embedding-based similarity using Google Gemini
- **Keyword Matching (30%)**: Term matching against your research keywords
- **Author Network (20%)**: Tracking papers from followed authors
- **Novelty Detection (10%)**: Identifying papers with new methods/findings

### Priority Levels

Based on relevance scores, papers are categorized:
- **Immediate (≥0.8)**: High-priority papers for instant notification
- **Weekly (0.5-0.8)**: Papers for weekly digest
- **Monthly (0.3-0.5)**: Papers for monthly roundup
- **Low (<0.3)**: Archived for reference

## Development

```bash
# Run tests
pytest tests/

# Run linter
ruff check src/ tests/

# Type checking
mypy src/
```

## License

MIT License
