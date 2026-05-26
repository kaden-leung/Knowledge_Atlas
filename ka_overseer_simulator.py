#!/usr/bin/env python3
"""Run a named AF traffic simulation against simulator-only AF and KA DBs."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from sim import scenarios
from sim import simulator_runner
from sim_supervisor import status_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=sorted(scenarios.scenario_library()),
        default="accept_wave",
        help="Named scenario to run against the simulator DBs.",
    )
    parser.add_argument("--sim-af-db", help="Override simulator AF DB path")
    parser.add_argument("--sim-ka-db", help="Override simulator KA DB path")
    parser.add_argument("--supervisor-db", help="Override simulator supervisor DB path")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete any prior simulator DBs at the chosen paths before running.",
    )
    args = parser.parse_args(argv)

    scenario = scenarios.scenario_library()[args.scenario]
    summary = simulator_runner.run_scenario(
        scenario=scenario,
        sim_af_db_path=args.sim_af_db,
        sim_ka_db_path=args.sim_ka_db,
        supervisor_db_path=args.supervisor_db,
        reset_databases=args.fresh,
    )
    report_paths = status_report.write_reports(db_path=summary.supervisor_db_path)
    print(
        json.dumps(
            {
                "scenario_summary": asdict(summary),
                "supervisor_reports": report_paths,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
