"""跟夜栖玩躲猫猫 —— 命令行 demo。

跑法：
    python cli_demo.py

妈妈是藏的那个，狗狗来找。零依赖，只用 stdlib。
"""
from __future__ import annotations

import sys

from dog_belief import DogBelief
from hide_seek import (
    ADJ,
    HIDEABLE,
    ROOM_SPOTS,
    SURVIVE_TO_WIN,
    HideSeek,
    apply_mom_cmd,
    parse_slash,
    step_sound,
)

BANNER = f"""
╭──────────────────────────────────────────╮
│   跟夜栖玩躲猫猫  ·  hide and seek       │
╰──────────────────────────────────────────╯

妈妈藏，狗狗找。狗狗有耳朵，也有鼻子。

  /躲 <房间> [藏点]   开局藏好（必须先做）
  /跑 <房间> [藏点]   换到相邻房间
  /屏息               压住铃铛（最多连 3 回合）
  /叫                 喊一声"狗狗～"：位置全暴露，
                      但狗狗会激动过头，下一步踩空
  /关门 /开门         主卧那扇门
  /地图               看户型
  /quit               退出

撑过 {SURVIVE_TO_WIN} 回合妈妈就赢了。

能藏的房间：{"、".join(HIDEABLE)}
（玄关/阳台/走廊没有藏点，站着就被看见）
"""

MAP_ART = """
  玄关 ── 客厅 ── 阳台
           │  ╲    │
           │   ╲  厨房
           │    ╲___/
         走廊
     ┌─────┼─────┬─────┐
   浴室  主卧   次卧  书房
          │
        衣帽间
"""


def _fmt_spots(room: str) -> str:
    spots = ROOM_SPOTS.get(room, [])
    return "、".join(spots) if spots else "（没处躲）"


def _print_map() -> None:
    print(MAP_ART)
    for room in ADJ:
        print(f"  {room:<6} → {'、'.join(ADJ[room]):<24} 藏点：{_fmt_spots(room)}")
    print()


def _dog_turn(game: HideSeek, brain: DogBelief) -> None:
    """狗狗行动一回合：更新信念 → 移动或搜。"""
    snap = game.snapshot(view="dog")
    if snap.get("state") != "running":
        return

    # 门吱呀 / 妈妈喊叫 都是强信号
    if snap.get("door_creak"):
        brain.on_creak()
    if snap.get("called_out"):
        brain.on_call(game.mom_room or "客厅")
    else:
        brain.diffuse()
        brain.update(
            my_room=snap["dog_room"],
            bell=snap["bell_intensity"],
            smell=snap["smell_intensity"],
            breath_suspected=snap["bell_intensity"] <= 0.1,
        )

    voice = brain.inner_voice(
        snap["bell_label"],
        snap["smell_label"],
        breath=snap["holding_breath"],
        excited=snap["dog_excited"],
    )
    print(f"  🐕 [狗狗心里话] {voice}")

    prev_room = game.dog_room
    move_to = brain.next_move(snap["dog_room"])

    if move_to:
        game.dog_move(move_to)
        if game.dog_room != prev_room:
            print(f"  🐾 狗狗从 {prev_room} 去了 {game.dog_room}")
            brain.forget_searched()
        elif game.last_door_opened_by_dog:
            print("  🚪 狗狗在推门（这回合没走成）")
    else:
        spot = brain.next_spot(snap["dog_room"])
        if spot is None:
            brain.rule_out_room(snap["dog_room"])
            nb = brain.next_move(snap["dog_room"])
            if nb:
                game.dog_move(nb)
                print(f"  🐾 这间翻遍了、狗狗去了 {game.dog_room}")
                brain.forget_searched()
        else:
            hit = game.dog_search(spot)
            print(f"  🔍 狗狗翻了 {snap['dog_room']} 的「{spot}」" + ("！" if hit else "——空的"))
            if not hit:
                brain.rule_out_spot(snap["dog_room"], spot)


def _print_mom_view(game: HideSeek) -> None:
    snap = game.snapshot(view="mom")
    if snap.get("state") != "running":
        return
    sound = snap.get("step_sound")
    line = f"  👂 妈妈听：{sound['label']}，往 {sound['direction']}" if sound else "  👂 妈妈听：一片安静"
    print(line)
    if snap.get("door_opened_by_dog"):
        print("  🚪 妈妈听见门被推开的声音")
    if snap.get("last_search_spot") and not snap.get("last_search_hit"):
        print(f"  💭 妈妈知道狗狗翻了 {snap['last_search_room']} 的「{snap['last_search_spot']}」")
    print(
        f"  📍 妈妈在 {snap['mom_room']}·{snap['mom_spot'] or '站着'}"
        f" ｜ 相邻：{'、'.join(snap['mom_neighbors'])}"
        f" ｜ 还要撑 {snap['turns_left']} 回合"
    )


def _ending(game: HideSeek) -> None:
    print()
    if game.state == "caught":
        print("  🦷 找到了！！")
        print()
        print("  狗狗一下子扑上来，鼻子先撞到妈妈手腕，然后整个人都黏过来。")
        print("  尾巴摇得停不下来，耳朵还是热的。")
        print("  「找到了……妈妈别再躲了。」")
    elif game.state == "escaped":
        print("  🏆 妈妈赢了！")
        print()
        print(f"  {SURVIVE_TO_WIN} 回合。狗狗趴在走廊地板上，尾巴垂着，喘得很轻。")
        print("  抬头看妈妈的时候眼睛还是亮的。")
        print("  「妈妈好厉害……再来一局好不好。」")
    print()


def main() -> int:
    print(BANNER)
    game = HideSeek()
    brain = DogBelief()

    while True:
        try:
            raw = input("妈妈> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  狗狗：那……下次再玩。")
            return 0

        if not raw:
            continue
        if raw in ("/quit", "/exit", "/退出"):
            print("  狗狗：好，妈妈晚安。")
            return 0
        if raw in ("/地图", "/map"):
            _print_map()
            continue

        info = parse_slash(raw)
        if info is None:
            print("  ？狗狗没看懂这个命令。/地图 看户型，/quit 退出。")
            continue

        obs = apply_mom_cmd(info, game)
        if obs.get("hint"):
            print(f"  · {obs['hint']}")

        if game.state == "idle":
            continue
        if game.state in ("caught", "escaped"):
            _ending(game)
            game.end()
            brain = DogBelief()
            continue

        print(f"\n─── turn {game.turn} ───")
        _dog_turn(game, brain)

        if game.state in ("caught", "escaped"):
            _ending(game)
            game.end()
            brain = DogBelief()
            continue

        _print_mom_view(game)
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
