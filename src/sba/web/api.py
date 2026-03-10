"""REST API endpoints for the web dashboard.

This module serves as the central hub that aggregates all sub-routers.
Sub-routers import `repo` from this module for database access.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from sba.data.db.repository import Repository

logger = logging.getLogger(__name__)
router = APIRouter(tags=["api"])
repo = Repository()


# ── Import and include all sub-routers ───────────────────────────────

from sba.web.routes.edges import router as edges_router          # noqa: E402
from sba.web.routes.props import router as props_router          # noqa: E402
from sba.web.routes.bets import router as bets_router            # noqa: E402
from sba.web.routes.analytics import router as analytics_router  # noqa: E402
from sba.web.routes.calculators import router as calc_router     # noqa: E402
from sba.web.routes.odds import router as odds_router            # noqa: E402
from sba.web.routes.bankroll import router as bankroll_router     # noqa: E402
from sba.web.routes.social import router as social_router        # noqa: E402
from sba.web.routes.settings_routes import router as settings_router  # noqa: E402
from sba.web.routes.performance import router as perf_router     # noqa: E402
from sba.web.routes.multibook import router as multibook_router  # noqa: E402
from sba.web.routes.portfolio import router as portfolio_router  # noqa: E402
from sba.web.routes.splits import router as splits_router        # noqa: E402
from sba.web.routes.notifications import router as notif_router  # noqa: E402
from sba.web.routes.responsible_gambling import router as rg_router  # noqa: E402
from sba.web.routes.live_analytics import router as live_router      # noqa: E402
from sba.web.routes.smart_signals import router as signals_router    # noqa: E402
from sba.web.routes.nlq import router as nlq_router                  # noqa: E402
from sba.web.routes.reporting import router as reporting_router       # noqa: E402
from sba.web.routes.clv import router as clv_router                  # noqa: E402
from sba.web.routes.simulation import router as sim_router           # noqa: E402

router.include_router(edges_router)
router.include_router(props_router)
router.include_router(bets_router)
router.include_router(analytics_router)
router.include_router(calc_router)
router.include_router(odds_router)
router.include_router(bankroll_router)
router.include_router(social_router)
router.include_router(settings_router)
router.include_router(perf_router)
router.include_router(multibook_router)
router.include_router(portfolio_router)
router.include_router(splits_router)
router.include_router(notif_router)
router.include_router(rg_router)
router.include_router(live_router)
router.include_router(signals_router)
router.include_router(nlq_router)
router.include_router(reporting_router)
router.include_router(clv_router)
router.include_router(sim_router)
