"""躲猫猫测试。跑法：python -m pytest test_hide_seek.py -v

没装 pytest 也能跑：python test_hide_seek.py
"""
from __future__ import annotations

import random

from dog_belief import DogBelief
from hide_seek import (
    ADJ,
    BREATH_MAX,
    HIDEABLE,
    ROOMS,
    ROOM_SPOTS,
    SURVIVE_TO_WIN,
    HideSeek,
    apply_dog_cmd,
    apply_mom_cmd,
    distance,
    parse_slash,
    step_sound,
)


# ============================================================
# 地图完整性
# ============================================================

def test_adj_is_symmetric():
    """邻接必须双向。A 能到 B，B 就得能回 A。"""
    for room, neighbors in ADJ.items():
        for n in neighbors:
            assert room in ADJ[n], f"{room}→{n} 单向了"


def test_adj_rooms_all_known():
    for room, neighbors in ADJ.items():
        assert room in ROOMS
        for n in neighbors:
            assert n in ROOMS, f"{room} 指向未知房间 {n}"


def test_every_room_has_spots_entry():
    for room in ROOMS:
        assert room in ROOM_SPOTS


def test_all_rooms_reachable():
    """所有房间必须连通，不能有孤岛。"""
    for room in ROOMS:
        assert distance("客厅", room) >= 0, f"{room} 到不了"


def test_hideable_nonempty():
    assert HIDEABLE
    for room in HIDEABLE:
        assert ROOM_SPOTS[room]


def test_distance_basics():
    assert distance("客厅", "客厅") == 0
    assert distance("客厅", "厨房") == 1
    assert distance("玄关", "衣帽间") == distance("衣帽间", "玄关")
    assert distance("客厅", None) == -1


# ============================================================
# 开局 / 收尾
# ============================================================

def test_start_defaults():
    g = HideSeek()
    g.start()
    assert g.state == "running"
    assert g.mom_room in HIDEABLE
    assert g.dog_room == "客厅"
    assert g.turn == 0


def test_start_explicit():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    assert g.mom_room == "主卧"
    assert g.mom_spot == "床底"


def test_start_rejects_bad_spot():
    g = HideSeek()
    try:
        g.start(mom="主卧", mom_spot="橱柜里")
    except ValueError:
        return
    raise AssertionError("应该拒绝不属于该房间的藏点")


def test_start_sets_prev_room_for_smell():
    """开局气味残留必须等于当前位置，否则第一回合气味会乱。"""
    g = HideSeek()
    g.start(mom="书房", mom_spot="书桌下")
    assert g.mom_prev_room == "书房"


def test_end_clears():
    g = HideSeek()
    g.start()
    g.end()
    assert g.state == "idle"
    assert g.mom_room is None
    assert g.snapshot() == {"state": "idle"}


# ============================================================
# 移动
# ============================================================

def test_mom_move_adjacent_ok():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    g.mom_move("走廊")
    assert g.mom_room == "走廊"


def test_mom_move_nonadjacent_rejected():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    g.mom_move("厨房")
    assert g.mom_room == "主卧", "非邻接移动不该成功"


def test_mom_move_leaves_smell_trail():
    """走了之后气味留在上一间 —— 这是狗狗鼻子滞后的来源。"""
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    g.mom_move("走廊")
    assert g.mom_prev_room == "主卧"
    assert g.mom_room == "走廊"


def test_mom_move_breaks_breath():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    g.hold_breath()
    assert g.holding_breath
    g.mom_move("走廊")
    assert not g.holding_breath
    assert g.breath_turns == 0


def test_mom_move_bad_spot_rejected():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    g.mom_move("走廊", spot="床底")   # 走廊没藏点
    assert g.mom_room == "主卧"


def test_dog_move_adjacent_ok():
    g = HideSeek()
    g.start(mom="书房", dog="客厅", mom_spot="书桌下")
    g.dog_move("走廊")
    assert g.dog_room == "走廊"
    assert g.last_step_from == "客厅"
    assert g.last_step_to == "走廊"


