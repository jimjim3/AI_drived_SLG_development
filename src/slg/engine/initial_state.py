"""Deterministic initial game state for scenario v3.

Three factions, nine cities, forty-two officers:
  - faction_1 (曹操 / Cao Cao) owns 許昌, 陳留, and 襄陽
  - faction_2 (劉備 / Liu Bei) owns 洛陽, 宛城, and 漢中
  - faction_3 (孫權 / Sun Quan) owns 建業, 吳郡, and 會稽
"""

from __future__ import annotations

import dataclasses

from ..schema import (
    CityState,
    FactionState,
    GameState,
    OfficerState,
)


FACTION_IDS = ("faction_1", "faction_2", "faction_3")


def parse_scenario(scenario: str) -> tuple[str, str | None]:
    """Split a scenario id into (kind, favored_faction).

    "default" -> ("default", None); "advantage" -> ("advantage", "faction_2") (the original
    Liu Bei attack scenario, kept so old logs/evals replay unchanged);
    "advantage:faction_N" -> the same boost given to faction N.
    """
    if scenario == "default":
        return "default", None
    if scenario == "advantage":
        return "advantage", "faction_2"
    kind, _, fid = scenario.partition(":")
    if kind == "advantage" and fid in FACTION_IDS:
        return "advantage", fid
    raise ValueError(f"Unknown scenario: {scenario!r}")


def resolve_scenario(scenario: str, player_faction: str) -> str:
    """Scenario id for a human who picked `player_faction`: the attack scenario favors the player's lord."""
    kind, _ = parse_scenario(scenario)
    if kind == "advantage":
        if player_faction not in FACTION_IDS:
            raise ValueError(f"unknown faction {player_faction!r}")
        return f"advantage:{player_faction}"
    return scenario


SUN_SECOND_ENTRANCE = "+sun2"  # experiment: give 孫權 a second land entrance (吳郡—襄陽)


SWAP13 = "+swap13"  # experiment: faction_1 and faction_3 trade cities and officers (ids/seats stay)


SWAPRES13 = "+swapres13"  # experiment: factions 1 and 3 trade city resources (ranked by troops), geography stays
SWAPOFF13 = "+swapoff13"  # experiment: factions 1 and 3 trade officer abilities (ranked by war+leadership), geography stays


def _swap_ranked(items, key, fields, replace_fn):
    """Pair the two ranked lists and exchange ``fields`` between pairs."""
    a, b = items
    a = sorted(a, key=key, reverse=True)
    b = sorted(b, key=key, reverse=True)
    out = {}
    for x, y in zip(a, b):
        out[x[0]] = replace_fn(x[1], {f: getattr(y[1], f) for f in fields})
        out[y[0]] = replace_fn(y[1], {f: getattr(x[1], f) for f in fields})
    return out


