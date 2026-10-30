#!/usr/bin/env python3
"""Sweep economic balance parameters using rule-based AI games.

Evaluates combinations of march_food_rate, cap tier sets (Koei tiers vs flattened),
and far_march_factor over multiple seeded games with rule-based AI.
Saves raw JSON evals to docs/evals/rule/ and prints a markdown summary table.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

from slg.engine import combat
from slg.sim.evaluate import parse_seeds
from slg.sim.headless import run_headless

FACTIONS = ("faction_1", "faction_2", "faction_3")
FACTION_NAMES = {"faction_1": "曹操", "faction_2": "劉備", "faction_3": "孫權"}


def evaluate_variant(
    rules: combat.CombatRules,
    seeds: list[int],
    turns: int = 30,
    scenario: str = "default",
) -> dict[str, Any]:
    """Run rule-based AI games for a given rule variant and collect stats."""
    # Register in memory so active() / set_rules() resolves it
    combat.RULESETS[rules.name] = rules
    combat.set_rules(rules.name)

    wins: dict[str | None, int] = {f: 0 for f in FACTIONS}
    wins[None] = 0

    sieges_by_faction: dict[str, int] = {f: 0 for f in FACTIONS}
    captures_by_faction: dict[str, int] = {f: 0 for f in FACTIONS}
    games_with_siege_by_faction: dict[str, int] = {f: 0 for f in FACTIONS}
    games_with_any_siege = 0

    game_records: list[dict[str, Any]] = []

    for seed in seeds:
        res = run_headless(seed=seed, turns=turns, scenario=scenario)
        wins[res.winner] += 1

        faction_sieges = {f: 0 for f in FACTIONS}
        faction_caps = {f: 0 for f in FACTIONS}

        for e in res.events:
            if e.action == "siege" and e.faction_id in FACTIONS:
                faction_sieges[e.faction_id] += 1
                if e.captured_city:
                    faction_caps[e.faction_id] += 1

        any_siege_in_game = sum(faction_sieges.values()) > 0
        if any_siege_in_game:
            games_with_any_siege += 1

        for fid in FACTIONS:
            sieges_by_faction[fid] += faction_sieges[fid]
            captures_by_faction[fid] += faction_caps[fid]
            if faction_sieges[fid] > 0:
                games_with_siege_by_faction[fid] += 1

        st = res.final_state
        game_factions = {}
        for fid in FACTIONS:
            owned = [c for c in st.cities.values() if c.owner == fid]
            game_factions[fid] = {
                "name": FACTION_NAMES[fid],
                "cities": len(owned),
                "troops": sum(c.troops for c in owned),
                "sieges": faction_sieges[fid],
                "captures": faction_caps[fid],
            }

        game_records.append({
            "seed": seed,
            "winner": res.winner,
            "total_sieges": sum(faction_sieges.values()),
            "total_captures": sum(faction_caps.values()),
            "factions": game_factions,
        })

    n_games = len(seeds)
    faction_summary = {}
    for fid in FACTIONS:
        w = wins[fid]
        faction_summary[fid] = {
            "name": FACTION_NAMES[fid],
            "wins": w,
            "win_share": round(w / n_games, 4) if n_games else 0.0,
            "sieges": sieges_by_faction[fid],
            "captures": captures_by_faction[fid],
            "games_with_siege": games_with_siege_by_faction[fid],
            "games_with_siege_share": round(games_with_siege_by_faction[fid] / n_games, 4) if n_games else 0.0,
        }

    return {
        "variant": rules.name,
        "rules": {
            "name": rules.name,
            "cap_tiers": rules.cap_tiers,
            "march_food_rate": rules.march_food_rate,
            "far_march_factor": rules.far_march_factor,
            "city_caps": rules.city_caps,
            "pool_factor": rules.pool_factor,
            "pool_depth": rules.pool_depth,
            "defense_divisor": rules.defense_divisor,
            "dq_base": rules.dq_base,
            "dq_div": rules.dq_div,
        },
        "seeds_count": n_games,
        "turns": turns,
        "scenario": scenario,
        "games_with_any_siege": games_with_any_siege,
        "games_with_any_siege_share": round(games_with_any_siege / n_games, 4) if n_games else 0.0,
        "total_sieges": sum(sieges_by_faction.values()),
        "total_captures": sum(captures_by_faction.values()),
        "factions": faction_summary,
        "ties": wins[None],
        "games": game_records,
    }


def balance_score(res: dict[str, Any]) -> float:
    """Calculate a balance penalty score (lower is more balanced).

    Design targets:
    - 3-way spread close to equal (1/3 each).
    - Sun active (sun_sieges > 0 and wins > 0). If Sun has 0 sieges or 0 wins, penalty is huge.
    - Sun not dominant (win_share <= 0.50).
    - All three factions participate (penalty if a faction has 0 wins).
    """
    factions = res["factions"]
    sun_sieges = factions["faction_3"]["sieges"]
    sun_wins = factions["faction_3"]["wins"]

    if sun_sieges == 0:
        return 999.0
    if sun_wins == 0:
        return 500.0

    shares = [factions[f]["win_share"] for f in FACTIONS]
    # Sum of squared deviations from ideal 1/3 share
    sq_dev = sum((s - (1.0 / 3.0)) ** 2 for s in shares)

    # Penalty if any faction has 0 wins (failure to achieve three-way spread)
    zero_win_penalty = sum(0.10 for s in shares if s == 0)

    # Penalty if any faction exceeds 50%
    over_dom = sum(max(0.0, s - 0.50) ** 2 for s in shares) * 2.0

    return sq_dev + zero_win_penalty + over_dom


def format_markdown_table(results: list[dict[str, Any]]) -> str:
    """Generate a clean markdown table summarizing variant evaluations."""
    lines = [
        "| 規則變體 | 上限階級 | 糧耗率 | 遠路戰力 | 曹勝(勝率) | 劉勝(勝率) | 孫勝(勝率) | 曹/劉/孫 攻城 | 曹/劉/孫 攻克 | 孫權出征 | AI攻城局數 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        ru = r["rules"]
        t_str = "Koei" if ru["cap_tiers"] is True else ("Flat" if ru["cap_tiers"] == "flat" else str(ru["cap_tiers"]))
        rate_str = f"{ru['march_food_rate']:.2f}".rstrip("0").rstrip(".")
        far_str = f"{ru['far_march_factor']:.2f}".rstrip("0").rstrip(".")
        f = r["factions"]
        c_w, c_ws = f["faction_1"]["wins"], f["faction_1"]["win_share"]
        l_w, l_ws = f["faction_2"]["wins"], f["faction_2"]["win_share"]
        s_w, s_ws = f["faction_3"]["wins"], f["faction_3"]["win_share"]

        c_s, l_s, s_s = f["faction_1"]["sieges"], f["faction_2"]["sieges"], f["faction_3"]["sieges"]
        c_c, l_c, s_c = f["faction_1"]["captures"], f["faction_2"]["captures"], f["faction_3"]["captures"]

        c_win_str = f"{c_w} ({c_ws*100:.1f}%)"
        l_win_str = f"{l_w} ({l_ws*100:.1f}%)"
        s_win_str = f"{s_w} ({s_ws*100:.1f}%)"

        siege_str = f"{c_s}/{l_s}/{s_s}"
        cap_str = f"{c_c}/{l_c}/{s_c}"
        any_siege = f"{r['games_with_any_siege']}/{r['seeds_count']}"

        lines.append(
            f"| `{r['variant']}` | {t_str} | {rate_str} | {far_str} | {c_win_str} | {l_win_str} | {s_win_str} | {siege_str} | {cap_str} | {s_s} | {any_siege} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default="0-39", help="Seed range or list, e.g. 0-39 (default: 0-39)")
    parser.add_argument("--turns", type=int, default=30, help="Number of turns per game (default: 30)")
    parser.add_argument("--scenario", default="default", help="Scenario name (default: default)")
    parser.add_argument("--out-dir", default="docs/evals/rule", help="Output directory for raw JSON files")
    args = parser.parse_args(argv)

    seeds = parse_seeds(args.seeds)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    base = combat.RULESETS["softer_pool2_econ2"]

    rates = [0.0, 0.25, 0.5, 0.75, 1.0]
    tier_sets = [
        ("koei", True),
        ("flat", "flat"),
    ]

    print(f"=== Starting Economic Parameter Sweep ({len(seeds)} seeds x {args.turns} turns) ===")
    initial_results: list[dict[str, Any]] = []

    # 1. 10 combinations: 5 rates x 2 tier sets (far_march_factor=1.0)
    for t_label, t_val in tier_sets:
        for rate in rates:
            name = f"econ_sweep_{t_label}_r{rate}_far1.0"
            var_rule = dataclasses.replace(
                base,
                name=name,
                cap_tiers=t_val,
                march_food_rate=rate,
                far_march_factor=1.0,
            )
            print(f"Running variant {name}...", flush=True)
            res = evaluate_variant(var_rule, seeds, turns=args.turns, scenario=args.scenario)
            initial_results.append(res)

            # Save raw variant JSON
            v_path = out_dir / f"{name}_s{seeds[0]}-{seeds[-1]}.json"
            with open(v_path, "w", encoding="utf-8") as fp:
                json.dump(res, fp, ensure_ascii=False, indent=2)

    # 2. Identify the best two variants to test far_march_factor in {1.0, 0.75}
    # Pick the best candidate with active march_food (rate > 0) from each tier set (Koei & Flat)
    koei_candidates = [r for r in initial_results if r["rules"]["cap_tiers"] is True and r["rules"]["march_food_rate"] > 0]
    flat_candidates = [r for r in initial_results if r["rules"]["cap_tiers"] == "flat" and r["rules"]["march_food_rate"] > 0]
    best_koei = min(koei_candidates, key=balance_score)
    best_flat = min(flat_candidates, key=balance_score)
    best_two = [best_koei, best_flat]

    print("\n=== Top Candidates from 10 Grid (Koei & Flat) ===")
    for idx, b in enumerate(best_two, 1):
        f = b["factions"]
        print(
            f"  Candidate {idx}: {b['variant']} (Score: {balance_score(b):.4f}) -> "
            f"Wins: 曹={f['faction_1']['wins']}, 劉={f['faction_2']['wins']}, 孫={f['faction_3']['wins']} | "
            f"Sun sieges={f['faction_3']['sieges']}"
        )

    # 3. For the best two, run far_march_factor=0.75
    far_results: list[dict[str, Any]] = []
    for b in best_two:
        ru = b["rules"]
        t_label = "koei" if ru["cap_tiers"] is True else "flat"
        name = f"econ_sweep_{t_label}_r{ru['march_food_rate']}_far0.75"
        var_rule = dataclasses.replace(
            base,
            name=name,
            cap_tiers=ru["cap_tiers"],
            march_food_rate=ru["march_food_rate"],
            far_march_factor=0.75,
        )
        print(f"\nRunning far-edge variant {name}...", flush=True)
        res = evaluate_variant(var_rule, seeds, turns=args.turns, scenario=args.scenario)
        far_results.append(res)

        v_path = out_dir / f"{name}_s{seeds[0]}-{seeds[-1]}.json"
        with open(v_path, "w", encoding="utf-8") as fp:
            json.dump(res, fp, ensure_ascii=False, indent=2)

    all_results = initial_results + far_results

    # Save summary JSON
    summary_path = out_dir / f"sweep_summary_s{seeds[0]}-{seeds[-1]}.json"
    summary_data = {
        "seeds": f"{seeds[0]}-{seeds[-1]}",
        "seeds_count": len(seeds),
        "turns": args.turns,
        "scenario": args.scenario,
        "best_two_variants": [b["variant"] for b in best_two],
        "variants": [
            {
                "variant": r["variant"],
                "rules": r["rules"],
                "balance_score": round(balance_score(r), 4),
                "games_with_any_siege": r["games_with_any_siege"],
                "total_sieges": r["total_sieges"],
                "total_captures": r["total_captures"],
                "factions": r["factions"],
            }
            for r in all_results
        ],
    }
    with open(summary_path, "w", encoding="utf-8") as fp:
        json.dump(summary_data, fp, ensure_ascii=False, indent=2)

    print(f"\nSaved raw JSON files to {out_dir}")
    print("\n=== Markdown Table ===")
    md_table = format_markdown_table(all_results)
    print(md_table)

    return 0


if __name__ == "__main__":
    sys.exit(main())
