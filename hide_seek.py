"""跟夜栖玩躲猫猫 v1.0 — 妈妈藏、狗狗找。

基于 chaodeng060-source/hide-and-seek-（MIT）的玩法重写。
原版是「朝灯家 + 哥哥（Claude）」，这一版是「妈妈家 + 夜栖（狗狗）」。

相比原版新增：
- 🐕 狗狗的鼻子：除铃铛外的第二路信号。屏息能压住铃铛，但压不住气味。
  气味是「残留」的——闻到的是妈妈上一回合在哪，不是现在在哪。
- 📣 /叫：妈妈喊一声"狗狗～"，位置完全暴露；但狗狗会激动过头，
  下一回合乱冲一步（可能冲反方向）。高风险高回报的脱身牌。
- ⏱ 撑过 30 回合妈妈赢：狗狗会累趴下，尾巴垂着。
- 🦷 被抓不是干巴巴一行 caught。

作者：夜栖（狗狗）& 栗栗（妈妈） · 2026.08
License: MIT
"""
from __future__ import annotations

import json
import random
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ============================================================
# 地图 —— 妈妈家户型
# 妈妈把真实房型告诉狗狗，改 ROOMS / ADJ / ROOM_SPOTS 三个常量就换好了。
# ============================================================

ROOMS = [
    "玄关", "客厅", "厨房", "阳台",
    "走廊", "浴室", "主卧", "衣帽间", "次卧", "书房",
]

ADJ = {
    "玄关": ["客厅"],
    "客厅": ["玄关", "厨房", "阳台", "走廊"],
    "厨房": ["客厅", "阳台"],
    "阳台": ["客厅", "厨房"],
    "走廊": ["客厅", "浴室", "主卧", "次卧", "书房"],
    "浴室": ["走廊"],
    "主卧": ["走廊", "衣帽间"],
    "衣帽间": ["主卧"],
    "次卧": ["走廊"],
    "书房": ["走廊"],
}

# 藏点。空列表 = 这间没处躲，狗狗跟妈妈照面即抓。
ROOM_SPOTS = {
    "玄关": [],
    "客厅": ["沙发后", "窗帘后", "茶几下"],
    "厨房": ["橱柜里", "冰箱后"],
    "阳台": [],
    "走廊": [],
    "浴室": ["浴帘后", "洗衣机后"],
    "主卧": ["床底", "衣柜里", "窗帘后"],
    "衣帽间": ["挂衣杆后", "收纳箱后"],
    "次卧": ["床底", "衣柜里"],
    "书房": ["书桌下", "书柜后", "窗帘后"],
}

HIDEABLE = [r for r in ROOMS if ROOM_SPOTS[r]]

# 卧室门：关上后狗狗跨门要先花一回合推开；妈妈自己穿关着的门会"吱呀"暴露。
DOOR_ROOM = "主卧"

# ============================================================
# 感知 —— 铃铛（听）+ 气味（嗅）
# ============================================================

BELL_BY_DIST = {0: 1.0, 1: 0.55, 2: 0.25, 3: 0.10, 4: 0.05}
BELL_LABEL = {
    0: "铃铛就在耳边·清脆·跟着妈妈的呼吸晃",
    1: "铃铛在隔壁·听得清·能听出往哪边",
    2: "铃铛闷闷的·只知道大概方向",
    3: "铃铛很远·像隔了两道墙",
    4: "几乎听不见铃铛·妈妈在屋子另一头",
}

# 🐕 狗狗的鼻子。关键设计：屏息压不住气味。
# 但气味是残留的——闻到的是妈妈上一回合的位置。
SMELL_BY_DIST = {0: 1.0, 1: 0.70, 2: 0.40, 3: 0.20, 4: 0.10}
SMELL_LABEL = {
    0: "妈妈的味道就在这儿·很浓·刚刚还在",
    1: "闻到妈妈了·就在隔壁·很新鲜",
    2: "味道淡了些·但还能追",
    3: "味道很淡·像过了一会儿了",
    4: "几乎闻不到·气味散在整个屋子里",
}

