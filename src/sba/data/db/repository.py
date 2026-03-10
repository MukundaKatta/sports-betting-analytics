"""Database CRUD operations."""

from __future__ import annotations

import json
from datetime import date, datetime

from sba.models.domain import (
    Event,
    EventOdds,
    OddsSnapshot,
    Player,
    PlayerGameLog,
    TrackedBet,
)


class Repository:

    # --- Events ---

    def upsert_event(self, conn, event: Event):
        conn.execute(
            """INSERT INTO events (id, sport, home_team, away_team, commence_time, completed, home_score, away_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 completed=excluded.completed,
                 home_score=excluded.home_score,
                 away_score=excluded.away_score""",
            (event.id, event.sport, event.home_team, event.away_team,
             event.commence_time.isoformat(), int(event.completed),
             event.home_score, event.away_score),
        )

    def get_event(self, conn, event_id: str) -> Event | None:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return self._row_to_event(row) if row else None

    def get_upcoming_events(self, conn, sport: str) -> list[Event]:
        rows = conn.execute(
            "SELECT * FROM events WHERE sport = ? AND completed = 0 ORDER BY commence_time",
            (sport,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    # --- Odds ---

    def insert_odds_snapshot(self, conn, snapshot: OddsSnapshot):
        conn.execute(
            """INSERT INTO odds_snapshots
               (event_id, bookmaker, market, outcome_name, outcome_point, price_american, price_decimal)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (snapshot.event_id, snapshot.bookmaker, snapshot.market,
             snapshot.outcome_name, snapshot.outcome_point,
             snapshot.price_american, snapshot.price_decimal),
        )

    def store_event_odds(self, conn, events_odds: list[EventOdds]):
        """Store events and all their odds snapshots in one call."""
        for eo in events_odds:
            self.upsert_event(conn, eo.event)
            for bm in eo.bookmakers:
                for outcome in bm.outcomes:
                    self.insert_odds_snapshot(conn, OddsSnapshot(
                        event_id=eo.event.id,
                        bookmaker=bm.bookmaker,
                        market=bm.market,
                        outcome_name=outcome.name,
                        outcome_point=outcome.point,
                        price_american=outcome.price_american,
                        price_decimal=outcome.price_decimal,
                    ))

    def get_latest_odds(self, conn, event_id: str, market: str) -> list[OddsSnapshot]:
        rows = conn.execute(
            """SELECT * FROM odds_snapshots
               WHERE event_id = ? AND market = ?
               AND snapshot_time = (
                   SELECT MAX(snapshot_time) FROM odds_snapshots
                   WHERE event_id = ? AND market = ?
               )
               ORDER BY bookmaker, outcome_name""",
            (event_id, market, event_id, market),
        ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def get_closing_odds(self, conn, event_id: str, market: str,
                         outcome_name: str) -> OddsSnapshot | None:
        """Get the last odds snapshot before the event's commence_time.

        This represents the closing line for a given outcome.
        """
        row = conn.execute(
            """SELECT os.* FROM odds_snapshots os
               JOIN events e ON os.event_id = e.id
               WHERE os.event_id = ?
                 AND os.market = ?
                 AND os.outcome_name = ?
                 AND os.snapshot_time <= e.commence_time
               ORDER BY os.snapshot_time DESC
               LIMIT 1""",
            (event_id, market, outcome_name),
        ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def get_odds_history(self, conn, event_id: str, market: str) -> list[OddsSnapshot]:
        rows = conn.execute(
            """SELECT * FROM odds_snapshots
               WHERE event_id = ? AND market = ?
               ORDER BY snapshot_time""",
            (event_id, market),
        ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    # --- Players ---

    def upsert_player(self, conn, player: Player):
        conn.execute(
            """INSERT INTO players (id, name, team, position, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, team=excluded.team,
                 position=excluded.position, updated_at=CURRENT_TIMESTAMP""",
            (player.id, player.name, player.team, player.position),
        )

    def get_player_by_name(self, conn, name: str) -> Player | None:
        row = conn.execute(
            "SELECT * FROM players WHERE LOWER(name) LIKE LOWER(?)", (f"%{name}%",)
        ).fetchone()
        return Player(id=row["id"], name=row["name"], team=row["team"] or "",
                      position=row["position"] or "") if row else None

    # --- Player Game Logs ---

    def insert_game_log(self, conn, log: PlayerGameLog):
        conn.execute(
            """INSERT OR IGNORE INTO player_game_logs
               (player_id, game_date, opponent, home_away, minutes,
                points, rebounds, assists, threes, steals, blocks, turnovers,
                fga, fgm, fta, ftm, plus_minus)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (log.player_id, log.game_date.isoformat(), log.opponent, log.home_away,
             log.minutes, log.points, log.rebounds, log.assists, log.threes,
             log.steals, log.blocks, log.turnovers, log.fga, log.fgm,
             log.fta, log.ftm, log.plus_minus),
        )

    def get_player_logs(self, conn, player_id: int, last_n: int | None = None) -> list[PlayerGameLog]:
        query = """SELECT * FROM player_game_logs
                   WHERE player_id = ? ORDER BY game_date DESC"""
        params: list = [player_id]
        if last_n:
            query += " LIMIT ?"
            params.append(int(last_n))
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_game_log(r) for r in rows]

    # --- Bets ---

    def insert_bet(self, conn, bet: TrackedBet) -> int:
        cursor = conn.execute(
            """INSERT INTO bets
               (event_id, market, selection, line, odds_american, odds_decimal,
                model_probability, expected_value, kelly_fraction, recommended_stake, bookmaker)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bet.event_id, bet.market, bet.selection, bet.line,
             bet.odds_american, bet.odds_decimal, bet.model_probability,
             bet.expected_value, bet.kelly_fraction, bet.recommended_stake,
             bet.bookmaker),
        )
        return cursor.lastrowid

    def update_bet_result(self, conn, bet_id: int, status: str, profit_loss: float):
        conn.execute(
            "UPDATE bets SET status = ?, profit_loss = ?, settled_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, profit_loss, bet_id),
        )

    def settle_bet(self, conn, bet_id: int, result: str) -> TrackedBet | None:
        """Settle a bet as won, lost, or push from CLI.

        Args:
            bet_id: The bet ID.
            result: One of 'won', 'lost', 'push'.

        Returns:
            The updated TrackedBet, or None if not found.
        """
        result = result.lower().strip()
        if result not in ("won", "lost", "push"):
            raise ValueError(f"Invalid result '{result}', must be 'won', 'lost', or 'push'")

        row = conn.execute("SELECT * FROM bets WHERE id = ?", (bet_id,)).fetchone()
        if not row:
            return None

        bet = self._row_to_bet(row)
        if result == "won":
            profit_loss = bet.recommended_stake * (bet.odds_decimal - 1)
        elif result == "lost":
            profit_loss = -bet.recommended_stake
        else:  # push
            profit_loss = 0.0

        self.update_bet_result(conn, bet_id, result, profit_loss)
        conn.commit()

        # Return the updated bet
        updated_row = conn.execute("SELECT * FROM bets WHERE id = ?", (bet_id,)).fetchone()
        return self._row_to_bet(updated_row)

    def get_bet_by_id(self, conn, bet_id: int) -> TrackedBet | None:
        row = conn.execute("SELECT * FROM bets WHERE id = ?", (bet_id,)).fetchone()
        return self._row_to_bet(row) if row else None

    def get_pending_bets(self, conn) -> list[TrackedBet]:
        rows = conn.execute(
            "SELECT * FROM bets WHERE status = 'pending' ORDER BY placed_at"
        ).fetchall()
        return [self._row_to_bet(r) for r in rows]

    def get_bet_history(self, conn, sport: str | None = None) -> list[TrackedBet]:
        query = "SELECT * FROM bets ORDER BY placed_at DESC"
        rows = conn.execute(query).fetchall()
        return [self._row_to_bet(r) for r in rows]

    # --- Model Versions ---

    def save_model_version(self, conn, model_type: str, sport: str, version: str,
                           metrics: dict, file_path: str):
        # Deactivate old versions
        conn.execute(
            "UPDATE model_versions SET is_active = 0 WHERE model_type = ? AND sport = ?",
            (model_type, sport),
        )
        conn.execute(
            """INSERT INTO model_versions (model_type, sport, version, metrics, file_path, is_active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (model_type, sport, version, json.dumps(metrics), file_path),
        )

    def get_active_model(self, conn, model_type: str, sport: str) -> dict | None:
        row = conn.execute(
            "SELECT * FROM model_versions WHERE model_type = ? AND sport = ? AND is_active = 1",
            (model_type, sport),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "model_type": row["model_type"], "sport": row["sport"],
            "version": row["version"], "metrics": json.loads(row["metrics"] or "{}"),
            "file_path": row["file_path"],
        }

    # --- Row converters ---

    def _row_to_event(self, row) -> Event:
        return Event(
            id=row["id"], sport=row["sport"],
            home_team=row["home_team"], away_team=row["away_team"],
            commence_time=datetime.fromisoformat(row["commence_time"]),
            completed=bool(row["completed"]),
            home_score=row["home_score"], away_score=row["away_score"],
        )

    def _row_to_snapshot(self, row) -> OddsSnapshot:
        return OddsSnapshot(
            id=row["id"], event_id=row["event_id"], bookmaker=row["bookmaker"],
            market=row["market"], outcome_name=row["outcome_name"],
            outcome_point=row["outcome_point"],
            price_american=row["price_american"], price_decimal=row["price_decimal"],
            snapshot_time=datetime.fromisoformat(row["snapshot_time"]) if row["snapshot_time"] else None,
        )

    def _row_to_game_log(self, row) -> PlayerGameLog:
        return PlayerGameLog(
            player_id=row["player_id"],
            game_date=date.fromisoformat(row["game_date"]),
            opponent=row["opponent"] or "", home_away=row["home_away"] or "",
            minutes=row["minutes"] or 0, points=row["points"] or 0,
            rebounds=row["rebounds"] or 0, assists=row["assists"] or 0,
            threes=row["threes"] or 0, steals=row["steals"] or 0,
            blocks=row["blocks"] or 0, turnovers=row["turnovers"] or 0,
            fga=row["fga"] or 0, fgm=row["fgm"] or 0,
            fta=row["fta"] or 0, ftm=row["ftm"] or 0,
            plus_minus=row["plus_minus"] or 0,
        )

    def _row_to_bet(self, row) -> TrackedBet:
        return TrackedBet(
            id=row["id"], event_id=row["event_id"], market=row["market"],
            selection=row["selection"], line=row["line"],
            odds_american=row["odds_american"], odds_decimal=row["odds_decimal"],
            model_probability=row["model_probability"],
            expected_value=row["expected_value"],
            kelly_fraction=row["kelly_fraction"],
            recommended_stake=row["recommended_stake"],
            bookmaker=row["bookmaker"], status=row["status"],
            profit_loss=row["profit_loss"] or 0,
            placed_at=datetime.fromisoformat(row["placed_at"]) if row["placed_at"] else None,
            settled_at=datetime.fromisoformat(row["settled_at"]) if row["settled_at"] else None,
        )
