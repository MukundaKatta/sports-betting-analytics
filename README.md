# sports-betting-analytics — Betting edge finder & prop bet analyzer — pulls odds from multiple books, runs statistical/ML models, surfaces +EV opportunities in real time

**Live:** <https://mukundakatta.github.io/sports-betting-analytics/>

Betting edge finder & prop bet analyzer — pulls odds from multiple books, runs statistical/ML models, surfaces +EV opportunities in real time.

## Why sports-betting-analytics

sports-betting-analytics exists to make this workflow practical. Betting edge finder & prop bet analyzer — pulls odds from multiple books, runs statistical/ml models, surfaces +ev opportunities in real time. It favours a small, inspectable surface over sprawling configuration.

## Features

- CLI command `sba`
- Included test suite

## Tech Stack

- **Runtime:** Python
- **Frameworks:** FastAPI, Typer
- **AI/ML:** NumPy, scikit-learn, Pandas
- **Tooling:** Docker, Pydantic, Rich

## How It Works

The codebase is organised into `src/`, `tests/`. The primary entry point is `src/sba/__init__.py`.

## Getting Started

```bash
pip install -e .
sba --help
```

## Usage

```bash
sba --help
```

## Project Structure

```
sports-betting-analytics/
├── .env.example
├── Dockerfile
├── FEATURES.md
├── PLAN.md
├── README.md
├── docker-compose.yml
├── index.html
├── pyproject.toml
├── src/
├── tests/
```