# Proof of the runs (for the jury)

## Long-running agent team (Claude Managed Agents)
- Run `20261015-113918-f201`, 11:39 to 12:49 UTC (70 min), stopped at its **USD 25 hard budget**.
- **58 claims** processed: 16 pursue, 16 pull logs first, 18 don't pursue, 8 not priced / need inputs.
- Recoverable pool: GBP 52k / 141k / 337k (low / mid / high, synthetic claims).
- **4,245 trace events**:

  | Agent | Events |
  |---|---|
  | Portfolio lead | 1,907 |
  | Reconstructor | 524 |
  | Counterfactual analyst | 445 |
  | Investigator | 396 |
  | Defence counsel | 174 |
  | Adjuster | 208 |
  | Debate referee | 46 |
  | Runner | 545 |

- **Model use:** 324 model requests from the lead, list cost USD 25.14 for the session, plus USD 6.11 for the adjuster/defence debates.
- **Files:**
  - [agent_run/trace.jsonl](agent_run/trace.jsonl): every hand-off and tool call, with timestamps
  - [agent_run/portfolio.json](agent_run/portfolio.json): every claim's finding
  - [agent_run/meta.json](agent_run/meta.json): config, usage, Console session id
- **Live views:**
  - read API: https://termvato--accel-fleet-web.us-east.modal.run/api/runs/20261015-113918-f201
  - dashboard: https://accel-claims-dashboard.vercel.app/run

## CCTV to decision (end to end, live system)
- **Input:** a synthetic CCTV render (`demo_media/cctv_blender_cut_in.mp4`; Blender, ground truth in `viz/isaac/samples/cctv_cut_in_truth.json`).
- **Pipeline:** detection and tracking, then calibration, measured speeds, sim reconstruction, careful drivers A/B, the insurance team's GBP engine and the debate.
- **Result:** [cctv_claim/CHECK-blender.json](cctv_claim/CHECK-blender.json), page https://accel-claims-dashboard.vercel.app/claims/CHECK-blender
  - Pull logs first.
  - P(avoid): careful driver A 0.91 (CI90 0.89-0.92), B 0.95 (CI90 0.93-0.96).
  - Expected recovery GBP 3.0k-48.7k.
  - Gates: engagement only alleged without AV logs; low reproduction.
- **Measured vs true speeds:** in viz/render (cutter 9.03 vs 9.0 m/s; AV before impact 14.86 vs 14.85 m/s).

## Real-crash evaluation
- [eval/REAL_CRASH_EVAL.md](../eval/REAL_CRASH_EVAL.md): 100-Car study (CC0).
- Real rear-end crashes avoided: careful driver A 5/8, careful driver B 8/8.
- The sim reproduces 88% of crashes and 94% of near-crashes.
