# Sports Betting Analytics (SBA)

A betting edge finder and player prop analyzer that pulls odds from multiple sportsbooks, runs statistical and ML models, and surfaces +EV opportunities in real time.

## Features

### Betting Edge Finder
- Aggregates odds from 20+ sportsbooks via [The Odds API](https://the-odds-api.com)
- Computes vig-free consensus probabilities from sharp bookmakers
- Calculates expected value (EV) for every outcome vs every book
- Recommends stake sizes using fractional Kelly criterion
- Tracks line movement history for closing line value analysis

### Prop Bet Analyzer
- XGBoost ML models trained on player game logs
- 25+ engineered features: rolling averages, trends, matchup history, home/away splits
- Dual model approach: regressor (predicted stat value) + classifier (over/under probability)
- Time-series cross-validation to prevent data leakage
- Feature importance for explainability

### Real-Time Monitor
- Live-updating terminal dashboard with Rich
- Concurrent scanning of game odds and player props
- Configurable refresh intervals and alert thresholds
- API credit tracking to stay within free tier limits

## Quick Start

```bash
# Install
cd sports-betting-analytics
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Configure
cp .env.example .env
# Edit .env and add your Odds API key (free at https://the-odds-api.com)

# Use
sba edge scan                              # Find +EV opportunities
sba data backfill --player "Jayson Tatum"  # Import player stats
sba props scan                             # ML-powered prop analysis
sba monitor                                # Real-time dashboard
```

## CLI Reference

```
sba edge scan [--sport nba] [--market h2h] [--min-ev 0.05]   # Scan for edges
sba edge lines <event_id>                                     # Line movement
sba edge track <event_id> <market> <selection> <odds>         # Track a bet
sba edge history                                              # ROI summary

sba props scan [--sport nba] [--event <id>]                   # Prop analysis
sba props player "Player Name"                                # Player profile

sba data sync [--sport nba]                                   # Sync odds/scores
sba data backfill --player "Name" [--seasons 2024,2025]       # Import stats
sba data status                                               # DB & API status

sba models train --player "Name" [--market player_points]     # Train ML model
sba models list                                               # List models

sba monitor [--sport nba] [--interval 300] [--no-props]       # Live dashboard
```

## Architecture

```
CLI (typer + rich)
    │
Services (edge_finder, prop_analyzer, monitor)
    │
Models
  ├── Statistical (EV, Kelly, Poisson, implied probability)
  └── ML (XGBoost props, feature engineering, pipeline)
    │
Data Layer
  ├── API Clients (The Odds API, balldontlie)
  └── SQLite (events, odds snapshots, player logs, bets)
```

## How It Works

### Edge Finding
1. Fetches live odds from all available bookmakers
2. Removes vig from sharp book lines (Pinnacle, Circa) to get fair probabilities
3. Compares fair probability against each soft bookmaker's odds
4. Flags any outcome where `EV = (prob × payout) - 1 > threshold`
5. Sizes bets using quarter-Kelly criterion

### Prop Prediction
1. Collects player game logs (points, rebounds, assists, etc.)
2. Engineers features: rolling averages (3/5/10/20 game), trends, matchup splits
3. Trains XGBoost regressor (predicted value) + classifier (over/under)
4. Compares model probability against bookmaker implied probability
5. Surfaces props where the model finds an edge

## API Keys

- **The Odds API** (required): Free tier = 500 credits/month. Get one at [the-odds-api.com](https://the-odds-api.com)
- **balldontlie** (optional): Free tier for NBA player stats. Get one at [balldontlie.io](https://www.balldontlie.io)

## Tech Stack

Python, XGBoost, scikit-learn, pandas, SQLite, httpx, Rich, Typer
