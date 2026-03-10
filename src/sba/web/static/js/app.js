/* ═══════════════════════════════════════════════════════════════════════
   SBA — Sports Betting Analytics — Premium Frontend Application
   ═══════════════════════════════════════════════════════════════════════ */

const SBA = {
    betSlip: [],
    refreshTimer: null,
    refreshInterval: 60,
    refreshCountdown: 60,
    sortState: {},

    // ── Initialization ────────────────────────────────────────────────
    init() {
        this.loadTheme();
        this.loadAccent();
        this.setupClock();
        this.setupSearch();
        this.setupKeyboardShortcuts();
        this.setupCommandPalette();
        this.updateStatus();
        this.highlightActiveNav();
        this.checkAlerts();
        setInterval(() => this.updateStatus(), 60000);
        setInterval(() => this.checkAlerts(), 30000);
    },

    // ── Clock ─────────────────────────────────────────────────────────
    setupClock() {
        const el = document.getElementById('live-clock');
        if (!el) return;
        const update = () => {
            const now = new Date();
            el.textContent = now.toLocaleTimeString('en-US', {
                hour: '2-digit', minute: '2-digit', second: '2-digit'
            });
        };
        update();
        setInterval(update, 1000);
    },

    // ── Navigation ────────────────────────────────────────────────────
    highlightActiveNav() {
        const path = window.location.pathname;
        // Sidebar nav
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
            const href = link.getAttribute('href');
            if (path === href || (path === '/' && href === '/')) {
                link.classList.add('active');
            }
        });
        // Mobile bottom nav
        document.querySelectorAll('.mobile-nav-item').forEach(item => {
            item.classList.remove('active');
            const href = item.getAttribute('href');
            if (path === href || (path === '/' && href === '/')) {
                item.classList.add('active');
            }
        });
    },

    // ── Keyboard Shortcuts ────────────────────────────────────────────
    _gKeyPending: false,
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl+K: Command palette
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                this.cmdPaletteOpen ? this.closeCommandPalette() : this.openCommandPalette();
                return;
            }

            // Don't fire shortcuts when typing in inputs or command palette
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                if (e.key === 'Escape') {
                    e.target.blur();
                    this.closeCommandPalette();
                }
                return;
            }

            // Handle Escape first
            if (e.key === 'Escape') {
                document.getElementById('bet-slip')?.classList.remove('open');
                document.getElementById('shortcuts-modal')?.classList.remove('open');
                this.closeCommandPalette();
                this._gKeyPending = false;
                return;
            }

            // G-key prefix navigation (g then d/e/p/b/a/l/o/s)
            if (this._gKeyPending) {
                this._gKeyPending = false;
                const navMap = {d:'/',e:'/edges',p:'/props',b:'/my-bets',a:'/analytics',l:'/line-movement',o:'/odds-comparison',s:'/settings',c:'/calculator',f:'/live-feed',m:'/simulator',w:'/watchlist'};
                if (navMap[e.key]) { location.href = navMap[e.key]; return; }
            }

            switch(e.key) {
                case '/':
                    e.preventDefault();
                    document.getElementById('player-search')?.focus();
                    break;
                case 'b':
                    this.toggleSlip();
                    break;
                case 't':
                    this.toggleTheme();
                    break;
                case 'g':
                    this._gKeyPending = true;
                    setTimeout(() => { this._gKeyPending = false; }, 800);
                    break;
                case '?':
                    this.showShortcutsModal();
                    break;
            }
        });
    },

    // ── Player Search ─────────────────────────────────────────────────
    setupSearch() {
        const input = document.getElementById('player-search');
        const results = document.getElementById('search-results');
        if (!input || !results) return;

        let debounce = null;
        input.addEventListener('input', () => {
            clearTimeout(debounce);
            const q = input.value.trim();
            if (q.length < 2) { results.classList.remove('active'); return; }
            debounce = setTimeout(() => this.searchPlayers(q), 300);
        });

        // Escape to close
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                results.classList.remove('active');
                input.blur();
            }
        });

        document.addEventListener('click', (e) => {
            if (!e.target.closest('.search-box')) results.classList.remove('active');
        });
    },

    async searchPlayers(query) {
        const results = document.getElementById('search-results');
        try {
            const resp = await fetch(`/api/search/players?q=${encodeURIComponent(query)}`);
            if (resp.ok) {
                const players = await resp.json();
                if (players.length > 0) {
                    results.innerHTML = players.map(p => `
                        <a class="search-result-item" href="/player/${encodeURIComponent(p.name)}">
                            <span>${p.name}</span>
                            <span class="text-dim">${p.team} · ${p.position}</span>
                        </a>`).join('');
                    results.classList.add('active');
                } else {
                    results.innerHTML = '<div class="search-result-item text-dim">No players found</div>';
                    results.classList.add('active');
                }
            } else {
                results.innerHTML = '<div class="search-result-item text-dim">No players found</div>';
                results.classList.add('active');
            }
        } catch {
            results.classList.remove('active');
        }
    },

    // ── API Status ────────────────────────────────────────────────────
    async updateStatus() {
        const el = document.getElementById('api-status');
        if (!el) return;
        try {
            const resp = await fetch('/api/status');
            const data = await resp.json();
            const dot = el.querySelector('.status-dot');
            const text = el.querySelector('.status-text');
            dot.classList.remove('offline');
            text.textContent = `${data.events} events · ${data.players} players`;
        } catch {
            const dot = el.querySelector('.status-dot');
            const text = el.querySelector('.status-text');
            dot.classList.add('offline');
            text.textContent = 'Offline';
        }
    },

    // ── Count-Up Animation ────────────────────────────────────────────
    animateCountUp(element, target, duration = 800) {
        const start = 0;
        const startTime = performance.now();
        const isFloat = String(target).includes('.');
        const prefix = element.dataset.prefix || '';
        const suffix = element.dataset.suffix || '';

        const step = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            // Ease out cubic
            const eased = 1 - Math.pow(1 - progress, 3);
            const current = start + (target - start) * eased;
            element.textContent = prefix + (isFloat ? current.toFixed(1) : Math.round(current).toLocaleString()) + suffix;
            if (progress < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    },

    // ── Table Sorting ─────────────────────────────────────────────────
    sortTable(tableId, colIndex, type = 'string') {
        const tbody = document.getElementById(tableId);
        if (!tbody) return;
        const rows = Array.from(tbody.querySelectorAll('tr'));
        if (rows.length === 0) return;

        const key = `${tableId}-${colIndex}`;
        const ascending = this.sortState[key] !== 'asc';
        this.sortState[key] = ascending ? 'asc' : 'desc';

        // Update header visual
        const table = tbody.closest('table');
        table.querySelectorAll('th').forEach(th => th.classList.remove('sort-asc', 'sort-desc'));
        const th = table.querySelectorAll('th')[colIndex];
        th.classList.add(ascending ? 'sort-asc' : 'sort-desc');

        rows.sort((a, b) => {
            let aVal = a.cells[colIndex]?.textContent.trim() || '';
            let bVal = b.cells[colIndex]?.textContent.trim() || '';

            if (type === 'number') {
                aVal = parseFloat(aVal.replace(/[^0-9.\-]/g, '')) || 0;
                bVal = parseFloat(bVal.replace(/[^0-9.\-]/g, '')) || 0;
            }

            if (aVal < bVal) return ascending ? -1 : 1;
            if (aVal > bVal) return ascending ? 1 : -1;
            return 0;
        });

        rows.forEach(row => tbody.appendChild(row));
    },

    // ── Auto-Refresh ──────────────────────────────────────────────────
    startAutoRefresh(callback, interval = 60) {
        this.refreshInterval = interval;
        this.refreshCountdown = interval;
        this.stopAutoRefresh();

        const timerEl = document.getElementById('refresh-countdown');
        const ringEl = document.querySelector('.refresh-ring .fg');

        this.refreshTimer = setInterval(() => {
            this.refreshCountdown--;
            if (timerEl) timerEl.textContent = `${this.refreshCountdown}s`;
            if (ringEl) {
                const pct = this.refreshCountdown / this.refreshInterval;
                ringEl.style.strokeDashoffset = 50.26 * (1 - pct);
            }
            if (this.refreshCountdown <= 0) {
                this.refreshCountdown = this.refreshInterval;
                callback();
            }
        }, 1000);
    },

    stopAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    },

    // ── Edge Finder ───────────────────────────────────────────────────
    async loadEdges(sport, market, minEv) {
        const container = document.getElementById('edges-table-body');
        const countEl = document.getElementById('edges-count');
        if (!container) return;

        container.innerHTML = '<tr><td colspan="11" class="loading-spinner"><div class="spinner"></div> Scanning odds across all books...</td></tr>';

        try {
            let url = '/api/edges?';
            if (sport) url += `sport=${sport}&`;
            if (market) url += `market=${market}&`;
            if (minEv) url += `min_ev=${minEv}&`;

            const resp = await fetch(url);
            const edges = await resp.json();

            if (countEl) {
                countEl.textContent = edges.length;
            }

            // Edge summary banner
            const bannerEl = document.getElementById('edge-summary-banner');
            if (bannerEl) {
                bannerEl.innerHTML = this.createEdgeSummaryBanner(edges);
            }

            if (edges.length === 0) {
                container.innerHTML = `<tr><td colspan="11" class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
                    <p>No +EV opportunities found right now. Try adjusting filters or check back later.</p>
                </td></tr>`;
                if (bannerEl) bannerEl.innerHTML = '';
                return;
            }

            container.innerHTML = edges.map((e, i) => `
                <tr class="new-row ${this.getEvHeatClass(e.ev)}" style="animation-delay:${i * 0.03}s">
                    <td>
                        <div class="matchup-teams">
                            <span class="team-name away">${e.event_away}</span>
                            <span class="team-name home">@ ${e.event_home}</span>
                        </div>
                    </td>
                    <td><span class="market-tag">${e.market}</span></td>
                    <td class="font-bold">${e.selection}${e.line ? ` (${e.line > 0 ? '+' : ''}${e.line})` : ''}</td>
                    <td class="right">
                        <span class="odds-badge ${e.best_odds_american > 0 ? 'positive' : 'negative'}"
                              onclick="SBA.addToSlip('${e.event_id}', '${e.selection}', ${e.best_odds_american}, '${e.market}', '${e.bookmaker}', '${e.event_away} @ ${e.event_home}', ${e.recommended_stake})"
                              data-tooltip="Click to add to bet slip">
                            ${e.best_odds_american > 0 ? '+' : ''}${e.best_odds_american}
                        </span>
                    </td>
                    <td class="text-dim">${e.bookmaker}</td>
                    <td class="right font-mono">${(e.model_prob * 100).toFixed(1)}%</td>
                    <td class="right font-mono">${(e.implied_prob * 100).toFixed(1)}%</td>
                    <td class="right"><span class="ev-badge ${e.ev >= 0.08 ? 'high' : e.ev >= 0.04 ? 'medium' : 'low'} ${e.ev >= 0.08 ? 'glow-green' : ''}">${e.ev_pct}</span></td>
                    <td class="right font-mono">${(e.kelly_pct * 100).toFixed(1)}%</td>
                    <td class="right font-bold text-green">$${e.recommended_stake.toFixed(0)}</td>
                    <td class="center">${this.createConfidenceMeter(e.confidence)}<div style="font-size:10px;color:var(--text-tertiary);margin-top:2px">${e.confidence}</div></td>
                </tr>
            `).join('');
        } catch (err) {
            container.innerHTML = `<tr><td colspan="11" class="empty-state"><p class="text-red">Error loading edges: ${err.message}</p></td></tr>`;
        }
    },

    // ── Props Analyzer ────────────────────────────────────────────────
    async loadProps(sport, markets) {
        const container = document.getElementById('props-table-body');
        const countEl = document.getElementById('props-count');
        if (!container) return;

        container.innerHTML = '<tr><td colspan="10" class="loading-spinner"><div class="spinner"></div> Analyzing player props with ML models...</td></tr>';

        try {
            let url = '/api/props?';
            if (sport) url += `sport=${sport}&`;
            if (markets) url += `markets=${markets}&`;

            const resp = await fetch(url);
            const props = await resp.json();

            if (countEl) countEl.textContent = props.length;

            if (props.length === 0) {
                container.innerHTML = `<tr><td colspan="10" class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
                    <p>No +EV props found. Models need player data — run backfill first.</p>
                </td></tr>`;
                return;
            }

            container.innerHTML = props.map((p, i) => {
                const recClass = p.recommendation.includes('OVER') ? 'over' : p.recommendation.includes('UNDER') ? 'under' : 'pass';
                const overEv = (p.over_ev * 100).toFixed(1);
                const underEv = (p.under_ev * 100).toFixed(1);
                return `
                <tr class="new-row" style="animation-delay:${i * 0.03}s">
                    <td>
                        <a href="/player/${encodeURIComponent(p.player_name)}" class="font-bold">${p.player_name}</a>
                        <div class="text-dim" style="font-size:11px">${p.player_team}</div>
                    </td>
                    <td><span class="market-tag">${p.market}</span></td>
                    <td class="right font-mono font-bold">${p.predicted_value}</td>
                    <td class="right font-mono">${p.line}</td>
                    <td class="right font-mono">${(p.over_prob * 100).toFixed(1)}%</td>
                    <td class="right">
                        ${p.over_odds_american !== null ? `<span class="odds-badge ${p.over_odds_american > 0 ? 'positive' : 'negative'}">${p.over_odds_american > 0 ? '+' : ''}${p.over_odds_american}</span>` : '-'}
                    </td>
                    <td class="right"><span class="ev-badge ${p.over_ev >= 0.04 ? 'high' : p.over_ev > 0 ? 'medium' : 'negative'}">${overEv > 0 ? '+' : ''}${overEv}%</span></td>
                    <td class="right"><span class="ev-badge ${p.under_ev >= 0.04 ? 'high' : p.under_ev > 0 ? 'medium' : 'negative'}">${underEv > 0 ? '+' : ''}${underEv}%</span></td>
                    <td class="center"><span class="rec-badge ${recClass}">${p.recommendation}</span></td>
                    <td class="text-dim" style="font-size:11px">${p.top_features.slice(0, 3).join(', ')}</td>
                </tr>`;
            }).join('');
        } catch (err) {
            container.innerHTML = `<tr><td colspan="10" class="empty-state"><p class="text-red">Error: ${err.message}</p></td></tr>`;
        }
    },

    // ── Bet Tracking ──────────────────────────────────────────────────
    async loadBets() {
        const summary = document.getElementById('bets-summary');
        const tableBody = document.getElementById('bets-table-body');
        if (!summary || !tableBody) return;

        try {
            const resp = await fetch('/api/bets');
            const data = await resp.json();

            // Summary cards with icons
            summary.innerHTML = `
                <div class="stat-card green">
                    <div class="stat-label">Total P/L</div>
                    <div class="stat-value ${data.total_profit >= 0 ? 'text-green' : 'text-red'}">$${data.total_profit >= 0 ? '+' : ''}${data.total_profit.toFixed(2)}</div>
                    <div class="stat-sub">ROI: <span class="${data.roi >= 0 ? 'text-green' : 'text-red'}">${data.roi >= 0 ? '+' : ''}${data.roi.toFixed(1)}%</span></div>
                </div>
                <div class="stat-card blue">
                    <div class="stat-label">Win Rate</div>
                    <div class="stat-value">${(data.win_rate * 100).toFixed(0)}%</div>
                    <div class="stat-sub">${data.wins}W - ${data.losses}L</div>
                    <div class="progress-bar"><div class="progress-fill green" style="width:${data.win_rate * 100}%"></div></div>
                </div>
                <div class="stat-card yellow">
                    <div class="stat-label">Total Staked</div>
                    <div class="stat-value">$${data.total_staked.toFixed(0)}</div>
                    <div class="stat-sub">${data.total_bets} settled bets</div>
                </div>
                <div class="stat-card purple">
                    <div class="stat-label">Pending</div>
                    <div class="stat-value">${data.pending}</div>
                    <div class="stat-sub">open bets</div>
                </div>
            `;

            // Bets table
            if (data.bets.length === 0) {
                tableBody.innerHTML = '<tr><td colspan="9" class="empty-state"><p>No bets tracked yet. Add bets from the Edge Finder or Props page.</p></td></tr>';
                return;
            }

            tableBody.innerHTML = data.bets.map((b, i) => {
                const payout = this.calcPayout(b.odds_american, b.recommended_stake);
                const actions = b.status === 'pending' ? `
                    <div style="display:flex;gap:4px;justify-content:center">
                        <button class="btn btn-sm" style="background:var(--accent-green-dim);color:var(--accent-green);padding:4px 8px;font-size:10px" onclick="SBA.settleBetWithEffect(${b.id}, 'won', ${payout.toFixed(2)})">Won</button>
                        <button class="btn btn-sm" style="background:var(--accent-red-dim);color:var(--accent-red);padding:4px 8px;font-size:10px" onclick="SBA.settleBet(${b.id}, 'lost', ${(-b.recommended_stake).toFixed(2)})">Lost</button>
                        <button class="btn btn-sm" style="background:var(--accent-yellow-dim);color:var(--accent-yellow);padding:4px 8px;font-size:10px" onclick="SBA.settleBet(${b.id}, 'push', 0)">Push</button>
                    </div>` : `<button class="btn btn-sm" style="color:var(--text-tertiary);padding:4px 8px;font-size:10px" onclick="SBA.deleteBet(${b.id})">Delete</button>`;
                return `
                <tr class="new-row" style="animation-delay:${i * 0.03}s">
                    <td class="text-dim" style="font-size:11px">${b.placed_at ? new Date(b.placed_at).toLocaleDateString() : '-'}</td>
                    <td class="font-bold">${b.selection}</td>
                    <td><span class="market-tag">${b.market}</span></td>
                    <td class="right">
                        <span class="odds-badge ${b.odds_american > 0 ? 'positive' : 'negative'}">${b.odds_american > 0 ? '+' : ''}${b.odds_american}</span>
                    </td>
                    <td class="right font-mono">$${b.recommended_stake.toFixed(0)}</td>
                    <td class="right text-dim">${b.bookmaker}</td>
                    <td class="center"><span class="confidence-badge ${b.status === 'won' ? 'high' : b.status === 'lost' ? '' : 'medium'}" style="${b.status === 'lost' ? 'background:var(--accent-red-dim);color:var(--accent-red)' : ''}">${b.status.toUpperCase()}</span></td>
                    <td class="right font-bold ${b.profit_loss >= 0 ? 'text-green' : 'text-red'}">${b.profit_loss !== 0 ? `$${b.profit_loss >= 0 ? '+' : ''}${b.profit_loss.toFixed(2)}` : '-'}</td>
                    <td class="center">${actions}</td>
                </tr>`;
            }).join('');
        } catch (err) {
            tableBody.innerHTML = `<tr><td colspan="9" class="empty-state text-red">Error loading bets</td></tr>`;
        }
    },

    // ── Player Profile ────────────────────────────────────────────────
    async loadPlayer(name) {
        const container = document.getElementById('player-content');
        if (!container) return;

        container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div> Loading player data...</div>';

        try {
            const resp = await fetch(`/api/players/${encodeURIComponent(name)}`);
            if (!resp.ok) {
                container.innerHTML = `<div class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
                    <p>Player "${name}" not found. Run <code class="step-code" style="display:inline">sba data backfill --player "${name}"</code> to import their stats.</p>
                </div>`;
                return;
            }

            const p = await resp.json();
            const initials = p.name.split(' ').map(n => n[0]).join('');

            container.innerHTML = `
                <div class="player-header">
                    <div class="player-avatar">${initials}</div>
                    <div class="player-info">
                        <h2>${p.name}</h2>
                        <div class="player-meta">${p.team} · ${p.position} · ${p.games} games</div>
                    </div>
                </div>

                <div class="stats-grid">
                    ${['points', 'rebounds', 'assists', 'minutes'].map(stat => {
                        const l5 = p.last_5[stat]?.toFixed(1) || '0.0';
                        const l20 = p.last_20[stat]?.toFixed(1) || '0.0';
                        const trend = p.trends[stat + '_trend'];
                        const trendStr = trend !== undefined ? (trend >= 0 ? '+' : '') + trend.toFixed(1) : '';
                        const trendColor = trend >= 0 ? 'green' : 'red';
                        const trendDir = trend >= 0 ? 'up' : 'down';
                        const trendArrow = trend >= 0 ? '&#9650;' : '&#9660;';
                        return `
                        <div class="stat-card ${trendColor}">
                            <div class="stat-label">${stat}</div>
                            <div class="stat-value">${l5}</div>
                            <div class="stat-sub">
                                L5 avg · Season: ${l20}
                                ${trendStr ? `<span class="stat-trend ${trendDir}">${trendArrow} ${trendStr}</span>` : ''}
                            </div>
                        </div>`;
                    }).join('')}
                </div>

                <div class="card">
                    <div class="card-header"><h3>Recent Games</h3></div>
                    <div class="card-body">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>Date</th><th>Opp</th><th class="right">Min</th>
                                    <th class="right">Pts</th><th class="right">Reb</th>
                                    <th class="right">Ast</th><th class="right">3PM</th>
                                    <th class="right">Stl</th><th class="right">Blk</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${p.recent_games.map((g, i) => `
                                <tr class="new-row" style="animation-delay:${i * 0.03}s">
                                    <td class="text-dim">${g.date}</td>
                                    <td>${g.opponent}</td>
                                    <td class="right font-mono">${Math.round(g.minutes)}</td>
                                    <td class="right font-mono font-bold">${g.points}</td>
                                    <td class="right font-mono">${g.rebounds}</td>
                                    <td class="right font-mono">${g.assists}</td>
                                    <td class="right font-mono">${g.threes}</td>
                                    <td class="right font-mono">${g.steals}</td>
                                    <td class="right font-mono">${g.blocks}</td>
                                </tr>`).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        } catch (err) {
            container.innerHTML = `<div class="empty-state text-red">Error loading player: ${err.message}</div>`;
        }
    },

    // ── Dashboard ─────────────────────────────────────────────────────
    async loadDashboard() {
        // Populate live ticker
        this.loadTicker();
        // Load onboarding progress
        this.loadOnboarding();

        // Load status with count-up animations
        try {
            const resp = await fetch('/api/status');
            const status = await resp.json();
            const statsEl = document.getElementById('dashboard-stats');
            if (statsEl) {
                statsEl.innerHTML = `
                    <div class="stat-card green">
                        <div class="stat-label">Events Tracked</div>
                        <div class="stat-value count-up" data-target="${status.events}">${status.events}</div>
                        <div class="stat-sub">across all sports</div>
                    </div>
                    <div class="stat-card blue">
                        <div class="stat-label">Odds Snapshots</div>
                        <div class="stat-value count-up" data-target="${status.odds_snapshots}">${status.odds_snapshots.toLocaleString()}</div>
                        <div class="stat-sub">historical data points</div>
                    </div>
                    <div class="stat-card yellow">
                        <div class="stat-label">Players</div>
                        <div class="stat-value count-up" data-target="${status.players}">${status.players}</div>
                        <div class="stat-sub">with game logs</div>
                    </div>
                    <div class="stat-card purple">
                        <div class="stat-label">Game Logs</div>
                        <div class="stat-value count-up" data-target="${status.game_logs}">${status.game_logs.toLocaleString()}</div>
                        <div class="stat-sub">for ML training</div>
                    </div>
                `;

                // Animate count-ups
                statsEl.querySelectorAll('.count-up').forEach(el => {
                    const target = parseInt(el.dataset.target);
                    if (target > 0) this.animateCountUp(el, target);
                });
            }
        } catch {}

        // Load recent bets summary with sparkline
        try {
            const [betsResp, analyticsResp] = await Promise.all([
                fetch('/api/bets'),
                fetch('/api/analytics'),
            ]);
            const bets = await betsResp.json();
            const analytics = await analyticsResp.json();
            const betEl = document.getElementById('dashboard-bets');
            if (betEl) {
                if (bets.total_bets === 0 && bets.pending === 0) {
                    betEl.innerHTML = `<div class="empty-state" style="padding:40px 20px">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="36" height="36"><rect x="2" y="3" width="20" height="18" rx="2"/><line x1="2" y1="9" x2="22" y2="9"/></svg>
                        <p>No bets tracked yet</p>
                    </div>`;
                } else {
                    const plColor = bets.total_profit >= 0 ? 'text-green' : 'text-red';
                    const plGlow = bets.total_profit >= 0 ? 'glow-green' : 'glow-red';
                    const roiColor = bets.roi >= 0 ? 'text-green' : 'text-red';
                    // Generate sparkline from daily P/L
                    const pnlData = analytics.daily_pnl?.map(d => d.pnl) || [];
                    const sparkline = this.createSparkline(pnlData);
                    const winGauge = this.createGauge(bets.win_rate * 100, 100, `${(bets.win_rate * 100).toFixed(0)}%`);

                    betEl.innerHTML = `
                        <div style="padding:24px;display:grid;grid-template-columns:repeat(4,1fr);gap:16px;text-align:center;align-items:center">
                            <div>
                                <div class="stat-value ${plColor} ${plGlow}" style="font-size:22px">$${bets.total_profit >= 0 ? '+' : ''}${bets.total_profit.toFixed(2)}</div>
                                <div class="stat-label" style="margin-top:6px">Total P/L</div>
                                ${sparkline}
                            </div>
                            <div>
                                ${winGauge}
                                <div class="stat-label" style="margin-top:6px">Win Rate</div>
                            </div>
                            <div>
                                <div class="stat-value" style="font-size:22px">${bets.total_bets + bets.pending}</div>
                                <div class="stat-label" style="margin-top:6px">Total Bets</div>
                            </div>
                            <div>
                                <div class="stat-value ${roiColor}" style="font-size:22px">${bets.roi >= 0 ? '+' : ''}${bets.roi.toFixed(1)}%</div>
                                <div class="stat-label" style="margin-top:6px">ROI</div>
                            </div>
                        </div>
                    `;
                }
            }
        } catch {}
    },

    // ── Bet Slip — Premium ────────────────────────────────────────────
    addToSlip(eventId, selection, odds, market, bookmaker, eventName, stake) {
        if (this.betSlip.find(b => b.eventId === eventId && b.selection === selection)) {
            this.toast('Already in bet slip', 'info');
            return;
        }

        this.betSlip.push({ eventId, selection, odds, market, bookmaker, eventName, stake: stake || 0 });
        this.renderSlip();
        this.toast(`${selection} added to slip`, 'success');

        document.getElementById('bet-slip').classList.add('open');

        // Update header count
        const headerCount = document.getElementById('slip-count-header');
        if (headerCount) headerCount.textContent = this.betSlip.length;
    },

    removeFromSlip(index) {
        this.betSlip.splice(index, 1);
        this.renderSlip();
        const headerCount = document.getElementById('slip-count-header');
        if (headerCount) headerCount.textContent = this.betSlip.length;
    },

    clearSlip() {
        this.betSlip = [];
        this.renderSlip();
        document.getElementById('bet-slip').classList.remove('open');
        const headerCount = document.getElementById('slip-count-header');
        if (headerCount) headerCount.textContent = '0';
    },

    calcPayout(odds, stake) {
        if (odds > 0) return stake * (odds / 100);
        return stake * (100 / Math.abs(odds));
    },

    renderSlip() {
        const body = document.getElementById('bet-slip-body');
        const footer = document.getElementById('bet-slip-footer');
        const count = document.getElementById('bet-count');

        count.textContent = this.betSlip.length;

        if (this.betSlip.length === 0) {
            body.innerHTML = `
                <div class="empty-slip">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48"><rect x="2" y="3" width="20" height="18" rx="2"/><line x1="2" y1="9" x2="22" y2="9"/></svg>
                    <p>Add selections to your bet slip</p>
                    <p class="text-dim" style="font-size:11px">Click odds on any edge to add</p>
                </div>`;
            footer.style.display = 'none';
            return;
        }

        footer.style.display = 'flex';
        let totalStake = 0;
        let totalPayout = 0;

        body.innerHTML = this.betSlip.map((b, i) => {
            const payout = this.calcPayout(b.odds, b.stake);
            totalStake += b.stake;
            totalPayout += payout + b.stake;
            return `
            <div class="slip-item">
                <div class="slip-item-header">
                    <div>
                        <div class="slip-selection">${b.selection}</div>
                        <div class="slip-event">${b.eventName} · ${b.market}</div>
                    </div>
                    <button class="slip-remove" onclick="SBA.removeFromSlip(${i})">&times;</button>
                </div>
                <div class="slip-odds">
                    <span class="slip-odds-value">${b.odds > 0 ? '+' : ''}${b.odds}</span>
                    <div class="slip-stake">
                        <input type="number" value="${b.stake.toFixed(0)}" placeholder="$0"
                               onchange="SBA.betSlip[${i}].stake = parseFloat(this.value) || 0; SBA.renderSlip()">
                    </div>
                </div>
                <div class="slip-payout">
                    <span>Potential Payout</span>
                    <span class="slip-payout-value">$${(payout + b.stake).toFixed(2)}</span>
                </div>
            </div>`;
        }).join('');

        // Parlay calculation
        const parlay = this.calcParlayOdds();
        const parlayHtml = parlay ? `
            <div class="slip-parlay">
                <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-top:1px solid var(--border-light);margin-top:4px">
                    <span style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-tertiary)">Parlay Odds</span>
                    <span class="font-mono font-bold" style="color:var(--accent-purple)">${parlay.american > 0 ? '+' : ''}${parlay.american}</span>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0">
                    <span style="font-size:11px;color:var(--text-tertiary)">Parlay Multiplier</span>
                    <span class="font-mono" style="font-size:12px">${parlay.decimal.toFixed(2)}x</span>
                </div>
            </div>` : '';

        // Update footer with totals
        footer.innerHTML = `
            <div class="slip-total">
                <span>Total Stake</span>
                <span>$${totalStake.toFixed(2)}</span>
            </div>
            <div class="slip-total" style="border-bottom:none;padding-bottom:0">
                <span>Total Payout</span>
                <span class="slip-total-value">$${totalPayout.toFixed(2)}</span>
            </div>
            ${parlayHtml}
            <button class="btn btn-primary btn-block" onclick="SBA.placeBets()" style="margin-top:8px">Track All Bets</button>
            <button class="btn btn-outline btn-block" onclick="SBA.clearSlip()">Clear Slip</button>
        `;
    },

    async placeBets() {
        const btn = document.querySelector('.bet-slip-footer .btn-primary');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Tracking...';
        }

        for (const bet of this.betSlip) {
            try {
                await fetch('/api/bets/track', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        event_id: bet.eventId,
                        market: bet.market,
                        selection: bet.selection,
                        odds_american: bet.odds,
                        stake: bet.stake,
                        bookmaker: bet.bookmaker,
                    }),
                });
            } catch (err) {
                this.toast(`Failed to track ${bet.selection}`, 'error');
            }
        }
        this.toast(`${this.betSlip.length} bet(s) tracked!`, 'success');
        this.clearSlip();
    },

    // ── Toasts — Premium ──────────────────────────────────────────────
    toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icons = { success: '&#10003;', error: '&#10007;', info: '&#8505;' };
        toast.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span> ${message}`;

        container.appendChild(toast);
        setTimeout(() => {
            toast.classList.add('removing');
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    },

    // ── Toggle Bet Slip ───────────────────────────────────────────────
    toggleSlip() {
        document.getElementById('bet-slip').classList.toggle('open');
    },

    // ── Analytics Page ────────────────────────────────────────────────
    async loadAnalytics() {
        try {
            const [analyticsResp, betsResp] = await Promise.all([
                fetch('/api/analytics'),
                fetch('/api/bets'),
            ]);
            const analytics = await analyticsResp.json();
            const bets = await betsResp.json();

            // Summary stats with gauges
            const summary = document.getElementById('analytics-summary');
            if (summary) {
                const streakColor = analytics.streak.type === 'won' ? 'text-green' : analytics.streak.type === 'lost' ? 'text-red' : '';
                const plGlow = bets.total_profit >= 0 ? 'glow-green' : 'glow-red';
                const pnlSparkData = analytics.daily_pnl?.map(d => d.pnl) || [];
                const sparkline = this.createSparkline(pnlSparkData);
                const winGauge = this.createGauge(bets.win_rate * 100, 100, `${(bets.win_rate * 100).toFixed(1)}%`);
                summary.innerHTML = `
                    <div class="stat-card green">
                        <div class="stat-label">Total P/L</div>
                        <div class="stat-value ${bets.total_profit >= 0 ? 'text-green' : 'text-red'} ${plGlow}">$${bets.total_profit >= 0 ? '+' : ''}${bets.total_profit.toFixed(2)}</div>
                        <div class="stat-sub">${bets.total_bets} settled bets</div>
                        ${sparkline}
                    </div>
                    <div class="stat-card blue">
                        <div class="stat-label">Win Rate</div>
                        ${winGauge}
                        <div class="stat-sub" style="margin-top:8px">${bets.wins}W - ${bets.losses}L - ${bets.pushes}P</div>
                    </div>
                    <div class="stat-card yellow">
                        <div class="stat-label">ROI</div>
                        <div class="stat-value ${bets.roi >= 0 ? 'text-green' : 'text-red'}">${bets.roi >= 0 ? '+' : ''}${bets.roi.toFixed(1)}%</div>
                        <div class="stat-sub">$${bets.total_staked.toFixed(0)} staked</div>
                    </div>
                    <div class="stat-card purple">
                        <div class="stat-label">Current Streak</div>
                        <div class="stat-value ${streakColor}">${analytics.streak.count > 0 ? `${analytics.streak.count}${analytics.streak.type.charAt(0).toUpperCase()}` : '—'}</div>
                        <div class="stat-sub">${analytics.streak.type || 'No bets'}</div>
                    </div>
                `;
            }

            // P/L chart (CSS bar chart)
            const chartEl = document.getElementById('pnl-chart-container');
            if (chartEl) {
                if (analytics.daily_pnl.length === 0) {
                    chartEl.innerHTML = '<div class="empty-state" style="padding:40px"><p>No settled bets yet for P/L chart</p></div>';
                } else {
                    let cumulative = 0;
                    const points = analytics.daily_pnl.map(d => {
                        cumulative += d.pnl;
                        return { date: d.date, pnl: d.pnl, cumulative };
                    });
                    const maxAbs = Math.max(Math.abs(Math.min(...points.map(p => p.cumulative))), Math.abs(Math.max(...points.map(p => p.cumulative))), 1);

                    chartEl.innerHTML = `
                        <div style="display:flex;flex-direction:column;gap:4px">
                            ${points.map(p => {
                                const width = Math.abs(p.cumulative / maxAbs * 100);
                                const color = p.cumulative >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
                                return `
                                <div style="display:flex;align-items:center;gap:12px">
                                    <span class="text-dim" style="font-size:11px;min-width:80px">${p.date.slice(5)}</span>
                                    <div style="flex:1;height:24px;position:relative;display:flex;align-items:center">
                                        <div style="height:16px;width:${Math.max(width, 2)}%;background:${color};border-radius:4px;opacity:0.7;transition:width 0.5s"></div>
                                    </div>
                                    <span class="font-mono font-bold ${p.cumulative >= 0 ? 'text-green' : 'text-red'}" style="font-size:12px;min-width:70px;text-align:right">$${p.cumulative >= 0 ? '+' : ''}${p.cumulative.toFixed(2)}</span>
                                </div>`;
                            }).join('')}
                        </div>
                    `;
                }
            }

            // Market breakdown
            const marketEl = document.getElementById('market-breakdown');
            if (marketEl) {
                const markets = Object.entries(analytics.by_market);
                if (markets.length === 0) {
                    marketEl.innerHTML = '<div class="empty-state" style="padding:40px"><p>No market data yet</p></div>';
                } else {
                    const donutColors = ['var(--accent-green)', 'var(--accent-blue)', 'var(--accent-yellow)', 'var(--accent-purple)', 'var(--accent-cyan)', 'var(--accent-red)'];
                    const totalBets = markets.reduce((sum, [, d]) => sum + d.bets, 0);
                    const donutSegments = markets.map(([, d], i) => ({ value: d.bets, color: donutColors[i % donutColors.length] }));
                    const donut = this.createDonutChart(donutSegments, totalBets.toString(), 'Total Bets');
                    const legend = markets.map(([name, d], i) => `
                        <div style="display:flex;align-items:center;gap:8px;padding:6px 0">
                            <span style="width:10px;height:10px;border-radius:3px;background:${donutColors[i % donutColors.length]};flex-shrink:0"></span>
                            <span style="font-size:13px;flex:1">${name}</span>
                            <span class="font-mono font-bold" style="font-size:12px">${d.bets}</span>
                        </div>
                    `).join('');
                    marketEl.innerHTML = `
                        <div style="padding:24px;display:grid;grid-template-columns:auto 1fr;gap:24px;align-items:center">
                            ${donut}
                            <div>${legend}</div>
                        </div>
                        <table class="data-table">
                            <thead><tr><th>Market</th><th class="right">Bets</th><th class="right">Win Rate</th><th class="right">P/L</th><th class="right">ROI</th></tr></thead>
                            <tbody>
                                ${markets.map(([name, d]) => `
                                <tr class="new-row">
                                    <td><span class="market-tag">${name}</span></td>
                                    <td class="right font-mono">${d.bets}</td>
                                    <td class="right font-mono">${d.win_rate}%</td>
                                    <td class="right font-mono font-bold ${d.profit >= 0 ? 'text-green' : 'text-red'}">$${d.profit >= 0 ? '+' : ''}${d.profit.toFixed(2)}</td>
                                    <td class="right"><span class="ev-badge ${d.roi >= 0 ? 'high' : 'negative'}">${d.roi >= 0 ? '+' : ''}${d.roi}%</span></td>
                                </tr>`).join('')}
                            </tbody>
                        </table>
                    `;
                }
            }

            // Bookmaker breakdown
            const bookEl = document.getElementById('bookmaker-breakdown');
            if (bookEl) {
                const books = Object.entries(analytics.by_bookmaker);
                if (books.length === 0) {
                    bookEl.innerHTML = '<div class="empty-state" style="padding:40px"><p>No bookmaker data yet</p></div>';
                } else {
                    bookEl.innerHTML = `
                        <table class="data-table">
                            <thead><tr><th>Bookmaker</th><th class="right">Bets</th><th class="right">Win Rate</th><th class="right">P/L</th><th class="right">ROI</th></tr></thead>
                            <tbody>
                                ${books.map(([name, d]) => `
                                <tr class="new-row">
                                    <td class="font-bold">${name}</td>
                                    <td class="right font-mono">${d.bets}</td>
                                    <td class="right font-mono">${d.win_rate}%</td>
                                    <td class="right font-mono font-bold ${d.profit >= 0 ? 'text-green' : 'text-red'}">$${d.profit >= 0 ? '+' : ''}${d.profit.toFixed(2)}</td>
                                    <td class="right"><span class="ev-badge ${d.roi >= 0 ? 'high' : 'negative'}">${d.roi >= 0 ? '+' : ''}${d.roi}%</span></td>
                                </tr>`).join('')}
                            </tbody>
                        </table>
                    `;
                }
            }

            // P/L Heatmap Calendar
            const heatmapEl = document.getElementById('pnl-heatmap');
            if (heatmapEl) {
                if (analytics.daily_pnl && analytics.daily_pnl.length > 0) {
                    heatmapEl.innerHTML = this.createHeatmapCalendar(analytics.daily_pnl);
                } else {
                    heatmapEl.innerHTML = '<div class="empty-state" style="padding:40px"><p>No data for heatmap yet</p></div>';
                }
            }

            // Bankroll health gauge
            const healthEl = document.getElementById('bankroll-health');
            if (healthEl) {
                try {
                    const settingsResp2 = await fetch('/api/settings');
                    const settings2 = await settingsResp2.json();
                    const bankroll = settings2.bankroll || 1000;
                    const roi = bets.roi || 0;
                    const winRate = bets.win_rate || 0;
                    let score = 50;
                    score += Math.min(roi, 20);
                    score += (winRate - 0.5) * 40;
                    if (bets.total_profit > 0) score += 10;
                    score = Math.max(0, Math.min(100, Math.round(score)));
                    healthEl.innerHTML = `
                        <div style="text-align:center">
                            ${this.createHealthGauge(score)}
                            <div style="margin-top:16px;display:grid;grid-template-columns:1fr 1fr;gap:12px">
                                <div class="step-card" style="text-align:center;padding:12px">
                                    <div class="stat-label">Bankroll</div>
                                    <div class="font-mono font-bold text-green" style="font-size:18px">$${bankroll.toLocaleString()}</div>
                                </div>
                                <div class="step-card" style="text-align:center;padding:12px">
                                    <div class="stat-label">Net P/L</div>
                                    <div class="font-mono font-bold ${bets.total_profit >= 0 ? 'text-green' : 'text-red'}" style="font-size:18px">$${bets.total_profit >= 0 ? '+' : ''}${bets.total_profit.toFixed(2)}</div>
                                </div>
                            </div>
                        </div>
                    `;
                } catch {
                    healthEl.innerHTML = '<div class="empty-state"><p>Could not load health data</p></div>';
                }
            }

            // Notable bets
            const notableEl = document.getElementById('notable-bets');
            if (notableEl) {
                if (!analytics.best_bet && !analytics.worst_bet) {
                    notableEl.innerHTML = '<div class="empty-state" style="padding:40px"><p>No settled bets yet</p></div>';
                } else {
                    notableEl.innerHTML = `
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
                            ${analytics.best_bet ? `
                            <div class="step-card" style="border-left:3px solid var(--accent-green)">
                                <div class="stat-label">Best Bet</div>
                                <div class="font-bold" style="margin:8px 0">${analytics.best_bet.selection}</div>
                                <div class="text-dim" style="font-size:12px">${analytics.best_bet.market} · ${analytics.best_bet.bookmaker}</div>
                                <div class="stat-value text-green" style="font-size:20px;margin-top:8px">$+${analytics.best_bet.profit_loss.toFixed(2)}</div>
                            </div>` : ''}
                            ${analytics.worst_bet ? `
                            <div class="step-card" style="border-left:3px solid var(--accent-red)">
                                <div class="stat-label">Worst Bet</div>
                                <div class="font-bold" style="margin:8px 0">${analytics.worst_bet.selection}</div>
                                <div class="text-dim" style="font-size:12px">${analytics.worst_bet.market} · ${analytics.worst_bet.bookmaker}</div>
                                <div class="stat-value text-red" style="font-size:20px;margin-top:8px">$${analytics.worst_bet.profit_loss.toFixed(2)}</div>
                            </div>` : ''}
                        </div>
                    `;
                }
            }
        } catch (err) {
            const summary = document.getElementById('analytics-summary');
            if (summary) summary.innerHTML = `<div class="stat-card red"><div class="stat-value text-red">Error loading analytics</div></div>`;
        }
    },

    // ── Settings Page ─────────────────────────────────────────────────
    async loadSettings() {
        try {
            const [settingsResp, healthResp, statusResp] = await Promise.all([
                fetch('/api/settings'),
                fetch('/api/health'),
                fetch('/api/status'),
            ]);
            const settings = await settingsResp.json();
            const health = await healthResp.json();
            const status = await statusResp.json();

            // Bankroll settings (editable)
            const bankrollEl = document.getElementById('bankroll-settings');
            if (bankrollEl) {
                bankrollEl.innerHTML = `
                    <div style="display:grid;gap:16px">
                        <div class="settings-row">
                            <div><div class="font-bold">Bankroll</div><div class="text-dim" style="font-size:12px">Total bankroll for Kelly criterion sizing</div></div>
                            <div style="display:flex;align-items:center;gap:8px">
                                <span class="font-mono font-bold text-green" style="font-size:18px">$${settings.bankroll.toLocaleString()}</span>
                                <button class="btn btn-outline btn-sm" onclick="const v=prompt('New bankroll:','${settings.bankroll}');if(v)SBA.updateSetting('bankroll',parseFloat(v))">Edit</button>
                            </div>
                        </div>
                        <div class="settings-row">
                            <div><div class="font-bold">Kelly Fraction</div><div class="text-dim" style="font-size:12px">Fractional Kelly multiplier (1.0 = full Kelly)</div></div>
                            <div style="display:flex;align-items:center;gap:8px">
                                <span class="font-mono font-bold" style="font-size:18px">${settings.kelly_fraction}</span>
                                <button class="btn btn-outline btn-sm" onclick="const v=prompt('New Kelly fraction:','${settings.kelly_fraction}');if(v)SBA.updateSetting('kelly_fraction',parseFloat(v))">Edit</button>
                            </div>
                        </div>
                        <div class="settings-row">
                            <div><div class="font-bold">EV Threshold</div><div class="text-dim" style="font-size:12px">Minimum expected value to flag as +EV</div></div>
                            <div style="display:flex;align-items:center;gap:8px">
                                <span class="font-mono font-bold" style="font-size:18px">${(settings.ev_threshold * 100).toFixed(1)}%</span>
                                <button class="btn btn-outline btn-sm" onclick="const v=prompt('New EV threshold (decimal, e.g. 0.03):','${settings.ev_threshold}');if(v)SBA.updateSetting('ev_threshold',parseFloat(v))">Edit</button>
                            </div>
                        </div>
                        <div class="settings-row" style="border-bottom:none">
                            <div><div class="font-bold">Default Sport</div><div class="text-dim" style="font-size:12px">Primary sport for scanning</div></div>
                            <div style="display:flex;align-items:center;gap:8px">
                                <span class="market-tag">${settings.default_sport}</span>
                                <button class="btn btn-outline btn-sm" onclick="const v=prompt('Default sport key:','${settings.default_sport}');if(v)SBA.updateSetting('default_sport',v)">Edit</button>
                            </div>
                        </div>
                    </div>
                    <p class="text-dim" style="font-size:11px;margin-top:16px">Settings are configured via environment variables or .env file</p>
                `;
            }

            // System info
            const sysEl = document.getElementById('system-info');
            if (sysEl) {
                sysEl.innerHTML = `
                    <div style="display:grid;gap:12px">
                        <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--border-light)">
                            <span class="text-secondary">Version</span>
                            <span class="font-mono">${health.version}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--border-light)">
                            <span class="text-secondary">Uptime</span>
                            <span class="font-mono">${health.uptime}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--border-light)">
                            <span class="text-secondary">Database</span>
                            <span class="confidence-badge ${health.database === 'healthy' ? 'high' : ''}" style="${health.database !== 'healthy' ? 'background:var(--accent-red-dim);color:var(--accent-red)' : ''}">${health.database.toUpperCase()}</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0">
                            <span class="text-secondary">API Docs</span>
                            <a href="/api/docs" target="_blank" class="btn btn-outline btn-sm">Open Swagger UI</a>
                        </div>
                    </div>
                `;
            }

            // DB status
            const dbEl = document.getElementById('db-status');
            if (dbEl) {
                dbEl.innerHTML = `
                    <div class="stats-grid" style="margin-bottom:0">
                        <div class="step-card" style="text-align:center">
                            <div class="stat-value" style="font-size:28px;color:var(--accent-green)">${status.events.toLocaleString()}</div>
                            <div class="stat-label" style="margin-top:6px">Events</div>
                        </div>
                        <div class="step-card" style="text-align:center">
                            <div class="stat-value" style="font-size:28px;color:var(--accent-blue)">${status.odds_snapshots.toLocaleString()}</div>
                            <div class="stat-label" style="margin-top:6px">Odds Snapshots</div>
                        </div>
                        <div class="step-card" style="text-align:center">
                            <div class="stat-value" style="font-size:28px;color:var(--accent-yellow)">${status.players.toLocaleString()}</div>
                            <div class="stat-label" style="margin-top:6px">Players</div>
                        </div>
                        <div class="step-card" style="text-align:center">
                            <div class="stat-value" style="font-size:28px;color:var(--accent-purple)">${status.game_logs.toLocaleString()}</div>
                            <div class="stat-label" style="margin-top:6px">Game Logs</div>
                        </div>
                    </div>
                `;
            }
        } catch (err) {
            const bankrollEl = document.getElementById('bankroll-settings');
            if (bankrollEl) bankrollEl.innerHTML = `<div class="empty-state text-red">Error loading settings</div>`;
        }
    },

    // ── Delete Bet ────────────────────────────────────────────────────
    async deleteBet(betId) {
        try {
            await fetch(`/api/bets/${betId}`, { method: 'DELETE' });
            this.toast('Bet deleted', 'success');
            this.loadBets();
        } catch {
            this.toast('Failed to delete bet', 'error');
        }
    },

    // ── Settle Bet ────────────────────────────────────────────────────
    async settleBet(betId, status, profitLoss) {
        try {
            await fetch(`/api/bets/${betId}/settle`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status, profit_loss: profitLoss }),
            });
            this.toast(`Bet marked as ${status}`, 'success');
            this.loadBets();
        } catch {
            this.toast('Failed to settle bet', 'error');
        }
    },

    // ── Line Movement ────────────────────────────────────────────────
    async loadLineMovementEvents() {
        const select = document.getElementById('lm-event-select');
        if (!select) return;

        try {
            const resp = await fetch('/api/events');
            const events = await resp.json();
            events.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = `${e.away_team} @ ${e.home_team}`;
                select.appendChild(opt);
            });
        } catch {}
    },

    async loadLineMovement(eventId) {
        const chartEl = document.getElementById('lm-chart');
        const tableBody = document.getElementById('lm-table-body');
        if (!eventId || !chartEl) return;

        const market = document.getElementById('lm-market-select')?.value || 'h2h';

        chartEl.innerHTML = '<div class="loading-spinner"><div class="spinner"></div> Loading line data...</div>';

        try {
            const resp = await fetch(`/api/line-movement/${eventId}?market=${market}`);
            const data = await resp.json();

            if (data.length === 0) {
                chartEl.innerHTML = '<div class="empty-state" style="padding:40px"><p>No odds history found for this event and market</p></div>';
                tableBody.innerHTML = '<tr><td colspan="6" class="empty-state"><p>No data</p></td></tr>';
                return;
            }

            // Group by bookmaker+outcome for visual chart
            const groups = {};
            data.forEach(s => {
                const key = `${s.bookmaker} · ${s.outcome}`;
                if (!groups[key]) groups[key] = [];
                groups[key].push(s);
            });

            const colors = ['var(--accent-green)', 'var(--accent-blue)', 'var(--accent-yellow)', 'var(--accent-purple)', 'var(--accent-cyan)', 'var(--accent-red)'];
            let colorIdx = 0;

            // SVG line chart visualization
            const svgChart = this.createLineMovementChart(groups);

            chartEl.innerHTML = `
                ${svgChart}
                <div style="display:flex;flex-direction:column;gap:12px;margin-top:16px">
                    ${Object.entries(groups).map(([key, snaps]) => {
                        const color = colors[colorIdx++ % colors.length];
                        const latest = snaps[snaps.length - 1];
                        const first = snaps[0];
                        const diff = latest.odds_american - first.odds_american;
                        const diffStr = diff > 0 ? `+${diff}` : `${diff}`;
                        const diffColor = diff > 0 ? 'text-green' : diff < 0 ? 'text-red' : 'text-dim';
                        return `
                        <div style="display:flex;align-items:center;gap:16px;padding:12px;background:rgba(255,255,255,0.02);border-radius:var(--radius-sm);border:1px solid var(--border-light)">
                            <div style="width:8px;height:8px;border-radius:50%;background:${color};flex-shrink:0"></div>
                            <div style="flex:1;min-width:0">
                                <div class="font-bold" style="font-size:13px">${key}</div>
                                <div class="text-dim" style="font-size:11px">${snaps.length} snapshot${snaps.length > 1 ? 's' : ''}</div>
                            </div>
                            <div class="font-mono" style="font-size:15px;font-weight:700">
                                ${latest.odds_american > 0 ? '+' : ''}${latest.odds_american}
                            </div>
                            ${snaps.length > 1 ? `<div class="font-mono ${diffColor}" style="font-size:12px">(${diffStr})</div>` : ''}
                        </div>`;
                    }).join('')}
                </div>
            `;

            // Table
            tableBody.innerHTML = data.map((s, i) => `
                <tr class="new-row" style="animation-delay:${i * 0.02}s">
                    <td class="text-dim" style="font-size:11px">${s.time}</td>
                    <td>${s.bookmaker}</td>
                    <td class="font-bold">${s.outcome}</td>
                    <td class="right font-mono">${s.line !== null ? s.line : '-'}</td>
                    <td class="right">
                        <span class="odds-badge ${s.odds_american > 0 ? 'positive' : 'negative'}">
                            ${s.odds_american > 0 ? '+' : ''}${s.odds_american}
                        </span>
                    </td>
                    <td class="right font-mono">${s.odds_decimal.toFixed(3)}</td>
                </tr>
            `).join('');
        } catch (err) {
            chartEl.innerHTML = `<div class="empty-state text-red">Error: ${err.message}</div>`;
        }
    },

    // ── Theme Toggle ─────────────────────────────────────────────────
    toggleTheme() {
        const html = document.documentElement;
        const current = html.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', next);
        localStorage.setItem('sba-theme', next);
        this.toast(`Switched to ${next} mode`, 'info');
    },

    loadTheme() {
        const saved = localStorage.getItem('sba-theme');
        if (saved) document.documentElement.setAttribute('data-theme', saved);
    },

    // ── Odds Comparison ──────────────────────────────────────────────
    async loadOddsComparisonEvents() {
        const select = document.getElementById('oc-event-select');
        if (!select) return;
        try {
            const resp = await fetch('/api/events');
            const events = await resp.json();
            events.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = `${e.away_team} @ ${e.home_team}`;
                select.appendChild(opt);
            });
        } catch {}
    },

    async loadOddsComparison(eventId) {
        const matrixEl = document.getElementById('oc-matrix');
        const bestEl = document.getElementById('oc-best-odds');
        const timeEl = document.getElementById('oc-snapshot-time');
        if (!eventId || !matrixEl) return;

        const market = document.getElementById('oc-market-select')?.value || 'h2h';
        matrixEl.innerHTML = '<div class="loading-spinner"><div class="spinner"></div> Loading odds matrix...</div>';

        try {
            const resp = await fetch(`/api/odds-comparison/${eventId}?market=${market}`);
            const data = await resp.json();

            if (data.bookmakers.length === 0) {
                matrixEl.innerHTML = '<div class="empty-state" style="padding:40px"><p>No odds data for this event. Run <code class="step-code" style="display:inline">sba data sync</code> first.</p></div>';
                return;
            }

            if (timeEl) timeEl.textContent = `${data.total_snapshots} snapshots`;

            // Find best odds per outcome
            const bestOdds = {};
            Object.entries(data.outcomes).forEach(([outcome, entries]) => {
                bestOdds[outcome] = entries.reduce((best, e) =>
                    e.odds_american > (best?.odds_american ?? -9999) ? e : best, null);
            });

            // Best odds cards
            if (bestEl) {
                bestEl.innerHTML = Object.entries(bestOdds).map(([outcome, best]) => `
                    <div class="stat-card green">
                        <div class="stat-label">${outcome}</div>
                        <div class="stat-value">${best.odds_american > 0 ? '+' : ''}${best.odds_american}</div>
                        <div class="stat-sub">Best at <span class="font-bold">${best.bookmaker}</span></div>
                    </div>
                `).join('');
            }

            // Build matrix table
            const outcomes = Object.keys(data.outcomes);
            matrixEl.innerHTML = `
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Bookmaker</th>
                            ${outcomes.map(o => `<th class="right">${o}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${data.bookmakers.map((bk, i) => {
                            return `<tr class="new-row" style="animation-delay:${i * 0.03}s">
                                <td class="font-bold">${bk}</td>
                                ${outcomes.map(o => {
                                    const entry = data.outcomes[o]?.find(e => e.bookmaker === bk);
                                    if (!entry) return '<td class="right text-dim">—</td>';
                                    const isBest = bestOdds[o]?.bookmaker === bk;
                                    return `<td class="right">
                                        <span class="odds-badge ${entry.odds_american > 0 ? 'positive' : 'negative'} ${isBest ? 'selected' : ''}"
                                              onclick="SBA.addToSlip('${eventId}', '${o}', ${entry.odds_american}, '${market}', '${bk}', '${o}', 0)"
                                              data-tooltip="Click to add to slip">
                                            ${entry.odds_american > 0 ? '+' : ''}${entry.odds_american}
                                        </span>
                                    </td>`;
                                }).join('')}
                            </tr>`;
                        }).join('')}
                    </tbody>
                </table>
            `;
        } catch (err) {
            matrixEl.innerHTML = `<div class="empty-state text-red">Error: ${err.message}</div>`;
        }
    },

    // ── Notifications / Alerts ───────────────────────────────────────
    async checkAlerts() {
        try {
            const resp = await fetch('/api/alerts');
            const data = await resp.json();
            const countEl = document.getElementById('notification-count');
            const bellEl = document.getElementById('notification-bell');
            if (countEl && data.count > 0) {
                countEl.textContent = data.count;
                countEl.style.display = 'flex';
                bellEl?.classList.add('has-alerts');
            } else if (countEl) {
                countEl.style.display = 'none';
                bellEl?.classList.remove('has-alerts');
            }
        } catch {}
    },

    toggleNotifications() {
        this.toggleNotificationPanel();
    },

    // ── Parlay Calculator ────────────────────────────────────────────
    calcParlayOdds() {
        if (this.betSlip.length < 2) return null;
        let parlayDecimal = 1;
        this.betSlip.forEach(b => {
            const dec = b.odds > 0 ? (b.odds / 100) + 1 : (100 / Math.abs(b.odds)) + 1;
            parlayDecimal *= dec;
        });
        // Convert back to American
        let parlayAmerican;
        if (parlayDecimal >= 2) {
            parlayAmerican = Math.round((parlayDecimal - 1) * 100);
        } else {
            parlayAmerican = Math.round(-100 / (parlayDecimal - 1));
        }
        return { decimal: parlayDecimal, american: parlayAmerican };
    },

    // ── Editable Settings ────────────────────────────────────────────
    async updateSetting(field, value) {
        try {
            const body = {};
            body[field] = value;
            const resp = await fetch('/api/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (resp.ok) {
                this.toast(`${field} updated`, 'success');
                this.loadSettings();
            } else {
                this.toast('Failed to update setting', 'error');
            }
        } catch {
            this.toast('Failed to update setting', 'error');
        }
    },

    // ── Sparkline Generator ──────────────────────────────────────────
    createSparkline(data, color = 'var(--accent-green)') {
        if (!data || data.length === 0) return '';
        const max = Math.max(...data.map(Math.abs), 1);
        return `<div class="sparkline-container">${data.map((v, i) => {
            const h = Math.max(Math.abs(v) / max * 28, 2);
            const c = v >= 0 ? color : 'var(--accent-red)';
            return `<div class="sparkline-bar${v < 0 ? ' negative' : ''}" style="height:${h}px;background:${c};opacity:${0.4 + (i / data.length) * 0.6}"></div>`;
        }).join('')}</div>`;
    },

    // ── Circular Gauge ───────────────────────────────────────────────
    createGauge(value, max = 100, label = '', color = 'var(--accent-green)') {
        const pct = Math.min(Math.max(value / max, 0), 1);
        const circumference = 2 * Math.PI * 34;
        const offset = circumference * (1 - pct);
        const cls = pct > 0.6 ? '' : pct > 0.35 ? 'warn' : 'danger';
        return `<div class="gauge">
            <svg viewBox="0 0 80 80">
                <circle class="gauge-bg" cx="40" cy="40" r="34"/>
                <circle class="gauge-fill ${cls}" cx="40" cy="40" r="34"
                    stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"
                    style="stroke:${cls ? '' : color}"/>
            </svg>
            <div class="gauge-value">${label || Math.round(value) + '%'}</div>
        </div>`;
    },

    // ── Confidence Meter (5 bars) ────────────────────────────────────
    createConfidenceMeter(level) {
        const bars = 5;
        const filled = level === 'high' ? 5 : level === 'medium' ? 3 : 2;
        return `<div class="confidence-meter ${level}">${
            Array.from({length: bars}, (_, i) =>
                `<div class="confidence-meter-bar"></div>`
            ).join('')
        }</div>`;
    },

    // ── Command Palette ──────────────────────────────────────────────
    cmdPaletteOpen: false,
    cmdPaletteIdx: 0,

    commands: [
        { name: 'Go to Dashboard', icon: 'home', action: () => location.href = '/', keys: 'G D' },
        { name: 'Go to Edge Finder', icon: 'trending', action: () => location.href = '/edges', keys: 'G E' },
        { name: 'Go to Player Props', icon: 'users', action: () => location.href = '/props', keys: 'G P' },
        { name: 'Go to My Bets', icon: 'table', action: () => location.href = '/my-bets', keys: 'G B' },
        { name: 'Go to Analytics', icon: 'chart', action: () => location.href = '/analytics', keys: 'G A' },
        { name: 'Go to Line Movement', icon: 'activity', action: () => location.href = '/line-movement', keys: 'G L' },
        { name: 'Go to Odds Comparison', icon: 'grid', action: () => location.href = '/odds-comparison', keys: 'G O' },
        { name: 'Go to Settings', icon: 'settings', action: () => location.href = '/settings', keys: 'G S' },
        { name: 'Go to Live Feed', icon: 'activity', action: () => location.href = '/live-feed', keys: 'G F' },
        { name: 'Go to Calculator', icon: 'chart', action: () => location.href = '/calculator', keys: 'G C' },
        { name: 'Go to Simulator', icon: 'trending', action: () => location.href = '/simulator', keys: 'G M' },
        { name: 'Go to Watchlist', icon: 'home', action: () => location.href = '/watchlist', keys: 'G W' },
        { name: 'Export Bets (CSV)', icon: 'table', action: () => window.open('/api/bets/export', '_blank'), keys: '' },
        { name: 'Export Bets (JSON)', icon: 'table', action: () => window.open('/api/bets/export/json', '_blank'), keys: '' },
        { name: 'Toggle Dark/Light Theme', icon: 'theme', action: () => SBA.toggleTheme(), keys: 'T' },
        { name: 'Toggle Bet Slip', icon: 'slip', action: () => SBA.toggleSlip(), keys: 'B' },
        { name: 'Focus Search', icon: 'search', action: () => document.getElementById('player-search')?.focus(), keys: '/' },
        { name: 'Show Keyboard Shortcuts', icon: 'keyboard', action: () => SBA.showShortcutsModal(), keys: '?' },
    ],

    setupCommandPalette() {
        // Create command palette DOM
        const palette = document.createElement('div');
        palette.className = 'cmd-palette';
        palette.id = 'cmd-palette';
        palette.innerHTML = `
            <input class="cmd-palette-input" placeholder="Type a command..." id="cmd-input">
            <div class="cmd-palette-results" id="cmd-results"></div>
        `;
        document.body.appendChild(palette);

        const input = document.getElementById('cmd-input');
        const results = document.getElementById('cmd-results');

        input.addEventListener('input', () => {
            this.cmdPaletteIdx = 0;
            this.renderCommandResults(input.value);
        });

        input.addEventListener('keydown', (e) => {
            const items = results.querySelectorAll('.cmd-palette-item');
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                this.cmdPaletteIdx = Math.min(this.cmdPaletteIdx + 1, items.length - 1);
                this.highlightCmd(items);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                this.cmdPaletteIdx = Math.max(this.cmdPaletteIdx - 1, 0);
                this.highlightCmd(items);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                const active = items[this.cmdPaletteIdx];
                if (active) active.click();
            } else if (e.key === 'Escape') {
                this.closeCommandPalette();
            }
        });

        this.renderCommandResults('');
    },

    renderCommandResults(query) {
        const results = document.getElementById('cmd-results');
        if (!results) return;
        const q = query.toLowerCase();
        const filtered = this.commands.filter(c =>
            c.name.toLowerCase().includes(q)
        );
        results.innerHTML = filtered.map((c, i) => `
            <div class="cmd-palette-item${i === this.cmdPaletteIdx ? ' active' : ''}"
                 onclick="SBA.executeCommand(${this.commands.indexOf(c)})">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
                    ${this.getCmdIcon(c.icon)}
                </svg>
                <span>${c.name}</span>
                <span class="cmd-kbd">${c.keys}</span>
            </div>
        `).join('');
    },

    highlightCmd(items) {
        items.forEach((item, i) => {
            item.classList.toggle('active', i === this.cmdPaletteIdx);
        });
    },

    getCmdIcon(type) {
        const icons = {
            home: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
            trending: '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
            users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>',
            table: '<rect x="2" y="3" width="20" height="18" rx="2"/><line x1="2" y1="9" x2="22" y2="9"/>',
            chart: '<path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/>',
            activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
            grid: '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="3" x2="9" y2="21"/>',
            settings: '<circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>',
            theme: '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/>',
            slip: '<rect x="2" y="3" width="20" height="18" rx="2"/><line x1="2" y1="9" x2="22" y2="9"/>',
            search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
            keyboard: '<rect x="2" y="4" width="20" height="16" rx="2"/><line x1="6" y1="8" x2="6.01" y2="8"/>',
        };
        return icons[type] || icons.home;
    },

    executeCommand(index) {
        const cmd = this.commands[index];
        if (cmd) {
            this.closeCommandPalette();
            cmd.action();
        }
    },

    openCommandPalette() {
        const el = document.getElementById('cmd-palette');
        const bd = document.getElementById('cmd-backdrop');
        if (!el) return;
        el.classList.add('open');
        if (bd) { bd.style.opacity = '1'; bd.style.pointerEvents = 'all'; bd.onclick = () => this.closeCommandPalette(); }
        this.cmdPaletteOpen = true;
        this.cmdPaletteIdx = 0;
        const input = document.getElementById('cmd-input');
        if (input) { input.value = ''; input.focus(); }
        this.renderCommandResults('');
    },

    closeCommandPalette() {
        const el = document.getElementById('cmd-palette');
        const bd = document.getElementById('cmd-backdrop');
        if (el) el.classList.remove('open');
        if (bd) { bd.style.opacity = '0'; bd.style.pointerEvents = 'none'; }
        this.cmdPaletteOpen = false;
    },

    // ── Keyboard Shortcuts Modal ─────────────────────────────────────
    showShortcutsModal() {
        let modal = document.getElementById('shortcuts-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.className = 'shortcuts-modal';
            modal.id = 'shortcuts-modal';
            modal.onclick = (e) => { if (e.target === modal) modal.classList.remove('open'); };
            modal.innerHTML = `
                <div class="shortcuts-modal-body">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                        <h2 style="font-size:18px;font-weight:700">Keyboard Shortcuts</h2>
                        <button onclick="document.getElementById('shortcuts-modal').classList.remove('open')" style="background:none;border:none;color:var(--text-tertiary);font-size:20px;cursor:pointer">&times;</button>
                    </div>
                    <p class="text-dim" style="font-size:13px;margin-bottom:4px">Navigate like a pro</p>
                    <div class="shortcuts-grid">
                        <div class="shortcut-item"><span class="shortcut-label">Search</span><span class="kbd">/</span></div>
                        <div class="shortcut-item"><span class="shortcut-label">Bet Slip</span><span class="kbd">B</span></div>
                        <div class="shortcut-item"><span class="shortcut-label">Theme</span><span class="kbd">T</span></div>
                        <div class="shortcut-item"><span class="shortcut-label">Close</span><span class="kbd">Esc</span></div>
                        <div class="shortcut-item"><span class="shortcut-label">Command</span><span class="kbd">Ctrl+K</span></div>
                        <div class="shortcut-item"><span class="shortcut-label">Shortcuts</span><span class="kbd">?</span></div>
                        <div class="shortcut-item"><span class="shortcut-label">Dashboard</span><span class="kbd">G D</span></div>
                        <div class="shortcut-item"><span class="shortcut-label">Edges</span><span class="kbd">G E</span></div>
                        <div class="shortcut-item"><span class="shortcut-label">Props</span><span class="kbd">G P</span></div>
                        <div class="shortcut-item"><span class="shortcut-label">My Bets</span><span class="kbd">G B</span></div>
                        <div class="shortcut-item"><span class="shortcut-label">Analytics</span><span class="kbd">G A</span></div>
                        <div class="shortcut-item"><span class="shortcut-label">Settings</span><span class="kbd">G S</span></div>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }
        setTimeout(() => modal.classList.add('open'), 10);
    },

    // ── Onboarding Progress ────────────────────────────────────────────
    async loadOnboarding() {
        const el = document.getElementById('onboarding-progress');
        if (!el) return;
        try {
            const resp = await fetch('/api/status');
            const status = await resp.json();
            const steps = [
                { label: 'Sync Data', done: status.events > 0 },
                { label: 'Backfill Players', done: status.players > 0 },
                { label: 'Train Models', done: status.game_logs > 0 },
                { label: 'Find Edges', done: status.bets > 0 },
            ];
            const completedCount = steps.filter(s => s.done).length;
            if (completedCount === steps.length) {
                el.style.display = 'none';
                return;
            }
            el.innerHTML = `
                <span class="text-dim" style="font-size:11px;white-space:nowrap;font-weight:600">Setup</span>
                ${steps.map((s, i) => {
                    const cls = s.done ? 'completed' : (i === completedCount ? 'active' : '');
                    return `${i > 0 ? `<div class="onboarding-connector ${s.done ? 'completed' : ''}"></div>` : ''}
                        <div class="onboarding-step ${cls}">
                            <div class="onboarding-step-check">${s.done ? '&#10003;' : i + 1}</div>
                            <span>${s.label}</span>
                        </div>`;
                }).join('')}
                <span class="text-dim" style="font-size:11px;margin-left:auto">${completedCount}/${steps.length}</span>
            `;
        } catch {
            el.style.display = 'none';
        }
    },

    // ── Live Ticker ────────────────────────────────────────────────────
    async loadTicker() {
        const el = document.getElementById('ticker-content');
        if (!el) return;
        try {
            const [statusResp, betsResp] = await Promise.all([
                fetch('/api/status'),
                fetch('/api/bets'),
            ]);
            const status = await statusResp.json();
            const bets = await betsResp.json();
            const items = [];
            items.push(`<span class="ticker-item">${status.events} events tracked across all sportsbooks</span>`);
            items.push(`<span class="ticker-item">${status.odds_snapshots.toLocaleString()} odds snapshots in database</span>`);
            items.push(`<span class="ticker-item">${status.players} players with ML models</span>`);
            if (bets.total_bets > 0) {
                items.push(`<span class="ticker-item">P/L: <span class="ticker-odds ${bets.total_profit >= 0 ? 'positive' : 'negative'}">$${bets.total_profit >= 0 ? '+' : ''}${bets.total_profit.toFixed(2)}</span></span>`);
                items.push(`<span class="ticker-item">Win Rate: ${(bets.win_rate * 100).toFixed(0)}% (${bets.wins}W-${bets.losses}L)</span>`);
                items.push(`<span class="ticker-item">ROI: <span class="ticker-odds ${bets.roi >= 0 ? 'positive' : 'negative'}">${bets.roi >= 0 ? '+' : ''}${bets.roi.toFixed(1)}%</span></span>`);
            }
            if (bets.pending > 0) {
                items.push(`<span class="ticker-item">${bets.pending} pending bets awaiting results</span>`);
            }
            // Duplicate for seamless scroll
            el.innerHTML = items.join('') + items.join('');
        } catch {}
    },

    // ── EV Heatmap Class ─────────────────────────────────────────────
    getEvHeatClass(ev) {
        if (ev >= 0.10) return 'ev-heat-5';
        if (ev >= 0.08) return 'ev-heat-4';
        if (ev >= 0.06) return 'ev-heat-3';
        if (ev >= 0.04) return 'ev-heat-2';
        if (ev > 0) return 'ev-heat-1';
        return '';
    },

    // ── SVG Line Chart ──────────────────────────────────────────────
    createSVGLineChart(data, {width = 600, height = 200, color = 'var(--accent-green)', showArea = true, labels = []} = {}) {
        if (!data || data.length < 2) return '<div class="empty-state" style="padding:20px"><p>Not enough data for chart</p></div>';
        const min = Math.min(...data);
        const max = Math.max(...data);
        const range = max - min || 1;
        const padding = {top: 20, right: 20, bottom: 30, left: 60};
        const w = width - padding.left - padding.right;
        const h = height - padding.top - padding.bottom;

        const points = data.map((v, i) => ({
            x: padding.left + (i / (data.length - 1)) * w,
            y: padding.top + h - ((v - min) / range) * h,
        }));

        const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
        const areaD = `${pathD} L${points[points.length-1].x.toFixed(1)},${padding.top + h} L${padding.left},${padding.top + h} Z`;

        // Y-axis labels (5 ticks)
        const yTicks = Array.from({length: 5}, (_, i) => {
            const val = min + (range * i / 4);
            const y = padding.top + h - (i / 4) * h;
            return `<text x="${padding.left - 8}" y="${y + 4}" text-anchor="end" fill="var(--text-tertiary)" font-size="10" font-family="var(--font)">$${val >= 0 ? '+' : ''}${val.toFixed(0)}</text>
                    <line x1="${padding.left}" y1="${y}" x2="${padding.left + w}" y2="${y}" stroke="var(--border-light)" stroke-dasharray="4"/>`;
        }).join('');

        // Zero line if applicable
        let zeroLine = '';
        if (min < 0 && max > 0) {
            const zeroY = padding.top + h - ((0 - min) / range) * h;
            zeroLine = `<line x1="${padding.left}" y1="${zeroY}" x2="${padding.left + w}" y2="${zeroY}" stroke="var(--text-tertiary)" stroke-width="1" stroke-dasharray="6,3"/>`;
        }

        // Hover dots
        const dots = points.map((p, i) => {
            const val = data[i];
            return `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3" fill="${val >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'}" opacity="0" class="chart-dot">
                <title>${labels[i] || `#${i+1}`}: $${val >= 0 ? '+' : ''}${val.toFixed(2)}</title>
            </circle>`;
        }).join('');

        const finalColor = data[data.length - 1] >= data[0] ? 'var(--accent-green)' : 'var(--accent-red)';

        return `<svg viewBox="0 0 ${width} ${height}" class="svg-line-chart" style="width:100%;height:auto;max-height:${height}px">
            <defs>
                <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="${finalColor}" stop-opacity="0.3"/>
                    <stop offset="100%" stop-color="${finalColor}" stop-opacity="0"/>
                </linearGradient>
            </defs>
            ${yTicks}
            ${zeroLine}
            ${showArea ? `<path d="${areaD}" fill="url(#chartGrad)"/>` : ''}
            <path d="${pathD}" fill="none" stroke="${finalColor}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            ${dots}
            <circle cx="${points[points.length-1].x.toFixed(1)}" cy="${points[points.length-1].y.toFixed(1)}" r="5" fill="${finalColor}" class="chart-endpoint"/>
        </svg>`;
    },

    // ── Advanced Analytics ────────────────────────────────────────────
    async loadAdvancedAnalytics() {
        const container = document.getElementById('advanced-metrics');
        const chartEl = document.getElementById('advanced-pnl-chart');
        const ddChartEl = document.getElementById('drawdown-chart');
        const monthlyEl = document.getElementById('monthly-breakdown');
        if (!container) return;

        try {
            const resp = await fetch('/api/analytics/advanced');
            const d = await resp.json();

            // Metrics cards
            container.innerHTML = `
                <div class="stat-card green">
                    <div class="stat-label">Sharpe Ratio</div>
                    <div class="stat-value ${d.sharpe_ratio >= 0 ? 'text-green' : 'text-red'}">${d.sharpe_ratio.toFixed(2)}</div>
                    <div class="stat-sub">Risk-adjusted return</div>
                </div>
                <div class="stat-card blue">
                    <div class="stat-label">Max Drawdown</div>
                    <div class="stat-value text-red">$${d.max_drawdown.toFixed(2)}</div>
                    <div class="stat-sub">${d.max_drawdown_pct}% of total staked</div>
                </div>
                <div class="stat-card yellow">
                    <div class="stat-label">Profit Factor</div>
                    <div class="stat-value ${d.profit_factor >= 1 ? 'text-green' : 'text-red'}">${d.profit_factor}x</div>
                    <div class="stat-sub">Gross profit / loss</div>
                </div>
                <div class="stat-card purple">
                    <div class="stat-label">Win Streaks</div>
                    <div class="stat-value">${d.longest_win_streak}W / ${d.longest_loss_streak}L</div>
                    <div class="stat-sub">Best / worst streak</div>
                </div>
            `;

            // P/L SVG chart
            if (chartEl && d.cumulative_pnl.length >= 2) {
                chartEl.innerHTML = this.createSVGLineChart(d.cumulative_pnl, {
                    width: 700, height: 220, showArea: true,
                    labels: d.cumulative_pnl.map((_, i) => `Bet ${i + 1}`),
                });
            } else if (chartEl) {
                chartEl.innerHTML = '<div class="empty-state" style="padding:40px"><p>No P/L data yet</p></div>';
            }

            // Drawdown chart
            if (ddChartEl && d.drawdown_series.length >= 2) {
                const negDD = d.drawdown_series.map(v => -v);
                ddChartEl.innerHTML = this.createSVGLineChart(negDD, {
                    width: 700, height: 160, color: 'var(--accent-red)', showArea: true,
                    labels: negDD.map((_, i) => `Bet ${i + 1}`),
                });
            } else if (ddChartEl) {
                ddChartEl.innerHTML = '<div class="empty-state" style="padding:30px"><p>No drawdown data</p></div>';
            }

            // Monthly breakdown
            if (monthlyEl && d.monthly_breakdown.length > 0) {
                monthlyEl.innerHTML = `
                    <table class="data-table">
                        <thead><tr><th>Month</th><th class="right">Bets</th><th class="right">P/L</th><th class="right">ROI</th></tr></thead>
                        <tbody>
                            ${d.monthly_breakdown.map(m => `
                            <tr class="new-row">
                                <td class="font-bold">${m.month}</td>
                                <td class="right font-mono">${m.bets}</td>
                                <td class="right font-mono font-bold ${m.profit >= 0 ? 'text-green' : 'text-red'}">$${m.profit >= 0 ? '+' : ''}${m.profit.toFixed(2)}</td>
                                <td class="right"><span class="ev-badge ${m.roi >= 0 ? 'high' : 'negative'}">${m.roi >= 0 ? '+' : ''}${m.roi}%</span></td>
                            </tr>`).join('')}
                        </tbody>
                    </table>`;
            } else if (monthlyEl) {
                monthlyEl.innerHTML = '<div class="empty-state" style="padding:30px"><p>No monthly data</p></div>';
            }
        } catch (err) {
            container.innerHTML = `<div class="stat-card red"><div class="stat-value text-red">Error: ${err.message}</div></div>`;
        }
    },

    // ── Watchlist ────────────────────────────────────────────────────
    async toggleWatchlist(eventId, label) {
        try {
            const resp = await fetch('/api/watchlist');
            const data = await resp.json();
            const exists = data.items.some(w => w.event_id === eventId);

            if (exists) {
                await fetch(`/api/watchlist/${eventId}`, { method: 'DELETE' });
                this.toast('Removed from watchlist', 'info');
            } else {
                await fetch(`/api/watchlist?event_id=${encodeURIComponent(eventId)}&label=${encodeURIComponent(label)}`, { method: 'POST' });
                this.toast('Added to watchlist', 'success');
            }
        } catch {
            this.toast('Watchlist error', 'error');
        }
    },

    // ── Load Watchlist Page ────────────────────────────────────────────
    async loadWatchlist() {
        const grid = document.getElementById('watchlist-grid');
        const countEl = document.getElementById('watchlist-count');
        if (!grid) return;

        grid.innerHTML = '<div class="loading-spinner"><div class="spinner"></div> Loading watchlist...</div>';

        try {
            const [wlResp, eventsResp] = await Promise.all([
                fetch('/api/watchlist'),
                fetch('/api/events'),
            ]);
            const wl = await wlResp.json();
            const events = await eventsResp.json();

            if (countEl) countEl.textContent = wl.count;

            if (wl.items.length === 0) {
                grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1;padding:60px">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
                    <p>No events in your watchlist</p>
                    <p class="text-dim" style="font-size:12px">Click the star icon on any edge or event to add it here</p>
                </div>`;
                return;
            }

            const evtMap = {};
            events.forEach(e => { evtMap[e.id] = e; });

            grid.innerHTML = wl.items.map((item, i) => {
                const evt = evtMap[item.event_id];
                const teams = evt ? `${evt.away_team} @ ${evt.home_team}` : item.label || item.event_id;
                const time = item.added_at ? new Date(item.added_at).toLocaleDateString() : '';
                return `
                <div class="watchlist-card" style="animation-delay:${i * 0.05}s;animation:stagger-in 0.5s cubic-bezier(0.2,0,0,1) forwards;opacity:0">
                    <div class="watchlist-card-header">
                        <div>
                            <div class="watchlist-card-teams">${teams}</div>
                            <div class="watchlist-card-time">Added ${time}</div>
                        </div>
                        <button class="watchlist-card-remove" onclick="SBA.removeWatchlistItem('${item.event_id}')" title="Remove">&times;</button>
                    </div>
                    <div class="watchlist-card-odds">
                        ${evt ? `
                            <a href="/line-movement?event=${item.event_id}" class="btn btn-outline btn-sm" style="font-size:11px">Line Movement</a>
                            <a href="/odds-comparison?event=${item.event_id}" class="btn btn-outline btn-sm" style="font-size:11px">Compare Odds</a>
                        ` : ''}
                    </div>
                </div>`;
            }).join('');
        } catch (err) {
            grid.innerHTML = `<div class="empty-state text-red"><p>Error loading watchlist: ${err.message}</p></div>`;
        }
    },

    async removeWatchlistItem(eventId) {
        try {
            await fetch(`/api/watchlist/${eventId}`, { method: 'DELETE' });
            this.toast('Removed from watchlist', 'info');
            this.loadWatchlist();
        } catch {
            this.toast('Error removing item', 'error');
        }
    },

    // ── Confetti Effect ────────────────────────────────────────────────
    showConfetti() {
        const container = document.createElement('div');
        container.className = 'confetti-container';
        document.body.appendChild(container);

        const colors = ['#00e68a', '#5b9aff', '#ffc234', '#a855f7', '#ff4d6a', '#22d3ee'];
        for (let i = 0; i < 60; i++) {
            const piece = document.createElement('div');
            piece.className = 'confetti-piece';
            piece.style.left = `${Math.random() * 100}%`;
            piece.style.top = `${-10 + Math.random() * 20}px`;
            piece.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
            piece.style.animationDelay = `${Math.random() * 0.5}s`;
            piece.style.animationDuration = `${1.5 + Math.random() * 1.5}s`;
            piece.style.width = `${4 + Math.random() * 8}px`;
            piece.style.height = `${4 + Math.random() * 8}px`;
            piece.style.transform = `rotate(${Math.random() * 360}deg)`;
            container.appendChild(piece);
        }

        setTimeout(() => container.remove(), 3000);
    },

    // ── Scroll Progress Bar ────────────────────────────────────────────
    setupScrollProgress() {
        let bar = document.getElementById('scroll-progress');
        if (!bar) {
            bar = document.createElement('div');
            bar.className = 'scroll-progress';
            bar.id = 'scroll-progress';
            bar.style.width = '0%';
            document.body.appendChild(bar);
        }

        window.addEventListener('scroll', () => {
            const winScroll = document.documentElement.scrollTop;
            const height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
            if (height > 0) {
                bar.style.width = `${(winScroll / height) * 100}%`;
            }
        }, { passive: true });
    },

    // ── Intersection Observer for Reveal Animations ────────────────────
    setupRevealAnimations() {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

        document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
    },

    // ── Notification Panel ─────────────────────────────────────────────
    toggleNotificationPanel() {
        let panel = document.getElementById('notification-panel');
        if (!panel) {
            panel = document.createElement('div');
            panel.className = 'notification-panel';
            panel.id = 'notification-panel';
            panel.innerHTML = `
                <div class="notification-panel-header">
                    <h3>Edge Alerts</h3>
                    <button onclick="document.getElementById('notification-panel').classList.remove('open')" style="background:none;border:none;color:var(--text-tertiary);font-size:20px;cursor:pointer">&times;</button>
                </div>
                <div class="notification-panel-body" id="notification-panel-body">
                    <div class="empty-state" style="padding:40px">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="36" height="36"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
                        <p>No alerts right now</p>
                        <p class="text-dim" style="font-size:11px">Alerts appear when high-EV edges are found</p>
                    </div>
                </div>
            `;
            document.body.appendChild(panel);
        }
        panel.classList.toggle('open');
        if (panel.classList.contains('open')) this.loadNotifications();
    },

    async loadNotifications() {
        const body = document.getElementById('notification-panel-body');
        if (!body) return;
        try {
            const resp = await fetch('/api/alerts');
            const data = await resp.json();
            if (data.alerts && data.alerts.length > 0) {
                body.innerHTML = data.alerts.map((a, i) => `
                    <div class="notification-item ${a.type || 'edge'}" style="animation-delay:${i * 0.05}s">
                        <div class="notif-title">${a.title || 'Edge Alert'}</div>
                        <div class="notif-body">${a.message || a.description || 'New opportunity detected'}</div>
                        <div class="notif-time">${a.time || 'Just now'}</div>
                    </div>
                `).join('');
            } else {
                body.innerHTML = `
                    <div class="empty-state" style="padding:40px">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="36" height="36"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/></svg>
                        <p>No alerts right now</p>
                    </div>`;
            }
        } catch {
            body.innerHTML = '<div class="empty-state"><p>Could not load alerts</p></div>';
        }
    },

    // ── Donut Chart Generator ──────────────────────────────────────────
    createDonutChart(segments, centerValue = '', centerLabel = '') {
        const circumference = 2 * Math.PI * 58;
        const total = segments.reduce((sum, s) => sum + s.value, 0) || 1;
        let accumulated = 0;

        const arcs = segments.map(s => {
            const pct = s.value / total;
            const dashArray = circumference * pct;
            const dashOffset = -circumference * accumulated;
            accumulated += pct;
            return `<circle class="donut-segment" cx="70" cy="70" r="58"
                stroke="${s.color}" stroke-dasharray="${dashArray} ${circumference - dashArray}"
                stroke-dashoffset="${dashOffset}" />`;
        }).join('');

        return `<div class="donut-chart">
            <svg viewBox="0 0 140 140">
                <circle class="donut-bg" cx="70" cy="70" r="58"/>
                ${arcs}
            </svg>
            <div class="donut-chart-center">
                <div class="donut-value">${centerValue}</div>
                <div class="donut-label">${centerLabel}</div>
            </div>
        </div>`;
    },

    // ── Floating Action Button ─────────────────────────────────────────
    setupFAB() {
        if (document.getElementById('fab-btn')) return;
        const fab = document.createElement('button');
        fab.className = 'fab';
        fab.id = 'fab-btn';
        fab.title = 'Quick Scan for Edges';
        fab.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>';
        fab.onclick = () => {
            if (window.location.pathname === '/edges') {
                document.querySelector('.btn-scan')?.click();
            } else {
                window.location.href = '/edges';
            }
        };
        document.body.appendChild(fab);
    },

    // ── Enhanced Settle with Confetti ──────────────────────────────────
    async settleBetWithEffect(betId, status, profitLoss) {
        await this.settleBet(betId, status, profitLoss);
        if (status === 'won') {
            this.showConfetti();
        }
    },

    // ── Heatmap Calendar ────────────────────────────────────────────
    createHeatmapCalendar(dailyPnl) {
        if (!dailyPnl || dailyPnl.length === 0) {
            return '<div class="empty-state" style="padding:40px"><p>No daily P/L data for heatmap</p></div>';
        }

        // Build a map of date -> pnl
        const pnlMap = {};
        dailyPnl.forEach(d => { pnlMap[d.date] = d.pnl; });

        // Get range: last 90 days
        const today = new Date();
        const start = new Date(today);
        start.setDate(start.getDate() - 89);

        // Align to start of week (Sunday)
        const dayOfWeek = start.getDay();
        start.setDate(start.getDate() - dayOfWeek);

        const days = [];
        const current = new Date(start);
        while (current <= today) {
            const dateStr = current.toISOString().slice(0, 10);
            const pnl = pnlMap[dateStr] || 0;
            const isInRange = current >= new Date(today.getTime() - 89 * 86400000);
            days.push({ date: dateStr, pnl, active: isInRange });
            current.setDate(current.getDate() + 1);
        }

        const maxAbs = Math.max(...days.filter(d => d.active).map(d => Math.abs(d.pnl)), 1);

        const weekLabels = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
        const labelsHtml = weekLabels.map(l =>
            `<div style="font-size:9px;color:var(--text-tertiary);display:flex;align-items:center;justify-content:center">${l}</div>`
        ).join('');

        const cellsHtml = days.map(d => {
            if (!d.active) {
                return '<div class="heatmap-day" style="background:transparent"></div>';
            }
            let bg;
            if (d.pnl === 0) {
                bg = 'rgba(255,255,255,0.03)';
            } else if (d.pnl > 0) {
                const intensity = Math.min(d.pnl / maxAbs, 1);
                const alpha = 0.15 + intensity * 0.65;
                bg = `rgba(0, 230, 138, ${alpha.toFixed(2)})`;
            } else {
                const intensity = Math.min(Math.abs(d.pnl) / maxAbs, 1);
                const alpha = 0.15 + intensity * 0.65;
                bg = `rgba(255, 77, 106, ${alpha.toFixed(2)})`;
            }
            const tooltip = `${d.date}: $${d.pnl >= 0 ? '+' : ''}${d.pnl.toFixed(2)}`;
            return `<div class="heatmap-day" style="background:${bg}" data-tooltip="${tooltip}"></div>`;
        }).join('');

        return `
            <div class="heatmap-calendar">
                ${labelsHtml}
                ${cellsHtml}
            </div>
            <div class="heatmap-legend">
                <span>Less</span>
                <div class="heatmap-legend-block" style="background:rgba(255,77,106,0.6)"></div>
                <div class="heatmap-legend-block" style="background:rgba(255,77,106,0.25)"></div>
                <div class="heatmap-legend-block" style="background:rgba(255,255,255,0.03)"></div>
                <div class="heatmap-legend-block" style="background:rgba(0,230,138,0.25)"></div>
                <div class="heatmap-legend-block" style="background:rgba(0,230,138,0.6)"></div>
                <span>More</span>
            </div>`;
    },

    // ── Bankroll Health Gauge (Half-circle) ──────────────────────────
    createHealthGauge(score, label = 'Health') {
        // Score 0-100
        const clamped = Math.max(0, Math.min(100, score));
        const angle = (clamped / 100) * 180;
        const color = clamped >= 70 ? 'var(--accent-green)' : clamped >= 40 ? 'var(--accent-yellow)' : 'var(--accent-red)';
        const status = clamped >= 70 ? 'Healthy' : clamped >= 40 ? 'Caution' : 'At Risk';

        // Arc math for SVG
        const cx = 90, cy = 80, r = 65;
        const startAngle = Math.PI;
        const endAngle = Math.PI + (angle * Math.PI / 180);
        const x1 = cx + r * Math.cos(startAngle);
        const y1 = cy + r * Math.sin(startAngle);
        const x2 = cx + r * Math.cos(endAngle);
        const y2 = cy + r * Math.sin(endAngle);
        const largeArc = angle > 180 ? 1 : 0;

        return `<div class="health-gauge">
            <svg viewBox="0 0 180 100">
                <path d="M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}"
                      fill="none" stroke="var(--bg-tertiary)" stroke-width="10" stroke-linecap="round"/>
                <path d="M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}"
                      fill="none" stroke="${color}" stroke-width="10" stroke-linecap="round"
                      style="filter:drop-shadow(0 0 6px ${color})"/>
            </svg>
            <div class="health-gauge-label">
                <div class="health-gauge-value" style="color:${color}">${clamped}</div>
                <div class="health-gauge-text">${status}</div>
            </div>
        </div>`;
    },

    // ── Advanced P/L Line Chart (SVG) ───────────────────────────────
    createLineChart(data, width = 800, height = 200) {
        if (!data || data.length < 2) return '';

        const padding = { top: 20, right: 20, bottom: 30, left: 60 };
        const chartW = width - padding.left - padding.right;
        const chartH = height - padding.top - padding.bottom;

        const minY = Math.min(...data.map(d => d.y), 0);
        const maxY = Math.max(...data.map(d => d.y), 0);
        const rangeY = maxY - minY || 1;

        const scaleX = (i) => padding.left + (i / (data.length - 1)) * chartW;
        const scaleY = (v) => padding.top + chartH - ((v - minY) / rangeY) * chartH;

        // Build path
        const linePath = data.map((d, i) =>
            `${i === 0 ? 'M' : 'L'} ${scaleX(i).toFixed(1)} ${scaleY(d.y).toFixed(1)}`
        ).join(' ');

        // Gradient fill area
        const areaPath = `${linePath} L ${scaleX(data.length - 1).toFixed(1)} ${scaleY(0).toFixed(1)} L ${scaleX(0).toFixed(1)} ${scaleY(0).toFixed(1)} Z`;

        // Zero line
        const zeroY = scaleY(0);

        // Y-axis labels
        const yTicks = 5;
        const yLabels = Array.from({length: yTicks + 1}, (_, i) => {
            const val = minY + (rangeY / yTicks) * i;
            return { val, y: scaleY(val) };
        });

        // X-axis labels (show ~6 dates)
        const xStep = Math.max(1, Math.floor(data.length / 6));
        const xLabels = data.filter((_, i) => i % xStep === 0 || i === data.length - 1);

        const finalVal = data[data.length - 1].y;
        const lineColor = finalVal >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
        const gradId = 'pnl-grad-' + Math.random().toString(36).slice(2, 8);

        return `<svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;max-height:${height}px">
            <defs>
                <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="${lineColor}" stop-opacity="0.2"/>
                    <stop offset="100%" stop-color="${lineColor}" stop-opacity="0"/>
                </linearGradient>
            </defs>
            ${yLabels.map(l => `
                <line x1="${padding.left}" y1="${l.y.toFixed(1)}" x2="${width - padding.right}" y2="${l.y.toFixed(1)}"
                      stroke="var(--border-light)" stroke-width="1"/>
                <text x="${padding.left - 8}" y="${l.y.toFixed(1)}" text-anchor="end" dominant-baseline="middle"
                      fill="var(--text-tertiary)" font-size="10" font-family="var(--font-mono)">$${l.val >= 0 ? '' : ''}${l.val.toFixed(0)}</text>
            `).join('')}
            <line x1="${padding.left}" y1="${zeroY.toFixed(1)}" x2="${width - padding.right}" y2="${zeroY.toFixed(1)}"
                  stroke="var(--text-tertiary)" stroke-width="1" stroke-dasharray="4,4" opacity="0.3"/>
            <path d="${areaPath}" fill="url(#${gradId})"/>
            <path d="${linePath}" fill="none" stroke="${lineColor}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            <circle cx="${scaleX(data.length - 1).toFixed(1)}" cy="${scaleY(finalVal).toFixed(1)}" r="4"
                    fill="${lineColor}" stroke="var(--bg-card)" stroke-width="2"/>
            ${xLabels.map(d => {
                const i = data.indexOf(d);
                return `<text x="${scaleX(i).toFixed(1)}" y="${height - 6}" text-anchor="middle"
                              fill="var(--text-tertiary)" font-size="10">${d.label || ''}</text>`;
            }).join('')}
        </svg>`;
    },

    // ── Advanced Analytics Loader ────────────────────────────────────
    async loadAdvancedAnalytics() {
        try {
            const [analyticsResp, betsResp, settingsResp] = await Promise.all([
                fetch('/api/analytics'),
                fetch('/api/bets'),
                fetch('/api/settings'),
            ]);
            const analytics = await analyticsResp.json();
            const bets = await betsResp.json();
            const settings = await settingsResp.json();

            // Advanced metrics
            const metricsEl = document.getElementById('advanced-metrics');
            if (metricsEl && analytics.daily_pnl && analytics.daily_pnl.length > 0) {
                const pnls = analytics.daily_pnl.map(d => d.pnl);
                const mean = pnls.reduce((a, b) => a + b, 0) / pnls.length;
                const variance = pnls.reduce((sum, p) => sum + Math.pow(p - mean, 2), 0) / pnls.length;
                const stdDev = Math.sqrt(variance) || 1;
                const sharpe = (mean / stdDev * Math.sqrt(252)).toFixed(2);

                // Max drawdown
                let peak = 0, maxDd = 0, cumulative = 0;
                pnls.forEach(p => {
                    cumulative += p;
                    if (cumulative > peak) peak = cumulative;
                    const dd = peak - cumulative;
                    if (dd > maxDd) maxDd = dd;
                });

                // Profit factor
                const grossWins = pnls.filter(p => p > 0).reduce((a, b) => a + b, 0);
                const grossLosses = Math.abs(pnls.filter(p => p < 0).reduce((a, b) => a + b, 0)) || 1;
                const profitFactor = (grossWins / grossLosses).toFixed(2);

                // Streaks
                let currentStreak = 0, maxWinStreak = 0, maxLossStreak = 0, curWin = 0, curLoss = 0;
                pnls.forEach(p => {
                    if (p > 0) { curWin++; curLoss = 0; maxWinStreak = Math.max(maxWinStreak, curWin); }
                    else if (p < 0) { curLoss++; curWin = 0; maxLossStreak = Math.max(maxLossStreak, curLoss); }
                });

                const sharpeColor = parseFloat(sharpe) >= 1 ? 'text-green' : parseFloat(sharpe) >= 0 ? 'text-dim' : 'text-red';

                metricsEl.innerHTML = `
                    <div class="stat-card green">
                        <div class="stat-label">Sharpe Ratio</div>
                        <div class="stat-value ${sharpeColor}">${sharpe}</div>
                        <div class="stat-sub">${parseFloat(sharpe) >= 1 ? 'Excellent' : parseFloat(sharpe) >= 0.5 ? 'Good' : 'Needs work'}</div>
                    </div>
                    <div class="stat-card blue">
                        <div class="stat-label">Max Drawdown</div>
                        <div class="stat-value text-red">$${maxDd.toFixed(2)}</div>
                        <div class="stat-sub">${settings.bankroll ? (maxDd / settings.bankroll * 100).toFixed(1) + '% of bankroll' : 'Peak to trough'}</div>
                    </div>
                    <div class="stat-card yellow">
                        <div class="stat-label">Profit Factor</div>
                        <div class="stat-value ${parseFloat(profitFactor) >= 1.5 ? 'text-green' : ''}">${profitFactor}</div>
                        <div class="stat-sub">${parseFloat(profitFactor) >= 1.5 ? 'Strong edge' : parseFloat(profitFactor) >= 1 ? 'Marginal' : 'Losing'}</div>
                    </div>
                    <div class="stat-card purple">
                        <div class="stat-label">Win Streaks</div>
                        <div class="stat-value">${maxWinStreak}W / ${maxLossStreak}L</div>
                        <div class="stat-sub">Best / Worst streaks</div>
                    </div>
                `;
            }

            // Advanced P/L line chart
            const advChartEl = document.getElementById('advanced-pnl-chart');
            if (advChartEl && analytics.daily_pnl && analytics.daily_pnl.length > 0) {
                let cumulative = 0;
                const chartData = analytics.daily_pnl.map(d => {
                    cumulative += d.pnl;
                    return { y: cumulative, label: d.date.slice(5) };
                });
                advChartEl.innerHTML = this.createLineChart(chartData);
            } else if (advChartEl) {
                advChartEl.innerHTML = '<div class="empty-state" style="padding:40px"><p>No data for P/L chart yet</p></div>';
            }

            // Drawdown chart
            const ddChartEl = document.getElementById('drawdown-chart');
            if (ddChartEl && analytics.daily_pnl && analytics.daily_pnl.length > 0) {
                let peak = 0, cumulative = 0;
                const ddData = analytics.daily_pnl.map(d => {
                    cumulative += d.pnl;
                    if (cumulative > peak) peak = cumulative;
                    return { y: -(peak - cumulative), label: d.date.slice(5) };
                });
                ddChartEl.innerHTML = this.createLineChart(ddData, 800, 160);
            } else if (ddChartEl) {
                ddChartEl.innerHTML = '<div class="empty-state" style="padding:40px"><p>No data for drawdown chart yet</p></div>';
            }

            // Monthly breakdown
            const monthlyEl = document.getElementById('monthly-breakdown');
            if (monthlyEl && analytics.by_month) {
                const months = Object.entries(analytics.by_month);
                if (months.length === 0) {
                    monthlyEl.innerHTML = '<div class="empty-state" style="padding:40px"><p>No monthly data yet</p></div>';
                } else {
                    monthlyEl.innerHTML = `
                        <table class="data-table">
                            <thead><tr><th>Month</th><th class="right">Bets</th><th class="right">Win Rate</th><th class="right">P/L</th><th class="right">ROI</th></tr></thead>
                            <tbody>
                                ${months.map(([name, d]) => `
                                <tr class="new-row">
                                    <td class="font-bold">${name}</td>
                                    <td class="right font-mono">${d.bets}</td>
                                    <td class="right font-mono">${d.win_rate}%</td>
                                    <td class="right font-mono font-bold ${d.profit >= 0 ? 'text-green' : 'text-red'}">$${d.profit >= 0 ? '+' : ''}${d.profit.toFixed(2)}</td>
                                    <td class="right"><span class="ev-badge ${d.roi >= 0 ? 'high' : 'negative'}">${d.roi >= 0 ? '+' : ''}${d.roi}%</span></td>
                                </tr>`).join('')}
                            </tbody>
                        </table>
                    `;
                }
            }
        } catch {}
    },

    // ── Dashboard Risk Summary ──────────────────────────────────────
    async loadDashboardRisk() {
        try {
            const [betsResp, settingsResp, analyticsResp] = await Promise.all([
                fetch('/api/bets'),
                fetch('/api/settings'),
                fetch('/api/analytics'),
            ]);
            const bets = await betsResp.json();
            const settings = await settingsResp.json();
            const analytics = await analyticsResp.json();

            const riskEl = document.getElementById('dashboard-risk');
            if (!riskEl) return;

            if (bets.total_bets === 0) {
                riskEl.innerHTML = `<div class="empty-state" style="padding:40px">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="36" height="36"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                    <p>Start tracking bets to see risk metrics</p>
                </div>`;
                return;
            }

            // Calculate health score (0-100)
            const bankroll = settings.bankroll || 1000;
            const roi = bets.roi || 0;
            const winRate = bets.win_rate || 0;

            // Health factors
            let score = 50; // baseline
            score += Math.min(roi, 20); // ROI contributes up to +20
            score += (winRate - 0.5) * 40; // Win rate above 50% contributes
            if (bets.total_profit > 0) score += 10;
            score = Math.max(0, Math.min(100, Math.round(score)));

            const gauge = this.createHealthGauge(score);
            const heatmap = this.createHeatmapCalendar(analytics.daily_pnl);

            riskEl.innerHTML = `
                <div style="display:grid;grid-template-columns:200px 1fr;gap:24px;align-items:start">
                    <div style="text-align:center">
                        ${gauge}
                        <div style="margin-top:12px;display:grid;gap:8px">
                            <div style="display:flex;justify-content:space-between;font-size:12px">
                                <span class="text-dim">Bankroll</span>
                                <span class="font-mono font-bold text-green">$${bankroll.toLocaleString()}</span>
                            </div>
                            <div style="display:flex;justify-content:space-between;font-size:12px">
                                <span class="text-dim">Net P/L</span>
                                <span class="font-mono font-bold ${bets.total_profit >= 0 ? 'text-green' : 'text-red'}">$${bets.total_profit >= 0 ? '+' : ''}${bets.total_profit.toFixed(2)}</span>
                            </div>
                            <div style="display:flex;justify-content:space-between;font-size:12px">
                                <span class="text-dim">ROI</span>
                                <span class="font-mono font-bold ${roi >= 0 ? 'text-green' : 'text-red'}">${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%</span>
                            </div>
                        </div>
                    </div>
                    <div>
                        <div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:8px">90-Day P/L Heatmap</div>
                        ${heatmap}
                    </div>
                </div>
            `;
        } catch {}
    },

    // ── Progress Ring Generator ──────────────────────────────────────
    createProgressRing(value, max = 100, size = 48, label = '') {
        const pct = Math.min(Math.max(value / max, 0), 1);
        const r = (size / 2) - 6;
        const circumference = 2 * Math.PI * r;
        const offset = circumference * (1 - pct);
        const color = pct > 0.6 ? 'var(--accent-green)' : pct > 0.35 ? 'var(--accent-yellow)' : 'var(--accent-red)';
        return `<div class="progress-ring" style="width:${size}px;height:${size}px">
            <svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
                <circle class="progress-ring-track" cx="${size/2}" cy="${size/2}" r="${r}"/>
                <circle class="progress-ring-fill" cx="${size/2}" cy="${size/2}" r="${r}"
                    stroke="${color}" stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"/>
            </svg>
            <div class="progress-ring-value">${label || Math.round(value) + '%'}</div>
        </div>`;
    },

    // ── Accent Theme System ─────────────────────────────────────────
    setAccent(accent) {
        document.documentElement.setAttribute('data-accent', accent);
        localStorage.setItem('sba-accent', accent);
        this.toast(`Accent theme: ${accent}`, 'success');
    },

    loadAccent() {
        const saved = localStorage.getItem('sba-accent');
        if (saved) document.documentElement.setAttribute('data-accent', saved);
    },

    // ── Enhanced Player Page ────────────────────────────────────────
    async loadPlayerEnhanced(name) {
        const container = document.getElementById('player-content');
        if (!container) return;

        container.innerHTML = `
            <div style="display:grid;gap:16px">
                <div class="skeleton" style="height:120px;border-radius:var(--radius-lg)"></div>
                <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px">
                    <div class="skeleton skeleton-card"></div>
                    <div class="skeleton skeleton-card"></div>
                    <div class="skeleton skeleton-card"></div>
                    <div class="skeleton skeleton-card"></div>
                </div>
            </div>`;

        try {
            const resp = await fetch(`/api/players/${encodeURIComponent(name)}`);
            if (!resp.ok) {
                container.innerHTML = `<div class="empty-state" style="padding:60px">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
                    <p>Player "${name}" not found</p>
                    <p class="text-dim" style="font-size:12px">Run <code class="step-code" style="display:inline">sba data backfill --player "${name}"</code> to import</p>
                </div>`;
                return;
            }

            const p = await resp.json();
            const initials = p.name.split(' ').map(n => n[0]).join('');

            // Build comparison bars for stats
            const statBars = (stat, color, maxVal) => {
                const l5 = p.last_5[stat] || 0;
                const l20 = p.last_20[stat] || 0;
                const trend = p.trends[stat + '_trend'];
                const trendStr = trend !== undefined ? (trend >= 0 ? '+' : '') + trend.toFixed(1) : '';
                const trendColor = trend >= 0 ? 'text-green' : 'text-red';
                return `
                    <div class="comparison-bar">
                        <span class="comparison-bar-label">L5</span>
                        <div class="comparison-bar-track"><div class="comparison-bar-fill ${color}" style="width:${Math.min(l5 / (maxVal || 1) * 100, 100)}%"></div></div>
                        <span class="comparison-bar-value">${l5.toFixed(1)}</span>
                    </div>
                    <div class="comparison-bar">
                        <span class="comparison-bar-label">L20</span>
                        <div class="comparison-bar-track"><div class="comparison-bar-fill ${color}" style="width:${Math.min(l20 / (maxVal || 1) * 100, 100)}%;opacity:0.6"></div></div>
                        <span class="comparison-bar-value text-dim">${l20.toFixed(1)}</span>
                    </div>
                    ${trendStr ? `<div style="font-size:11px;text-align:right" class="${trendColor}">Trend: ${trendStr}</div>` : ''}
                `;
            };

            container.innerHTML = `
                <div class="player-hero">
                    <div class="player-hero-content">
                        <div class="player-avatar-lg">${initials}</div>
                        <div class="player-hero-info">
                            <h2>${p.name}</h2>
                            <div class="player-hero-meta">
                                <span>${p.team}</span>
                                <span class="sep"></span>
                                <span>${p.position}</span>
                                <span class="sep"></span>
                                <span>${p.games} games</span>
                            </div>
                            <div class="player-stat-pills">
                                <div class="player-stat-pill">
                                    <span class="pill-label">PPG</span>
                                    <span class="pill-value text-green">${(p.last_5.points || 0).toFixed(1)}</span>
                                </div>
                                <div class="player-stat-pill">
                                    <span class="pill-label">RPG</span>
                                    <span class="pill-value text-blue" style="color:var(--accent-blue)">${(p.last_5.rebounds || 0).toFixed(1)}</span>
                                </div>
                                <div class="player-stat-pill">
                                    <span class="pill-label">APG</span>
                                    <span class="pill-value text-yellow" style="color:var(--accent-yellow)">${(p.last_5.assists || 0).toFixed(1)}</span>
                                </div>
                                <div class="player-stat-pill">
                                    <span class="pill-label">MPG</span>
                                    <span class="pill-value" style="color:var(--accent-purple)">${(p.last_5.minutes || 0).toFixed(1)}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="dashboard-grid">
                    <div class="card tilt-card">
                        <div class="card-header"><h3 style="color:var(--accent-green)">Points</h3></div>
                        <div class="card-body padded">${statBars('points', '', 40)}</div>
                    </div>
                    <div class="card tilt-card">
                        <div class="card-header"><h3 style="color:var(--accent-blue)">Rebounds</h3></div>
                        <div class="card-body padded">${statBars('rebounds', 'blue', 15)}</div>
                    </div>
                    <div class="card tilt-card">
                        <div class="card-header"><h3 style="color:var(--accent-yellow)">Assists</h3></div>
                        <div class="card-body padded">${statBars('assists', 'yellow', 12)}</div>
                    </div>
                    <div class="card tilt-card">
                        <div class="card-header"><h3 style="color:var(--accent-purple)">Minutes</h3></div>
                        <div class="card-body padded">${statBars('minutes', 'purple', 42)}</div>
                    </div>

                    <div class="card full-width">
                        <div class="card-header">
                            <h3>
                                <svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><rect x="2" y="3" width="20" height="18" rx="2"/><line x1="2" y1="9" x2="22" y2="9"/></svg>
                                Recent Games
                            </h3>
                            <span class="text-dim" style="font-size:12px">${p.recent_games.length} games</span>
                        </div>
                        <div class="card-body">
                            <div style="overflow-x:auto">
                                <table class="data-table">
                                    <thead>
                                        <tr>
                                            <th>Date</th><th>Opp</th><th class="right">Min</th>
                                            <th class="right">Pts</th><th class="right">Reb</th>
                                            <th class="right">Ast</th><th class="right">3PM</th>
                                            <th class="right">Stl</th><th class="right">Blk</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${p.recent_games.map((g, i) => {
                                            const isHot = g.points >= (p.last_20.points || 0) * 1.3;
                                            const isCold = g.points <= (p.last_20.points || 0) * 0.5;
                                            return `
                                            <tr class="new-row ${isHot ? 'hot-row' : isCold ? 'cold-row' : ''}" style="animation-delay:${i * 0.03}s">
                                                <td class="text-dim">${g.date}</td>
                                                <td>${g.opponent}</td>
                                                <td class="right font-mono">${Math.round(g.minutes)}</td>
                                                <td class="right font-mono font-bold">${g.points}</td>
                                                <td class="right font-mono">${g.rebounds}</td>
                                                <td class="right font-mono">${g.assists}</td>
                                                <td class="right font-mono">${g.threes}</td>
                                                <td class="right font-mono">${g.steals}</td>
                                                <td class="right font-mono">${g.blocks}</td>
                                            </tr>`;
                                        }).join('')}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        } catch (err) {
            container.innerHTML = `<div class="empty-state text-red">Error loading player: ${err.message}</div>`;
        }
    },

    // ── Edge Summary Banner ─────────────────────────────────────────
    createEdgeSummaryBanner(edges) {
        if (!edges || edges.length === 0) return '';
        const avgEv = edges.reduce((s, e) => s + e.ev, 0) / edges.length;
        const totalStake = edges.reduce((s, e) => s + e.recommended_stake, 0);
        const highConf = edges.filter(e => e.confidence === 'high').length;
        const bestEv = Math.max(...edges.map(e => e.ev));
        return `
            <div class="edge-summary-banner">
                <div class="edge-summary-item">
                    <div class="edge-sum-value text-green">${edges.length}</div>
                    <div class="edge-sum-label">Edges Found</div>
                </div>
                <div class="edge-summary-item">
                    <div class="edge-sum-value text-green">${(avgEv * 100).toFixed(1)}%</div>
                    <div class="edge-sum-label">Avg EV</div>
                </div>
                <div class="edge-summary-item">
                    <div class="edge-sum-value" style="color:var(--accent-yellow)">${(bestEv * 100).toFixed(1)}%</div>
                    <div class="edge-sum-label">Best EV</div>
                </div>
                <div class="edge-summary-item">
                    <div class="edge-sum-value" style="color:var(--accent-blue)">${highConf}</div>
                    <div class="edge-sum-label">High Confidence</div>
                </div>
                <div class="edge-summary-item">
                    <div class="edge-sum-value" style="color:var(--accent-purple)">$${totalStake.toFixed(0)}</div>
                    <div class="edge-sum-label">Total Stake</div>
                </div>
            </div>
        `;
    },

    // ── EV Heat Class ───────────────────────────────────────────────
    getEvHeatClass(ev) {
        if (ev >= 0.08) return 'ev-heat-ultra';
        if (ev >= 0.05) return 'ev-heat-high';
        return '';
    },

    // ── Line Movement SVG Chart ─────────────────────────────────────
    createLineMovementChart(groups) {
        const allSnaps = Object.values(groups).flat();
        if (allSnaps.length < 2) return '';

        const width = 800, height = 200;
        const padding = { top: 20, right: 20, bottom: 30, left: 60 };
        const chartW = width - padding.left - padding.right;
        const chartH = height - padding.top - padding.bottom;

        // Get all odds values
        const allOdds = allSnaps.map(s => s.odds_american);
        const minOdds = Math.min(...allOdds);
        const maxOdds = Math.max(...allOdds);
        const rangeOdds = maxOdds - minOdds || 1;

        const colors = ['var(--accent-green)', 'var(--accent-blue)', 'var(--accent-yellow)', 'var(--accent-purple)', 'var(--accent-cyan)', 'var(--accent-red)'];
        let colorIdx = 0;

        const scaleY = (v) => padding.top + chartH - ((v - minOdds) / rangeOdds) * chartH;

        // Y-axis labels
        const yTicks = 5;
        const yLabels = Array.from({length: yTicks + 1}, (_, i) => {
            const val = minOdds + (rangeOdds / yTicks) * i;
            return { val: Math.round(val), y: scaleY(val) };
        });

        let paths = '';
        let dots = '';
        let legend = '';

        Object.entries(groups).forEach(([key, snaps]) => {
            const color = colors[colorIdx++ % colors.length];
            const scaleX = (i) => padding.left + (i / Math.max(snaps.length - 1, 1)) * chartW;

            const pathD = snaps.map((s, i) =>
                `${i === 0 ? 'M' : 'L'} ${scaleX(i).toFixed(1)} ${scaleY(s.odds_american).toFixed(1)}`
            ).join(' ');

            paths += `<path d="${pathD}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.8"/>`;
            dots += snaps.map((s, i) =>
                `<circle class="lm-chart-dot" cx="${scaleX(i).toFixed(1)}" cy="${scaleY(s.odds_american).toFixed(1)}" r="3.5" fill="${color}" stroke="var(--bg-card)" stroke-width="1.5" data-tooltip="${s.odds_american > 0 ? '+' : ''}${s.odds_american}"/>`
            ).join('');

            legend += `<span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;color:var(--text-secondary)"><span style="width:10px;height:3px;background:${color};border-radius:2px"></span>${key}</span>`;
        });

        return `
            <div class="lm-visual-chart">
                <svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;max-height:${height}px">
                    ${yLabels.map(l => `
                        <line x1="${padding.left}" y1="${l.y.toFixed(1)}" x2="${width - padding.right}" y2="${l.y.toFixed(1)}" stroke="var(--border-light)" stroke-width="1"/>
                        <text x="${padding.left - 8}" y="${l.y.toFixed(1)}" text-anchor="end" dominant-baseline="middle" fill="var(--text-tertiary)" font-size="10" font-family="var(--font-mono)">${l.val > 0 ? '+' : ''}${l.val}</text>
                    `).join('')}
                    ${paths}
                    ${dots}
                </svg>
                <div style="display:flex;gap:16px;padding:8px 0 0;flex-wrap:wrap">${legend}</div>
            </div>
        `;
    },

    // ── Enhanced Settings with Accent Picker ────────────────────────
    renderAccentPicker() {
        const currentAccent = localStorage.getItem('sba-accent') || '';
        const accents = [
            { id: '', label: 'Default', color: '#00e68a' },
            { id: 'emerald', label: 'Emerald', color: '#10b981' },
            { id: 'neon', label: 'Neon', color: '#39ff14' },
            { id: 'gold', label: 'Gold', color: '#f59e0b' },
            { id: 'ocean', label: 'Ocean', color: '#06b6d4' },
        ];
        return `
            <div class="settings-row" style="border-bottom:none">
                <div>
                    <div class="font-bold">Accent Theme</div>
                    <div class="text-dim" style="font-size:12px">Customize the app's primary accent color</div>
                </div>
                <div class="accent-picker">
                    ${accents.map(a => `
                        <div class="accent-swatch ${currentAccent === a.id ? 'active' : ''}"
                             style="background:${a.color}"
                             onclick="SBA.setAccent('${a.id}');document.querySelectorAll('.accent-swatch').forEach(s=>s.classList.remove('active'));this.classList.add('active')"
                             data-tooltip="${a.label}"></div>
                    `).join('')}
                </div>
            </div>
        `;
    },

    // ── NProgress-style Top Loading Bar ──────────────────────────────
    setupProgressBar() {
        // Create the progress bar element
        const bar = document.createElement('div');
        bar.id = 'nprogress-bar';
        document.body.prepend(bar);

        // Intercept link clicks for page navigation loading effect
        document.addEventListener('click', (e) => {
            const link = e.target.closest('a[href]');
            if (!link) return;
            const href = link.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('javascript:') || link.target === '_blank') return;
            if (href.startsWith('http') && !href.includes(window.location.host)) return;

            bar.classList.remove('done');
            bar.style.width = '0%';
            // Force reflow
            void bar.offsetWidth;
            bar.style.width = '30%';

            setTimeout(() => { bar.style.width = '60%'; }, 150);
            setTimeout(() => { bar.style.width = '85%'; }, 400);
        });

        // Complete the bar when page finishes loading
        window.addEventListener('load', () => {
            bar.style.width = '100%';
            setTimeout(() => {
                bar.classList.add('done');
                setTimeout(() => { bar.style.width = '0'; bar.classList.remove('done'); }, 500);
            }, 200);
        });
    },

    // ── Ticker Tape ───────────────────────────────────────────────────
    setupTickerTape() {
        const contentArea = document.querySelector('.content-area');
        if (!contentArea) return;

        const tickers = [
            { label: 'NFL', team: 'KC Chiefs', odds: '-155', change: 'up' },
            { label: 'NBA', team: 'LAL vs BOS', odds: '+210', change: 'down' },
            { label: 'MLB', team: 'NYY', odds: '-130', change: 'up' },
            { label: 'NHL', team: 'TOR vs MTL', odds: '+145', change: 'up' },
            { label: 'NCAAF', team: 'Alabama', odds: '-180', change: 'down' },
            { label: 'NBA', team: 'GSW vs PHX', odds: '-110', change: 'up' },
            { label: 'NFL', team: 'SF 49ers', odds: '+125', change: 'down' },
            { label: 'MLB', team: 'LAD', odds: '-165', change: 'up' },
        ];

        const itemsHTML = tickers.map(t => `
            <span class="ticker-item">
                <strong>${t.label}</strong>
                <span class="ticker-sep">|</span>
                ${t.team}
                <span class="ticker-${t.change}">${t.change === 'up' ? '\u25B2' : '\u25BC'}</span>
                ${t.odds}
            </span>
        `).join('');

        const tape = document.createElement('div');
        tape.className = 'ticker-tape';
        tape.setAttribute('aria-hidden', 'true');
        tape.innerHTML = `<div class="ticker-track">${itemsHTML}${itemsHTML}</div>`;

        contentArea.insertBefore(tape, contentArea.firstChild);
    },

    // ── Animated Number Counter ───────────────────────────────────────
    animateCounters() {
        const statValues = document.querySelectorAll('.stat-value, .metric-value, .kpi-value');
        statValues.forEach(el => {
            const text = el.textContent.trim();
            const num = parseFloat(text.replace(/[^0-9.\-]/g, ''));
            if (isNaN(num) || num === 0) return;

            const prefix = text.match(/^[^0-9\-]*/)?.[0] || '';
            const suffix = text.match(/[^0-9.]*$/)?.[0] || '';
            const decimals = (text.split('.')[1] || '').replace(/[^0-9]/g, '').length;

            el.setAttribute('data-animate', 'true');
            el.classList.add('counting');
            const start = 0;
            const duration = 800;
            const startTime = performance.now();

            const update = (now) => {
                const elapsed = now - startTime;
                const progress = Math.min(elapsed / duration, 1);
                const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
                const current = start + (num - start) * eased;
                el.textContent = prefix + current.toFixed(decimals) + suffix;
                if (progress < 1) {
                    requestAnimationFrame(update);
                } else {
                    el.textContent = text; // restore original
                    el.classList.remove('counting');
                }
            };
            requestAnimationFrame(update);
        });
    },

    // ── SVG Path Drawing Animation ────────────────────────────────────
    animateChartPaths() {
        const charts = document.querySelectorAll('.lm-visual-chart svg');
        charts.forEach(svg => {
            const paths = svg.querySelectorAll('path[d]');
            const dots = svg.querySelectorAll('circle');

            paths.forEach(path => {
                const length = path.getTotalLength();
                path.classList.add('chart-line-animated');
                path.style.setProperty('--path-length', length);
                path.style.strokeDasharray = length;
                path.style.strokeDashoffset = length;
            });

            dots.forEach((dot, i) => {
                dot.classList.add('chart-dot-animated');
                dot.style.animationDelay = `${0.8 + i * 0.05}s`;
            });
        });
    },

    // ── Calculator Gauge Rendering ────────────────────────────────────
    renderGauge(containerId, value, max, label, colorStops) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const pct = Math.min(Math.max(value / max, 0), 1);
        const radius = 60;
        const circumference = Math.PI * radius; // half circle
        const offset = circumference * (1 - pct);

        // Color based on percentage
        let color = colorStops?.[0] || 'var(--accent-green)';
        if (colorStops) {
            if (pct < 0.33) color = colorStops[0];
            else if (pct < 0.66) color = colorStops[1];
            else color = colorStops[2];
        }

        container.innerHTML = `
            <div class="gauge-container">
                <svg class="gauge-svg" viewBox="0 0 160 100">
                    <path class="gauge-bg"
                        d="M 15 90 A 60 60 0 0 1 145 90"
                        stroke-dasharray="${circumference}"
                        stroke-dashoffset="0"/>
                    <path class="gauge-fill"
                        d="M 15 90 A 60 60 0 0 1 145 90"
                        stroke="${color}"
                        stroke-dasharray="${circumference}"
                        stroke-dashoffset="${offset}"
                        style="transition: stroke-dashoffset 1.2s cubic-bezier(0.4,0,0.2,1)"/>
                    <text class="gauge-value" x="80" y="82">${typeof value === 'number' ? value.toFixed(1) : value}</text>
                    <text class="gauge-label" x="80" y="96">${label}</text>
                </svg>
            </div>
        `;
    },

    // ── Onboarding Welcome ────────────────────────────────────────────
    showOnboarding() {
        if (localStorage.getItem('sba-onboarded')) return;

        const overlay = document.createElement('div');
        overlay.className = 'onboarding-overlay';
        overlay.innerHTML = `
            <div class="onboarding-card">
                <h2>Welcome to SBA Elite</h2>
                <p>Your premium sports betting analytics platform with ML-powered predictions and real-time edge detection.</p>
                <div class="onboarding-features">
                    <div class="onboarding-feature">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/></svg>
                        Edge Detection
                    </div>
                    <div class="onboarding-feature">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
                        Player Props
                    </div>
                    <div class="onboarding-feature">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                        Line Movement
                    </div>
                    <div class="onboarding-feature">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                        Live Feed
                    </div>
                </div>
                <button class="btn btn-primary" onclick="SBA.dismissOnboarding()" style="padding:12px 48px;font-size:15px;font-weight:700">
                    Get Started
                </button>
                <p style="font-size:11px;color:var(--text-tertiary);margin-top:16px;margin-bottom:0">Press <kbd style="background:var(--bg-tertiary);padding:2px 6px;border-radius:4px;font-size:10px">Ctrl+K</kbd> anytime for commands</p>
            </div>
        `;
        document.body.appendChild(overlay);
    },

    dismissOnboarding() {
        localStorage.setItem('sba-onboarded', '1');
        const overlay = document.querySelector('.onboarding-overlay');
        if (overlay) {
            overlay.style.opacity = '0';
            setTimeout(() => overlay.remove(), 500);
        }
    },

    // ── Enhanced Notification Bell ────────────────────────────────────
    ringBell() {
        const bell = document.getElementById('notification-bell');
        if (bell) {
            bell.classList.remove('has-alerts');
            void bell.offsetWidth;
            bell.classList.add('has-alerts');
        }
    },

    // ── 3D Card Tilt Effect ───────────────────────────────────────────
    setup3DCardTilt() {
        const cards = document.querySelectorAll('.stat-card, .quick-action-card');
        cards.forEach(card => {
            card.addEventListener('mousemove', (e) => {
                const rect = card.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                const centerX = rect.width / 2;
                const centerY = rect.height / 2;
                const rotateX = ((y - centerY) / centerY) * -4;
                const rotateY = ((x - centerX) / centerX) * 4;
                card.style.transform = `perspective(800px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-2px)`;
            });
            card.addEventListener('mouseleave', () => {
                card.style.transform = '';
            });
        });
    },

    // ── Ripple Effect on Buttons ──────────────────────────────────────
    setupRippleEffect() {
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('.btn');
            if (!btn) return;
            const rect = btn.getBoundingClientRect();
            const ripple = document.createElement('span');
            ripple.className = 'ripple';
            const size = Math.max(rect.width, rect.height);
            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
            ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
            btn.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        });
    },

    // ── Confetti Celebration ──────────────────────────────────────────
    showConfetti() {
        const container = document.createElement('div');
        container.className = 'confetti-container';
        const colors = ['#00e68a', '#5b9aff', '#ffc234', '#a855f7', '#22d3ee', '#ff4d6a'];

        for (let i = 0; i < 50; i++) {
            const piece = document.createElement('div');
            piece.className = 'confetti-piece';
            piece.style.left = Math.random() * 100 + '%';
            piece.style.background = colors[Math.floor(Math.random() * colors.length)];
            piece.style.setProperty('--drift', (Math.random() - 0.5) * 200 + 'px');
            piece.style.setProperty('--spin', Math.random() * 1440 + 'deg');
            piece.style.animationDelay = Math.random() * 0.5 + 's';
            piece.style.animationDuration = (2 + Math.random() * 2) + 's';
            piece.style.width = (6 + Math.random() * 8) + 'px';
            piece.style.height = (6 + Math.random() * 8) + 'px';
            container.appendChild(piece);
        }

        document.body.appendChild(container);
        setTimeout(() => container.remove(), 4000);
    },

    // ── Override settleBet for win celebration ────────────────────────
    settleBetWithEffect(betId, status, profitLoss) {
        this.settleBet(betId, status, profitLoss);
        if (status === 'won') {
            this.showConfetti();
        }
    },

    // ── Floating Particles ───────────────────────────────────────────
    setupParticles() {
        const colors = ['rgba(0, 230, 138, 0.4)', 'rgba(91, 154, 255, 0.3)', 'rgba(168, 85, 247, 0.2)'];
        for (let i = 0; i < 8; i++) {
            const p = document.createElement('div');
            p.className = 'particle';
            p.style.left = Math.random() * 100 + '%';
            p.style.background = colors[Math.floor(Math.random() * colors.length)];
            p.style.setProperty('--duration', (15 + Math.random() * 25) + 's');
            p.style.setProperty('--drift', (Math.random() - 0.5) * 200 + 'px');
            p.style.setProperty('--max-opacity', (0.1 + Math.random() * 0.2).toString());
            p.style.animationDelay = Math.random() * 20 + 's';
            p.style.width = (2 + Math.random() * 4) + 'px';
            p.style.height = p.style.width;
            document.body.appendChild(p);
        }
    },

    // ── Scroll Progress Bar ──────────────────────────────────────────
    setupScrollProgressBar() {
        const bar = document.createElement('div');
        bar.className = 'scroll-progress-bar';
        document.body.appendChild(bar);

        const contentArea = document.querySelector('.content-area');
        if (!contentArea) return;

        const mainContent = document.querySelector('.main-content');
        if (!mainContent) return;

        mainContent.addEventListener('scroll', () => {
            const scrollTop = mainContent.scrollTop;
            const scrollHeight = mainContent.scrollHeight - mainContent.clientHeight;
            const progress = scrollHeight > 0 ? (scrollTop / scrollHeight) * 100 : 0;
            bar.style.width = progress + '%';
        });

        // Also handle window scroll
        window.addEventListener('scroll', () => {
            const scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
            const scrollHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight;
            const progress = scrollHeight > 0 ? (scrollTop / scrollHeight) * 100 : 0;
            bar.style.width = progress + '%';
        });
    },

    // ── Enhanced Reveal Animations (v2) ──────────────────────────────
    setupRevealAnimationsV2() {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('revealed');
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

        document.querySelectorAll('.card, .stat-card, .step-card').forEach((el, i) => {
            el.classList.add('reveal-up');
            el.style.transitionDelay = `${i * 0.05}s`;
            observer.observe(el);
        });
    },

    // ── Enhanced Odds Comparison with Heat Colors ────────────────────
    applyOddsHeatMap() {
        const tables = document.querySelectorAll('.data-table');
        tables.forEach(table => {
            const rows = table.querySelectorAll('tbody tr');
            if (rows.length === 0) return;

            rows.forEach(row => {
                const cells = row.querySelectorAll('td .odds-badge');
                if (cells.length < 2) return;

                const values = Array.from(cells).map(cell => {
                    const text = cell.textContent.trim().replace('+', '');
                    return parseFloat(text) || 0;
                });

                const max = Math.max(...values);
                const min = Math.min(...values);
                const range = max - min;
                if (range === 0) return;

                cells.forEach((cell, idx) => {
                    const v = values[idx];
                    const pct = (v - min) / range;
                    if (pct === 1) cell.closest('td').classList.add('odds-heat-best');
                    else if (pct > 0.7) cell.closest('td').classList.add('odds-heat-good');
                    else if (pct > 0.3) cell.closest('td').classList.add('odds-heat-mid');
                    else cell.closest('td').classList.add('odds-heat-worst');
                });
            });
        });
    },
};