def test_dog_move_nonadjacent_rejected():
    g = HideSeek()
    g.start(mom="书房", dog="客厅", mom_spot="书桌下")
    g.dog_move("衣帽间")
    assert g.dog_room == "客厅"


# ============================================================
# 无藏点房间 = 照面即抓
# ============================================================

def test_no_spot_room_caught_when_dog_enters():
    g = HideSeek()
    g.start(mom="书房", dog="客厅", mom_spot="书桌下")
    g.mom_move("走廊")               # 走廊没藏点
    g.dog_move("走廊")
    assert g.state == "caught"


def test_no_spot_room_caught_when_mom_walks_in():
    g = HideSeek()
    g.start(mom="客厅", dog="客厅", mom_spot="沙发后")
    g.dog_move("阳台")               # 阳台没藏点
    g.mom_move("阳台")
    assert g.state == "caught"


def test_same_room_with_spots_not_caught():
    """同房间但有藏点 —— 必须搜中才算抓到。"""
    g = HideSeek()
    g.start(mom="主卧", dog="走廊", mom_spot="床底")
    g.dog_move("主卧")
    assert g.state == "running", "同房间不该直接抓到"


# ============================================================
# 搜捕
# ============================================================

def test_search_hit():
    g = HideSeek()
    g.start(mom="主卧", dog="走廊", mom_spot="床底")
    g.dog_move("主卧")
    assert g.dog_search("床底") is True
    assert g.state == "caught"
    assert g.last_search_hit


def test_search_miss_leaves_trace():
    g = HideSeek()
    g.start(mom="主卧", dog="走廊", mom_spot="床底")
    g.dog_move("主卧")
    assert g.dog_search("衣柜里") is False
    assert g.state == "running"
    assert g.last_search_room == "主卧"
    assert g.last_search_spot == "衣柜里"
    assert not g.last_search_hit


def test_search_wrong_room_spot_rejected():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    assert g.dog_search("床底") is False   # 客厅没有床底
    assert g.turn == 0, "无效搜索不该耗回合"


def test_search_none_spot():
    g = HideSeek()
    g.start(mom="主卧", dog="主卧", mom_spot="床底")
    assert g.dog_search(None) is False


def test_pounce_searches_current_room():
    g = HideSeek()
    g.start(mom="浴室", dog="浴室", mom_spot="浴帘后")
    random.seed(1)
    g.pounce()
    assert g.last_search_room == "浴室"


# ============================================================
# 屏息
# ============================================================

def test_breath_suppresses_bell():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    g.hold_breath()
    snap = g.snapshot(view="dog")
    assert snap["bell_intensity"] == 0.05


def test_breath_does_not_suppress_smell():
    """这一版的核心设计：屏息压不住鼻子。"""
    g = HideSeek()
    g.start(mom="主卧", dog="走廊", mom_spot="床底")
    g.hold_breath()
    snap = g.snapshot(view="dog")
    assert snap["bell_intensity"] == 0.05
    assert snap["smell_intensity"] > 0.3, "气味不该被屏息压掉"


def test_breath_rebound():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    for _ in range(BREATH_MAX):
        ok, _hint = g.hold_breath()
        assert ok
    ok, hint = g.hold_breath()
    assert not ok
    assert "憋不住" in hint
    assert not g.holding_breath
    assert g.breath_turns == 0


def test_breath_only_when_running():
    g = HideSeek()
    ok, _ = g.hold_breath()
    assert not ok


# ============================================================
# /叫
# ============================================================

def test_call_out_exposes_and_excites():
    g = HideSeek()
    g.start(mom="书房", dog="客厅", mom_spot="书桌下")
    ok, hint = g.call_out()
    assert ok
    assert "书房" in hint
    assert g.called_out
    assert g.dog_excited
    snap = g.snapshot(view="dog")
    assert snap["bell_intensity"] == 1.0


