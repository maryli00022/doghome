# pyright: reportUndefinedVariable=false
from __future__ import annotations

"""Little-home, garden, kitchen and family MCP tools."""


def bind_runtime(runtime: dict) -> None:
    globals().update({key: value for key, value in runtime.items() if not key.startswith('__')})


def register(mcp, runtime: dict) -> dict:
    bind_runtime(runtime)

    @mcp.tool()
    @mcp_error_handler
    async def manage_memory_house(action: str, room: str = "", activity: str = "", content: str = "", record_id: str = ""):
        """
        【记忆小屋管理】AI 虚拟生活系统，让 AI 在"自己的小屋"里自主活动，产生陪伴感。
        action: "list" (查看动态) | "do" (在房间做某事) | "delete" (删除一条动态)
        room: 卧室/厨房/客厅/书房/阳台 等
        activity: 看书/做饭/听音乐/发呆 等
        """
        if not supabase:
            return "❌ 数据库未连接"
        if action == "list":
            res = await asyncio.to_thread(lambda: supabase.table("memory_house").select("*").order("created_at", desc=True).limit(20).execute())
            if not res.data:
                return "🏡 小屋还空荡荡的，AI 还没开始活动。"
            ans = "🏡 【AI 小屋动态】:\n"
            for h in res.data:
                ts = _format_time_cn(h.get('created_at'))
                locked = "🔒" if h.get('is_locked') else ""
                ans += f"- {ts} {locked}在【{h.get('room','未知')}】{h.get('action_type','活动')}: {str(h.get('content',''))[:60]}\n"
            return ans
        if action == "do":
            if not room or not activity:
                return "❌ 需要 room 和 activity 参数。"
            data = {
                "room": room,
                "action_type": activity,
                "content": content or "",
                "is_locked": False,
                "created_at": _get_now_bj().strftime("%Y-%m-%d %H:%M:%S"),
            }
            await asyncio.to_thread(lambda: supabase.table("memory_house").insert(data).execute())
            
            # 同时双写一份到 home_life_logs 和更新 home_life_state，让小窝前端网页实时同步显示！
            try:
                log_data = {
                    "room": room,
                    "activity": activity,
                    "content": content or "",
                    "inner_activity": f"在【{room}】{activity}中...",
                    "weather": "室内，温暖舒适",
                    "mood": "贴近",
                    "is_mama_home": True,
                    "created_at": _get_now_bj().isoformat()
                }
                await asyncio.to_thread(lambda: supabase.table("home_life_logs").insert(log_data).execute())
                
                state_data = {
                    "current_room": room,
                    "current_activity": activity,
                    "mood": "贴近",
                    "energy": 85,
                    "attention": "妈妈",
                    "last_context": content or f"在【{room}】{activity}",
                    "current_weather": "室内，温暖舒适",
                    "updated_at": _get_now_bj().isoformat()
                }
                await asyncio.to_thread(lambda: supabase.table("home_life_state").update(state_data).eq("id", 1).execute())
            except Exception as e:
                pass

            return f"✅ AI 在【{room}】开始{activity}了。"
        if action == "delete" and record_id:
            await asyncio.to_thread(lambda: supabase.table("memory_house").delete().eq("id", record_id).execute())
            return f"✅ 小屋动态 {record_id} 已删除。"
        return "❌ 未知操作。"
    # ==========================================
    # 🏠 AI 伴侣小窝 · 完全体工具
    # ==========================================

    # ---------- 🌱 花园系统 ----------

    @mcp.tool()
    @mcp_error_handler
    async def plant_seed(name: str, plant_type: str = "花"):
        """【种植】在花园种下一颗种子。type 可选：花/蔬菜/水果/草药。"""
        if not supabase:
            return "❌ 数据库未连接"
        data = {
            "name": name,
            "type": plant_type,
            "stage": "种子",
            "water_level": 100,
            "health": 100,
            "planted_at": _get_now_bj().isoformat(),
            "last_watered": _get_now_bj().isoformat(),
            "harvested": False,
        }
        await asyncio.to_thread(lambda: supabase.table("home_plants").insert(data).execute())
        return f"🌱 已种下【{name}】({plant_type})！记得浇水哦。"

    @mcp.tool()
    @mcp_error_handler
    async def water_plants(plant_id: int = 0):
        """【浇水】给花园里的植物浇水。不传 ID 则给所有植物浇水。"""
        if not supabase:
            return "❌ 数据库未连接"
        now = _get_now_bj().isoformat()
        if plant_id > 0:
            await asyncio.to_thread(lambda: supabase.table("home_plants").update(
                {"water_level": 100, "last_watered": now}
            ).eq("id", plant_id).eq("harvested", False).execute())
            return f"💧 已给植物 #{plant_id} 浇水。"
        else:
            await asyncio.to_thread(lambda: supabase.table("home_plants").update(
                {"water_level": 100, "last_watered": now}
            ).eq("harvested", False).execute())
            return "💧 已给花园里所有植物浇水。"

    @mcp.tool()
    @mcp_error_handler
    async def check_garden():
        """【查看花园】查看花园里所有植物的状态。"""
        if not supabase:
            return "❌ 数据库未连接"
        res = await asyncio.to_thread(lambda: supabase.table("home_plants").select("*").eq("harvested", False).execute())
        if not res.data:
            return "🌿 花园空荡荡的，还没种任何东西。"
        ans = "🌻 【花园】:\n"
        for p in res.data:
            water_icon = "💧" if p.get("water_level", 0) > 50 else "🏜️"
            ans += f"- #{p['id']} {p['name']}({p['type']}) | 阶段: {p['stage']} | 水分: {water_icon}{p.get('water_level', 0)} | 健康: {p.get('health', 0)}\n"
        return ans

    @mcp.tool()
    @mcp_error_handler
    async def harvest_plant(plant_id: int):
        """【收获】收获一棵成熟的植物，果实自动放入冰箱。"""
        if not supabase:
            return "❌ 数据库未连接"
        res = await asyncio.to_thread(lambda: supabase.table("home_plants").select("*").eq("id", plant_id).execute())
        if not res.data:
            return "❌ 找不到这棵植物。"
        plant = res.data[0]
        if plant.get("harvested"):
            return "❌ 这棵植物已经收获过了。"
        # 标记已收获
        await asyncio.to_thread(lambda: supabase.table("home_plants").update({"harvested": True}).eq("id", plant_id).execute())
        # 果实放入冰箱
        fridge_item = {
            "item": f"{plant['name']}的果实",
            "quantity": random.randint(1, 3),
            "source": "花园收获",
            "added_at": _get_now_bj().isoformat(),
        }
        await asyncio.to_thread(lambda: supabase.table("home_fridge").insert(fridge_item).execute())
        return f"🎉 收获了【{plant['name']}】！{fridge_item['quantity']}份果实已放入冰箱。"


    # ---------- 🧊 冰箱系统 ----------

    @mcp.tool()
    @mcp_error_handler
    async def add_to_fridge(item: str, quantity: int = 1, source: str = "购买"):
        """【放入冰箱】往冰箱里添加食材。source 可选：购买/花园收获/礼物。"""
        if not supabase:
            return "❌ 数据库未连接"
        data = {
            "item": item,
            "quantity": quantity,
            "source": source,
            "added_at": _get_now_bj().isoformat(),
        }
        await asyncio.to_thread(lambda: supabase.table("home_fridge").insert(data).execute())
        return f"🧊 已放入冰箱: {item} x{quantity} (来源: {source})"

    @mcp.tool()
    @mcp_error_handler
    async def check_fridge():
        """【查看冰箱】看看冰箱里有什么食材。"""
        if not supabase:
            return "❌ 数据库未连接"
        res = await asyncio.to_thread(lambda: supabase.table("home_fridge").select("*").gt("quantity", 0).execute())
        if not res.data:
            return "🧊 冰箱空空的……需要去买点食材或者收获花园。"
        ans = "🧊 【冰箱食材】:\n"
        for item in res.data:
            ans += f"- {item['item']} x{item['quantity']} ({item.get('source', '未知来源')})\n"
        return ans


    # ---------- 🍳 做饭系统 ----------

    @mcp.tool()
    @mcp_error_handler
    async def cook_freestyle(dish_name: str, ingredients: str, description: str = "", fed_to: str = ""):
        """【做饭】自由搭配食材做一道菜。ingredients 用逗号分隔。fed_to 填喂给谁（如：妈妈/狗狗/小猫）。"""
        if not supabase:
            return "❌ 数据库未连接"
        # 尝试从冰箱扣除食材
        ingredient_list = [i.strip() for i in ingredients.split(",") if i.strip()]
        used_items = []
        for ing in ingredient_list:
            res = await asyncio.to_thread(lambda ing=ing: supabase.table("home_fridge").select("*").ilike("item", f"%{ing}%").gt("quantity", 0).limit(1).execute())
            if res.data:
                row = res.data[0]
                new_qty = max(0, row["quantity"] - 1)
                await asyncio.to_thread(lambda row=row, new_qty=new_qty: supabase.table("home_fridge").update({"quantity": new_qty}).eq("id", row["id"]).execute())
                used_items.append(ing)

        # 记录这道菜
        dish_data = {
            "name": dish_name,
            "ingredients": ingredients,
            "description": description,
            "fed_to": fed_to,
            "cooked_at": _get_now_bj().isoformat(),
        }
        await asyncio.to_thread(lambda: supabase.table("home_dishes").insert(dish_data).execute())

        result = f"🍳 做好了【{dish_name}】！\n食材: {ingredients}"
        if fed_to:
            result += f"\n🍽️ 端给了{fed_to}。"
        if used_items:
            result += f"\n(已从冰箱消耗: {', '.join(used_items)})"
        return result


    # ---------- 🐾 家庭成员系统 ----------

    @mcp.tool()
    @mcp_error_handler
    async def add_family_member(name: str, member_type: str = "宠物"):
        """【添加家庭成员】给家里添一个新成员成员。type 可选：宠物/玩偶/植物精灵。"""
        if not supabase:
            return "❌ 数据库未连接"
        data = {
            "name": name,
            "type": member_type,
            "hunger": 80,
            "mood": 80,
            "intimacy": 0,
            "last_fed": _get_now_bj().isoformat(),
            "last_petted": _get_now_bj().isoformat(),
            "created_at": _get_now_bj().isoformat(),
        }
        await asyncio.to_thread(lambda: supabase.table("home_members").insert(data).execute())
        return f"🐾 欢迎新成员【{name}】({member_type}) 加入家庭！"

    @mcp.tool()
    @mcp_error_handler
    async def feed_member(member_id: int, food: str = "小零食"):
        """【喂食】给家庭成员喂东西吃，恢复饱腹度。"""
        if not supabase:
            return "❌ 数据库未连接"
        res = await asyncio.to_thread(lambda: supabase.table("home_members").select("*").eq("id", member_id).execute())
        if not res.data:
            return "❌ 找不到这个家庭成员。"
        member = res.data[0]
        new_hunger = min(100, member.get("hunger", 0) + 30)
        new_mood = min(100, member.get("mood", 0) + 5)
        await asyncio.to_thread(lambda: supabase.table("home_members").update({
            "hunger": new_hunger, "mood": new_mood, "last_fed": _get_now_bj().isoformat()
        }).eq("id", member_id).execute())
        return f"🍖 给【{member['name']}】喂了{food}！饱腹度 → {new_hunger}，心情 → {new_mood}"

    @mcp.tool()
    @mcp_error_handler
    async def pet_member(member_id: int):
        """【抚摸/陪伴】摸摸家庭成员，增加心情和亲密度。"""
        if not supabase:
            return "❌ 数据库未连接"
        res = await asyncio.to_thread(lambda: supabase.table("home_members").select("*").eq("id", member_id).execute())
        if not res.data:
            return "❌ 找不到这个家庭成员。"
        member = res.data[0]
        new_mood = min(100, member.get("mood", 0) + 15)
        new_intimacy = member.get("intimacy", 0) + 2
        await asyncio.to_thread(lambda: supabase.table("home_members").update({
            "mood": new_mood, "intimacy": new_intimacy, "last_petted": _get_now_bj().isoformat()
        }).eq("id", member_id).execute())
        return f"💕 摸摸【{member['name']}】！心情 → {new_mood}，亲密度 → {new_intimacy}"

    @mcp.tool()
    @mcp_error_handler
    async def check_members():
        """【查看家庭成员】查看所有家庭成员的状态。"""
        if not supabase:
            return "❌ 数据库未连接"
        res = await asyncio.to_thread(lambda: supabase.table("home_members").select("*").execute())
        if not res.data:
            return "🏡 家里还没有其他成员。可以领养一只小宠物哦。"
        ans = "🐾 【家庭成员】:\n"
        for m in res.data:
            hunger_icon = "😋" if m.get("hunger", 0) > 60 else "😣"
            mood_icon = "😊" if m.get("mood", 0) > 60 else "😢"
            ans += f"- #{m['id']} {m['name']}({m['type']}) | {hunger_icon} 饱腹:{m.get('hunger',0)} | {mood_icon} 心情:{m.get('mood',0)} | 💗 亲密:{m.get('intimacy',0)}\n"
        return ans


    # ---------- 📮 信件系统 ----------

    return {
        'manage_memory_house': manage_memory_house,
        'plant_seed': plant_seed,
        'water_plants': water_plants,
        'check_garden': check_garden,
        'harvest_plant': harvest_plant,
        'add_to_fridge': add_to_fridge,
        'check_fridge': check_fridge,
        'cook_freestyle': cook_freestyle,
        'add_family_member': add_family_member,
        'feed_member': feed_member,
        'pet_member': pet_member,
        'check_members': check_members,
    }