// ── v4.0: Cursor Spotlight ─────────────────────────────────────
function setupCursorSpotlight() {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (window.innerWidth < 768) return;

    const spotlight = document.createElement('div');
    spotlight.className = 'cursor-spotlight';
    document.body.appendChild(spotlight);

    let ticking = false;
    document.addEventListener('mousemove', (e) => {
        if (!ticking) {
            requestAnimationFrame(() => {
                spotlight.style.left = e.clientX + 'px';
                spotlight.style.top = e.clientY + 'px';
                ticking = false;
            });
            ticking = true;
        }
    });

    document.addEventListener('mouseleave', () => { spotlight.style.opacity = '0'; });
    document.addEventListener('mouseenter', () => { spotlight.style.opacity = '1'; });
}

// ── v4.0: Scroll Progress Bar ──────────────────────────────────
function setupScrollProgressBarV2() {
    const bar = document.getElementById('scroll-progress-bar');
    if (!bar) return;

    const contentArea = document.querySelector('.content-area');
    if (!contentArea) return;

    let ticking = false;
    contentArea.addEventListener('scroll', () => {
        if (!ticking) {
            requestAnimationFrame(() => {
                const scrollTop = contentArea.scrollTop;
                const scrollHeight = contentArea.scrollHeight - contentArea.clientHeight;
                const pct = scrollHeight > 0 ? (scrollTop / scrollHeight) * 100 : 0;
                bar.style.width = pct + '%';
                ticking = false;
            });
            ticking = true;
        }
    });
}