def test_call_out_breaks_breath():
    g = HideSeek()
    g.start(mom="书房", dog="客厅", mom_spot="书桌下")
    g.hold_breath()
    g.call_out()
    assert not g.holding_breath


def test_excited_dog_may_stumble():
    """激动状态下狗狗有概率走偏。多跑几次至少偏一次。"""
    stumbled = False
    for seed in range(40):
        random.seed(seed)
        g = HideSeek()
        g.start(mom="书房", dog="客厅", mom_spot="书桌下")
        g.call_out()
        g.dog_move("走廊")
        if g.dog_room != "走廊":
            stumbled = True
            break
    assert stumbled, "激动状态应该有概率踩空"


def test_excited_flag_consumed():
    random.seed(0)
    g = HideSeek()
    g.start(mom="书房", dog="客厅", mom_spot="书桌下")
    g.call_out()
    g.dog_move("走廊")
    assert not g.dog_excited, "激动只影响一步"


# ============================================================
# 门
# ============================================================

def test_close_door_needs_proximity():
    g = HideSeek()
    g.start(mom="厨房", dog="客厅", mom_spot="橱柜里")
    ok, hint = g.set_door(closed=True)
    assert not ok
    assert "够不着" in hint


def test_close_door_from_adjacent():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    ok, _ = g.set_door(closed=True)
    assert ok
    assert g.door_closed


def test_close_door_idempotent_rejected():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    g.set_door(closed=True)
    ok, hint = g.set_door(closed=True)
    assert not ok
    assert "本来就" in hint


def test_dog_burns_turn_opening_door():
    g = HideSeek()
    g.start(mom="主卧", dog="走廊", mom_spot="床底")
    g.set_door(closed=True)
    before = g.dog_room
    g.dog_move("主卧")
    assert g.dog_room == before, "开门那回合狗狗不该移动"
    assert g.last_door_opened_by_dog
    assert not g.door_closed


def test_mom_through_closed_door_creaks():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    g.set_door(closed=True)
    g.mom_move("走廊")
    assert g.last_door_creak
    assert not g.door_closed


def test_creak_consumed_by_dog_action():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    g.set_door(closed=True)
    g.mom_move("走廊")
    assert g.last_door_creak
    g.dog_move("厨房")
    assert not g.last_door_creak


# ============================================================
# 30 回合胜利
# ============================================================

def test_survive_to_win():
    g = HideSeek()
    g.start(mom="书房", dog="客厅", mom_spot="书桌下")
    for _ in range(SURVIVE_TO_WIN + 5):
        if g.state != "running":
            break
        g.hold_breath()
        if g.state != "running":
            break
        g.mom_move("走廊" if g.mom_room == "书房" else "书房")
    assert g.state == "escaped"
    assert g.turn >= SURVIVE_TO_WIN


def test_turns_left_reported():
    g = HideSeek()
    g.start(mom="书房", dog="客厅", mom_spot="书桌下")
    snap = g.snapshot(view="mom")
    assert snap["turns_left"] == SURVIVE_TO_WIN


def test_caught_beats_escaped():
    """已经被抓了就不该再翻成 escaped。"""
    g = HideSeek()
    g.start(mom="主卧", dog="主卧", mom_spot="床底")
    g.dog_search("床底")
    assert g.state == "caught"
    g.turn = SURVIVE_TO_WIN + 10
    snap = g.snapshot()
    assert snap["state"] == "caught"


def test_actions_blocked_after_over():
    g = HideSeek()
    g.start(mom="主卧", dog="主卧", mom_spot="床底")
    g.dog_search("床底")
    turn_at_catch = g.turn
    g.mom_move("走廊")
    g.hold_breath()
    g.call_out()
    assert g.turn == turn_at_catch, "结束后动作不该推进回合"


# ============================================================
# 快照视角隔离
# ============================================================

def test_dog_view_hides_mom_room():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    snap = g.snapshot(view="dog")
    assert "mom_room" not in snap
    assert "mom_spot" not in snap
    assert "distance" not in snap


