import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

from _tune_harness import make_state, run_game
from slg.engine.game import compute_winner
from slg.agents.rule_based import RuleBasedAgent

CITIES = {
    "xuchang": dict(agriculture=300, commerce=1700, defense=30, gold=3000, food=1800, troops=400),
    "chenliu": dict(agriculture=350, commerce=1400, defense=50, gold=2400, food=1500, troops=700),
    "xiangyang": dict(agriculture=450, commerce=1400, defense=30, gold=2400, food=1500, troops=400),
    "luoyang": dict(agriculture=800, commerce=1700, defense=75, gold=3000, food=3000, troops=1500),
    "jianye": dict(agriculture=800, commerce=1800, defense=40, gold=3300, food=3000, troops=1200),
}


def main(seed):
    RuleBasedAgent.RECRUIT_TARGET = 300
    state = make_state(CITIES)
    final, game = run_game(state, seed, 30, ("balanced", "aggressive", "turtle"))
    for e in game.log_entries:
        if e.action == "siege":
            print(e.turn, e.faction_id, e.officer_id, e.event.city_id, dict(e.params),
                  "cap:", e.event.captured_city, "|", e.event.detail)
    print("---- final")
    for cid in sorted(final.cities):
        c = final.city(cid)
        print(cid, c.owner, "troops", c.troops, "agri", c.agriculture, "def", c.defense)
    print("winner:", compute_winner(final))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