def build_initial_state(scenario: str = "default") -> GameState:
    swapres13 = scenario.endswith(SWAPRES13)
    scenario = scenario[: -len(SWAPRES13)] if swapres13 else scenario
    swapoff13 = scenario.endswith(SWAPOFF13)
    scenario = scenario[: -len(SWAPOFF13)] if swapoff13 else scenario
    swap13 = scenario.endswith(SWAP13)
    scenario = scenario[: -len(SWAP13)] if swap13 else scenario
    sun2 = scenario.endswith(SUN_SECOND_ENTRANCE)
    scenario = scenario[: -len(SUN_SECOND_ENTRANCE)] if sun2 else scenario
    kind, favored = parse_scenario(scenario)

    factions = {
        "faction_1": FactionState("faction_1", "曹操", True),
        "faction_2": FactionState("faction_2", "劉備", True),
        "faction_3": FactionState("faction_3", "孫權", True),
    }

    cities = {
        # faction_1
        "xuchang": CityState(
            "xuchang", "許昌", "faction_1",
            agriculture=550, commerce=550, defense=150,
            gold=1000, food=1000, troops=1400,
        ),
        "chenliu": CityState(
            "chenliu", "陳留", "faction_1",
            agriculture=450, commerce=450, defense=120,
            gold=600, food=600, troops=800,
        ),
        "xiangyang": CityState(
            "xiangyang", "襄陽", "faction_1",
            agriculture=500, commerce=500, defense=150,
            gold=800, food=800, troops=1200,
        ),
        # faction_2
        "luoyang": CityState(
            "luoyang", "洛陽", "faction_2",
            agriculture=550, commerce=550, defense=120,
            gold=900, food=900, troops=1100,
        ),
        "wancheng": CityState(
            "wancheng", "宛城", "faction_2",
            agriculture=450, commerce=450, defense=120,
            gold=600, food=600, troops=700,
        ),
        "hanzhong": CityState(
            "hanzhong", "漢中", "faction_2",
            agriculture=450, commerce=450, defense=120,
            gold=600, food=600, troops=700,
        ),
        # faction_3
        "jianye": CityState(
            "jianye", "建業", "faction_3",
            agriculture=550, commerce=550, defense=120,
            gold=900, food=900, troops=1200,
        ),
        "wujun": CityState(
            "wujun", "吳郡", "faction_3",
            agriculture=450, commerce=450, defense=120,
            gold=600, food=600, troops=800,
        ),
        "kuaiji": CityState(
            "kuaiji", "會稽", "faction_3",
            agriculture=450, commerce=450, defense=120,
            gold=600, food=600, troops=800,
        ),
    }

    officers = {
        # faction_1 (14 officers: 6 xuchang, 2 chenliu, 6 xiangyang)
        "xun_yu": OfficerState(
            "xun_yu", "荀彧", "faction_1", "xuchang",
            politics=95, war=30, leadership=60, loyalty=90, ambition=30,
        ),
        "xiahou_dun": OfficerState(
            "xiahou_dun", "夏侯惇", "faction_1", "xuchang",
            politics=40, war=85, leadership=85, loyalty=85, ambition=40,
        ),
        "yu_jin": OfficerState(
            "yu_jin", "于禁", "faction_1", "xuchang",
            politics=45, war=78, leadership=78, loyalty=80, ambition=45,
        ),
        "dian_wei": OfficerState(
            "dian_wei", "典韋", "faction_1", "xuchang",
            politics=20, war=90, leadership=75, loyalty=80, ambition=50,
        ),
        "cao_ren": OfficerState(
            "cao_ren", "曹仁", "faction_1", "chenliu",
            politics=50, war=80, leadership=80, loyalty=88, ambition=35,
        ),
        "li_dian": OfficerState(
            "li_dian", "李典", "faction_1", "chenliu",
            politics=60, war=70, leadership=70, loyalty=82, ambition=30,
        ),
        "yue_jin": OfficerState(
            "yue_jin", "樂進", "faction_1", "xiangyang",
            politics=55, war=80, leadership=72, loyalty=80, ambition=50,
        ),
        "cheng_yu": OfficerState(
            "cheng_yu", "程昱", "faction_1", "xiangyang",
            politics=60, war=75, leadership=68, loyalty=80, ambition=50,
        ),
        "guo_jia": OfficerState(
            "guo_jia", "郭嘉", "faction_1", "xuchang",
            politics=92, war=20, leadership=55, loyalty=90, ambition=30,
        ),
        "jia_xu": OfficerState(
            "jia_xu", "賈詡", "faction_1", "xiangyang",
            politics=88, war=35, leadership=60, loyalty=80, ambition=35,
        ),
        "xu_chu": OfficerState(
            "xu_chu", "許褚", "faction_1", "xuchang",
            politics=20, war=92, leadership=70, loyalty=90, ambition=25,
        ),
        "xiahou_yuan": OfficerState(
            "xiahou_yuan", "夏侯淵", "faction_1", "xiangyang",
            politics=40, war=84, leadership=80, loyalty=88, ambition=35,
        ),
        "zhang_he": OfficerState(
            "zhang_he", "張郃", "faction_1", "xiangyang",
            politics=45, war=82, leadership=78, loyalty=82, ambition=35,
        ),
        "zhang_liao": OfficerState(
            "zhang_liao", "張遼", "faction_1", "xiangyang",
            politics=45, war=85, leadership=76, loyalty=85, ambition=35,
        ),

        # faction_2 (14 officers: 3 luoyang, 6 wancheng, 5 hanzhong)
        "zhuge_liang": OfficerState(
            "zhuge_liang", "諸葛亮", "faction_2", "luoyang",
            politics=98, war=60, leadership=75, loyalty=95, ambition=20,
        ),
        "guan_yu": OfficerState(
            "guan_yu", "關羽", "faction_2", "luoyang",
            politics=65, war=95, leadership=90, loyalty=92, ambition=30,
        ),
        "zhang_fei": OfficerState(
            "zhang_fei", "張飛", "faction_2", "luoyang",
            politics=30, war=92, leadership=85, loyalty=90, ambition=40,
        ),
        "zhao_yun": OfficerState(
            "zhao_yun", "趙雲", "faction_2", "wancheng",
            politics=50, war=93, leadership=88, loyalty=93, ambition=25,
        ),
        "huang_zhong": OfficerState(
            "huang_zhong", "黃忠", "faction_2", "wancheng",
            politics=40, war=88, leadership=82, loyalty=85, ambition=35,
        ),
        "wei_yan": OfficerState(
            "wei_yan", "魏延", "faction_2", "hanzhong",
            politics=40, war=85, leadership=78, loyalty=85, ambition=45,
        ),
        "pang_tong": OfficerState(
            "pang_tong", "龐統", "faction_2", "wancheng",
            politics=92, war=40, leadership=65, loyalty=90, ambition=25,
        ),
        "fa_zheng": OfficerState(
            "fa_zheng", "法正", "faction_2", "wancheng",
            politics=88, war=45, leadership=70, loyalty=88, ambition=40,
        ),
        "ma_chao": OfficerState(
            "ma_chao", "馬超", "faction_2", "wancheng",
            politics=30, war=93, leadership=85, loyalty=80, ambition=45,
        ),
        "jiang_wei": OfficerState(
            "jiang_wei", "姜維", "faction_2", "hanzhong",
            politics=70, war=88, leadership=88, loyalty=90, ambition=40,
        ),
        "ma_liang": OfficerState(
            "ma_liang", "馬良", "faction_2", "hanzhong",
            politics=85, war=25, leadership=50, loyalty=90, ambition=20,
        ),
        "xu_shu": OfficerState(
            "xu_shu", "徐庶", "faction_2", "wancheng",
            politics=88, war=50, leadership=68, loyalty=88, ambition=20,
        ),
        "jian_yong": OfficerState(
            "jian_yong", "簡雍", "faction_2", "hanzhong",
            politics=72, war=25, leadership=45, loyalty=88, ambition=20,
        ),
        "sun_qian": OfficerState(
            "sun_qian", "孫乾", "faction_2", "hanzhong",
            politics=75, war=25, leadership=45, loyalty=88, ambition=20,
        ),

        # faction_3 (14 officers: 6 jianye, 5 wujun, 3 kuaiji)
        "zhou_yu": OfficerState(
            "zhou_yu", "周瑜", "faction_3", "jianye",
            politics=85, war=75, leadership=90, loyalty=80, ambition=50,
        ),
        "lu_su": OfficerState(
            "lu_su", "魯肅", "faction_3", "jianye",
            politics=80, war=40, leadership=60, loyalty=80, ambition=50,
        ),
        "taishi_ci": OfficerState(
            "taishi_ci", "太史慈", "faction_3", "jianye",
            politics=45, war=85, leadership=78, loyalty=80, ambition=50,
        ),
        "huang_gai": OfficerState(
            "huang_gai", "黃蓋", "faction_3", "wujun",
            politics=50, war=78, leadership=70, loyalty=80, ambition=50,
        ),
        "gan_ning": OfficerState(
            "gan_ning", "甘寧", "faction_3", "wujun",
            politics=30, war=92, leadership=80, loyalty=80, ambition=50,
        ),
        "zhou_tai": OfficerState(
            "zhou_tai", "周泰", "faction_3", "wujun",
            politics=40, war=80, leadership=75, loyalty=80, ambition=50,
        ),
        "lu_xun": OfficerState(
            "lu_xun", "陸遜", "faction_3", "jianye",
            politics=88, war=75, leadership=92, loyalty=90, ambition=30,
        ),
        "lu_meng": OfficerState(
            "lu_meng", "呂蒙", "faction_3", "jianye",
            politics=75, war=82, leadership=88, loyalty=88, ambition=35,
        ),
        "zhang_zhao": OfficerState(
            "zhang_zhao", "張昭", "faction_3", "jianye",
            politics=90, war=20, leadership=45, loyalty=85, ambition=30,
        ),
        "ling_tong": OfficerState(
            "ling_tong", "凌統", "faction_3", "wujun",
            politics=40, war=84, leadership=78, loyalty=85, ambition=40,
        ),
        "cheng_pu": OfficerState(
            "cheng_pu", "程普", "faction_3", "wujun",
            politics=65, war=80, leadership=80, loyalty=88, ambition=30,
        ),
        "han_dang": OfficerState(
            "han_dang", "韓當", "faction_3", "kuaiji",
            politics=45, war=78, leadership=75, loyalty=82, ambition=35,
        ),
        "gu_yong": OfficerState(
            "gu_yong", "顧雍", "faction_3", "kuaiji",
            politics=85, war=20, leadership=45, loyalty=88, ambition=20,
        ),
        "zhu_ran": OfficerState(
            "zhu_ran", "朱然", "faction_3", "kuaiji",
            politics=60, war=80, leadership=82, loyalty=85, ambition=35,
        ),
    }

    # Scenario map (bidirectional):
    #   chenliu - xuchang - luoyang - wancheng - hanzhong
    #              |          |
    #            xiangyang ---+
    #              |
    #            jianye - wujun - kuaiji
    adjacency = {
        "chenliu": ("xuchang",),
        "xuchang": ("chenliu", "luoyang", "xiangyang"),
        "luoyang": ("xuchang", "xiangyang", "wancheng"),
        "xiangyang": ("luoyang", "xuchang", "jianye"),
        "jianye": ("xiangyang", "wujun"),
        "wancheng": ("luoyang", "hanzhong"),
        "hanzhong": ("wancheng",),
        "wujun": ("jianye", "kuaiji"),
        "kuaiji": ("wujun",),
    }

    if kind == "advantage":
        f2_city_ids = {cid for cid, c in cities.items() if c.owner == favored}
        f2_neighbor_enemy_ids = set()
        for f2_cid in f2_city_ids:
            for nbr in adjacency.get(f2_cid, ()):
                if cities[nbr].owner != favored:
                    f2_neighbor_enemy_ids.add(nbr)

        cities = {
            cid: dataclasses.replace(
                c,
                troops=int(c.troops * 2.5),
                gold=int(c.gold * 1.5),
            )
            if c.owner == favored
            else (
                dataclasses.replace(c, troops=int(c.troops * 0.5))
                if cid in f2_neighbor_enemy_ids
                else c
            )
            for cid, c in cities.items()
        }

    if swap13:
        flip = {"faction_1": "faction_3", "faction_3": "faction_1"}
        cities = {cid: dataclasses.replace(c, owner=flip.get(c.owner, c.owner)) for cid, c in cities.items()}
        officers = {oid: dataclasses.replace(o, faction_id=flip.get(o.faction_id, o.faction_id))
                    for oid, o in officers.items()}
    if swapres13:
        f1 = [(cid, c) for cid, c in cities.items() if c.owner == "faction_1"]
        f3 = [(cid, c) for cid, c in cities.items() if c.owner == "faction_3"]
        cities.update(_swap_ranked((f1, f3), lambda t: t[1].troops,
                                   ("agriculture", "commerce", "defense", "gold", "food", "troops"),
                                   lambda c, kw: dataclasses.replace(c, **kw)))
    if swapoff13:
        f1 = [(oid, o) for oid, o in officers.items() if o.faction_id == "faction_1"]
        f3 = [(oid, o) for oid, o in officers.items() if o.faction_id == "faction_3"]
        officers.update(_swap_ranked((f1, f3), lambda t: (t[1].war + t[1].leadership, t[0]),
                                     ("politics", "war", "leadership", "loyalty", "ambition"),
                                     lambda o, kw: dataclasses.replace(o, **kw)))
    if sun2:
        adjacency["wujun"] = adjacency["wujun"] + ("xiangyang",)
        adjacency["xiangyang"] = adjacency["xiangyang"] + ("wujun",)
    return GameState(turn=0, factions=factions, cities=cities, officers=officers,
                     adjacency=adjacency)