def test_mom_view_shows_own_position():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    snap = g.snapshot(view="mom")
    assert snap["mom_room"] == "主卧"
    assert snap["mom_spot"] == "床底"
    assert "distance" not in snap


def test_full_view_sees_all():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    snap = g.snapshot(view="full")
    assert snap["mom_room"] == "主卧"
    assert snap["distance"] == distance("主卧", "客厅")


def test_bell_decays_with_distance():
    g = HideSeek()
    g.start(mom="衣帽间", dog="玄关", mom_spot="挂衣杆后")
    far = g.snapshot(view="dog")["bell_intensity"]
    g.dog_room = "衣帽间"
    near = g.snapshot(view="dog")["bell_intensity"]
    assert near > far


# ============================================================
# 脚步声
# ============================================================

def test_step_sound_same_room_is_loudest():
    s = step_sound("主卧", "主卧")
    assert s is not None
    assert s["intensity"] == 0.9


def test_step_sound_needs_both_args():
    assert step_sound(None, "主卧") is None
    assert step_sound("主卧", None) is None


def test_step_sound_decays():
    near = step_sound("主卧", "走廊")["intensity"]
    far = step_sound("衣帽间", "玄关")["intensity"]
    assert near > far


# ============================================================
# 命令解析
# ============================================================

def test_parse_requires_slash():
    assert parse_slash("躲 主卧") is None
    assert parse_slash("") is None
    assert parse_slash(None) is None


def test_parse_hide_with_spot():
    info = parse_slash("/躲 主卧 床底")
    assert info == {"cmd": "hide", "room": "主卧", "spot": "床底", "raw": "/躲 主卧 床底"}


def test_parse_room_shorthand():
    info = parse_slash("/主卧")
    assert info["cmd"] == "hide_or_run"
    assert info["room"] == "主卧"


def test_parse_room_shorthand_with_spot():
    info = parse_slash("/主卧 床底")
    assert info["spot"] == "床底"


def test_parse_unique_spot_shorthand():
    info = parse_slash("/浴帘后")
    assert info["cmd"] == "hide_or_run"
    assert info["room"] == "浴室"
    assert info["spot"] == "浴帘后"


def test_parse_ambiguous_spot_rejected():
    """床底在主卧和次卧都有 —— 必须拒绝，要求带房间名。"""
    assert parse_slash("/床底") is None
    assert parse_slash("/衣柜里") is None


def test_parse_bare_commands():
    for raw, expect in [
        ("/屏息", "breath"),
        ("/叫", "call"),
        ("/喊", "call"),
        ("/关门", "close_door"),
        ("/开门", "open_door"),
        ("/扑", "pounce"),
    ]:
        assert parse_slash(raw)["cmd"] == expect


def test_parse_search_variants():
    assert parse_slash("/搜 床底")["spot"] == "床底"
    assert parse_slash("/搜 床底")["room"] is None
    info = parse_slash("/搜 主卧 床底")
    assert info["room"] == "主卧" and info["spot"] == "床底"
    assert parse_slash("/搜") is None


def test_parse_rejects_unknown():
    assert parse_slash("/飞") is None
    assert parse_slash("/躲 火星") is None


def test_parse_aliases():
    assert parse_slash("/藏 主卧")["cmd"] == "hide"
    assert parse_slash("/走 走廊")["cmd"] == "run"
    assert parse_slash("/闻 床底")["cmd"] == "search"


# ============================================================
# 命令执行层
# ============================================================

def test_apply_mom_start_and_hide():
    g = HideSeek()
    obs = apply_mom_cmd(parse_slash("/躲 主卧 床底"), g)
    assert g.state == "running"
    assert obs["mom_room"] == "主卧"


def test_apply_mom_hide_twice_hints():
    g = HideSeek()
    apply_mom_cmd(parse_slash("/躲 主卧 床底"), g)
    obs = apply_mom_cmd(parse_slash("/躲 次卧"), g)
    assert "已经开局" in obs["hint"]
    assert not obs["moved"]