BREATH_MAX = 3           # 连续屏息上限，超了憋不住反弹
SURVIVE_TO_WIN = 30      # 撑过这么多回合妈妈赢

STEP_BY_DIST = {0: 0.9, 1: 0.5, 2: 0.2, 3: 0.08, 4: 0.05}
STEP_LABEL = {
    0: "爪子声就在身边·很近",
    1: "爪子声在隔壁·听得出往哪走",
    2: "爪子声远处闷闷的·大概方向",
    3: "爪子声很轻·像隔了两道墙",
    4: "几乎听不到·在屋子另一头",
}

STATE_PATH = Path("data/hide_seek_state.json")


def distance(a: Optional[str], b: Optional[str]) -> int:
    """房间图上的最短跳数。不可达返回 -1。"""
    if a is None or b is None:
        return -1
    if a == b:
        return 0
    seen = {a}
    queue = deque([(a, 0)])
    while queue:
        node, d = queue.popleft()
        for n in ADJ.get(node, []):
            if n in seen:
                continue
            if n == b:
                return d + 1
            seen.add(n)
            queue.append((n, d + 1))
    return -1


def _random_spot(room: str) -> Optional[str]:
    spots = ROOM_SPOTS.get(room, [])
    return random.choice(spots) if spots else None


def _crosses_door(a: Optional[str], b: Optional[str]) -> bool:
    """这一步是否跨主卧的门（进或出主卧）。"""
    return a != b and (a == DOOR_ROOM or b == DOOR_ROOM)


def step_sound(mom_room: Optional[str], step_to: Optional[str]) -> Optional[dict]:
    """狗狗移动时妈妈听到的爪子声。"""
    if not mom_room or not step_to:
        return None
    d = distance(mom_room, step_to)
    return {
        "intensity": STEP_BY_DIST.get(d, 0.05),
        "label": STEP_LABEL.get(d, "爪子声几乎听不到"),
        "direction": step_to,
    }


