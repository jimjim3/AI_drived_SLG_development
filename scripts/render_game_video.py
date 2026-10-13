"""Render a headless rule-AI game as a ~28 s map video (CPU only). Usage: python3 scripts/render_game_video.py [seed=3] [turns=20] [out=videos/game.mp4]"""
import random, sys, pathlib
import numpy as np, cv2
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "textbook"))
import fig_common as fc
from fig_common import plt
from slg.agents.rule_based import RuleBasedAgent
from slg.engine.game import Game, compute_winner
from slg.engine.initial_state import build_initial_state

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 3
turns = int(sys.argv[2]) if len(sys.argv) > 2 else 20
out = sys.argv[3] if len(sys.argv) > 3 else "videos/game.mp4"
POS = {"hanzhong": (1.4, 2.6), "wancheng": (3.4, 3.8), "luoyang": (4.2, 6.4), "chenliu": (7.2, 7.2), "xuchang": (7.0, 4.8),
       "xiangyang": (5.6, 2.2), "jianye": (8.8, 3.4), "wujun": (9.8, 2.1), "kuaiji": (9.8, 0.7)}
COL = {"faction_1": "#2b5fa8", "faction_2": "#2f7d5b", "faction_3": "#d9822b"}
SC = sys.argv[4] if len(sys.argv) > 4 else "default"
state = build_initial_state(scenario=SC); rng = random.Random(seed)
agents = {f: RuleBasedAgent("balanced") for f in sorted(state.factions)}
game = Game(state, agents, rng)
fname = {k: v.name for k, v in state.factions.items()}

def frame(st, turn, evs, hl):
    fig = plt.figure(figsize=(12.8, 7.2), dpi=100); ax = fig.add_axes([0.02, 0.02, 0.64, 0.86]); ax.set_xlim(0, 11); ax.set_ylim(0, 8.5); ax.axis("off")
    for a, nb in st.adjacency.items():
        for b in nb:
            if a < b: ax.plot(*zip(POS[a], POS[b]), color="#9ca3af", lw=2, zorder=1)
    for a, b in hl: ax.plot(*zip(POS[a], POS[b]), color="#b8342f", lw=5, zorder=2)
    for cid, (x, y) in POS.items():
        c = st.cities[cid]; col = COL[c.owner]
        ax.add_patch(plt.Rectangle((x - 1.0, y - 0.55), 2.0, 1.1, fc="white", ec=col, lw=3, zorder=3))
        ax.text(x, y + 0.2, f"{c.name}（{fname[c.owner]}）", ha="center", va="center", fontsize=11, color=col, weight="bold", zorder=4)
        ax.text(x, y - 0.22, f"兵 {c.troops}  金 {c.gold}", ha="center", va="center", fontsize=10, zorder=4)
    fig.text(0.02, 0.94, f"AI 三國志　第 {turn} 回合 / {turns}", fontsize=20, weight="bold", color=fc.NAVY)
    ax2 = fig.add_axes([0.69, 0.1, 0.29, 0.78]); ax2.axis("off"); ax2.set_xlim(0, 1); ax2.set_ylim(0, 1)
    y = 0.97; ax2.text(0, y, "勢力", fontsize=13, weight="bold"); y -= 0.06
    for f in sorted(st.factions):
        cs = st.cities_of(f); ax2.text(0, y, f"{fname[f]}：{len(cs)} 城　兵 {sum(c.troops for c in cs)}", fontsize=12, color=COL[f]); y -= 0.055
    y -= 0.03; ax2.text(0, y, "本回合要事", fontsize=13, weight="bold"); y -= 0.06
    for t in evs[:9]: ax2.text(0, y, t, fontsize=11, color="#b8342f" if "攻" in t or "佔" in t else "black"); y -= 0.058
    fig.canvas.draw(); im = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy(); plt.close(fig); return cv2.cvtColor(im, cv2.COLOR_RGB2BGR)

frames = [(build_initial_state(scenario=SC), 0, ["開局：三勢力各據三城"], [])]
for _ in range(turns):
    n0 = len(game.events); st = game.step(); new = game.events[n0:]; evs = []; hl = []
    for e in new:
        if e.captured_city:
            evs.append(f"{fname[e.faction_id]}攻佔{st.cities[e.captured_city].name}"); hl.append((e.city_id, e.captured_city))
        elif e.action == "siege":
            tg = next((k for k, c in st.cities.items() if c.name in e.detail), None)
            evs.append(f"{fname[e.faction_id]}攻{st.cities[tg].name if tg else ''}失利：" + ("守軍擊退" if "repelled" in e.detail else e.detail[:12]))
            if tg: hl.append((e.city_id, tg))
    from collections import Counter
    ZH = {"rest": "休息", "recruit": "徵兵", "develop_agri": "農業", "develop_commerce": "商業", "develop_defense": "城防", "siege": "攻城"}
    cnt = Counter(e.action for e in new)
    evs.append("行動：" + "、".join(f"{ZH.get(k, k)}{v}" for k, v in cnt.most_common(5)))
    frames.append((st, st.turn, evs, hl))
FPS, HOLD = 10, int(28 * 10 / (turns + 1))
w = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (1280, 720))
for st, t, evs, hl in frames:
    im = frame(st, t, evs, hl)
    for _ in range(HOLD): w.write(im)
w.release()
fs = frames[-1][0]; print("winner", compute_winner(fs), "frames", len(frames) * HOLD, "->", out)
