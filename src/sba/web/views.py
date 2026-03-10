"""Template view routes for the web dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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


@router.get("/player/{name}")
def player_page(request: Request, name: str):
    return templates.TemplateResponse(request, "player.html", {"player_name": name})
