import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

from _tune_harness import scan

CONFIGS = {
    "c1_gold3_def_half_xiangyang700": {
        "cities": {
            "xuchang": dict(commerce=1500, defense=75, gold=3000, food=2000, troops=1000),
            "chenliu": dict(commerce=1200, defense=50, gold=2400, food=1500, troops=800),
            "xiangyang": dict(commerce=1200, defense=60, gold=2400, food=1500, troops=700),
            "luoyang": dict(commerce=1500, defense=75, gold=3000, food=2000, troops=1000),
            "jianye": dict(commerce=1650, defense=60, gold=3300, food=2000, troops=900),
        },
    },
    "c2_rebal_recruit300": {
        "cities": {
            "xuchang": dict(agriculture=400, commerce=1500, defense=75, gold=3000, food=2000, troops=800),
            "chenliu": dict(agriculture=400, commerce=1200, defense=50, gold=2400, food=1500, troops=800),
            "xiangyang": dict(agriculture=450, commerce=1200, defense=60, gold=2400, food=1500, troops=700),
            "luoyang": dict(agriculture=600, commerce=1500, defense=75, gold=3000, food=2500, troops=1200),
            "jianye": dict(agriculture=600, commerce=1650, defense=60, gold=3300, food=2500, troops=1000),
        },
        "recruit_target": 300,
    },
    "c3_weak_hub_f2growth": {
        "cities": {
            "xuchang": dict(agriculture=400, commerce=1600, defense=75, gold=3000, food=2000, troops=800),
            "chenliu": dict(agriculture=350, commerce=1300, defense=50, gold=2400, food=1500, troops=700),
            "xiangyang": dict(agriculture=450, commerce=1300, defense=30, gold=2400, food=1500, troops=400),
            "luoyang": dict(agriculture=800, commerce=1600, defense=75, gold=3000, food=3000, troops=1500),
            "jianye": dict(agriculture=800, commerce=1700, defense=40, gold=3300, food=3000, troops=1200),
        },
        "recruit_target": 300,
    },
    "c4_weak_xuchang_recruit200": {
        "cities": {
            "xuchang": dict(agriculture=300, commerce=1700, defense=30, gold=3000, food=1800, troops=400),
            "chenliu": dict(agriculture=350, commerce=1400, defense=50, gold=2400, food=1500, troops=700),
            "xiangyang": dict(agriculture=450, commerce=1400, defense=30, gold=2400, food=1500, troops=400),
            "luoyang": dict(agriculture=800, commerce=1700, defense=75, gold=3000, food=3000, troops=1500),
            "jianye": dict(agriculture=800, commerce=1800, defense=40, gold=3300, food=3000, troops=1200),
        },
        "recruit_target": 200,
    },
}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else list(CONFIGS)[0]
    cfg = CONFIGS[which]
    print("==", which)
    scan(**cfg)
