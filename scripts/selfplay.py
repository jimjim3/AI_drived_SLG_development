#!/usr/bin/env python3
"""LLM self-play: every faction is controlled by the same LLM; reports who actually attacks.

Unlike evaluate.py (one LLM seat vs rule-AI baseline) this shows LLM-vs-LLM behaviour, and it separates
sieges the LLM *ordered* from sieges made by officers the rule-AI delegate handled.

  PYTHONPATH=src python3 scripts/selfplay.py --openai-base-url URL/v1 --model qwen3.8:27b \
      --extra-body-json '{"reasoning_effort":"none"}' --seeds 0-1 --turns 20 --siege-verdict --out out.json
"""
import argparse
import json
import sys
from types import SimpleNamespace

from slg.agents.llm_agent import LLMFactionAgent
from slg.engine.combat import RULESETS, set_rules
from slg.sim.evaluate import parse_seeds
from slg.sim.headless import run_headless
from slg.sim.run_llm import _parse_extra_body_json, build_completer


def summarize(res, seed):
    st = res.final_state
    ordered = {}   # (turn, officer) -> faction, for officers the LLM named that turn
    for fl in res.log.faction_logs:
        for oid in getattr(fl, "ordered", ()):
            ordered[(fl.turn, oid)] = fl.faction_id
    out = {"seed": seed, "winner": res.winner, "factions": {}}
    for fid in sorted(st.factions):
        cities = [c for c in st.cities.values() if c.owner == fid]
        living = [o for o in st.officers.values() if o.faction_id == fid and o.is_alive]
        sieges = [e for e in res.events if e.action == "siege" and e.faction_id == fid]
        llm = [e for e in sieges if (e.turn, e.officer_id) in ordered]
        out["factions"][fid] = {
            "name": st.factions[fid].name, "cities": len(cities), "troops": sum(c.troops for c in cities),
            "sieges_llm": len(llm), "captured_llm": sum(1 for e in llm if e.captured_city),
            "sieges_delegated": len(sieges) - len(llm),
            "captured_delegated": sum(1 for e in sieges if e not in llm and e.captured_city),
            "min_loyalty": min((o.loyalty for o in living), default=None),
            "officers": len(living),
        }
    out["rejected"] = res.stats.get("rejected", 0)
    out["decisions"] = res.stats.get("decisions", 0)
    out["usage"] = {k: v for k, v in res.usage.items()}
    return out


def save(args, results):
    skip = ("openai_base_url", "api_key_env")  # never write endpoints or key names into reports
    json.dump({"args": {k: v for k, v in vars(args).items() if k not in skip}, "games": results},
              open(args.out, "w"), ensure_ascii=False, indent=1)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--openai-base-url")
    ap.add_argument("--model")
    ap.add_argument("--api-key-env")
    ap.add_argument("--extra-body-json", type=_parse_extra_body_json, default=None)
    ap.add_argument("--http-retries", type=int, default=0)
    ap.add_argument("--http-timeout", type=float, default=None)
    ap.add_argument("--min-interval", type=float, default=0.0)
    ap.add_argument("--max-consecutive-errors", type=int, default=5)
    ap.add_argument("--siege-verdict", action="store_true")
    ap.add_argument("--persona", choices=("aggressive", "defensive"), default=None)
    ap.add_argument("--rules", default="v2", choices=sorted(RULESETS), help="experimental combat rule set (see engine/combat.py)")
    ap.add_argument("--seeds", default="0-1")
    ap.add_argument("--turns", type=int, default=20)
    ap.add_argument("--scenario", default="default")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    args.command = None
    set_rules(args.rules)
    completer = build_completer(args)
    if completer is None:
        ap.error("need --demo or --openai-base-url and --model")
    results = []
    for seed in parse_seeds(args.seeds):
        agents = {f: LLMFactionAgent(completer, siege_verdict=args.siege_verdict, persona=args.persona)
                  for f in ("faction_1", "faction_2", "faction_3")}
        res = run_headless(seed=seed, turns=args.turns, agents_by_faction=agents, scenario=args.scenario)
        r = summarize(res, seed)
        results.append(r)
        print(f"seed {seed}: winner={r['winner']} rejected={r['rejected']}/{r['decisions']}", flush=True)
        for fid, f in r["factions"].items():
            print(f"  {fid} {f['name']}: {f['cities']} cities, {f['troops']} troops | LLM sieges {f['sieges_llm']} "
                  f"(captured {f['captured_llm']}) | delegated sieges {f['sieges_delegated']} "
                  f"(captured {f['captured_delegated']}) | min loyalty {f['min_loyalty']}", flush=True)
        if args.out:  # save after every game so an interrupted run keeps what it finished
            save(args, results)
        if getattr(completer, "is_open", False):
            print("  ! circuit breaker opened; later calls fell back to the rule AI", flush=True)
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
