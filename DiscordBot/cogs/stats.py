import asyncio
import disnake
from disnake.ext import commands, tasks
from typing import Optional, Dict, Any, Set
from api import api
from config import GUILD_ONLY, BRAND_COLOR, TACTICAL_GREEN, ACCENT_GOLD, UNIFIED_FOOTER, log


STAT_LABELS = {
    "en": {
        "category": "📊 SERVER STATS 📊",
        "all_members": "All Members: {count}",
        "members": "Members: {count}",
        "bots": "Bots: {count}",
        "channels": "Channels: {count}",
        "roles": "Roles: {count}",
        "voice": "In Voice: {count}",
    },
    "ru": {
        "category": "📊 СТАТИСТИКА СЕРВЕРА 📊",
        "all_members": "👥 Всего: {count}",
        "members": "👤 Участники: {count}",
        "bots": "🤖 Боты: {count}",
        "channels": "💬 Каналы: {count}",
        "roles": "🎭 Роли: {count}",
        "voice": "🔊 В войсе: {count}",
    },
}

STAT_FIELD_MAP = [
    ("all_members", "allMembersChannelId"),
    ("members", "membersChannelId"),
    ("bots", "botsChannelId"),
    ("channels", "channelsChannelId"),
    ("roles", "rolesChannelId"),
    ("voice", "voiceChannelId"),
]


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ignored_audit_ids: Set[int] = set()
        self.update_stats_loop.start()

    def cog_unload(self):
        self.update_stats_loop.cancel()

    @staticmethod
    def _compute_metrics(guild: disnake.Guild) -> Dict[str, int]:
        all_members = guild.member_count or len(guild.members)
        bots = sum(1 for m in guild.members if m.bot)
        members = max(0, all_members - bots)
        channels = sum(1 for c in guild.channels if not isinstance(c, disnake.CategoryChannel))
        roles = max(0, len(guild.roles) - 1)  # без @everyone
        voice = sum(len([m for m in vc.members if not m.bot]) for vc in guild.voice_channels)
        return {
            "all_members": all_members,
            "members": members,
            "bots": bots,
            "channels": channels,
            "roles": roles,
            "voice": voice,
        }

    @staticmethod
    def _format_name(style: str, key: str, value: int) -> str:
        tpl_map = STAT_LABELS.get(style, STAT_LABELS["en"])
        return tpl_map[key].format(count=value)[:100]

    async def _sync_guild_stats(self, guild: disnake.Guild, stats_cfg: Dict[str, Any]) -> int:
        """Обновляет названия каналов статистики, если цифры изменились. Возвращает число обновлённых каналов."""
        if not stats_cfg.get("enabled"):
            return 0

        style = stats_cfg.get("style") or "en"
        metrics = self._compute_metrics(guild)
        updated = 0

        for metric_key, dto_field in STAT_FIELD_MAP:
            ch_id_str = stats_cfg.get(dto_field)
            if not ch_id_str or not str(ch_id_str).isdigit():
                continue

            ch = guild.get_channel(int(ch_id_str))
            if not isinstance(ch, disnake.VoiceChannel):
                continue

            target_name = self._format_name(style, metric_key, metrics[metric_key])
            if ch.name == target_name:
                continue

            self.ignored_audit_ids.add(ch.id)
            try:
                await ch.edit(name=target_name, reason="Обновление счётчиков статистики Mirei")
                updated += 1
                await asyncio.sleep(1.0)
            except disnake.HTTPException:
                pass
            finally:
                self.ignored_audit_ids.discard(ch.id)

        return updated

    @tasks.loop(minutes=10.0)
    async def update_stats_loop(self):
        for guild in list(self.bot.guilds):
            try:
                cfg = await api.get_guild_config(str(guild.id))
                stats_cfg = (cfg or {}).get("stats") or {}
                if stats_cfg.get("enabled"):
                    await self._sync_guild_stats(guild, stats_cfg)
            except Exception:
                log.exception("Ошибка обновления статистики для сервера %s", guild.id)

    @update_stats_loop.before_loop
    async def before_update_stats_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)


    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="stats",
        description="📊 Управление счётчиками статистики сервера"
    )
    @commands.default_member_permissions(administrator=True)
    async def stats_group(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @stats_group.sub_command(name="setup", description="Создать или обновить категорию и каналы счётчиков статистики")
    async def stats_setup(
        self,
        inter: disnake.ApplicationCommandInteraction,
        style: str = commands.Param(
            default="en",
            choices={
                "🇬🇧 English (All Members: 218)": "en",
                "🇷🇺 Русский (👥 Всего: 218)": "ru",
            },
            description="Язык и стиль подписей каналов"
        ),
        include_all_members: bool = commands.Param(default=True, description="Счётчик всех участников"),
        include_members: bool = commands.Param(default=True, description="Счётчик людей (без ботов)"),
        include_bots: bool = commands.Param(default=True, description="Счётчик ботов"),
        include_channels: bool = commands.Param(default=True, description="Счётчик каналов"),
        include_roles: bool = commands.Param(default=True, description="Счётчик ролей"),
        include_voice: bool = commands.Param(default=False, description="Счётчик участников в войсе прямо сейчас"),
        category: Optional[disnake.CategoryChannel] = commands.Param(default=None, description="Существующая категория (если не указывать — создаст новую сверху)")
    ):
        await inter.response.defer(ephemeral=True)
        guild = inter.guild
        guild_id = str(guild.id)

        cfg = await api.get_guild_config(guild_id) or {}
        existing_stats = cfg.get("stats") or {}

        # 1. Находим или создаём категорию
        target_cat = category
        if not target_cat and existing_stats.get("categoryId") and str(existing_stats["categoryId"]).isdigit():
            maybe_cat = guild.get_channel(int(existing_stats["categoryId"]))
            if isinstance(maybe_cat, disnake.CategoryChannel):
                target_cat = maybe_cat

        overwrites = {
            guild.default_role: disnake.PermissionOverwrite(view_channel=True, connect=False),
        }
        if guild.me:
            overwrites[guild.me] = disnake.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True)

        if not target_cat:
            cat_name = STAT_LABELS[style]["category"]
            try:
                target_cat = await guild.create_category(
                    name=cat_name,
                    overwrites=overwrites,
                    position=0,
                    reason=f"Настройка статистики Mirei ({inter.author})"
                )
                self.ignored_audit_ids.add(target_cat.id)
            except disnake.Forbidden:
                await inter.edit_original_response(content="⚠️ У бота недостаточно прав для создания категорий и каналов.")
                return

        metrics = self._compute_metrics(guild)
        toggles = {
            "all_members": include_all_members,
            "members": include_members,
            "bots": include_bots,
            "channels": include_channels,
            "roles": include_roles,
            "voice": include_voice,
        }

        if not any(toggles.values()):
            await inter.edit_original_response(content="⚠️ Вы отключили все счётчики. Включите хотя бы один!")
            return

        payload: Dict[str, Any] = {
            "enabled": True,
            "style": style,
            "categoryId": str(target_cat.id),
        }

        created_lines = []
        for metric_key, dto_field in STAT_FIELD_MAP:
            enabled_flag = toggles[metric_key]
            existing_id = existing_stats.get(dto_field)
            existing_ch = guild.get_channel(int(existing_id)) if (existing_id and str(existing_id).isdigit()) else None

            if not enabled_flag:
                # Если админ отключил конкретный счётчик при повторной настройке — удаляем старый канал
                if isinstance(existing_ch, disnake.VoiceChannel):
                    self.ignored_audit_ids.add(existing_ch.id)
                    try:
                        await existing_ch.delete(reason="Отключение счётчика статистики")
                    except disnake.HTTPException:
                        pass
                payload[dto_field] = None
                continue

            ch_name = self._format_name(style, metric_key, metrics[metric_key])
            if isinstance(existing_ch, disnake.VoiceChannel):
                if existing_ch.name != ch_name:
                    self.ignored_audit_ids.add(existing_ch.id)
                    try:
                        await existing_ch.edit(name=ch_name)
                    except disnake.HTTPException:
                        pass
                payload[dto_field] = str(existing_ch.id)
                created_lines.append(f"• {existing_ch.mention} (`{ch_name}`)")
            else:
                try:
                    new_ch = await guild.create_voice_channel(
                        name=ch_name,
                        category=target_cat,
                        overwrites=overwrites,
                        reason="Канал статистики сервера Mirei"
                    )
                    self.ignored_audit_ids.add(new_ch.id)
                    payload[dto_field] = str(new_ch.id)
                    created_lines.append(f"• {new_ch.mention} (`{ch_name}`)")
                    await asyncio.sleep(0.4)
                except disnake.Forbidden:
                    payload[dto_field] = None

        await asyncio.sleep(1.5)
        self.ignored_audit_ids.clear()

        if await api.update_stats_config(guild_id, payload):
            embed = disnake.Embed(
                title="📊 Статистика сервера настроена!",
                description=(
                    f"**Категория:** `{target_cat.name}`\n"
                    f"**Авто-обновление:** каждые 10 минут\n\n"
                    + ("\n".join(created_lines) if created_lines else "*Каналы не созданы*")
                ),
                color=TACTICAL_GREEN
            )
            embed.set_footer(text=UNIFIED_FOOTER)
            await inter.edit_original_response(embed=embed)
        else:
            await inter.edit_original_response(content="❌ Каналы созданы, но не удалось сохранить настройки в БД.")

    @stats_group.sub_command(name="refresh", description="Принудительно обновить каналы статистики прямо сейчас")
    @commands.cooldown(1, 300, commands.BucketType.guild)
    async def stats_refresh(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        cfg = await api.get_guild_config(str(inter.guild_id)) or {}
        stats_cfg = cfg.get("stats") or {}
        if not stats_cfg.get("enabled"):
            await inter.edit_original_response(content="⚠️ Статистика на этом сервере не настроена или отключена. Используйте `/stats setup`.")
            return

        updated = await self._sync_guild_stats(inter.guild, stats_cfg)
        if updated > 0:
            await inter.edit_original_response(content=f"✅ Обновлено каналов статистики: **{updated}** шт.!")
        else:
            await inter.edit_original_response(content="✅ Все показатели уже актуальны — переименование не потребовалось.")

    @stats_group.sub_command(name="toggle", description="Включить или поставить на паузу авто-обновление счётчиков")
    async def stats_toggle(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)
        cfg = await api.get_guild_config(guild_id) or {}
        stats_cfg = dict(cfg.get("stats") or {})

        if not any(stats_cfg.get(f) for _, f in STAT_FIELD_MAP):
            await inter.edit_original_response(content="⚠️ Сначала создайте каналы статистики командой `/stats setup`.")
            return

        new_state = not stats_cfg.get("enabled", False)
        stats_cfg["enabled"] = new_state
        if await api.update_stats_config(guild_id, stats_cfg):
            msg = "🟢 Авто-обновление статистики **включено**!" if new_state else "🟡 Авто-обновление статистики **поставлено на паузу**."
            await inter.edit_original_response(content=msg)
        else:
            await inter.edit_original_response(content="❌ Не удалось сохранить состояние в БД.")

    @stats_group.sub_command(name="remove", description="Отключить статистику и удалить созданные каналы")
    async def stats_remove(
        self,
        inter: disnake.ApplicationCommandInteraction,
        delete_channels: bool = commands.Param(default=True, description="Удалить сами голосовые каналы и пустую категорию из Discord?")
    ):
        await inter.response.defer(ephemeral=True)
        guild = inter.guild
        guild_id = str(guild.id)

        cfg = await api.get_guild_config(guild_id) or {}
        stats_cfg = cfg.get("stats") or {}

        deleted_count = 0
        if delete_channels:
            for _, dto_field in STAT_FIELD_MAP:
                ch_id = stats_cfg.get(dto_field)
                if ch_id and str(ch_id).isdigit():
                    ch = guild.get_channel(int(ch_id))
                    if ch:
                        self.ignored_audit_ids.add(ch.id)
                        try:
                            await ch.delete(reason=f"Удаление статистики ({inter.author})")
                            deleted_count += 1
                            await asyncio.sleep(0.3)
                        except disnake.HTTPException:
                            pass

            cat_id = stats_cfg.get("categoryId")
            if cat_id and str(cat_id).isdigit():
                cat = guild.get_channel(int(cat_id))
                if isinstance(cat, disnake.CategoryChannel) and len(cat.channels) == 0:
                    self.ignored_audit_ids.add(cat.id)
                    try:
                        await cat.delete(reason="Удаление пустой категории статистики")
                    except disnake.HTTPException:
                        pass

            await asyncio.sleep(1.0)
            self.ignored_audit_ids.clear()

        reset_payload = {
            "enabled": False,
            "style": stats_cfg.get("style", "en"),
            "categoryId": None,
            "allMembersChannelId": None,
            "membersChannelId": None,
            "botsChannelId": None,
            "channelsChannelId": None,
            "rolesChannelId": None,
            "voiceChannelId": None,
        }
        await api.update_stats_config(guild_id, reset_payload)
        await inter.edit_original_response(
            content=f"🗑️ Модуль статистики отключен! Удалено каналов: **{deleted_count}** шт."
        )

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="server_stats",
        description="📊 Подробная статистика сервера в реальном времени"
    )
    async def server_stats(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer()
        guild = inter.guild
        m = self._compute_metrics(guild)

        online = sum(1 for u in guild.members if not u.bot and u.status == disnake.Status.online)
        idle = sum(1 for u in guild.members if not u.bot and u.status == disnake.Status.idle)
        dnd = sum(1 for u in guild.members if not u.bot and u.status == disnake.Status.dnd)
        offline = max(0, m["members"] - (online + idle + dnd))

        embed = disnake.Embed(
            title=f"📊 Статистика сервера: {guild.name}",
            color=BRAND_COLOR,
            timestamp=disnake.utils.utcnow()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name="👥 Участники",
            value=f"Всего: **{m['all_members']}**\nЛюдей: **{m['members']}** | Ботов: **{m['bots']}**",
            inline=True
        )
        embed.add_field(
            name="📡 Онлайн-активность",
            value=f"🟢 В сети: **{online}** | 🌙 Отошёл: **{idle}**\n⛔ Не бесп.: **{dnd}** | ⚫ Оффлайн: **{offline}**",
            inline=True
        )
        embed.add_field(
            name="🔊 В голосовых каналах",
            value=f"Сейчас общаются: **{m['voice']}** чел.",
            inline=False
        )
        embed.add_field(
            name="💬 Структура",
            value=f"Каналов: **{m['channels']}** (Текст: {len(guild.text_channels)} | Голос: {len(guild.voice_channels)})\nРолей: **{m['roles']}**",
            inline=True
        )
        embed.add_field(
            name="🚀 Бусты сервера",
            value=f"Уровень: **{guild.premium_tier}**\nБустов: **{guild.premium_subscription_count or 0}**",
            inline=True
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Stats(bot))