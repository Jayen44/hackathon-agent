"""Trace store: one JSONL file of events per run, plus meta.json and portfolio.json.

Layout under `root` (a local dir, or the Modal volume `accel-fleet` mounted at /fleet):
    runs/<run_id>/meta.json        run config, status, usage, cost
    runs/<run_id>/trace.jsonl      one event per line, seq = line number
    runs/<run_id>/portfolio.json   latest portfolio summary + findings

On Modal the writer passes `commit=volume.commit` (throttled) and readers call `volume.reload()`.
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
from pathlib import Path
from typing import Callable


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def clip(x, n: int = 600) -> str:
    s = x if isinstance(x, str) else json.dumps(x, default=str, separators=(",", ":"))
    return s if len(s) <= n else s[:n] + f"... [{len(s) - n} more chars]"


class TraceStore:
    def __init__(self, root: str | Path, commit: Callable[[], None] | None = None, commit_every_s: float = 2.0):
        self.root = Path(root)
        self._commit, self.every = commit, commit_every_s
        self._last = 0.0
        self.lock = threading.RLock()
        self._seq: dict[str, int] = {}

    def run_dir(self, run_id: str) -> Path:
        return self.root / "runs" / run_id

    # ------------------------------------------------------------- write
    def create_run(self, run_id: str, meta: dict) -> None:
        d = self.run_dir(run_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "trace.jsonl").touch()
        self.write_meta(run_id, {"run_id": run_id, "created_at": now(), "status": "starting", **meta})

    def write_meta(self, run_id: str, meta: dict) -> None:
        with self.lock:
            p = self.run_dir(run_id) / "meta.json"
            old = json.loads(p.read_text()) if p.exists() else {}
            old.update(meta)
            old["updated_at"] = now()
            self._atomic(p, old)
            self.maybe_commit()

    def write_portfolio(self, run_id: str, portfolio: dict) -> None:
        with self.lock:
            self._atomic(self.run_dir(run_id) / "portfolio.json", {**portfolio, "updated_at": now()})
            self.maybe_commit()

    def append(self, run_id: str, row: dict) -> dict:
        with self.lock:
            p = self.run_dir(run_id) / "trace.jsonl"
            if run_id not in self._seq:
                self._seq[run_id] = sum(1 for _ in p.open()) if p.exists() else 0
            row = {"seq": self._seq[run_id], "ts": row.get("ts") or now(), "run_id": run_id, **row}
            with p.open("a") as f:
                f.write(json.dumps(row, default=str) + "\n")
            self._seq[run_id] += 1
            self.maybe_commit()
            return row

    def _atomic(self, p: Path, obj) -> None:
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, default=str, indent=1))
        tmp.replace(p)

    def maybe_commit(self, force: bool = False) -> None:
        if self._commit and (force or time.monotonic() - self._last >= self.every):
            self._last = time.monotonic()
            try:
                self._commit()
            except Exception:  # noqa: BLE001 - a failed commit retries on the next write
                self._last = 0.0

    # ------------------------------------------------------------- read
    def runs(self) -> list[dict]:
        out = []
        for d in sorted((self.root / "runs").glob("*/meta.json")) if (self.root / "runs").exists() else []:
            try:
                out.append(json.loads(d.read_text()))
            except json.JSONDecodeError:
                continue
        return sorted(out, key=lambda m: m.get("created_at", ""), reverse=True)

    def meta(self, run_id: str) -> dict | None:
        p = self.run_dir(run_id) / "meta.json"
        return json.loads(p.read_text()) if p.exists() else None

    def trace(self, run_id: str, since: int = 0, limit: int = 500) -> list[dict]:
        p = self.run_dir(run_id) / "trace.jsonl"
        if not p.exists():
            return []
        out = []
        with p.open() as f:
            for i, line in enumerate(f):
                if i < since:
                    continue
                if len(out) >= limit:
                    break
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    break   # partially written last line
        return out

    def portfolio(self, run_id: str) -> dict | None:
        p = self.run_dir(run_id) / "portfolio.json"
        return json.loads(p.read_text()) if p.exists() else None
