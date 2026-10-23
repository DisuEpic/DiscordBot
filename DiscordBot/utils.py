import disnake
from typing import Optional, List, Dict, Any
from api import api

async def send_log(guild: disnake.Guild, embed: disnake.Embed):
    cfg = await api.get_guild_config(str(guild.id))
    if not cfg or not cfg.get("logChannelId"):
        return
    try:
        log_channel_id = int(cfg["logChannelId"])
    except (ValueError, TypeError):
        return
    log_channel = guild.get_channel(log_channel_id)
    if log_channel and isinstance(log_channel, disnake.TextChannel):
        try:
            await log_channel.send(embed=embed)
        except disnake.Forbidden:
            pass

def parse_emoji(raw: Optional[str]):
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.startswith("<"):
        try:
            return disnake.PartialEmoji.from_str(raw)
        except Exception:
            return None
    return raw if len(raw) <= 8 else None

def add_chunked_role_fields(embed: disnake.Embed, field_name: str, roles_list: List[Dict[str, Any]]):
    lines = [f"• {r.get('emoji', '🔹')} <@&{r['roleId']}> — **{r['name']}**" for r in roles_list]
    chunks: List[str] = []
    current_chunk = ""

    for line in lines:
        candidate = f"{current_chunk}\n{line}" if current_chunk else line
        if len(candidate) > 1024:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line[:1024]
        else:
            current_chunk = candidate

    if current_chunk:
        chunks.append(current_chunk)

    for idx, chunk in enumerate(chunks):
        title = field_name if idx == 0 else f"{field_name} (продолжение {idx + 1})"
        embed.add_field(name=title, value=chunk, inline=False)

def check_moderation_target(inter: disnake.ApplicationCommandInteraction, target: disnake.Member) -> Optional[str]:
    if target.id == inter.author.id:
        return "❌ Вы не можете применить это действие к самому себе."
    if target.id == inter.bot.user.id:
        return "❌ Вы не можете применить это действие к модулю Aigis."
    if target.id == inter.guild.owner_id:
        return "❌ Невозможно применить наказание к владельцу сервера."
    if inter.author.id != inter.guild.owner_id and target.top_role >= inter.author.top_role:
        return "❌ Вы не можете применить это действие к участнику с ролью равной или выше вашей."
    if inter.guild.me and target.top_role >= inter.guild.me.top_role:
        return "⚠️ Роль этого участника находится выше или на одном уровне с ролью бота."
    return None

def check_role_target(inter: disnake.ApplicationCommandInteraction, target: disnake.Member, role: disnake.Role) -> Optional[str]:
    is_owner = inter.author.id == inter.guild.owner_id

    if not is_owner and role >= inter.author.top_role:
        return "❌ Вы не можете управлять ролью, равной или выше вашей собственной."
    if not is_owner and target.id != inter.author.id and target.top_role >= inter.author.top_role:
        return "❌ Вы не можете менять роли участника с ролью равной или выше вашей."
    if role.is_default() or role.managed:
        return "❌ Эту роль нельзя выдавать или снимать вручную (системная или интеграционная)."
    if inter.guild.me and role >= inter.guild.me.top_role:
        return "⚠️ Эта роль находится выше или на одном уровне с ролью бота."
    return None