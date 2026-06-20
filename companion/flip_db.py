"""SQLite history store: items, price_history, observations (handoff §3.3, §5.3).

All schema and SQL live here (DRY). Parameterized queries only. Safe to open with
``:memory:`` for tests. The store is unit-consistent: every `price_history` row is
tagged with its `step` (`5m` / `1h` / `24h`) so windows are never cross-compared
(handoff §6.1).
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from companion.models import PendingAction, PricePoint, Verdict

log = logging.getLogger("runeclaw.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    buy_limit  INTEGER,
    members    INTEGER,
    first_seen INTEGER,
    backfilled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS price_history (
    item_id  INTEGER NOT NULL,
    ts       INTEGER NOT NULL,
    avg_high INTEGER,
    avg_low  INTEGER,
    high_vol INTEGER NOT NULL DEFAULT 0,
    low_vol  INTEGER NOT NULL DEFAULT 0,
    step     TEXT NOT NULL,
    PRIMARY KEY (item_id, ts, step)
);
CREATE TABLE IF NOT EXISTS observations (
    item_id INTEGER NOT NULL,
    ts      INTEGER NOT NULL,
    buy     INTEGER,
    sell    INTEGER,
    margin  INTEGER,
    profit  INTEGER,
    roi     REAL,
    volume  INTEGER,
    verdict TEXT
);
CREATE INDEX IF NOT EXISTS idx_obs_item_ts ON observations(item_id, ts);
CREATE TABLE IF NOT EXISTS pending_actions (
    action_id    TEXT PRIMARY KEY,
    created_at   INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL,
    action       TEXT NOT NULL,
    item_id      INTEGER NOT NULL,
    name         TEXT NOT NULL,
    price        INTEGER NOT NULL,
    qty          INTEGER NOT NULL,
    slot         INTEGER,
    verdict      TEXT,
    status       TEXT NOT NULL,
    error        TEXT,
    completed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_actions(status);
"""

_PENDING_COLUMNS = (
    "action_id, created_at, expires_at, action, item_id, name, price, qty, "
    "slot, verdict, status, error, completed_at"
)


