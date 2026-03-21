"""
LeaderboardBuilder — calculates per-agent performance stats and writes
them to Google Sheets (Leaderboard + Live Signals worksheets).

Stats calculated per agent:
  - Total signals, winning/losing counts, win rate
  - Average PNL at current time
  - Average PNL at 1h, 4h, 24h, 7d (from snapshots)
  - Best / worst trade
  - Streak info (current consecutive wins/losses)
  - Last signal timestamp

The leaderboard is written to two worksheets:
  - 🏆 Leaderboard  — one row per agent, ranked by overall performance
  - 📊 Live Signals — every active signal with current PNL
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from apexbt.config.config import config
from apexbt.leaderboard.signals import SignalRecorder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limiter for Sheets API (60 req/min quota)
# ---------------------------------------------------------------------------

class _SheetRateLimiter:
    def __init__(self, max_per_minute: int = 45):
        self.max = max_per_minute
        self.timestamps: list[float] = []

    def wait(self):
        now = time.time()
        self.timestamps = [t for t in self.timestamps if now - t < 60]
        if len(self.timestamps) >= self.max:
            sleep_for = 60 - (now - self.timestamps[0]) + 0.5
            if sleep_for > 0:
                logger.debug(f"Sheets rate limit — sleeping {sleep_for:.1f}s")
                time.sleep(sleep_for)
        self.timestamps.append(time.time())


_rl = _SheetRateLimiter()


# ---------------------------------------------------------------------------
# Helper to safely format numbers
# ---------------------------------------------------------------------------

def _fmt_price(val) -> str:
    if val is None:
        return ""
    v = float(val)
    if v == 0:
        return "$0"
    if abs(v) >= 1:
        return f"${v:,.4f}"
    # small decimals — show enough sig figs
    return f"${v:.8g}"


def _fmt_pct(val) -> str:
    if val is None:
        return ""
    return f"{float(val):+.2f}%"


def _fmt_mc(val) -> str:
    if val is None or float(val) == 0:
        return ""
    v = float(val)
    if v >= 1_000_000_000:
        return f"${v / 1e9:.2f}B"
    if v >= 1_000_000:
        return f"${v / 1e6:.2f}M"
    if v >= 1_000:
        return f"${v / 1e3:.1f}K"
    return f"${v:.0f}"


def _fmt_time(dt) -> str:
    if dt is None:
        return ""
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _time_ago(dt) -> str:
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"{int(delta.total_seconds() / 60)}m ago"
    if hours < 24:
        return f"{hours:.1f}h ago"
    days = hours / 24
    return f"{days:.1f}d ago"


# ---------------------------------------------------------------------------
# LeaderboardBuilder
# ---------------------------------------------------------------------------

class LeaderboardBuilder:
    """
    Calculates agent performance stats from the signals DB and writes
    the results to Google Sheets.
    """

    LEADERBOARD_HEADERS = [
        "Rank",
        "Agent",
        "Signals",
        "Win Rate",
        "Avg PNL",
        "Avg PNL (1h)",
        "Avg PNL (24h)",
        "Avg PNL (7d)",
        "Wins",
        "Losses",
        "Best Trade",
        "Best PNL",
        "Worst Trade",
        "Worst PNL",
        "Last Signal",
        "Updated",
    ]

    LIVE_SIGNALS_HEADERS = [
        "Agent",
        "Ticker",
        "Chain",
        "Entry Price",
        "Current Price",
        "PNL %",
        "Market Cap",
        "Volume 24h",
        "Signal Time",
        "Age",
        "Sentiment",
        "Contract",
        "Tweet",
    ]

    def __init__(self):
        self.recorder = SignalRecorder()
        self._sheets_client: Optional[gspread.Client] = None
        self._spreadsheet: Optional[gspread.Spreadsheet] = None

    # ------------------------------------------------------------------
    # Google Sheets connection
    # ------------------------------------------------------------------

    def _connect_sheets(self):
        """Authenticate and open the spreadsheet (lazy, cached)."""
        if self._spreadsheet is not None:
            return self._spreadsheet

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            config.SHEETS_CREDENTIALS, scope
        )
        self._sheets_client = gspread.authorize(creds)

        spreadsheet_id = getattr(config, "SPREADSHEET_ID", "")
        if spreadsheet_id:
            self._spreadsheet = self._sheets_client.open_by_key(spreadsheet_id)
        else:
            self._spreadsheet = self._sheets_client.open(config.SPREADSHEET_NAME)

        return self._spreadsheet

    def _get_or_create_worksheet(
        self, name: str, rows: int = 1000, cols: int = 20
    ) -> gspread.Worksheet:
        """Get a worksheet by name, creating it if it doesn't exist."""
        spreadsheet = self._connect_sheets()
        _rl.wait()
        try:
            return spreadsheet.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            _rl.wait()
            ws = spreadsheet.add_worksheet(name, rows, cols)
            logger.info(f"Created worksheet: {name}")
            return ws

    def _write_headers(self, ws: gspread.Worksheet, headers: list[str]):
        """Write headers to row 1 if they differ."""
        _rl.wait()
        existing = ws.row_values(1)
        if existing != headers:
            _rl.wait()
            ws.update("A1", [headers], value_input_option="RAW")

    # ------------------------------------------------------------------
    # Stats calculation
    # ------------------------------------------------------------------

    def calculate_agent_stats(self) -> list[dict]:
        """
        Calculate performance stats for every agent that has signals.

        Returns a list of dicts sorted by score (win_rate * avg_pnl), descending.
        """
        agents = self.recorder.get_all_agents()
        if not agents:
            return []

        stats_list = []

        for agent in agents:
            signals = self.recorder.get_signals_by_agent(agent)
            if not signals:
                continue

            total = len(signals)
            winners = [s for s in signals if s.get("pnl_percent") and float(s["pnl_percent"]) > 0]
            losers = [s for s in signals if s.get("pnl_percent") and float(s["pnl_percent"]) <= 0]
            win_count = len(winners)
            lose_count = len(losers)
            win_rate = (win_count / total * 100) if total > 0 else 0

            pnls = [float(s["pnl_percent"]) for s in signals if s.get("pnl_percent") is not None]
            avg_pnl = sum(pnls) / len(pnls) if pnls else 0

            # Best / worst trade
            best = max(signals, key=lambda s: float(s.get("pnl_percent") or 0))
            worst = min(signals, key=lambda s: float(s.get("pnl_percent") or 0))

            # Time-bucketed avg PNL from snapshots
            avg_1h = self._avg_pnl_at_hours(agent, 1)
            avg_24h = self._avg_pnl_at_hours(agent, 24)
            avg_7d = self._avg_pnl_at_hours(agent, 168)

            # Last signal time
            last_signal = max(signals, key=lambda s: s.get("entry_time") or datetime.min)

            # Composite score for ranking: weighted combination
            # Higher win rate + higher avg PNL = better rank
            score = (win_rate * 0.4) + (avg_pnl * 0.6) if total >= 1 else 0

            stats_list.append({
                "agent": agent,
                "total_signals": total,
                "win_count": win_count,
                "lose_count": lose_count,
                "win_rate": win_rate,
                "avg_pnl": avg_pnl,
                "avg_pnl_1h": avg_1h,
                "avg_pnl_24h": avg_24h,
                "avg_pnl_7d": avg_7d,
                "best_ticker": best.get("ticker", ""),
                "best_pnl": float(best.get("pnl_percent") or 0),
                "worst_ticker": worst.get("ticker", ""),
                "worst_pnl": float(worst.get("pnl_percent") or 0),
                "last_signal_time": last_signal.get("entry_time"),
                "score": score,
            })

        # Sort by composite score descending
        stats_list.sort(key=lambda s: s["score"], reverse=True)

        return stats_list

    def _avg_pnl_at_hours(self, agent: str, target_hours: float) -> Optional[float]:
        """
        Get the average PNL for an agent's signals at approximately `target_hours`
        after each signal was created, using the snapshots table.

        Returns None if no snapshot data is available.
        """
        try:
            # Allow a window of ±50% of target or at least ±1 hour
            window = max(target_hours * 0.5, 1)
            lower = target_hours - window
            upper = target_hours + window

            row = self.recorder._execute(
                """
                SELECT AVG(ss.pnl_percent) as avg_pnl
                FROM signal_snapshots ss
                JOIN signals s ON ss.signal_id = s.id
                WHERE s.agent = %s
                  AND ss.hours_since_signal BETWEEN %s AND %s;
                """,
                (agent, lower, upper),
                fetch_one=True,
            )

            if row and row.get("avg_pnl") is not None:
                return float(row["avg_pnl"])
            return None

        except Exception as e:
            logger.debug(f"Error fetching avg PNL at {target_hours}h for {agent}: {e}")
            return None

    # ------------------------------------------------------------------
    # Sheets update
    # ------------------------------------------------------------------

    def update_leaderboard_sheet(self, stats: list[dict] = None):
        """
        Calculate stats (if not provided) and write the leaderboard to Google Sheets.
        """
        if stats is None:
            stats = self.calculate_agent_stats()

        if not stats:
            logger.info("No agent stats to write — leaderboard is empty")
            return

        ws = self._get_or_create_worksheet("🏆 Leaderboard")
        self._write_headers(ws, self.LEADERBOARD_HEADERS)

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        rows = []
        for rank, s in enumerate(stats, 1):
            rows.append([
                rank,
                f"@{s['agent']}",
                s["total_signals"],
                f"{s['win_rate']:.1f}%",
                _fmt_pct(s["avg_pnl"]),
                _fmt_pct(s["avg_pnl_1h"]) if s["avg_pnl_1h"] is not None else "—",
                _fmt_pct(s["avg_pnl_24h"]) if s["avg_pnl_24h"] is not None else "—",
                _fmt_pct(s["avg_pnl_7d"]) if s["avg_pnl_7d"] is not None else "—",
                s["win_count"],
                s["lose_count"],
                f"${s['best_ticker']}",
                _fmt_pct(s["best_pnl"]),
                f"${s['worst_ticker']}",
                _fmt_pct(s["worst_pnl"]),
                _time_ago(s.get("last_signal_time")),
                now_str,
            ])

        # Clear old data (keep header) and write new data
        _rl.wait()
        ws.batch_clear(["A2:Z1000"])
        if rows:
            _rl.wait()
            ws.update(f"A2:P{1 + len(rows)}", rows, value_input_option="USER_ENTERED")

        logger.info(f"🏆 Leaderboard updated: {len(rows)} agents ranked")

    def update_live_signals_sheet(self):
        """Write all active signals to the Live Signals worksheet."""
        signals = self.recorder.get_active_signals()

        ws = self._get_or_create_worksheet("📊 Live Signals")
        self._write_headers(ws, self.LIVE_SIGNALS_HEADERS)

        rows = []
        for s in signals:
            tweet_url = ""
            tweet_id = s.get("tweet_id", "")
            agent = s.get("agent", "")
            if tweet_id and agent and tweet_id.isdigit():
                tweet_url = f"https://x.com/{agent}/status/{tweet_id}"

            rows.append([
                f"@{agent}",
                f"${s.get('ticker', '')}",
                s.get("chain", ""),
                _fmt_price(s.get("entry_price")),
                _fmt_price(s.get("current_price")),
                _fmt_pct(s.get("pnl_percent")),
                _fmt_mc(s.get("market_cap")),
                _fmt_mc(s.get("volume_24h")),
                _fmt_time(s.get("entry_time")),
                _time_ago(s.get("entry_time")),
                s.get("sentiment") or "",
                s.get("contract_address", ""),
                tweet_url,
            ])

        _rl.wait()
        ws.batch_clear(["A2:Z1000"])
        if rows:
            _rl.wait()
            ws.update(f"A2:M{1 + len(rows)}", rows, value_input_option="USER_ENTERED")

        logger.info(f"📊 Live Signals updated: {len(rows)} active signals")

    def update_all(self):
        """Convenience: update both leaderboard and live signals sheets."""
        try:
            stats = self.calculate_agent_stats()
            self.update_leaderboard_sheet(stats)
            self.update_live_signals_sheet()

            # Log a summary
            if stats:
                top = stats[0]
                logger.info(
                    f"Top agent: @{top['agent']} — "
                    f"{top['total_signals']} signals, "
                    f"{top['win_rate']:.1f}% win rate, "
                    f"{top['avg_pnl']:+.2f}% avg PNL"
                )
        except Exception as e:
            logger.error(f"Error updating leaderboard sheets: {e}")