// ── v4.0: Enhanced Reveal Animations ───────────────────────────
function setupRevealAnimationsV2() {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        document.querySelectorAll('.reveal-up, .reveal-left, .reveal-scale').forEach(el => {
            el.classList.add('revealed');
        });
        return;
    }

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const delay = entry.target.style.animationDelay || '0s';
                const ms = parseFloat(delay) * 1000;
                setTimeout(() => {
                    entry.target.classList.add('revealed');
                }, ms);
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1, rootMargin: '0px 0px -30px 0px' });

    document.querySelectorAll('.reveal-up, .reveal-left, .reveal-scale').forEach(el => {
        observer.observe(el);
    });
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    SBA.init();
    SBA.setupScrollProgress();
    SBA.setupFAB();
    SBA.setupProgressBar();
    SBA.setupTickerTape();
    SBA.setupRippleEffect();
    SBA.setupScrollProgressBar();

    // v4.0 enhancements
    setupCursorSpotlight();
    setupScrollProgressBarV2();

    // Setup reveal animations after a brief delay
    setTimeout(() => {
        setupRevealAnimationsV2();
        SBA.setup3DCardTilt();
        SBA.setupParticles();
    }, 100);

    // Animate counters, chart paths, and apply heat colors after content loads
    setTimeout(() => {
        SBA.animateCounters();
        SBA.animateChartPaths();
        SBA.applyOddsHeatMap();
    }, 300);

    // Show onboarding for first-time users
    setTimeout(() => SBA.showOnboarding(), 800);
});

// Make globally accessible
window.SBA = SBA;
