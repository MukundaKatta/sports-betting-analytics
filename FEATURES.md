# Sports Betting Analytics (SBA) — Feature Documentation

A professional sports betting analytics platform with ML-powered predictions, real-time edge detection, and bankroll management tools.

---

## Table of Contents

1. [Dashboard](#1-dashboard)
2. [Edge Finder](#2-edge-finder)
3. [Player Props (ML)](#3-player-props-ml-powered)
4. [My Bets](#4-my-bets)
5. [Analytics](#5-analytics)
6. [Arbitrage Scanner](#6-arbitrage-scanner)
7. [Line Movement](#7-line-movement)
8. [Odds Comparison](#8-odds-comparison)
9. [Power Ratings](#9-power-ratings)
10. [Calculator](#10-calculator)
11. [Backtester](#11-backtester)
12. [Simulator](#12-simulator-monte-carlo)
13. [SGP Builder](#13-sgp-builder-same-game-parlay)
14. [Bankroll Management](#14-bankroll-management)
15. [Bet Grades](#15-bet-grades)
16. [Watchlist](#16-watchlist)
17. [Live Feed](#17-live-feed)
18. [Odds Screen](#18-odds-screen)
19. [Achievements](#19-achievements)
20. [Smart Insights](#20-smart-insights)
21. [Devig Engine](#21-devig-engine)
22. [Promo Optimizer](#22-promo-optimizer)
23. [Public Money Tracker](#23-public-money-tracker)
24. [Sharp Money Tracker](#24-sharp-money-tracker)
25. [Community](#25-community)
26. [Settings](#26-settings)
27. [CLI Commands](#27-cli-commands)
28. [API Reference](#28-api-reference)
29. [Data Sources](#29-data-sources)
30. [Configuration](#30-configuration)

---

## 1. Dashboard

**Page:** `http://localhost:8000/`

The dashboard is your home base. It gives you a quick snapshot of everything happening in the app.

**What you see:**

- **Live Activity Ticker** — A scrolling bar at the top showing system status and recent activity.
- **Stat Cards** — Four cards showing: Events Tracked, Odds Snapshots collected, Players in database, and Game Logs available for ML training.
- **Quick Edge Scan** — A table showing the latest +EV (positive expected value) betting opportunities. Click "Scan Now" to refresh.
- **Bet Performance** — A summary of your tracked bets: total profit/loss, win rate, and ROI.
- **Bankroll Health & P/L Heatmap** — Visual breakdown of your bankroll risk and daily profit/loss as a color-coded calendar.
- **Today's P/L** — Your profit or loss for today with wins, losses, and win rate.
- **Equity Curve** — A line chart showing your cumulative bankroll growth over time.
- **Achievements** — Your gamification progress (points, rank, recent unlocks).
- **Smart Insights** — AI-generated tips based on your betting patterns.
- **Getting Started** — Step-by-step onboarding guide for new users.

**Keyboard Shortcuts:**
- `Ctrl+K` — Command palette (quick navigation)
- `/` — Focus the player search bar
- `G` then `D` — Jump to Dashboard
- `T` — Toggle dark/light theme
- `?` — Show all keyboard shortcuts

---

## 2. Edge Finder

**Page:** `http://localhost:8000/edges`

The Edge Finder is the core feature. It scans odds from 20+ sportsbooks in real-time and finds bets where you have a mathematical advantage.

**How it works (in simple terms):**

1. The app pulls live odds from all major sportsbooks (DraftKings, FanDuel, BetMGM, Pinnacle, etc.).
2. It calculates the "true probability" of each outcome by averaging odds across sharp (professional) bookmakers.
3. It compares the true probability to each bookmaker's odds.
4. If a bookmaker's odds are better than what the true probability suggests, that's a "+EV" edge — you have an advantage.
5. It then calculates exactly how much you should bet using the Kelly Criterion (a mathematical formula for optimal bet sizing).

**What you see:**

- **Filters** — Choose sport (NBA, NFL, MLB, NHL, etc.), market type (Moneyline, Spreads, Totals), and minimum EV threshold.
- **Results Table** — Each row shows:
  - The matchup (e.g., Lakers vs Celtics)
  - The market (Moneyline, Spread, Total)
  - The selection (which side to bet)
  - Best available odds and which bookmaker has them
  - Model probability vs implied probability
  - EV percentage (higher = better edge)
  - Kelly percentage and recommended dollar stake
  - Confidence level (High, Medium, Low)
- **Auto-Refresh** — Toggle to automatically re-scan every few minutes.
- **Bet Slip** — Click any edge to add it to your bet slip for tracking.

**Example:** If the app shows "Lakers ML +150 at FanDuel, EV: +5.2%, Stake: $13.00" — it means FanDuel's odds on the Lakers are better than the true probability suggests, and based on your bankroll you should wager $13.

---

## 3. Player Props (ML-Powered)

**Page:** `http://localhost:8000/props`

Uses machine learning (XGBoost) to predict whether a player will go over or under their prop line.

**How it works:**

1. You first import a player's historical game data using the CLI (`sba data backfill --player "LeBron James"`).
2. The app trains an ML model on that player's stats — looking at their last 5 and 20 game averages, opponent matchup quality, home vs away performance, and recent trends.
3. When sportsbooks post prop lines (e.g., "LeBron James Over 25.5 Points"), the model predicts the probability of going over.
4. It compares the prediction to the sportsbook odds and flags +EV opportunities.

**What you see:**

- Player name, market (Points, Rebounds, Assists, 3-Pointers, etc.)
- The model's predicted value vs the sportsbook line
- Over/Under probabilities and EV for each side
- A recommendation (Over, Under, or Skip)
- Top contributing features (what the model relied on most)

**Supported prop markets:** Points, Rebounds, Assists, 3-Pointers, Blocks, Steals, Points+Rebounds+Assists (PRA)

---

## 4. My Bets

**Page:** `http://localhost:8000/my-bets`

A personal bet tracker. Log every bet you place and monitor your results over time.

**What you can do:**

- **Track a bet** — Record the selection, odds, stake, and bookmaker (either manually or from the Edge Finder bet slip).
- **Settle bets** — Mark bets as Won, Lost, or Push when they resolve.
- **Delete bets** — Remove incorrect entries.
- **Filter & Search** — Filter by status (Pending, Won, Lost, Push), market type, or search by text.
- **Export** — Download your entire bet history as CSV or JSON.

**What you see:**

- Summary stats at the top: Total P/L, Win Rate, ROI, Current Streak
- A table of all your bets with date, selection, market, odds, stake, bookmaker, status, and profit/loss
- Performance breakdowns by market type and by bookmaker

---

## 5. Analytics

**Page:** `http://localhost:8000/analytics`

Deep-dive into your betting performance with advanced metrics and visualizations.

**Sections:**

- **Summary** — Total P/L, Win Rate, ROI, and current streak at a glance.
- **Advanced Metrics** — Sharpe Ratio (risk-adjusted returns), Max Drawdown (worst losing streak impact), Profit Factor (gross wins / gross losses), longest win and loss streaks.
- **Cumulative P/L Chart** — Line graph of your profit over time.
- **Drawdown Analysis** — Shows peak-to-trough drops in your bankroll.
- **P/L Heatmap** — A 90-day calendar where each day is color-coded green (profit) or red (loss).
- **Performance Breakdowns** — Separate charts for performance by:
  - Sport (NBA vs NFL vs MLB, etc.)
  - Market type (Moneyline vs Spreads vs Totals)
  - Bookmaker (DraftKings vs FanDuel, etc.)
  - Day of week (are you better on weekends?)
  - Odds range (are you better at favorites or underdogs?)
- **Monthly Breakdown** — Month-by-month ROI and P/L.
- **Notable Bets** — Your biggest win and biggest loss.
- **Streak Analysis** — How quickly you recover from losing streaks.

---

## 6. Arbitrage Scanner

**Page:** `http://localhost:8000/arbitrage`

Finds guaranteed-profit opportunities by exploiting odds differences between sportsbooks.

**Three scan modes:**

### A. Arbitrage (Arbs)
When two bookmakers disagree enough on odds, you can bet both sides and guarantee a profit regardless of outcome. The app finds these situations automatically.

**Example:** Book A has Team X at +110, Book B has Team Y at +105. The combined implied probability is less than 100%, meaning you can split your stake to guarantee profit.

### B. Middles
Two bookmakers have different spread or total lines, creating a gap where both bets could win.

**Example:** Book A has Team X -3.5, Book B has Team Y +4.5. If Team X wins by exactly 4, both bets win.

### C. Low-Hold Markets
Markets where the sportsbook's vig (commission) is unusually low. Lower vig means the odds are closer to fair value, which is better for you long-term.

---

## 7. Line Movement

**Page:** `http://localhost:8000/line-movement`

Track how odds change over time for any event.

**Why it matters:** When odds move sharply in one direction, it often means sharp (professional) bettors are placing large wagers. Following sharp money movement is one of the most reliable betting strategies.

**What you see:**
- Select an event and market
- A timeline showing odds at each snapshot point
- Direction and magnitude of the line shift
- Which bookmakers moved first (often indicates where the sharp money landed)

---

## 8. Odds Comparison

**Page:** `http://localhost:8000/odds-comparison`

A side-by-side matrix comparing odds from every sportsbook for a given event.

**Format:**
- Rows = Outcomes (Home Win, Away Win, Draw)
- Columns = Bookmakers (DraftKings, FanDuel, BetMGM, Pinnacle, etc.)
- The best odds for each outcome are highlighted so you always know where to get the best price

---

## 9. Power Ratings

**Page:** `http://localhost:8000/power-ratings`

Team strength rankings derived from market odds.

**What you see:**
- A ranked list of all teams with their power rating, win percentage, games played, and trend direction
- **Matchup Analyzer** — Enter any two teams to get a predicted spread and win probability based on their ratings

**How it works:** The app uses odds from across all sportsbooks to reverse-engineer how strong each team is relative to others. Higher rating = stronger team.

---

## 10. Calculator

**Page:** `http://localhost:8000/calculator`

A suite of betting math tools:

| Tool | What It Does |
|------|-------------|
| **Odds Converter** | Convert between American (-110), Decimal (1.91), and Fractional (10/11) formats. Shows implied probability and payout. |
| **Kelly Criterion** | Enter the true win probability and odds — get the optimal percentage of your bankroll to wager. |
| **Hedge Calculator** | You placed a bet and want to guarantee profit. Enter your original bet details and the opposing odds — it tells you exactly how much to hedge. |
| **Parlay Calculator** | Combine multiple bets into a parlay. See the combined odds, total payout, and implied probability. |
| **Free Bet Converter** | Convert a sportsbook free bet into guaranteed cash by hedging with another bookmaker. |
| **No-Vig Fair Odds** | Enter both sides of a market — get the true fair odds with the bookmaker's vig removed. |

---

## 11. Backtester

**Page:** `http://localhost:8000/backtester`

Test a betting strategy against your historical data to see how it would have performed.

**How to use:**

1. Name your strategy
2. Set starting bankroll
3. Choose stake type: Flat dollar amount, Percentage of bankroll, or Kelly Criterion
4. Set filters: Minimum EV threshold, minimum/maximum odds range
5. Optionally set stop-loss and take-profit limits
6. Click "Run Backtest"

**Results include:**
- Letter grade (A through F)
- Total profit, ROI, win rate
- Number of bets placed, total amount wagered
- Max drawdown (worst dip), Sharpe ratio (risk-adjusted return)
- Win/loss streaks, profit factor
- An equity curve chart showing the bankroll over time

---

## 12. Simulator (Monte Carlo)

**Page:** `http://localhost:8000/simulator`

Project your future bankroll using Monte Carlo simulation (running thousands of random scenarios).

**You enter:**
- Starting bankroll
- Expected number of bets
- Average odds and win rate
- Kelly fraction (how aggressive your sizing is)

**You get:**
- A fan chart showing percentile outcomes (best case, likely case, worst case)
- Median final bankroll value
- Percentage of scenarios that are profitable
- Median ROI

This helps answer questions like: "If I make 500 bets at these average odds and win rate, what's the range of outcomes?"

---

## 13. SGP Builder (Same-Game Parlay)

**Page:** `http://localhost:8000/sgp-builder`

Build multi-leg same-game parlays with correlation awareness.

**How it works:**

1. Add legs one by one: select the market (Points, Rebounds, Team Win, Spread, etc.), direction (Over/Under), and odds.
2. The app checks for correlations between legs. For example, "Player scores 30+ points" and "Team wins" are positively correlated — the combined probability isn't just multiplying both.
3. It adjusts the combined odds to account for these correlations.
4. It warns you about dangerous combinations (high correlation means the sportsbook's combined odds are likely a bad deal for you).

---

## 14. Bankroll Management

**Page:** `http://localhost:8000/bankroll`

Track your betting bankroll separately from bet P/L.

**Features:**
- Set your initial bankroll amount
- Record deposits and withdrawals
- See a running history of all transactions
- Daily P/L summary chart
- Current balance always visible

---

## 15. Bet Grades

**Page:** `http://localhost:8000/bet-grades`

Every betting opportunity gets a 1-5 star quality rating.

**Rating factors:**
- **Edge size** (35% of score) — How big is the EV advantage?
- **Sharp book agreement** (25%) — Do professional bookmakers agree with the edge?
- **Line movement** (15%) — Is the line moving in a favorable direction?
- **Historical hit rate** (15%) — How often has this type of bet hit historically?
- **Market efficiency** (10%) — How liquid and well-priced is this market?

**Star thresholds:**
- 5 stars = 8%+ edge (rare, high confidence)
- 4 stars = 5-8% edge
- 3 stars = 3-5% edge
- 2 stars = 1.5-3% edge
- 1 star = 0-1.5% edge

---

## 16. Watchlist

**Page:** `http://localhost:8000/watchlist`

Save events you want to keep an eye on. Add or remove events with one click. Your watchlist persists across sessions.

---

## 17. Live Feed

**Page:** `http://localhost:8000/live-feed`

A real-time stream of the latest odds updates from all sportsbooks. See which odds just changed and by how much.

---

## 18. Odds Screen

**Page:** `http://localhost:8000/odds-screen`

A comprehensive odds board showing all upcoming events with their current odds across bookmakers, similar to what you'd see at a sportsbook.

---

## 19. Achievements

**Page:** `http://localhost:8000/achievements`

Gamification to make tracking your bets more engaging.

**Tier system:** Bronze, Silver, Gold, Diamond

**Examples of achievements:**
- "First Blood" — Place your first bet
- "Sharp Eye" — Win 5 bets in a row
- "Bankroll Builder" — Grow your bankroll by 20%
- "Data Scientist" — Backfill 10 players

Each achievement earns points that contribute to your overall rank (Rookie, Amateur, Semi-Pro, Pro, Sharp, Elite).

---

## 20. Smart Insights

**Page:** `http://localhost:8000/insights`

AI-generated personalized advice based on your betting history.

**Example insights:**
- "You're on a 5-loss streak. Consider reducing stake size until it breaks."
- "Your ROI on totals is +12% but spreads is -8%. Consider focusing more on totals."
- "You tend to lose more on evening games. Review your approach."
- "Great job! You've been profitable 7 of the last 10 days."

**Severity levels:** Critical (red), Warning (yellow), Success (green), Info (blue)

---

## 21. Devig Engine

**Page:** `http://localhost:8000/devig`

Remove the bookmaker's vig (commission) to find the true fair probability.

**Why it matters:** Sportsbooks inflate odds to guarantee themselves a profit. By removing the vig, you can see the real implied probability and know if you're getting a fair price.

**Methods available:**
1. **Multiplicative** — Standard approach, scales probabilities proportionally
2. **Additive** — Subtracts vig equally from both sides
3. **Power/Shin** — More sophisticated mathematical adjustment
4. **Worst Case** — Conservative estimate (assumes worst case for the bettor)

**How to use:** Enter the odds for all outcomes in a market. The engine shows you the true fair odds and probabilities for each.

---

## 22. Promo Optimizer

**Page:** `http://localhost:8000/promo-optimizer`

Maximize the value of sportsbook promotional offers like free bets, odds boosts, deposit matches, and risk-free bets.

---

## 23. Public Money Tracker

**Page:** `http://localhost:8000/public-money`

See where casual bettors are putting their money. Public money often moves lines in predictable ways, and professional bettors frequently bet against ("fade") the public.

---

## 24. Sharp Money Tracker

**Page:** `http://localhost:8000/sharp-money`

Identify where professional bettors are placing their money. Sharp money is detected through:
- Sudden, large line movements
- Movement originating from sharp books (Pinnacle, Circa)
- Reverse line movement (line moves opposite to public betting percentages)

---

## 25. Community

**Page:** `http://localhost:8000/community`

User engagement and social features including leaderboards and shared picks.

---

## 26. Settings

**Page:** `http://localhost:8000/settings`

Customize your app experience:

| Setting | What It Controls |
|---------|-----------------|
| **Bankroll** | Your total betting bankroll (used for Kelly sizing) |
| **Kelly Fraction** | How aggressive your bet sizing is (0.25 = quarter Kelly, conservative) |
| **EV Threshold** | Minimum edge percentage to show in results (0.02 = 2%) |
| **Default Sport** | Which sport loads by default |
| **Refresh Interval** | How often auto-refresh polls for new odds (in seconds) |
| **Accent Theme** | Choose from Default, Emerald, Neon, Gold, or Ocean color themes |

---

## 27. CLI Commands

The app also has a command-line interface for power users.

### Data Management
```bash
sba data sync --sport basketball_nba     # Fetch live odds from The Odds API
sba data backfill --player "LeBron James" # Import player's historical game logs
sba data status                           # Show database counts
```

### Edge Finding
```bash
sba edge scan -s basketball_nba -m h2h,spreads --min-ev 0.05   # Find edges
sba edge arbs -s basketball_nba                                  # Find arbitrage
sba edge track [event_id] [market] [selection] [odds]            # Track a bet
sba edge settle [bet_id] won|lost|push                           # Settle a bet
```

### ML Models
```bash
sba models train --player "LeBron James"  # Train prop prediction model
```

### Props Analysis
```bash
sba props analyze --sport basketball_nba  # Analyze all available props
```

### Web Dashboard
```bash
sba web                    # Start dashboard at http://localhost:8000
sba web --reload           # Start with auto-reload (for development)
sba web --port 3000        # Use a custom port
```

### Monitoring
```bash
sba monitor                # Real-time terminal dashboard
```

---

## 28. API Reference

All API endpoints are prefixed with `/api/`.

### Health & Status
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | System health check |
| GET | `/status` | Database table counts |

### Edge Finding
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/edges` | Scan for +EV opportunities |
| GET | `/arbitrage` | Scan for arbitrage |
| GET | `/middles` | Scan for middles |
| GET | `/low-holds` | Scan for low-vig markets |

### Player Props
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/props` | ML prop predictions |
| GET | `/players/{name}` | Player profile and game logs |
| GET | `/search/players?q=...` | Search for players |

### Bet Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/bets` | Bet history and summary |
| POST | `/bets/track` | Track a new bet |
| PUT | `/bets/{id}/settle` | Settle a bet (won/lost/push) |
| DELETE | `/bets/{id}` | Delete a bet |
| GET | `/bets/export` | Export bets as CSV |
| GET | `/bets/export/json` | Export bets as JSON |

### Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/analytics` | Overall performance summary |
| GET | `/analytics/advanced` | Sharpe ratio, drawdown, streaks |
| GET | `/analytics/by-sport` | Performance by sport |
| GET | `/analytics/by-market` | Performance by market type |
| GET | `/analytics/by-book` | Performance by bookmaker |
| GET | `/analytics/by-day` | Performance by day of week |
| GET | `/analytics/by-odds-range` | Performance by odds range |
| GET | `/analytics/streaks` | Streak analysis |
| GET | `/analytics/trends` | Rolling trends |
| GET | `/analytics/heatmap` | Day x Hour performance matrix |

### Calculators
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/calculator` | Odds conversion and payout |
| POST | `/calculator/hedge` | Hedge calculator |
| POST | `/calculator/parlay` | Parlay odds and payout |
| POST | `/calculator/freebet` | Free bet converter |
| POST | `/calculator/novig` | Remove vig from odds |
| POST | `/calculator/devig` | Devig calculation |
| POST | `/calculator/devig/multi` | Multi-way devig |
| POST | `/calculator/sgp` | Same-game parlay correlation |
| POST | `/calculator/promo` | Promo value calculation |

### Odds & Events
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/events` | All tracked events |
| GET | `/live-odds` | Real-time odds stream |
| GET | `/odds-screen` | Full odds board |
| GET | `/odds-comparison/{event_id}` | Side-by-side book comparison |
| GET | `/line-movement/{event_id}` | Historical odds changes |
| GET | `/consensus/{event_id}` | Consensus probability |
| GET | `/sports` | Available sports list |

### Power Ratings
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/power-ratings` | Team strength rankings |
| GET | `/matchup` | Head-to-head prediction |

### Bankroll
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/bankroll` | Current balance and history |
| POST | `/bankroll/initialize` | Set starting bankroll |
| POST | `/bankroll/deposit` | Record a deposit |
| POST | `/bankroll/withdraw` | Record a withdrawal |
| GET | `/bankroll/daily` | Daily P/L summary |

### Simulations & Backtesting
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/simulate` | Monte Carlo bankroll projection |
| POST | `/backtest` | Strategy backtest |

### Watchlist
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/watchlist` | Saved events |
| POST | `/watchlist` | Add event to watchlist |
| DELETE | `/watchlist/{event_id}` | Remove from watchlist |

### Alerts & Insights
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/alerts` | Unread alerts |
| POST | `/alerts` | Create alert |
| DELETE | `/alerts` | Clear all alerts |
| GET | `/insights` | AI-generated insights |
| GET | `/achievements` | All achievements |
| GET | `/achievements/summary` | Achievement progress |

### Settings
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/settings` | Current configuration |
| PUT | `/settings` | Update settings |

Full interactive API docs available at `http://localhost:8000/api/docs`.

---

## 29. Data Sources

| Source | What It Provides | API Key Required |
|--------|-----------------|-----------------|
| **The Odds API** | Live and historical odds from 30+ sportsbooks (DraftKings, FanDuel, BetMGM, Pinnacle, etc.) | Yes (`SBA_ODDS_API_KEY`) |
| **BallDontLie API** | NBA/NCAAB player statistics and game logs | Yes (`SBA_BALLDONTLIE_API_KEY`) |
| **SQLite Database** | Local storage for bets, events, odds snapshots, players, and game logs | No (auto-created) |

---

## 30. Configuration

All settings are configured via the `.env` file in the project root:

```env
# API Keys
SBA_ODDS_API_KEY=your_odds_api_key_here        # Required for odds data
SBA_BALLDONTLIE_API_KEY=your_key_here           # Required for player stats

# Database
SBA_DB_PATH=data/sba.db                        # SQLite database location

# Betting Defaults
SBA_BANKROLL=1000.0                            # Starting bankroll ($)
SBA_KELLY_FRACTION=0.25                        # Kelly multiplier (0.25 = quarter Kelly)
SBA_EV_THRESHOLD=0.02                          # Minimum EV to display (0.02 = 2%)

# Preferences
SBA_DEFAULT_SPORT=basketball_nba               # Default sport to load
SBA_DEFAULT_REGION=us                          # Odds region
SBA_REFRESH_INTERVAL_SECONDS=300               # Auto-refresh interval
SBA_LOG_LEVEL=INFO                             # Logging verbosity
```

### Getting API Keys

1. **The Odds API** — Sign up at [the-odds-api.com](https://the-odds-api.com). Free tier includes 500 requests/month.
2. **BallDontLie API** — Sign up at [balldontlie.io](https://balldontlie.io). Free tier available.

---

## Quick Start

```bash
# 1. Install
cd sports-betting-analytics
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Sync data
sba data sync --sport basketball_nba

# 4. Launch
sba web --reload
# Open http://localhost:8000
```