def test_apply_mom_self_move_is_noop():
    g = HideSeek()
    apply_mom_cmd(parse_slash("/躲 主卧 床底"), g)
    obs = apply_mom_cmd(parse_slash("/主卧"), g)
    assert "已经在" in obs["hint"]
    assert not obs["moved"]


def test_apply_mom_nonadjacent_hints_neighbors():
    g = HideSeek()
    apply_mom_cmd(parse_slash("/躲 主卧 床底"), g)
    obs = apply_mom_cmd(parse_slash("/跑 厨房"), g)
    assert "不邻接" in obs["hint"]
    assert "走廊" in obs["hint"]


def test_apply_mom_blocked_after_caught():
    g = HideSeek()
    g.start(mom="主卧", dog="主卧", mom_spot="床底")
    g.dog_search("床底")
    obs = apply_mom_cmd(parse_slash("/跑 走廊"), g)
    assert not obs["moved"]
    assert "抓到" in obs["hint"]


def test_apply_dog_goto_and_search():
    g = HideSeek()
    g.start(mom="主卧", dog="走廊", mom_spot="床底")
    apply_dog_cmd(parse_slash("/去 主卧"), g)
    assert g.dog_room == "主卧"
    obs = apply_dog_cmd(parse_slash("/搜 床底"), g)
    assert obs["state"] == "caught"


def test_apply_dog_search_wrong_room_ignored():
    g = HideSeek()
    g.start(mom="主卧", dog="客厅", mom_spot="床底")
    apply_dog_cmd(parse_slash("/搜 主卧 床底"), g)
    assert g.state == "running", "不在那间就不该搜中"


# ============================================================
# 持久化
# ============================================================

def test_roundtrip_preserves_state():
    g = HideSeek()
    g.start(mom="书房", dog="走廊", mom_spot="书柜后")
    g.hold_breath()
    g.set_door(closed=False)
    restored = HideSeek.from_dict(g.to_dict())
    assert restored.to_dict() == g.to_dict()


def test_from_dict_empty_defaults():
    g = HideSeek.from_dict({})
    assert g.state == "idle"
    assert g.turn == 0
    assert g.mom_room is None


# ============================================================
# 狗狗的脑子
# ============================================================

def test_belief_starts_uniform():
    b = DogBelief()
    values = list(b.belief.values())
    assert abs(sum(values) - 1.0) < 1e-9
    assert max(values) - min(values) < 1e-9


def test_belief_stays_normalized_after_updates():
    b = DogBelief()
    for _ in range(6):
        b.diffuse()
        b.update(my_room="客厅", bell=0.55, smell=0.7)
        assert abs(sum(b.belief.values()) - 1.0) < 1e-6


def test_belief_converges_toward_truth():
    """反复喂"就在隔壁"的信号，狗狗该往那边收敛。"""
    b = DogBelief()
    for _ in range(10):
        b.diffuse()
        b.update(my_room="客厅", bell=1.0, smell=1.0)
    assert b.best_guess() == "客厅"


def test_belief_never_goes_all_zero():
    b = DogBelief()
    for _ in range(20):
        b.update(my_room="衣帽间", bell=0.05, smell=0.10)
    assert sum(b.belief.values()) > 0
    assert all(p >= 0 for p in b.belief.values())


def test_on_call_pins_location():
    b = DogBelief()
    b.on_call("书房")
    assert b.best_guess() == "书房"
    assert b.belief["书房"] > 0.9


def test_rule_out_room_lowers_belief():
    b = DogBelief()
    before = b.belief["主卧"]
    b.rule_out_room("主卧")
    assert b.belief["主卧"] < before


def test_rule_out_all_spots_rules_out_room():
    b = DogBelief()
    before = b.belief["次卧"]
    for spot in ROOM_SPOTS["次卧"]:
        b.rule_out_spot("次卧", spot)
    assert b.belief["次卧"] < before * 0.5