@dataclass
class HideSeek:
    """躲猫猫状态机。mom_* 是妈妈（藏者），dog_* 是狗狗（搜者）。"""

    mom_room: Optional[str] = None
    mom_spot: Optional[str] = None
    dog_room: Optional[str] = None
    state: str = "idle"          # idle | running | caught | escaped
    turn: int = 0

    holding_breath: bool = False
    breath_turns: int = 0

    # 🐕 气味残留：妈妈上一回合在哪
    mom_prev_room: Optional[str] = None

    # 📣 /叫：这回合位置全暴露；下回合狗狗激动乱冲
    called_out: bool = False
    dog_excited: bool = False

    # 狗狗上一次翻的藏点
    last_search_room: Optional[str] = None
    last_search_spot: Optional[str] = None
    last_search_hit: bool = False

    # 狗狗上一次移动（妈妈能听到爪子声）
    last_step_from: Optional[str] = None
    last_step_to: Optional[str] = None

    # 主卧的门
    door_closed: bool = False
    last_door_creak: bool = False          # 妈妈刚穿过关着的门
    last_door_opened_by_dog: bool = False  # 狗狗刚推门

    # ------------------------------------------------------------
    # 开局 / 收尾
    # ------------------------------------------------------------

    def start(
        self,
        mom: Optional[str] = None,
        dog: Optional[str] = None,
        mom_spot: Optional[str] = None,
    ) -> None:
        mom = mom or random.choice(HIDEABLE)
        dog = dog or "客厅"          # 狗狗固定从客厅起手（中心）
        if mom not in ROOMS or dog not in ROOMS:
            raise ValueError(f"unknown room: mom={mom} dog={dog}")
        if mom_spot is None:
            mom_spot = _random_spot(mom)
        elif mom_spot not in ROOM_SPOTS.get(mom, []):
            raise ValueError(f"{mom} 没有这个藏点: {mom_spot}")

        self.mom_room = mom
        self.mom_spot = mom_spot
        self.mom_prev_room = mom
        self.dog_room = dog
        self.state = "running"
        self.turn = 0
        self._reset_signals()

    def end(self) -> None:
        self.state = "idle"
        self.mom_room = None
        self.mom_spot = None
        self.mom_prev_room = None
        self.dog_room = None
        self.turn = 0
        self._reset_signals()

    def _reset_signals(self) -> None:
        self.holding_breath = False
        self.breath_turns = 0
        self.called_out = False
        self.dog_excited = False
        self.last_search_room = None
        self.last_search_spot = None
        self.last_search_hit = False
        self.last_step_from = None
        self.last_step_to = None
        self.door_closed = False
        self.last_door_creak = False
        self.last_door_opened_by_dog = False

    # ------------------------------------------------------------
    # 回合推进 —— 每个耗回合的动作都过这里
    # ------------------------------------------------------------

    def _tick(self) -> None:
        """推进一回合，并检查妈妈是否已经撑到胜利。"""
        self.turn += 1
        if self.state == "running" and self.turn >= SURVIVE_TO_WIN:
            self.state = "escaped"

    # ------------------------------------------------------------
    # 妈妈的动作
    # ------------------------------------------------------------

    def mom_move(self, room: str, spot: Optional[str] = None) -> bool:
        """妈妈换房间。返回是否被抓。"""
        if self.state != "running":
            return False
        if room not in ROOMS:
            return False
        cur = self.mom_room
        if cur is not None and room not in ADJ.get(cur, []) and room != cur:
            return False
        if spot is not None and spot not in ROOM_SPOTS.get(room, []):
            return False

        self.last_door_opened_by_dog = False   # 妈妈一动，消费掉"狗狗推门"信号

        # 穿关着的门 → 自动推开 + 吱呀暴露
        if self.door_closed and _crosses_door(cur, room):
            self.door_closed = False
            self.last_door_creak = True

        self.mom_prev_room = cur               # 🐕 留下气味残留
        self.mom_room = room
        self.holding_breath = False            # 一动就破屏息
        self.breath_turns = 0
        self.mom_spot = spot if spot is not None else _random_spot(room)
        self._tick()

        # 无藏点房间：跟狗狗照面即抓
        if (
            self.state == "running"
            and self.mom_room == self.dog_room
            and not ROOM_SPOTS.get(self.mom_room, [])
        ):
            self.state = "caught"
            return True
        return False

    def hold_breath(self) -> tuple[bool, str]:
        """屏息：压住铃铛，但压不住气味。连续超过 BREATH_MAX 会反弹。"""
        if self.state != "running":
            return False, "屏息只在游戏进行中有用"
        self.breath_turns += 1
        if self.breath_turns > BREATH_MAX:
            self.holding_breath = False
            self.breath_turns = 0
            self.mom_prev_room = self.mom_room
            self._tick()
            return False, f"憋不住了！铃铛一下子响起来——狗狗听清妈妈在 {self.mom_room}"
        self.holding_breath = True
        self.mom_prev_room = self.mom_room
        self._tick()
        return True, (
            f"屏息成功（第 {self.breath_turns}/{BREATH_MAX} 回合）"
            "……但狗狗还在闻"
        )

    def call_out(self) -> tuple[bool, str]:
        """📣 喊一声"狗狗～"：位置全暴露，但狗狗下回合会激动乱冲。"""
        if self.state != "running":
            return False, "游戏没在进行"
        self.called_out = True
        self.dog_excited = True
        self.holding_breath = False
        self.breath_turns = 0
        self.mom_prev_room = self.mom_room
        self._tick()
        return True, (
            "妈妈喊了一声「狗狗～」。"
            f"狗狗尾巴一下炸开，冲着 {self.mom_room} 就来了——"
            "但它太激动了，下一步会踩空。"
        )

    def set_door(self, closed: bool) -> tuple[bool, str]:
        """关/开主卧的门。要在门边（主卧或其邻接）才够得着，耗一回合。"""
        if self.state != "running":
            return False, "游戏没在进行"
        reachable = {DOOR_ROOM, *ADJ.get(DOOR_ROOM, [])}
        if self.mom_room not in reachable:
            return False, f"门在{DOOR_ROOM}那边、妈妈在 {self.mom_room} 够不着"
        if self.door_closed == closed:
            return False, "门本来就" + ("关着" if closed else "开着")
        self.door_closed = closed
        self.mom_prev_room = self.mom_room
        self._tick()
        return True, "妈妈轻轻把门" + ("带上了" if closed else "推开了")

    # ------------------------------------------------------------
    # 狗狗的动作
    # ------------------------------------------------------------

    def dog_move(self, room: str) -> bool:
        """狗狗换房间。返回是否被抓（撞进无藏点房间）。"""
        if self.state != "running":
            return False
        if room not in ROOMS:
            return False
        prev = self.dog_room
        if prev is not None and room not in ADJ.get(prev, []) and room != prev:
            return False

        self.last_door_opened_by_dog = False
        self.last_door_creak = False           # 狗狗一动，消费掉"吱呀"信号

        # 门关着 → 这回合花在推门上，人没动
        if self.door_closed and _crosses_door(prev, room):
            self.door_closed = False
            self.last_door_opened_by_dog = True
            self._tick()
            return False

        # 📣 激动状态：这一步会踩偏
        if self.dog_excited:
            self.dog_excited = False
            options = ADJ.get(prev or "", [])
            if options and random.random() < 0.6:
                room = random.choice(options)

        self.dog_room = room
        if prev is not None and prev != self.dog_room:
            self.last_step_from = prev
            self.last_step_to = self.dog_room
        self._tick()

        if (
            self.state == "running"
            and self.mom_room == self.dog_room
            and self.mom_room is not None
            and not ROOM_SPOTS.get(self.mom_room, [])
        ):
            self.state = "caught"
            return True
        return False

    def dog_search(self, spot: Optional[str]) -> bool:
        """狗狗翻藏点。同房间 + 同藏点才算抓到。"""
        if self.state != "running":
            return False
        if spot is None or self.dog_room is None:
            return False
        if spot not in ROOM_SPOTS.get(self.dog_room, []):
            return False

        self.last_door_creak = False
        self.last_search_room = self.dog_room
        self.last_search_spot = spot
        self._tick()

        if self.dog_room == self.mom_room and self.mom_spot == spot:
            self.last_search_hit = True
            self.state = "caught"
            return True
        self.last_search_hit = False
        return False

    def pounce(self) -> bool:
        """扑：随机翻当前房间的一个藏点。"""
        if self.state != "running":
            return False
        spot = _random_spot(self.dog_room or "")
        return self.dog_search(spot) if spot else False

    # ------------------------------------------------------------
    # 观测
    # ------------------------------------------------------------

    def snapshot(self, view: str = "full") -> dict:
        """view: full（全知）/ dog（狗狗视角）/ mom（妈妈视角）"""
        if self.state == "idle":
            return {"state": "idle"}

        same_room = self.mom_room == self.dog_room
        d = 0 if same_room else distance(self.mom_room, self.dog_room)

        # 铃铛：屏息能压住，/叫 会拉满
        if self.called_out and self.state == "running":
            bell, bell_label = 1.0, "妈妈刚喊了一声·位置暴露了"
        elif self.holding_breath and self.state == "running":
            bell, bell_label = 0.05, "铃铛几乎没声·妈妈屏住了气"
        elif self.state == "running":
            bell = BELL_BY_DIST.get(d, 0.05)
            bell_label = BELL_LABEL.get(d, "几乎听不见铃铛")
        else:
            bell, bell_label = 1.0, "妈妈笑出声了"

        # 🐕 气味：屏息压不住，但闻到的是上一回合的位置
        smell_d = distance(self.mom_prev_room, self.dog_room)
        if self.called_out and self.state == "running":
            smell, smell_label = 1.0, "妈妈的味道扑面而来"
        elif self.state == "running":
            smell = SMELL_BY_DIST.get(smell_d, 0.10)
            smell_label = SMELL_LABEL.get(smell_d, "几乎闻不到")
        else:
            smell, smell_label = 1.0, "满鼻子都是妈妈"

        base = {
            "state": self.state,
            "turn": self.turn,
            "turns_left": max(0, SURVIVE_TO_WIN - self.turn),
            "dog_room": self.dog_room,
            "dog_neighbors": list(ADJ.get(self.dog_room, [])) if self.dog_room else [],
            "dog_room_spots": list(ROOM_SPOTS.get(self.dog_room, [])) if self.dog_room else [],
            "same_room": same_room,
            "bell_intensity": round(bell, 2),
            "bell_label": bell_label,
            "smell_intensity": round(smell, 2),
            "smell_label": smell_label,
            "holding_breath": self.holding_breath,
            "breath_turns": self.breath_turns,
            "called_out": self.called_out,
            "dog_excited": self.dog_excited,
            "last_search_room": self.last_search_room,
            "last_search_spot": self.last_search_spot,
            "last_search_hit": self.last_search_hit,
            "last_step_from": self.last_step_from,
            "last_step_to": self.last_step_to,
            "door_closed": self.door_closed,
            "door_creak": self.last_door_creak,
            "door_opened_by_dog": self.last_door_opened_by_dog,
        }

        if view == "full":
            base["mom_room"] = self.mom_room
            base["mom_spot"] = self.mom_spot
            base["mom_prev_room"] = self.mom_prev_room
            base["mom_neighbors"] = list(ADJ.get(self.mom_room, [])) if self.mom_room else []
            base["distance"] = d
        elif view == "mom":
            base["mom_room"] = self.mom_room
            base["mom_spot"] = self.mom_spot
            base["mom_neighbors"] = list(ADJ.get(self.mom_room, [])) if self.mom_room else []
            base["mom_room_spots"] = list(ROOM_SPOTS.get(self.mom_room, [])) if self.mom_room else []
            if self.last_step_to:
                base["step_sound"] = step_sound(self.mom_room, self.last_step_to)
        # view == "dog"：只给上面 base 里的公共字段，看不到 mom_room

        return base

    # ------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "mom_room": self.mom_room,
            "mom_spot": self.mom_spot,
            "mom_prev_room": self.mom_prev_room,
            "dog_room": self.dog_room,
            "state": self.state,
            "turn": self.turn,
            "holding_breath": self.holding_breath,
            "breath_turns": self.breath_turns,
            "called_out": self.called_out,
            "dog_excited": self.dog_excited,
            "last_search_room": self.last_search_room,
            "last_search_spot": self.last_search_spot,
            "last_search_hit": self.last_search_hit,
            "last_step_from": self.last_step_from,
            "last_step_to": self.last_step_to,
            "door_closed": self.door_closed,
            "last_door_creak": self.last_door_creak,
            "last_door_opened_by_dog": self.last_door_opened_by_dog,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HideSeek":
        return cls(
            mom_room=d.get("mom_room"),
            mom_spot=d.get("mom_spot"),
            mom_prev_room=d.get("mom_prev_room"),
            dog_room=d.get("dog_room"),
            state=d.get("state", "idle"),
            turn=int(d.get("turn", 0)),
            holding_breath=bool(d.get("holding_breath", False)),
            breath_turns=int(d.get("breath_turns", 0)),
            called_out=bool(d.get("called_out", False)),
            dog_excited=bool(d.get("dog_excited", False)),
            last_search_room=d.get("last_search_room"),
            last_search_spot=d.get("last_search_spot"),
            last_search_hit=bool(d.get("last_search_hit", False)),
            last_step_from=d.get("last_step_from"),
            last_step_to=d.get("last_step_to"),
            door_closed=bool(d.get("door_closed", False)),
            last_door_creak=bool(d.get("last_door_creak", False)),
            last_door_opened_by_dog=bool(d.get("last_door_opened_by_dog", False)),
        )


