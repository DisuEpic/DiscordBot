import asyncio
import time
import disnake
from collections import deque
from typing import Optional, List, Dict, Any, Tuple
from api import api
from config import TACTICAL_GREEN, UNIFIED_FOOTER

DEFAULT_WELCOME_TITLE = "🌸 Добро пожаловать на {server}!"
DEFAULT_WELCOME_DESC = (
    "Приветствуем, {user}!\n"
    "Рады видеть тебя на нашем сервере!"
)

# Настраиваемые лимиты очереди логов и кэша вебхуков
MAX_LOG_BUFFER_PER_GUILD = 100
MAX_WEBHOOK_CACHE_ENTRIES = 1000
_WEBHOOK_CACHE_TTL = 600.0

# Очередь батчинга логов: guild_id -> deque[(TextChannel, Embed)]
_log_buffers: Dict[int, deque] = {}
_log_flush_tasks: Dict[int, asyncio.Task] = {}
# Кэш вебхуков: channel_id -> (timestamp, Webhook | None)
_webhook_cache: Dict[int, Tuple[float, Optional[disnake.Webhook]]] = {}


def _prune_webhook_cache(now: float):
    """Удаляет устаревшие записи из кэша вебхуков, чтобы не тратить лишнюю ОЗУ."""
    if len(_webhook_cache) <= MAX_WEBHOOK_CACHE_ENTRIES:
        return
    expired = [cid for cid, (ts, _) in _webhook_cache.items() if (now - ts) >= _WEBHOOK_CACHE_TTL]
    for cid in expired:
        _webhook_cache.pop(cid, None)

    if len(_webhook_cache) > MAX_WEBHOOK_CACHE_ENTRIES:
        oldest = sorted(_webhook_cache.items(), key=lambda item: item[1][0])[: len(_webhook_cache) // 5]
        for cid, _ in oldest:
            _webhook_cache.pop(cid, None)


async def _get_or_create_log_webhook(channel: disnake.TextChannel) -> Optional[disnake.Webhook]:
    now = time.time()
    cached = _webhook_cache.get(channel.id)
    if cached and (now - cached[0]) < _WEBHOOK_CACHE_TTL:
        return cached[1]

    _prune_webhook_cache(now)

    me = channel.guild.me
    if not me or not channel.permissions_for(me).manage_webhooks:
        _webhook_cache[channel.id] = (now, None)
        return None

    try:
        webhooks = await channel.webhooks()
        for wh in webhooks:
            if wh.user and me and wh.user.id == me.id and wh.name == "Mirei Logs":
                _webhook_cache[channel.id] = (now, wh)
                return wh

        if len(webhooks) < 15:
            wh = await channel.create_webhook(name="Mirei Logs", reason="Оптимизированное логирование Mirei")
            _webhook_cache[channel.id] = (now, wh)
            return wh
    except disnake.HTTPException:
        pass

    _webhook_cache[channel.id] = (now, None)
    return None


async def _send_embed_batch(channel: disnake.TextChannel, embeds: List[disnake.Embed]):
    if not embeds:
        return

    webhook = await _get_or_create_log_webhook(channel)
    if webhook is not None:
        try:
            me = channel.guild.me
            await webhook.send(
                embeds=embeds,
                username="Mirei • Аудит",
                avatar_url=me.display_avatar.url if me else None,
            )
            return
        except disnake.NotFound:
            _webhook_cache.pop(channel.id, None)
        except disnake.HTTPException:
            pass

    try:
        await channel.send(embeds=embeds)
    except disnake.HTTPException:
        pass


async def _flush_guild_logs(guild_id: int):
    try:
        await asyncio.sleep(1.2)
        buf = _log_buffers.get(guild_id)
        while buf:
            first_channel, first_embed = buf.popleft()
            batch: List[disnake.Embed] = [first_embed]
            total_chars = len(first_embed)

            while buf and len(batch) < 10:
                next_channel, next_embed = buf[0]
                if next_channel.id != first_channel.id:
                    break
                next_len = len(next_embed)
                if total_chars + next_len > 5500:
                    break
                buf.popleft()
                batch.append(next_embed)
                total_chars += next_len

            await _send_embed_batch(first_channel, batch)
            if buf:
                await asyncio.sleep(0.5)
    finally:
        _log_flush_tasks.pop(guild_id, None)
        if guild_id in _log_buffers and len(_log_buffers[guild_id]) == 0:
            _log_buffers.pop(guild_id, None)


async def send_log(guild: disnake.Guild, embed: disnake.Embed):
    cfg = await api.get_guild_config(str(guild.id))
    if not cfg or not cfg.get("logChannelId"):
        return
    try:
        log_channel_id = int(cfg["logChannelId"])
    except (ValueError, TypeError):
        return
    log_channel = guild.get_channel(log_channel_id)
    if not log_channel or not isinstance(log_channel, disnake.TextChannel):
        return

    buf = _log_buffers.setdefault(guild.id, deque(maxlen=MAX_LOG_BUFFER_PER_GUILD))
    buf.append((log_channel, embed))

    task = _log_flush_tasks.get(guild.id)
    if task is None or task.done():
        _log_flush_tasks[guild.id] = asyncio.create_task(_flush_guild_logs(guild.id))


async def send_welcome_card(
    member: disnake.Member,
    guild_config: Dict[str, Any],
    extra_roles: Optional[List[disnake.Role]] = None
):
    welcome_cfg = guild_config.get("welcome") or {}
    welcome_channel_id = welcome_cfg.get("channelId")
    if not welcome_channel_id:
        return
    try:
        welcome_channel = member.guild.get_channel(int(welcome_channel_id))
    except (ValueError, TypeError):
        return

    if not welcome_channel or not isinstance(welcome_channel, disnake.TextChannel):
        return

    raw_title = welcome_cfg.get("title") or DEFAULT_WELCOME_TITLE
    raw_desc = welcome_cfg.get("description") or DEFAULT_WELCOME_DESC

    final_title = raw_title.replace("{user}", member.display_name).replace("{server}", member.guild.name)
    final_desc = raw_desc.replace("{user}", member.mention).replace("{server}", member.guild.name)

    welcome_embed = disnake.Embed(
        title=final_title,
        description=final_desc,
        color=TACTICAL_GREEN
    )
    welcome_embed.set_thumbnail(url=member.display_avatar.url)
    welcome_embed.set_footer(text=UNIFIED_FOOTER)

    try:
        await welcome_channel.send(embed=welcome_embed)
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
        return "❌ Вы не можете применить это действие к боту Mirei."
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