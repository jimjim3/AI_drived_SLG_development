"""Deterministic initial game state for the M0b skeleton.

Three factions, five cities, twenty officers:
  - faction_1 (曹操 / Cao Cao) owns 許昌, 陳留, and 襄陽
  - faction_2 (劉備 / Liu Bei) owns 洛陽
  - faction_3 (孫權 / Sun Quan) owns 建業
"""

from __future__ import annotations

from ..schema import (
    CityState,
    FactionState,
    GameState,
    OfficerState,
)


def build_initial_state() -> GameState:
    factions = {
        "faction_1": FactionState("faction_1", "曹操", True),
        "faction_2": FactionState("faction_2", "劉備", True),
        "faction_3": FactionState("faction_3", "孫權", True),
    }

    cities = {
        "xuchang": CityState(
            "xuchang", "許昌", "faction_1",
            agriculture=500, commerce=500, defense=150,
            gold=1000, food=1000, troops=1000,
        ),
        "chenliu": CityState(
            "chenliu", "陳留", "faction_1",
            agriculture=400, commerce=400, defense=100,
            gold=500, food=500, troops=500,
        ),
        "xiangyang": CityState(
            "xiangyang", "襄陽", "faction_1",
            agriculture=450, commerce=400, defense=120,
            gold=700, food=700, troops=800,
        ),
        "luoyang": CityState(
            "luoyang", "洛陽", "faction_2",
            agriculture=450, commerce=450, defense=150,
            gold=800, food=800, troops=1000,
        ),
        "jianye": CityState(
            "jianye", "建業", "faction_3",
            agriculture=500, commerce=550, defense=120,
            gold=900, food=900, troops=900,
        ),
    }

    officers = {
        # faction_1
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
        # faction_2
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
            "zhao_yun", "趙雲", "faction_2", "luoyang",
            politics=50, war=93, leadership=88, loyalty=93, ambition=25,
        ),
        "huang_zhong": OfficerState(
            "huang_zhong", "黃忠", "faction_2", "luoyang",
            politics=40, war=88, leadership=82, loyalty=85, ambition=35,
        ),
        "wei_yan": OfficerState(
            "wei_yan", "魏延", "faction_2", "luoyang",
            politics=40, war=85, leadership=78, loyalty=85, ambition=45,
        ),
        # faction_3
        "zhou_yu": OfficerState(
            "zhou_yu", "周瑜", "faction_3", "jianye",
            politics=85, war=75, leadership=90, loyalty=80, ambition=50,
        ),
        "lu_su": OfficerState(
            "lu_su", "魯粛", "faction_3", "jianye",
            politics=80, war=40, leadership=60, loyalty=80, ambition=50,
        ),
        "taishi_ci": OfficerState(
            "taishi_ci", "太史慈", "faction_3", "jianye",
            politics=45, war=85, leadership=78, loyalty=80, ambition=50,
        ),
        "huang_gai": OfficerState(
            "huang_gai", "黄蓋", "faction_3", "jianye",
            politics=50, war=78, leadership=70, loyalty=80, ambition=50,
        ),
        "gan_ning": OfficerState(
            "gan_ning", "甘寧", "faction_3", "jianye",
            politics=30, war=92, leadership=80, loyalty=80, ambition=50,
        ),
        "zhou_tai": OfficerState(
            "zhou_tai", "周泰", "faction_3", "jianye",
            politics=40, war=80, leadership=75, loyalty=80, ambition=50,
        ),
    }

    return GameState(turn=0, factions=factions, cities=cities, officers=officers)
