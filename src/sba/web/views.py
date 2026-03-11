"""Template view routes for the web dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from sba import __version__

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["version"] = __version__

router = APIRouter(tags=["views"])


@router.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@router.get("/edges")
def edges_page(request: Request):
    return templates.TemplateResponse(request, "edges.html")


@router.get("/props")
def props_page(request: Request):
    return templates.TemplateResponse(request, "props.html")


@router.get("/my-bets")
def bets_page(request: Request):
    return templates.TemplateResponse(request, "bets.html")


@router.get("/analytics")
def analytics_page(request: Request):
    return templates.TemplateResponse(request, "analytics.html")


@router.get("/settings")
def settings_page(request: Request):
    return templates.TemplateResponse(request, "settings.html")


@router.get("/line-movement")
def line_movement_page(request: Request):
    return templates.TemplateResponse(request, "line-movement.html")


@router.get("/odds-comparison")
def odds_comparison_page(request: Request):
    return templates.TemplateResponse(request, "odds-comparison.html")


@router.get("/simulator")
def simulator_page(request: Request):
    return templates.TemplateResponse(request, "simulator.html")


@router.get("/live-feed")
def live_feed_page(request: Request):
    return templates.TemplateResponse(request, "live-feed.html")


@router.get("/arbitrage")
def arbitrage_page(request: Request):
    return templates.TemplateResponse(request, "arbitrage.html")


@router.get("/calculator")
def calculator_page(request: Request):
    return templates.TemplateResponse(request, "calculator.html")


@router.get("/watchlist")
def watchlist_page(request: Request):
    return templates.TemplateResponse(request, "watchlist.html")


@router.get("/bankroll")
def bankroll_page(request: Request):
    return templates.TemplateResponse(request, "bankroll.html")


@router.get("/sharp-money")
def sharp_money_page(request: Request):
    return templates.TemplateResponse(request, "sharp-money.html")


@router.get("/community")
def community_page(request: Request):
    return templates.TemplateResponse(request, "community.html")


@router.get("/sgp-builder")
def sgp_builder_page(request: Request):
    return templates.TemplateResponse(request, "sgp-builder.html")


@router.get("/power-ratings")
def power_ratings_page(request: Request):
    return templates.TemplateResponse(request, "power-ratings.html")


@router.get("/odds-screen")
def odds_screen_page(request: Request):
    return templates.TemplateResponse(request, "odds-screen.html")


@router.get("/promo-optimizer")
def promo_optimizer_page(request: Request):
    return templates.TemplateResponse(request, "promo-optimizer.html")


@router.get("/devig")
def devig_page(request: Request):
    return templates.TemplateResponse(request, "devig.html")


@router.get("/bet-grades")
def bet_grades_page(request: Request):
    return templates.TemplateResponse(request, "bet-grades.html")


@router.get("/backtester")
def backtester_page(request: Request):
    return templates.TemplateResponse(request, "backtester.html")


@router.get("/public-money")
def public_money_page(request: Request):
    return templates.TemplateResponse(request, "public-money.html")


@router.get("/achievements")
def achievements_page(request: Request):
    return templates.TemplateResponse(request, "achievements.html")


@router.get("/insights")
def insights_page(request: Request):
    return templates.TemplateResponse(request, "insights.html")


@router.get("/clv-dashboard")
def clv_dashboard_page(request: Request):
    return templates.TemplateResponse(request, "clv-dashboard.html")


@router.get("/bonus-converter")
def bonus_converter_page(request: Request):
    return templates.TemplateResponse(request, "bonus-converter.html")


@router.get("/responsible-gambling")
def responsible_gambling_page(request: Request):
    return templates.TemplateResponse(request, "responsible-gambling.html")


@router.get("/player/{name}")
def player_page(request: Request, name: str):
    return templates.TemplateResponse(request, "player.html", {"player_name": name})


@router.get("/multibook")
def multibook_page(request: Request):
    return templates.TemplateResponse(request, "multibook.html")


@router.get("/account-limits")
def account_limits_page(request: Request):
    return templates.TemplateResponse(request, "account-limits.html")


@router.get("/portfolio")
def portfolio_page(request: Request):
    return templates.TemplateResponse(request, "portfolio.html")


@router.get("/bet-import")
def bet_import_page(request: Request):
    return templates.TemplateResponse(request, "bet-import.html")


@router.get("/notifications")
def notifications_page(request: Request):
    return templates.TemplateResponse(request, "notifications.html")


@router.get("/roi-forecast")
def roi_forecast_page(request: Request):
    return templates.TemplateResponse(request, "roi-forecast.html")


@router.get("/bet-timing")
def bet_timing_page(request: Request):
    return templates.TemplateResponse(request, "bet-timing.html")


@router.get("/risk-metrics")
def risk_metrics_page(request: Request):
    return templates.TemplateResponse(request, "risk-metrics.html")


@router.get("/performance-digest")
def performance_digest_page(request: Request):
    return templates.TemplateResponse(request, "performance-digest.html")
