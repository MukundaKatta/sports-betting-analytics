/* ═══════════════════════════════════════════════════════════════════════
   SBA — Sports Betting Analytics — Frontend Application
   ═══════════════════════════════════════════════════════════════════════ */

const SBA = {
    betSlip: [],
    refreshTimer: null,

    // ── Initialization ────────────────────────────────────────────────
    init() {
        this.setupClock();
        this.setupSearch();
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

            if (countEl) countEl.textContent = edges.length;

            if (edges.length === 0) {
                container.innerHTML = '<tr><td colspan="11" class="empty-state"><p>No +EV opportunities found right now. Try adjusting filters or check back later.</p></td></tr>';
                return;
            }

            container.innerHTML = edges.map(e => `
                <tr>
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
                              onclick="SBA.addToSlip('${e.event_id}', '${e.selection}', ${e.best_odds_american}, '${e.market}', '${e.bookmaker}', '${e.event_away} @ ${e.event_home}', ${e.recommended_stake})">
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
                container.innerHTML = '<tr><td colspan="10" class="empty-state"><p>No +EV props found. Models need player data — run backfill first.</p></td></tr>';
                return;
            }

            container.innerHTML = props.map(p => {
                const recClass = p.recommendation.includes('OVER') ? 'over' : p.recommendation.includes('UNDER') ? 'under' : 'pass';
                const overEv = (p.over_ev * 100).toFixed(1);
                const underEv = (p.under_ev * 100).toFixed(1);
                return `
                <tr>
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

            // Summary cards
            summary.innerHTML = `
                <div class="stat-card green">
                    <div class="stat-label">Total P/L</div>
                    <div class="stat-value ${data.total_profit >= 0 ? 'text-green' : 'text-red'}">$${data.total_profit >= 0 ? '+' : ''}${data.total_profit.toFixed(2)}</div>
                    <div class="stat-sub">ROI: ${data.roi >= 0 ? '+' : ''}${data.roi.toFixed(1)}%</div>
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
                tableBody.innerHTML = '<tr><td colspan="8" class="empty-state"><p>No bets tracked yet. Add bets from the Edge Finder or Props page.</p></td></tr>';
                return;
            }

            tableBody.innerHTML = data.bets.map(b => {
                const statusClass = b.status === 'won' ? 'text-green' : b.status === 'lost' ? 'text-red' : b.status === 'push' ? 'text-yellow' : 'text-blue';
                return `
                <tr>
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
                </tr>`;
            }).join('');
        } catch (err) {
            tableBody.innerHTML = `<tr><td colspan="8" class="empty-state text-red">Error loading bets</td></tr>`;
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
                container.innerHTML = `<div class="empty-state"><p>Player "${name}" not found. Run <code>sba data backfill --player "${name}"</code> to import their stats.</p></div>`;
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
                        return `
                        <div class="stat-card ${trendColor}">
                            <div class="stat-label">${stat}</div>
                            <div class="stat-value">${l5}</div>
                            <div class="stat-sub">Last 5 avg · Season: ${l20} ${trendStr ? `<span class="text-${trendColor}">(${trendStr})</span>` : ''}</div>
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
                                ${p.recent_games.map(g => `
                                <tr>
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
        // Load status
        try {
            const resp = await fetch('/api/status');
            const status = await resp.json();
            const statsEl = document.getElementById('dashboard-stats');
            if (statsEl) {
                statsEl.innerHTML = `
                    <div class="stat-card green">
                        <div class="stat-label">Events Tracked</div>
                        <div class="stat-value">${status.events}</div>
                        <div class="stat-sub">across all sports</div>
                    </div>
                    <div class="stat-card blue">
                        <div class="stat-label">Odds Snapshots</div>
                        <div class="stat-value">${status.odds_snapshots.toLocaleString()}</div>
                        <div class="stat-sub">historical data points</div>
                    </div>
                    <div class="stat-card yellow">
                        <div class="stat-label">Players</div>
                        <div class="stat-value">${status.players}</div>
                        <div class="stat-sub">with game logs</div>
                    </div>
                    <div class="stat-card purple">
                        <div class="stat-label">Game Logs</div>
                        <div class="stat-value">${status.game_logs.toLocaleString()}</div>
                        <div class="stat-sub">for ML training</div>
                    </div>
                `;
            }
        } catch {}

        // Load recent bets summary
        try {
            const resp = await fetch('/api/bets');
            const bets = await resp.json();
            const betEl = document.getElementById('dashboard-bets');
            if (betEl) {
                if (bets.total_bets === 0 && bets.pending === 0) {
                    betEl.innerHTML = '<div class="empty-state"><p>No bets tracked yet</p></div>';
                } else {
                    betEl.innerHTML = `
                        <div style="padding:20px;display:flex;justify-content:space-around;text-align:center">
                            <div>
                                <div class="stat-value ${bets.total_profit >= 0 ? 'text-green' : 'text-red'}" style="font-size:22px">$${bets.total_profit >= 0 ? '+' : ''}${bets.total_profit.toFixed(2)}</div>
                                <div class="stat-label">Total P/L</div>
                            </div>
                            <div>
                                <div class="stat-value" style="font-size:22px">${(bets.win_rate * 100).toFixed(0)}%</div>
                                <div class="stat-label">Win Rate</div>
                            </div>
                            <div>
                                <div class="stat-value" style="font-size:22px">${bets.total_bets + bets.pending}</div>
                                <div class="stat-label">Total Bets</div>
                            </div>
                            <div>
                                <div class="stat-value text-blue" style="font-size:22px">${bets.roi >= 0 ? '+' : ''}${bets.roi.toFixed(1)}%</div>
                                <div class="stat-label">ROI</div>
                            </div>
                        </div>
                    `;
                }
            }
        } catch {}
    },

    // ── Bet Slip ──────────────────────────────────────────────────────
    addToSlip(eventId, selection, odds, market, bookmaker, eventName, stake) {
        // Check if already in slip
        if (this.betSlip.find(b => b.eventId === eventId && b.selection === selection)) {
            this.toast('Already in bet slip', 'info');
            return;
        }

        this.betSlip.push({ eventId, selection, odds, market, bookmaker, eventName, stake: stake || 0 });
        this.renderSlip();
        this.toast(`${selection} added to slip`, 'success');

        // Open slip
        document.getElementById('bet-slip').classList.add('open');
    },

    removeFromSlip(index) {
        this.betSlip.splice(index, 1);
        this.renderSlip();
    },

    clearSlip() {
        this.betSlip = [];
        this.renderSlip();
        document.getElementById('bet-slip').classList.remove('open');
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
                </div>`;
            footer.style.display = 'none';
            return;
        }

        footer.style.display = 'flex';
        body.innerHTML = this.betSlip.map((b, i) => `
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
                               onchange="SBA.betSlip[${i}].stake = parseFloat(this.value) || 0">
                    </div>
                </div>
            </div>
        `).join('');
    },

    async placeBets() {
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

    // ── Toasts ────────────────────────────────────────────────────────
    toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 4000);
    },

    // ── Toggle Bet Slip ───────────────────────────────────────────────
    toggleSlip() {
        document.getElementById('bet-slip').classList.toggle('open');
    },
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => SBA.init());

// Make globally accessible
window.SBA = SBA;