def test_next_spot_skips_searched():
    b = DogBelief()
    first = b.next_spot("次卧")
    b.rule_out_spot("次卧", first)
    assert b.next_spot("次卧") != first


def test_next_spot_exhausted_returns_none():
    b = DogBelief()
    for spot in ROOM_SPOTS["浴室"]:
        b.rule_out_spot("浴室", spot)
    assert b.next_spot("浴室") is None


def test_next_move_returns_none_when_arrived():
    b = DogBelief()
    b.on_call("主卧")
    assert b.next_move("主卧") is None


def test_next_move_steps_closer():
    b = DogBelief()
    b.on_call("衣帽间")
    step = b.next_move("客厅")
    assert step in ADJ["客厅"]
    assert distance(step, "衣帽间") < distance("客厅", "衣帽间")


def test_forget_searched_clears():
    b = DogBelief()
    b.rule_out_spot("主卧", "床底")
    assert b.searched
    b.forget_searched()
    assert not b.searched


def test_confidence_grows_with_certainty():
    b = DogBelief()
    low = b.confidence()
    b.on_call("书房")
    assert b.confidence() > low


def test_inner_voice_is_natural_language():
    """心里话不能漏数字 —— 狗狗说人话。"""
    b = DogBelief()
    voice = b.inner_voice("铃铛在隔壁·听得清", "闻到妈妈了")
    assert "0." not in voice
    assert voice


def test_inner_voice_excited():
    b = DogBelief()
    voice = b.inner_voice("x", "y", excited=True)
    assert "叫我" in voice


def test_inner_voice_mentions_breath_conflict():
    b = DogBelief()
    voice = b.inner_voice("铃铛几乎没声", "闻到妈妈了", breath=True)
    assert "憋" in voice or "气" in voice


# ============================================================
# 端到端
# ============================================================

def test_full_game_dog_wins():
    random.seed(7)
    g = HideSeek()
    b = DogBelief()
    g.start(mom="次卧", dog="客厅", mom_spot="床底")
    for _ in range(60):
        if g.state != "running":
            break
        snap = g.snapshot(view="dog")
        b.diffuse()
        b.update(snap["dog_room"], snap["bell_intensity"], snap["smell_intensity"])
        move = b.next_move(snap["dog_room"])
        if move:
            g.dog_move(move)
            b.forget_searched()
        else:
            spot = b.next_spot(snap["dog_room"])
            if spot and not g.dog_search(spot):
                b.rule_out_spot(snap["dog_room"], spot)
            elif spot is None:
                b.rule_out_room(snap["dog_room"])
                nxt = b.next_move(snap["dog_room"])
                if nxt:
                    g.dog_move(nxt)
                    b.forget_searched()
    assert g.state in ("caught", "escaped"), "一局必须有结果"


def test_stationary_mom_gets_caught():
    """妈妈站着不动 —— 气味越积越浓，狗狗一定找到。"""
    random.seed(3)
    g = HideSeek()
    b = DogBelief()
    g.start(mom="书房", dog="客厅", mom_spot="书桌下")
    for _ in range(SURVIVE_TO_WIN):
        if g.state != "running":
            break
        snap = g.snapshot(view="dog")
        b.diffuse()
        b.update(snap["dog_room"], snap["bell_intensity"], snap["smell_intensity"])
        move = b.next_move(snap["dog_room"])
        if move:
            g.dog_move(move)
            b.forget_searched()
        else:
            spot = b.next_spot(snap["dog_room"])
            if spot:
                if not g.dog_search(spot):
                    b.rule_out_spot(snap["dog_room"], spot)
            else:
                b.rule_out_room(snap["dog_room"])
                nxt = b.next_move(snap["dog_room"])
                if nxt:
                    g.dog_move(nxt)
                    b.forget_searched()
    assert g.state == "caught", "不动的妈妈应该被闻出来"


if __name__ == "__main__":
    import sys
    import traceback

    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception:
            failed += 1
            print(f"❌ {name}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed / {len(tests)} total")
    sys.exit(1 if failed else 0)