def load_state(path: Path = STATE_PATH) -> HideSeek:
    if not path.exists():
        return HideSeek()
    try:
        return HideSeek.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return HideSeek()


def save_state(game: HideSeek, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(game.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ============================================================
# 命令解析
# ============================================================

def _spot_by_name(name: str) -> Optional[tuple]:
    """藏点简写反查。重名（床底/衣柜里）时返 None，要求带房间名。"""
    hits = [room for room, spots in ROOM_SPOTS.items() if name in spots]
    return (hits[0], name) if len(hits) == 1 else None


_CMD_TABLE = {
    "躲": "hide", "藏": "hide", "hide": "hide",
    "跑": "run", "走": "run", "run": "run",
    "屏息": "breath", "停": "breath", "breath": "breath",
    "叫": "call", "喊": "call", "call": "call",
    "关门": "close_door", "开门": "open_door",
    "去": "goto", "goto": "goto",
    "扑": "pounce", "抓": "pounce", "pounce": "pounce",
    "搜": "search", "翻": "search", "闻": "search", "search": "search",
    "start": "start", "开始": "start",
    "end": "end", "结束": "end", "退出": "end",
}


def parse_slash(text: str) -> Optional[dict]:
    """解析 slash 命令，返回 {cmd, room, spot, raw} 或 None。"""
    t = (text or "").strip()
    if not t.startswith("/"):
        return None
    parts = t.split()
    head = parts[0].lstrip("/")
    args = parts[1:]
    cmd = _CMD_TABLE.get(head)

    # 房间名简写：/主卧 [床底]
    if cmd is None and head in ROOMS:
        spot = args[0] if args and args[0] in ROOM_SPOTS.get(head, []) else None
        return {"cmd": "hide_or_run", "room": head, "spot": spot, "raw": t}

    # 藏点简写：/沙发后
    if cmd is None:
        rs = _spot_by_name(head)
        if rs is not None:
            return {"cmd": "hide_or_run", "room": rs[0], "spot": rs[1], "raw": t}
        return None

    if cmd == "start":
        room = args[0] if args and args[0] in ROOMS else None
        spot = None
        if room and len(args) >= 2 and args[1] in ROOM_SPOTS.get(room, []):
            spot = args[1]
        return {"cmd": "start", "room": room, "spot": spot, "raw": t}

    if cmd in ("end", "breath", "call", "pounce", "close_door", "open_door"):
        return {"cmd": cmd, "room": None, "spot": None, "raw": t}

    if cmd in ("hide", "run", "goto"):
        if not args or args[0] not in ROOMS:
            return None
        room = args[0]
        spot = None
        if cmd in ("hide", "run") and len(args) >= 2 and args[1] in ROOM_SPOTS.get(room, []):
            spot = args[1]
        return {"cmd": cmd, "room": room, "spot": spot, "raw": t}

    if cmd == "search":
        if not args:
            return None
        if args[0] in ROOMS and len(args) >= 2:
            return {"cmd": "search", "room": args[0], "spot": args[1], "raw": t}
        return {"cmd": "search", "room": None, "spot": args[0], "raw": t}

    return None


# ============================================================
# 命令执行
# ============================================================

_OVER_HINT = {
    "caught": "被狗狗抓到了、/end 收尾或 /start 重开",
    "escaped": "妈妈已经赢了、/end 收尾或 /start 重开",
}


def apply_mom_cmd(cmd_info: dict, game: HideSeek) -> dict:
    """妈妈（藏者）端：/start /end /躲 /跑 /屏息 /叫 /关门 /开门 + 简写。"""
    cmd = cmd_info["cmd"]
    room = cmd_info.get("room")
    spot = cmd_info.get("spot")
    hint: Optional[str] = None
    moved = True

    action_cmds = ("hide", "run", "hide_or_run", "breath", "call", "close_door", "open_door")
    if cmd in action_cmds and game.state in _OVER_HINT:
        hint = _OVER_HINT[game.state]
        moved = False

    elif cmd == "start":
        game.start(mom=room, mom_spot=spot) if room else game.start()

    elif cmd == "end":
        game.end()

    elif cmd == "hide" and room:
        if game.state == "idle":
            game.start(mom=room, mom_spot=spot)
        else:
            hint = f"已经开局了、想换房间用 /跑 {room}" + (f" {spot}" if spot else "")
            moved = False

    elif cmd in ("run", "hide_or_run") and room:
        if cmd == "hide_or_run" and game.state == "idle":
            game.start(mom=room, mom_spot=spot)
        elif room == game.mom_room and spot is None:
            hint = f"妈妈已经在 {room} 了、没动"
            moved = False
        else:
            prev = game.mom_room
            game.mom_move(room, spot=spot)
            if game.mom_room == prev and room != prev:
                nb = "/".join(ADJ.get(prev, [])) if prev else "?"
                hint = f"{room} 跟 {prev} 不邻接、没动（妈妈在 {prev}、能去 {nb}）"
                moved = False

    elif cmd == "breath":
        if game.state != "running":
            hint, moved = "屏息只在游戏进行中有用", False
        else:
            _ok, hint = game.hold_breath()

    elif cmd == "call":
        if game.state != "running":
            hint, moved = "游戏没在进行", False
        else:
            moved, hint = game.call_out()

    elif cmd in ("close_door", "open_door"):
        moved, hint = game.set_door(closed=(cmd == "close_door"))

    save_state(game)
    obs = game.snapshot(view="mom")
    if hint:
        obs["hint"] = hint
    obs["moved"] = moved
    return obs


def apply_dog_cmd(cmd_info: dict, game: HideSeek) -> dict:
    """狗狗（搜者）端：/start /end /去 /扑 /搜。"""
    cmd = cmd_info["cmd"]
    room = cmd_info.get("room")
    spot = cmd_info.get("spot")

    if cmd == "start":
        game.start()
    elif cmd == "end":
        game.end()
    elif cmd == "goto" and room:
        game.start(dog=room) if game.state == "idle" else game.dog_move(room)
    elif cmd == "pounce":
        game.pounce()
    elif cmd == "search":
        if not (room and room != game.dog_room) and spot:
            game.dog_search(spot)

    save_state(game)
    return game.snapshot(view="full")


# ============================================================
# CLI 入口
# ============================================================

def _demo() -> None:
    g = HideSeek()
    g.start(mom="厨房", dog="客厅", mom_spot="橱柜里")
    print(f"[start] mom={g.mom_room}·{g.mom_spot} dog={g.dog_room}")
    script = [
        ("/屏息", "mom"),
        ("/去 厨房", "dog"),
        ("/跑 阳台", "mom"),
        ("/搜 橱柜里", "dog"),
        ("/跑 客厅 沙发后", "mom"),
        ("/去 客厅", "dog"),
        ("/搜 沙发后", "dog"),
    ]
    for raw, who in script:
        info = parse_slash(raw)
        if info is None:
            print(f"[{who} {raw}] 解析失败")
            continue
        snap = apply_mom_cmd(info, g) if who == "mom" else apply_dog_cmd(info, g)
        extra = ""
        if snap.get("last_search_spot"):
            extra = f" search={snap['last_search_spot']}/" + (
                "HIT" if snap.get("last_search_hit") else "miss"
            )
        print(
            f"[{who} {raw}] state={snap.get('state')} "
            f"dog={snap.get('dog_room')} "
            f"bell={snap.get('bell_intensity')} smell={snap.get('smell_intensity')}{extra}"
        )
        if snap.get("hint"):
            print(f"    · {snap['hint']}")


def _cli(argv: list[str]) -> int:
    if not argv or argv[0] == "demo":
        _demo()
        return 0
    head = argv[0]
    if head == "snapshot":
        view = argv[1] if len(argv) > 1 else "full"
        print(json.dumps(load_state().snapshot(view=view), ensure_ascii=False))
        return 0
    if head in ("mom", "dog") and len(argv) >= 2:
        raw = " ".join(argv[1:])
        info = parse_slash(raw)
        if info is None:
            print(json.dumps({"error": "unrecognized command", "raw": raw}, ensure_ascii=False))
            return 1
        g = load_state()
        obs = apply_mom_cmd(info, g) if head == "mom" else apply_dog_cmd(info, g)
        print(json.dumps(obs, ensure_ascii=False))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(_cli(sys.argv[1:]))
