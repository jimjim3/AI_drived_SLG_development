"""Diagnostic: for each siege order the NIM model issues, record the siege_odds it was shown.
Usage: diag_siege_odds.py <model> <n_seeds> <turns> <out.json> [scenario]   (needs NVIDIA_API_KEY)"""
import json, os, sys
from slg.agents.backends import OpenAIChatCompleter
from slg.agents.llm_agent import LLMFactionAgent
from slg.sim.headless import run_headless
rows = []
class Probe(LLMFactionAgent):
    def decide(self, view):
        plan = super().decide(view)
        odds = {o["id"]: o.get("siege_odds", {}) for o in view.to_dict()["cast"] if o.get("siege_odds")}
        for od in plan.orders:
            if od.action == "siege":
                shown = odds.get(od.officer_id, {}).get(od.params.get("to"))
                rows.append({"seed": SEED, "turn": view.turn, "officer": od.officer_id, "to": od.params.get("to"),
                             "troops": od.params.get("troops"), "odds_shown": shown, "memo": od.memo})
        return plan
comp = OpenAIChatCompleter(base_url="https://integrate.api.nvidia.com/v1", model=sys.argv[1], api_key_env="NVIDIA_API_KEY",
                           extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                           http_retries=6, min_interval=3.0)
for SEED in range(int(sys.argv[2])):
    run_headless(seed=SEED, turns=int(sys.argv[3]), agents_by_faction={"faction_2": Probe(comp)},
                 scenario=sys.argv[5] if len(sys.argv) > 5 else "default")
json.dump(rows, open(sys.argv[4], "w"), ensure_ascii=False, indent=1)
sh = [r["odds_shown"] for r in rows if r["odds_shown"] is not None]
print("siege orders:", len(rows), "with odds:", len(sh))
print("below 1.3:", sum(x < 1.3 for x in sh), " 1.3-2:", sum(1.3 <= x < 2 for x in sh), " >=2:", sum(x >= 2 for x in sh))
print("sample:", [(r["turn"], r["odds_shown"], r["memo"]) for r in rows[:8]])
