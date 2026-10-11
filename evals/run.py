"""Run the eval harness.

  cd backend
  .venv/bin/python ../evals/run.py --mock                     # free, Fire mocked
  .venv/bin/python ../evals/run.py --live --budget 0.08       # real Fire; ask first

Live runs use the database in backend/.env and count toward the $1 monthly
Fire budget. The run stops before starting a candidate that could push the
spend past --budget.
"""

import argparse
import sys
from pathlib import Path

from harness import FIELDS, PERSONAS, checks, run_one, save, summarize

# A 10-minute interview + report + candidate replies, with headroom.
EST_RUN_USD = 0.023  # measured 0.016–0.023 on 2026-10-11


def make_app(live: bool):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from app import create_app
    from app.config import Config, TestConfig
    from app.extensions import db

    app = create_app(Config if live else TestConfig)
    app.config.update(REPORTS_INLINE=True, RATE_LIMITS=False)
    if not live:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
        from tests.fakes import FakeFire

        app.extensions["fire"] = FakeFire()
        app.config["FIRE_MONTHLY_BUDGET_USD"] = 1000
    ctx = app.app_context()
    ctx.push()
    if not live:
        db.create_all()
    return app


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--live", action="store_true", help="use the real Fire API (costs money)"
    )
    mode.add_argument(
        "--mock", action="store_true", help="Fire mocked, canned answers (free)"
    )
    p.add_argument(
        "--fields",
        default=",".join(FIELDS),
        help="comma-separated: " + ",".join(FIELDS),
    )
    p.add_argument(
        "--personas",
        default=",".join(PERSONAS),
        help="comma-separated: " + ",".join(PERSONAS),
    )
    p.add_argument(
        "--budget", type=float, default=0.08, help="max USD for this live run"
    )
    p.add_argument("--out", default=str(Path(__file__).resolve().parent / "results"))
    a = p.parse_args(argv)

    app = make_app(a.live)
    runs, spent = [], 0.0
    for f in a.fields.split(","):
        for persona in a.personas.split(","):
            if a.live and spent + EST_RUN_USD > a.budget:
                print(
                    f"Stopping before {f}/{persona}: ${spent:.4f} spent of ${a.budget}"
                )
                break
            print(f"running {f}/{persona} …", flush=True)
            r = run_one(app, f, persona, a.live)
            spent += r.spend_usd
            runs.append(r)
    results = checks(runs)
    print(summarize(runs))
    for name, ok in results:
        print(("PASS " if ok else "FAIL ") + name)
    path = save(runs, results, Path(a.out))
    print(f"saved {path}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