def _row_to_pending(row: sqlite3.Row) -> PendingAction:
    return PendingAction(
        action_id=row["action_id"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        action=row["action"],
        item_id=row["item_id"],
        name=row["name"],
        price=row["price"],
        qty=row["qty"],
        slot=row["slot"],
        verdict=row["verdict"],
        status=row["status"],
        error=row["error"],
        completed_at=row["completed_at"],
    )


def _opt_int(value: Any) -> int | None:
    return None if value is None else int(value)


class FlipDB:
    """Thin SQLite wrapper. Use as a context manager to ensure the connection closes."""

    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def __enter__(self) -> "FlipDB":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    # -- items ----------------------------------------------------------------

    def upsert_item(
        self, item_id: int, name: str, buy_limit: int | None, members: int | None
    ) -> None:
        """Insert or refresh item metadata without disturbing first_seen/backfilled."""
        self._conn.execute(
            """
            INSERT INTO items (id, name, buy_limit, members, first_seen, backfilled)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                buy_limit = excluded.buy_limit,
                members = excluded.members
            """,
            (item_id, name, buy_limit, members, int(time.time())),
        )
        self._conn.commit()

    def is_backfilled(self, item_id: int) -> bool:
        row = self._conn.execute(
            "SELECT backfilled FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        return bool(row and row["backfilled"])

    def mark_backfilled(self, item_id: int) -> None:
        self._conn.execute("UPDATE items SET backfilled = 1 WHERE id = ?", (item_id,))
        self._conn.commit()

    # -- price history --------------------------------------------------------

    def insert_price_points(
        self, item_id: int, points: Iterable[dict[str, Any]], step: str
    ) -> int:
        """Store `/timeseries` points. INSERT OR REPLACE refreshes the latest partial point."""
        rows = []
        for p in points:
            ts = p.get("timestamp")
            if ts is None:
                continue
            rows.append(
                (
                    item_id,
                    int(ts),
                    _opt_int(p.get("avgHighPrice")),
                    _opt_int(p.get("avgLowPrice")),
                    int(p.get("highPriceVolume") or 0),
                    int(p.get("lowPriceVolume") or 0),
                    step,
                )
            )
        self._conn.executemany(
            """
            INSERT OR REPLACE INTO price_history
                (item_id, ts, avg_high, avg_low, high_vol, low_vol, step)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._conn.commit()
        return len(rows)

    def get_price_history(self, item_id: int, step: str, limit: int) -> list[PricePoint]:
        """Return up to `limit` most-recent points for `step`, in chronological order."""
        cur = self._conn.execute(
            """
            SELECT item_id, ts, avg_high, avg_low, high_vol, low_vol, step
            FROM price_history
            WHERE item_id = ? AND step = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (item_id, step, limit),
        )
        rows = cur.fetchall()
        rows.reverse()  # oldest -> newest for trend/percentile math
        return [
            PricePoint(
                item_id=r["item_id"],
                ts=r["ts"],
                avg_high=r["avg_high"],
                avg_low=r["avg_low"],
                high_vol=r["high_vol"],
                low_vol=r["low_vol"],
                step=r["step"],
            )
            for r in rows
        ]

    # -- observations ---------------------------------------------------------

    def insert_observation(
        self,
        item_id: int,
        buy: int,
        sell: int,
        margin: int,
        profit: int,
        roi: float,
        volume: int | None,
        verdict: Verdict,
        ts: int | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO observations
                (item_id, ts, buy, sell, margin, profit, roi, volume, verdict)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                ts if ts is not None else int(time.time()),
                buy,
                sell,
                margin,
                profit,
                roi,
                volume,
                verdict.value,
            ),
        )
        self._conn.commit()

    # -- pending actions ------------------------------------------------------

    def create_pending(self, action: PendingAction) -> None:
        self._conn.execute(
            f"INSERT INTO pending_actions ({_PENDING_COLUMNS}) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                action.action_id,
                action.created_at,
                action.expires_at,
                action.action,
                action.item_id,
                action.name,
                action.price,
                action.qty,
                action.slot,
                action.verdict,
                action.status,
                action.error,
                action.completed_at,
            ),
        )
        self._conn.commit()

    def get_pending(self, action_id: str) -> PendingAction | None:
        row = self._conn.execute(
            f"SELECT {_PENDING_COLUMNS} FROM pending_actions WHERE action_id = ?",
            (action_id,),
        ).fetchone()
        return _row_to_pending(row) if row else None

    def list_pending(self, statuses: tuple[str, ...] = ("pending",)) -> list[PendingAction]:
        placeholders = ", ".join("?" for _ in statuses)
        cur = self._conn.execute(
            f"SELECT {_PENDING_COLUMNS} FROM pending_actions "
            f"WHERE status IN ({placeholders}) ORDER BY created_at DESC",
            statuses,
        )
        return [_row_to_pending(r) for r in cur.fetchall()]

    def latest_pending(self) -> PendingAction | None:
        row = self._conn.execute(
            f"SELECT {_PENDING_COLUMNS} FROM pending_actions "
            f"WHERE status = 'pending' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return _row_to_pending(row) if row else None

    def update_status(
        self,
        action_id: str,
        status: str,
        error: str | None = None,
        completed_at: int | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE pending_actions
            SET status = ?,
                error = COALESCE(?, error),
                completed_at = COALESCE(?, completed_at)
            WHERE action_id = ?
            """,
            (status, error, completed_at, action_id),
        )
        self._conn.commit()

    def expire_stale(self, now: int) -> int:
        """Mark pending actions past their grace window as expired. Returns count expired."""
        cur = self._conn.execute(
            "UPDATE pending_actions SET status = 'expired' "
            "WHERE status = 'pending' AND expires_at < ?",
            (now,),
        )
        self._conn.commit()
        return cur.rowcount
