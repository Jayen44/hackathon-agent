"""CCTV / dashcam video -> measured trajectories -> crash bundle `conflict` (evidence tier 1).

  detect.py        vehicle detection (RT-DETR, Apache-2.0) + tracking (ByteTrack via supervision, MIT).
                   Runs on Modal GPU; heavy imports are lazy so the rest stays numpy-only.
  calibrate.py     image -> road-plane homography from user-clicked points with user-entered metres,
                   plus an ensemble of perturbed homographies for uncertainty.
  trajectories.py  project tracks to metres, smooth, speed/accel with error bars, road frame,
                   conflict extraction -> bundle dict for montecarlo.estimate.

Privacy: vehicles only, never number plates or faces. Persons are detected only to blur them.
Uploaded videos are untrusted data and stay in the Modal volume, never in git.
"""
