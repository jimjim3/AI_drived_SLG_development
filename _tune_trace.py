import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

from _tune_harness import make_state, run_game

CITIES = {
    "xuchang": dict(commerce=1500, defense=75, gold=3000, food=2000, troops=1000),
    "chenliu": dict(commerce=1200, defense=50, gold=2400, food=1500, troops=800),
    "xiangyang": dict(commerce=1200, defense=60, gold=2400, food=1500, troops=700),
    "luoyang": dict(commerce=1500, defense=75, gold=3000, food=2000, troops=1000),
    "jianye": dict(commerce=1650, defense=60, gold=3300, food=2000, troops=900),
}

if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    state = make_state(CITIES)
    final, game = run_game(state, seed, 30, ("balanced", "aggressive", "turtle"))
    for e in game.log_entries:
        if e.action in ("siege",) or e.turn in (1, 2, 3):
            p = dict(e.params)
            print(e.turn, e.faction_id, e.officer_id, e.action, p,
                  "| cap:", e.event.captured_city if e.event else None,
                  "|", (e.event.detail if e.event else ""))
    print("---- final")
    for cid in sorted(final.cities):
        c = final.city(cid)
        print(cid, c.owner, "agri", c.agriculture, "com", c.commerce, "def", c.defense,
              "gold", c.gold, "food", c.food, "troops", c.troops)
    from slg.engine.game import compute_winner
    print("winner:", compute_winner(final))
