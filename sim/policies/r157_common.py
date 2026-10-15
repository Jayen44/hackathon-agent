"""Shared bookkeeping for the two UN R157 Annex 3 careful-driver models.

No regulation values live here. careful_a.py (Performance model 1) and
careful_b.py (Performance model 2) pass in the wandering-zone width they take
from the text.

Sim assumptions (NOT from R157, disclosed in R157_ANNEX3.md):
- The ego lane centre is the ego's y at the first observation (the sim frame
  puts the ego lane at y = 0, and the careful drivers never steer).
- Each other vehicle's own lane centre is its y at the first observation, i.e.
  scenarios start every actor centred in its lane.
- A vehicle ahead in the ego lane whose centre is inside the wandering zone
  hides every vehicle further ahead (the cut-out "reveal"; R157 Annex 3
  3.3.2.2 and 3.4.3(c)). There is no other sensor model.
"""
from __future__ import annotations

from dataclasses import dataclass

from sim.world import ActorObs, Observation


@dataclass(frozen=True)
class Seen:
    actor: ActorObs
    gap: float           # m, bumper to bumper, ego front to actor rear (> 0: actor rear is ahead)
    closing: float       # m/s, ego longitudinal speed minus actor longitudinal speed
    dy: float            # m, actor centre minus ego centre (lateral)
    lat_gap: float       # m, edge-to-edge lateral distance (<= 0: bodies overlap laterally)
    lane0: float         # m, actor's own lane centre (y at first observation)
    ego_lane_origin: bool  # actor started in the ego lane
    was_hidden: bool     # actor was hidden behind an in-lane vehicle at some earlier step
    hidden_by: str | None  # name of the last vehicle that hid it (the cut-out vehicle)


class LaneTracker:
    """Lane centres, visibility (cut-out reveal) and relative geometry of the actors ahead."""

    def __init__(self, wander: float):
        self.wander = wander
        self.reset()

    def reset(self) -> None:
        self.ego_lane: float | None = None
        self.lane0: dict[str, float] = {}
        self.hidden_by: dict[str, str] = {}

    def deviation_toward_ego_lane(self, s: Seen) -> float:
        """How far the actor's centre has moved from its own lane centre towards the ego lane (m)."""
        side = 1.0 if s.lane0 > self.ego_lane else -1.0
        return (s.lane0 - s.actor.state.y) * side

    def in_ego_lane_zone(self, a: ActorObs) -> bool:
        """Actor centre inside the wandering zone around the ego lane centre."""
        return abs(a.state.y - self.ego_lane) <= self.wander

    def update(self, obs: Observation) -> list[Seen]:
        """Visible actors whose rear is ahead of the ego front, nearest first."""
        if self.ego_lane is None:
            self.ego_lane = obs.ego.y
        eg = obs.ego_geometry
        ego_vx = obs.ego.velocity()[0]
        ahead: list[Seen] = []
        for a in obs.actors:
            self.lane0.setdefault(a.name, a.state.y)
            gap = a.state.x - obs.ego.x - (eg.length + a.geometry.length) / 2
            if gap <= 0:
                continue
            dy = a.state.y - obs.ego.y
            ahead.append(Seen(
                actor=a, gap=gap, closing=ego_vx - a.state.velocity()[0], dy=dy,
                lat_gap=abs(dy) - (eg.width + a.geometry.width) / 2,
                lane0=self.lane0[a.name],
                ego_lane_origin=abs(self.lane0[a.name] - self.ego_lane) <= self.wander,
                was_hidden=a.name in self.hidden_by, hidden_by=self.hidden_by.get(a.name)))
        ahead.sort(key=lambda s: s.gap)
        visible: list[Seen] = []
        occluder: Seen | None = None
        for s in ahead:
            if occluder is not None and s.gap > occluder.gap:
                self.hidden_by[s.actor.name] = occluder.actor.name
                continue
            visible.append(s)
            if occluder is None and self.in_ego_lane_zone(s.actor):
                occluder = s
        return visible
