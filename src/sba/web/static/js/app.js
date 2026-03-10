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
        this.setupClock();
        this.setupSearch();
        this.setupKeyboardShortcuts();
        this.updateStatus();
        this.highlightActiveNav();
        setInterval(() => this.updateStatus(), 60000);
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
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
            const href = link.getAttribute('href');
            if (path === href || (path === '/' && href === '/')) {
                link.classList.add('active');
            }
        });
    },

    // ── Keyboard Shortcuts ────────────────────────────────────────────
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Don't fire shortcuts when typing in inputs
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

            switch(e.key) {
                case '/':
                    e.preventDefault();
                    document.getElementById('player-search')?.focus();
                    break;
                case 'b':
                    this.toggleSlip();
                    break;
                case 'Escape':
                    document.getElementById('bet-slip')?.classList.remove('open');
                    document.getElementById('player-search')?.blur();
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
            const resp = await fetch(`/api/players/${encodeURIComponent(query)}`);
            if (resp.ok) {
                const player = await resp.json();
                results.innerHTML = `
                    <a class="search-result-item" href="/player/${encodeURIComponent(player.name)}">
                        <span>${player.name}</span>
                        <span class="text-dim">${player.team} · ${player.position}</span>
                    </a>`;
                results.classList.add('active');
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

            if (edges.length === 0) {
                container.innerHTML = `<tr><td colspan="11" class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
                    <p>No +EV opportunities found right now. Try adjusting filters or check back later.</p>
                </td></tr>`;
                return;
            }

            container.innerHTML = edges.map((e, i) => `
                <tr class="new-row" style="animation-delay:${i * 0.03}s">
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
                    <td class="right"><span class="ev-badge ${e.ev >= 0.08 ? 'high' : e.ev >= 0.04 ? 'medium' : 'low'}">${e.ev_pct}</span></td>
                    <td class="right font-mono">${(e.kelly_pct * 100).toFixed(1)}%</td>
                    <td class="right font-bold text-green">$${e.recommended_stake.toFixed(0)}</td>
                    <td class="center"><span class="confidence-badge ${e.confidence}">${e.confidence}</span></td>
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
                        <button class="btn btn-sm" style="background:var(--accent-green-dim);color:var(--accent-green);padding:4px 8px;font-size:10px" onclick="SBA.settleBet(${b.id}, 'won', ${payout.toFixed(2)})">Won</button>
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

        // Load recent bets summary
        try {
            const resp = await fetch('/api/bets');
            const bets = await resp.json();
            const betEl = document.getElementById('dashboard-bets');
            if (betEl) {
                if (bets.total_bets === 0 && bets.pending === 0) {
                    betEl.innerHTML = `<div class="empty-state" style="padding:40px 20px">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="36" height="36"><rect x="2" y="3" width="20" height="18" rx="2"/><line x1="2" y1="9" x2="22" y2="9"/></svg>
                        <p>No bets tracked yet</p>
                    </div>`;
                } else {
                    const plColor = bets.total_profit >= 0 ? 'text-green' : 'text-red';
                    const roiColor = bets.roi >= 0 ? 'text-green' : 'text-red';
                    betEl.innerHTML = `
                        <div style="padding:24px;display:grid;grid-template-columns:repeat(4,1fr);gap:16px;text-align:center">
                            <div>
                                <div class="stat-value ${plColor}" style="font-size:22px">$${bets.total_profit >= 0 ? '+' : ''}${bets.total_profit.toFixed(2)}</div>
                                <div class="stat-label" style="margin-top:6px">Total P/L</div>
                            </div>
                            <div>
                                <div class="stat-value" style="font-size:22px">${(bets.win_rate * 100).toFixed(0)}%</div>
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

            // Summary stats
            const summary = document.getElementById('analytics-summary');
            if (summary) {
                const streakIcon = analytics.streak.type === 'won' ? '&#9650;' : analytics.streak.type === 'lost' ? '&#9660;' : '—';
                const streakColor = analytics.streak.type === 'won' ? 'text-green' : analytics.streak.type === 'lost' ? 'text-red' : '';
                summary.innerHTML = `
                    <div class="stat-card green">
                        <div class="stat-label">Total P/L</div>
                        <div class="stat-value ${bets.total_profit >= 0 ? 'text-green' : 'text-red'}">$${bets.total_profit >= 0 ? '+' : ''}${bets.total_profit.toFixed(2)}</div>
                        <div class="stat-sub">${bets.total_bets} settled bets</div>
                    </div>
                    <div class="stat-card blue">
                        <div class="stat-label">Win Rate</div>
                        <div class="stat-value">${(bets.win_rate * 100).toFixed(1)}%</div>
                        <div class="stat-sub">${bets.wins}W - ${bets.losses}L - ${bets.pushes}P</div>
                        <div class="progress-bar"><div class="progress-fill green" style="width:${bets.win_rate * 100}%"></div></div>
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
                    marketEl.innerHTML = `
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

            // Bankroll settings
            const bankrollEl = document.getElementById('bankroll-settings');
            if (bankrollEl) {
                bankrollEl.innerHTML = `
                    <div style="display:grid;gap:16px">
                        <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid var(--border-light)">
                            <div><div class="font-bold">Bankroll</div><div class="text-dim" style="font-size:12px">Total bankroll for Kelly criterion sizing</div></div>
                            <div class="font-mono font-bold text-green" style="font-size:18px">$${settings.bankroll.toLocaleString()}</div>
                        </div>
                        <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid var(--border-light)">
                            <div><div class="font-bold">Kelly Fraction</div><div class="text-dim" style="font-size:12px">Fractional Kelly multiplier (1.0 = full Kelly)</div></div>
                            <div class="font-mono font-bold" style="font-size:18px">${settings.kelly_fraction}</div>
                        </div>
                        <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid var(--border-light)">
                            <div><div class="font-bold">EV Threshold</div><div class="text-dim" style="font-size:12px">Minimum expected value to flag as +EV</div></div>
                            <div class="font-mono font-bold" style="font-size:18px">${(settings.ev_threshold * 100).toFixed(1)}%</div>
                        </div>
                        <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0">
                            <div><div class="font-bold">Default Sport</div><div class="text-dim" style="font-size:12px">Primary sport for scanning</div></div>
                            <span class="market-tag">${settings.default_sport}</span>
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
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => SBA.init());

// Make globally accessible
window.SBA = SBA;
