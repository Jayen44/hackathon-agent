"""The long-running tick loop. Use --fast for fake-clock demo replay."""
import argparse
import time

from agent import data, explain, model, store


def run(ticks: int, delay: float) -> None:
    conn = store.connect()
    start = store.get_state(conn, "tick", 0)
    prev = store.get_state(conn, "last_assessment")

    for tick in range(start, start + ticks):
        inputs = data.get_inputs(tick)
        assessment = model.evaluate({}, inputs)

        if model.changed_materially(prev, assessment):
            note = explain.explain(prev, assessment)
            store.log_event(conn, tick, "alert", {"assessment": assessment, "note": note})
            print(f"[tick {tick}] {note}")

        store.log_event(conn, tick, "tick", {"inputs": inputs, "assessment": assessment})
        store.set_state(conn, "tick", tick + 1)
        store.set_state(conn, "last_assessment", assessment)
        prev = assessment
        time.sleep(delay)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--fast", action="store_true", help="fake clock: no sleep between ticks")
    p.add_argument("--ticks", type=int, default=100)
    p.add_argument("--delay", type=float, default=5.0, help="seconds per tick in live mode")
    a = p.parse_args()
    run(a.ticks, 0.0 if a.fast else a.delay)
