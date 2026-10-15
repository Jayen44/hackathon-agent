# Driverless-car crash triage: who pays, and can the insurer get it back?

**Pitch:** when a self-driving car is in a crash, UK insurers pay the victim first and may recover from the tech company later (AEVA 2018 s.5). We give the claims team a fast, auditable first read on each crash: who is at fault, the insurer's recoverable money as a GBP *range*, whether to pursue, what evidence to request, and which limitation deadline is running. It is triage for a claims handler, not a liability finding.

**Honest scope (read before pitching):** no vehicle is on the AEVA list today and most of the AV Act 2024 is not yet in force (expected H2 2027), so for today's supervised pilots the s.5 model is a proxy. The human-driver model is a placeholder until the R157 models from `sim/` are wired in, and all crashes are synthetic. See `docs/legal-basis.md` (what we may and may not say) and `docs/system-overview.md` (how it works, known issues).

## Try it
```bash
pip install -r requirements.txt
python -m insurance.portfolio --dir insurance/examples --recon-error 0.1   # ranked recoverability map in GBP
python -m insurance insurance/examples/21_pursue_cut_in.json --price       # one claim: verdict, GBP range, next steps
python -m insurance.queue_html --dir insurance/examples -o queue.html      # insurer-facing claims queue (open in a browser)
python -m insurance.watch --dir insurance/examples                         # limitation deadlines, most urgent first
python -m pytest -q
```
Useful flags: `--recon-error 0.1` (assume +-10% error on the reconstruction; widens the interval), `--min-net 2000` (pursue threshold in GBP; a policy choice), `--ledger runs.jsonl` (log every run and print what changed since the last one).

## Layout
| Path | Owner | Purpose |
|---|---|---|
| `insurance/` | Jayen | bundle, liability engine, counterfactual, bridge, legal clocks, resolution, queue |
| `finance/` | Antonio | claim value, legal cost, expected recovery, pursue decision |
| `agents/` | Antonio | adjuster / defence counsel / rebuttal debate over the finance tools |
| `sim/` (branch `sim`) | Vakhtang | physics and UN R157 careful-driver models |
| `ukcrash/`, `claimsim/` | Antonio | UK crash profile and synthetic claims |
| `docs/` | shared | `system-overview.md`, `legal-basis.md`, `liability-spec.md`, `validation.md`, `verification.md` |
| `coord/HANDOFF.md` | shared | current state and open work |

## Team
| Name | Role | GitHub |
|---|---|---|
| Jayen | Owner, insurance | [@Jayen44](https://github.com/Jayen44) |
| Antonio | Finance | [@antoniohede-ai](https://github.com/antoniohede-ai) |
| Vakhtang | Robotics / sim | [@termvato](https://github.com/termvato) |

Private repo: access is limited to the three people above. See [CONTRIBUTING.md](CONTRIBUTING.md) and `coord/PROTOCOL.md` for the workflow.

_Decision support only. Not legal or financial advice. Demo uses synthetic or public data only._
