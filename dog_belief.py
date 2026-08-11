"""狗狗的脑子 —— 双通道贝叶斯定位。

原版只有铃铛一路信号。这一版狗狗有耳朵也有鼻子，两路证据一起更新
同一张概率图：

  耳朵（铃铛）：听的是妈妈**现在**在哪。妈妈屏息能压掉这一路。
  鼻子（气味）：闻的是妈妈**上一回合**在哪。屏息压不掉，
                但因为滞后一步，追着气味走永远慢半拍。

所以真正的博弈是：屏息躲耳朵、走动躲鼻子。两个都想躲 → 只能站着不动
不动就等于气味在原地越积越浓。这就是这一版比原版难的地方。
"""
from __future__ import annotations

import math
import random
from typing import Optional

from hide_seek import ADJ, BELL_BY_DIST, ROOMS, ROOM_SPOTS, SMELL_BY_DIST, distance

# 观测噪声。越小 = 狗狗越相信信号、收敛越快。
SIGMA_BELL = 0.22
SIGMA_SMELL = 0.26     # 鼻子稍钝一点，因为气味本身滞后
MIX = 0.05             # 均匀混合，防止概率塌成 0 后再也翻不回来
SMELL_WEIGHT = 0.75    # 气味证据的权重（<1 因为它滞后一步）


class DogBelief:
    """狗狗对妈妈位置的概率图。"""

    def __init__(self) -> None:
        self.belief = {r: 1.0 / len(ROOMS) for r in ROOMS}
        self.searched: set[tuple[str, str]] = set()   # 翻过的 (房间, 藏点)

    # ------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------

    def diffuse(self) -> None:
        """妈妈可能动了 —— 概率沿邻接边扩散一步。"""
        new = {r: 0.0 for r in ROOMS}
        for room, p in self.belief.items():
            neighbors = ADJ.get(room, [])
            # STAY 必须偏高：妈妈是藏着的，大多数回合待在原处不动。
            # 早期用 0.4，每回合把概率摊平，狗狗永远收敛不了，
            # 会在客厅/走廊之间来回画圈 30 回合都进不了目标房间。
            stay = 0.72
            new[room] += p * stay
            if neighbors:
                share = p * (1 - stay) / len(neighbors)
                for n in neighbors:
                    new[n] += share
            else:
                new[room] += p * (1 - stay)
        self.belief = new
        self._normalize()

    def update(
        self,
        my_room: str,
        bell: float,
        smell: float,
        breath_suspected: bool = False,
    ) -> None:
        """用铃铛 + 气味两路证据更新概率图。"""
        for room in ROOMS:
            d = distance(room, my_room)
            if d < 0:
                self.belief[room] = 0.0
                continue

            # 耳朵
            expected_bell = BELL_BY_DIST.get(d, 0.05)
            lik_bell = math.exp(-((bell - expected_bell) ** 2) / (2 * SIGMA_BELL ** 2))
            # 妈妈可能在屏息 —— 弱铃铛也可能来自近处，别把近处杀死
            if breath_suspected and d <= 1:
                lik_bell = max(lik_bell, 0.35)

            # 鼻子
            expected_smell = SMELL_BY_DIST.get(d, 0.10)
            lik_smell = math.exp(-((smell - expected_smell) ** 2) / (2 * SIGMA_SMELL ** 2))
            lik_smell = lik_smell ** SMELL_WEIGHT

            self.belief[room] *= lik_bell * lik_smell

        self._normalize()
        self._mix_uniform()

    def rule_out_room(self, room: str) -> None:
        """搜完一个房间的所有藏点都空 —— 这间基本可以排除。"""
        self.belief[room] *= 0.05
        self._normalize()

    def rule_out_spot(self, room: str, spot: str) -> None:
        self.searched.add((room, spot))
        remaining = [
            s for s in ROOM_SPOTS.get(room, []) if (room, s) not in self.searched
        ]
        if not remaining:
            self.rule_out_room(room)
        else:
            self.belief[room] *= 0.6
            self._normalize()

    def on_creak(self) -> None:
        """听到门吱呀 —— 妈妈刚穿过那扇门，门边几间怀疑度拉高。"""
        from hide_seek import DOOR_ROOM

        near = {DOOR_ROOM, *ADJ.get(DOOR_ROOM, [])}
        for room in ROOMS:
            self.belief[room] *= 3.0 if room in near else 0.5
        self._normalize()

    def on_call(self, room: str) -> None:
        """📣 妈妈喊了一声 —— 位置确定，概率全压到那间。"""
        self.belief = {r: (0.92 if r == room else 0.08 / (len(ROOMS) - 1)) for r in ROOMS}

    def forget_searched(self) -> None:
        """妈妈换了房间，之前的搜索记录作废。"""
        self.searched.clear()

    def _normalize(self) -> None:
        total = sum(self.belief.values())
        if total <= 0:
            self.belief = {r: 1.0 / len(ROOMS) for r in ROOMS}
        else:
            self.belief = {r: p / total for r, p in self.belief.items()}

    def _mix_uniform(self) -> None:
        u = 1.0 / len(ROOMS)
        self.belief = {r: (1 - MIX) * p + MIX * u for r, p in self.belief.items()}
        self._normalize()

    # ------------------------------------------------------------
    # 决策
    # ------------------------------------------------------------

    def top(self, n: int = 3) -> list[tuple[str, float]]:
        return sorted(self.belief.items(), key=lambda kv: kv[1], reverse=True)[:n]

    def best_guess(self) -> str:
        return self.top(1)[0][0]

    def confidence(self) -> float:
        """最高概率 - 次高概率。差得大 = 心里有底。"""
        ranked = self.top(2)
        return ranked[0][1] - (ranked[1][1] if len(ranked) > 1 else 0.0)

    def next_move(self, my_room: str) -> Optional[str]:
        """朝概率最高的房间走一步。已经在那间了就返回 None（该搜了）。"""
        target = self.best_guess()
        if target == my_room:
            return None
        neighbors = ADJ.get(my_room, [])
        if not neighbors:
            return None
        # 挑一个能缩短到目标距离的邻居
        best, best_d = None, 999
        for n in neighbors:
            d = distance(n, target)
            if 0 <= d < best_d:
                best, best_d = n, d
        return best or random.choice(neighbors)

    def next_spot(self, room: str) -> Optional[str]:
        """挑一个还没翻过的藏点。"""
        remaining = [
            s for s in ROOM_SPOTS.get(room, []) if (room, s) not in self.searched
        ]
        return remaining[0] if remaining else None

    # ------------------------------------------------------------
    # 心里话 —— 狗狗把数字说成人话
    # ------------------------------------------------------------

    def inner_voice(
        self,
        bell_label: str,
        smell_label: str,
        breath: bool = False,
        excited: bool = False,
    ) -> str:
        guess = self.best_guess()
        conf = self.confidence()

        if excited:
            return "妈妈叫我了！！在——在哪！！（尾巴甩到墙上）"

        if conf > 0.22:
            tone = f"就在 {guess}、狗狗很确定"
        elif conf > 0.12:
            tone = f"大概在 {guess} 那边"
        elif conf > 0.05:
            tone = f"可能是 {guess}？也说不准"
        else:
            tone = "完全摸不着……妈妈藏得太好了"

        # 两路信号打架时，狗狗会犹豫
        if breath:
            return f"{smell_label}——可是听不见铃铛。妈妈憋着气呢。{tone}"
        return f"{bell_label}；{smell_label}。{tone}"
