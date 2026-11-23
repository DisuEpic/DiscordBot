import asyncio
from typing import Any, Dict, Optional, Set

import disnake
from disnake.ext import commands, tasks

from api import api
from config import BRAND_COLOR, GUILD_ONLY, TACTICAL_GREEN, UNIFIED_FOOTER, log


STAT_LABELS = {
    "en": {
        "category": "📊 Server stats 📊",
        "all_members": "All Members: {count}",
        "members": "Members: {count}",
        "bots": "Bots: {count}",
        "channels": "Channels: {count}",
        "roles": "Roles: {count}",
        "voice": "In Voice: {count}",
    },
    "ru": {
        "category": "📊 Статистика сервера 📊",
        "all_members": "Всего участников: {count}",
        "members": "Участники: {count}",
        "bots": "Боты: {count}",
        "channels": "Каналы: {count}",
        "roles": "Роли: {count}",
        "voice": "В войсе: {count}",
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
    def _compute_metrics(
        guild: disnake.Guild, include_statuses: bool = False
    ) -> Dict[str, int]:
        all_members = guild.member_count or len(guild.members)
        bots = online = idle = dnd = 0

        for member in guild.members:
            if member.bot:
                bots += 1
            elif include_statuses:
                if member.status == disnake.Status.online:
                    online += 1
                elif member.status == disnake.Status.idle:
                    idle += 1
                elif member.status == disnake.Status.dnd:
                    dnd += 1

        members = max(0, all_members - bots)
        channels = sum(
            1 for channel in guild.channels
            if not isinstance(channel, disnake.CategoryChannel)
        )
        roles = max(0, len(guild.roles) - 1)
        voice = sum(
            1
            for channel in guild.voice_channels
            for member in channel.members
            if not member.bot
        )

        metrics = {
            "all_members": all_members,
            "members": members,
            "bots": bots,
            "channels": channels,
            "roles": roles,
            "voice": voice,
        }
        if include_statuses:
            metrics.update(
                online=online,
                idle=idle,
                dnd=dnd,
                offline=max(0, members - online - idle - dnd),
            )
        return metrics

    @staticmethod
    def _format_name(style: str, key: str, value: int) -> str:
        labels = STAT_LABELS.get(style, STAT_LABELS["en"])
        return labels[key].format(count=value)[:100]

    async def _sync_guild_stats(
        self, guild: disnake.Guild, stats: Dict[str, Any]
    ) -> int:
        if not stats.get("enabled"):
            return 0

        style = stats.get("style") or "en"
        metrics = self._compute_metrics(guild)
        updated = 0

        for key, field in STAT_FIELD_MAP:
            channel_id = stats.get(field)
            if not channel_id or not str(channel_id).isdigit():
                continue

            channel = guild.get_channel(int(channel_id))
            if not isinstance(channel, disnake.VoiceChannel):
                continue

            name = self._format_name(style, key, metrics[key])
            if channel.name == name:
                continue

            self.ignored_audit_ids.add(channel.id)
            try:
                await channel.edit(name=name, reason="Обновление счётчиков Mirei")
                updated += 1
                await asyncio.sleep(1.0)
            except disnake.HTTPException:
                pass
            finally:
                self.ignored_audit_ids.discard(channel.id)

        return updated

    @tasks.loop(minutes=10.0)
    async def update_stats_loop(self):
        for guild in list(self.bot.guilds):
            try:
                config = await api.get_guild_config(str(guild.id))
                stats = (config or {}).get("stats") or {}
                if stats.get("enabled"):
                    await self._sync_guild_stats(guild, stats)
            except Exception:
                log.exception("Ошибка обновления статистики для сервера %s", guild.id)
            await asyncio.sleep(0)

    @update_stats_loop.before_loop
    async def before_update_stats_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)

    @commands.slash_command(
        contexts=GUILD_ONLY,
        name="статистика",
        description="Управление счётчиками статистики сервера",
    )
    async def stats_group(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @stats_group.sub_command(
        name="настроить", description="Создать или обновить каналы счётчиков"
    )
    @commands.has_guild_permissions(administrator=True)
    async def stats_setup(
        self,
        inter: disnake.ApplicationCommandInteraction,
        style: str = commands.Param(
            name="стиль",
            default="en",
            choices={
                "🇬🇧 English (All Members: 218)": "en",
                "🇷🇺 Русский (👥 Всего: 218)": "ru",
            },
            description="Язык подписей каналов",
        ),
        include_all_members: bool = commands.Param(
            name="все_участники", default=True, description="Счётчик всех участников"
        ),
        include_members: bool = commands.Param(
            name="люди", default=True, description="Счётчик людей без ботов"
        ),
        include_bots: bool = commands.Param(
            name="боты", default=True, description="Счётчик ботов"
        ),
        include_channels: bool = commands.Param(
            name="каналы", default=True, description="Счётчик каналов"
        ),
        include_roles: bool = commands.Param(
            name="роли", default=True, description="Счётчик ролей"
        ),
        include_voice: bool = commands.Param(
            name="в_голосовых",
            default=False,
            description="Счётчик участников в голосовых каналах",
        ),
        category: Optional[disnake.CategoryChannel] = commands.Param(
            name="категория", default=None, description="Категория для новых счётчиков"
        ),
    ):
        await inter.response.defer(ephemeral=True)
        guild = inter.guild
        guild_id = str(guild.id)

        toggles = {
            "all_members": include_all_members,
            "members": include_members,
            "bots": include_bots,
            "channels": include_channels,
            "roles": include_roles,
            "voice": include_voice,
        }
        if not any(toggles.values()):
            await inter.edit_original_response(content="Включи хотя бы один счётчик.")
            return

        config = await api.get_guild_config_for_update(guild_id)
        if config is None:
            await inter.edit_original_response(content="API не вернуло настройки статистики.")
            return
        existing = config.get("stats") or {}

        target_category = category
        existing_category_id = str(existing.get("categoryId") or "")
        if target_category is None and existing_category_id.isdecimal():
            old_category = guild.get_channel(int(existing_category_id))
            if isinstance(old_category, disnake.CategoryChannel):
                target_category = old_category

        overwrites = {
            guild.default_role: disnake.PermissionOverwrite(
                view_channel=True, connect=False
            ),
        }
        if guild.me:
            overwrites[guild.me] = disnake.PermissionOverwrite(
                view_channel=True, connect=True, manage_channels=True
            )

        if target_category is None:
            try:
                target_category = await guild.create_category(
                    name=STAT_LABELS[style]["category"],
                    overwrites=overwrites,
                    position=0,
                    reason=f"Настройка статистики Mirei ({inter.author})",
                )
                self.ignored_audit_ids.add(target_category.id)
            except disnake.Forbidden:
                await inter.edit_original_response(
                    content="⚠️ У бота недостаточно прав для создания категории."
                )
                return

        metrics = self._compute_metrics(guild)
        payload: Dict[str, Any] = {
            "enabled": True,
            "style": style,
            "categoryId": str(target_category.id),
        }
        lines = []

        for key, field in STAT_FIELD_MAP:
            channel_id = str(existing.get(field) or "")
            channel = guild.get_channel(int(channel_id)) if channel_id.isdecimal() else None

            if not toggles[key]:
                if isinstance(channel, disnake.VoiceChannel):
                    self.ignored_audit_ids.add(channel.id)
                    try:
                        await channel.delete(reason="Отключение счётчика статистики")
                    except disnake.NotFound:
                        pass
                    except disnake.HTTPException:
                        payload[field] = str(channel.id)
                        lines.append(f"• Не удалось удалить {channel.mention}.")
                        continue

                payload[field] = None
                continue

            name = self._format_name(style, key, metrics[key])
            if isinstance(channel, disnake.VoiceChannel):
                if channel.name != name:
                    self.ignored_audit_ids.add(channel.id)
                    try:
                        await channel.edit(name=name)
                    except disnake.HTTPException:
                        lines.append(f"• Не удалось переименовать {channel.mention}.")
                        payload[field] = str(channel.id)
                        continue

                payload[field] = str(channel.id)
                lines.append(f"• {channel.mention} (`{name}`)")
            else:
                try:
                    new_channel = await guild.create_voice_channel(
                        name=name,
                        category=target_category,
                        overwrites=overwrites,
                        reason="Канал статистики сервера Mirei",
                    )
                    self.ignored_audit_ids.add(new_channel.id)
                    payload[field] = str(new_channel.id)
                    lines.append(f"• {new_channel.mention} (`{name}`)")
                    await asyncio.sleep(0.4)
                except disnake.HTTPException:
                    payload[field] = None
                    lines.append(f"• Не удалось создать счётчик `{name}`.")

        await asyncio.sleep(1.5)
        self.ignored_audit_ids.clear()

        if not await api.update_stats_config(guild_id, payload):
            await inter.edit_original_response(
                content="❌ Discord мог применить изменения. API не подтвердило сохранение настроек."
            )
            return

        summary = "\n".join(lines) or "Каналы счётчиков отсутствуют."
        embed = disnake.Embed(
            title="📊 Статистика сервера",
            description=(
                f"**Категория:** `{target_category.name}`\n"
                "**Автообновление:** каждые 10 минут\n\n"
                f"{summary}"
            ),
            color=TACTICAL_GREEN,
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)

    @stats_group.sub_command(
        name="обновить", description="Обновить счётчики прямо сейчас"
    )
    @commands.has_guild_permissions(administrator=True)
    @commands.cooldown(1, 300, commands.BucketType.guild)
    async def stats_refresh(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        config = await api.get_guild_config(str(inter.guild_id)) or {}
        stats = config.get("stats") or {}
        if not stats.get("enabled"):
            await inter.edit_original_response(
                content="⚠️ Статистика отключена или ещё не настроена. Используй `/статистика настроить`."
            )
            return

        updated = await self._sync_guild_stats(inter.guild, stats)
        await inter.edit_original_response(content=f"Обновлено счётчиков: **{updated}**.")

    @stats_group.sub_command(
        name="переключить", description="Включить или приостановить автообновление"
    )
    @commands.has_guild_permissions(administrator=True)
    async def stats_toggle(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer(ephemeral=True)
        guild_id = str(inter.guild_id)
        config = await api.get_guild_config_for_update(guild_id)
        if config is None:
            await inter.edit_original_response(content="API не вернуло настройки статистики.")
            return

        stats = dict(config.get("stats") or {})
        if not any(stats.get(field) for _, field in STAT_FIELD_MAP):
            await inter.edit_original_response(
                content="⚠️ Сначала создай счётчики командой `/статистика настроить`."
            )
            return

        stats["enabled"] = not stats.get("enabled", False)
        if not await api.update_stats_config(guild_id, stats):
            await inter.edit_original_response(
                content="❌ API не подтвердило сохранение."
            )
            return

        message = (
            "🟢 Автообновление статистики включено."
            if stats["enabled"]
            else "🟡 Автообновление статистики приостановлено."
        )
        await inter.edit_original_response(content=message)

    @stats_group.sub_command(
        name="отключить", description="Отключить статистику и удалить счётчики"
    )
    @commands.has_guild_permissions(administrator=True)
    async def stats_remove(
        self,
        inter: disnake.ApplicationCommandInteraction,
        delete_channels: bool = commands.Param(
            name="удалить_каналы",
            default=True,
            description="Удалить голосовые каналы счётчиков",
        ),
    ):
        await inter.response.defer(ephemeral=True)
        guild = inter.guild
        guild_id = str(guild.id)
        config = await api.get_guild_config_for_update(guild_id)
        if config is None:
            await inter.edit_original_response(content="API не вернуло настройки статистики.")
            return

        disabled = {**(config.get("stats") or {}), "enabled": False}
        if not await api.update_stats_config(guild_id, disabled):
            await inter.edit_original_response(
                content="API не подтвердило отключение статистики."
            )
            return

        deleted = failed = 0
        if delete_channels:
            for _, field in STAT_FIELD_MAP:
                channel_id = str(disabled.get(field) or "")
                channel = guild.get_channel(int(channel_id)) if channel_id.isdecimal() else None

                if isinstance(channel, disnake.VoiceChannel):
                    self.ignored_audit_ids.add(channel.id)
                    try:
                        await channel.delete(reason=f"Удаление статистики ({inter.author})")
                    except disnake.NotFound:
                        pass
                    except disnake.HTTPException:
                        failed += 1
                        continue
                    else:
                        deleted += 1
                    finally:
                        self.ignored_audit_ids.discard(channel.id)

                disabled[field] = None

            if not await api.update_stats_config(guild_id, disabled):
                await inter.edit_original_response(
                    content=(
                        f"Статистика отключена. Удалено каналов: {deleted}. "
                        "API не подтвердило сохранение списка каналов."
                    )
                )
                return

        await inter.edit_original_response(
            content=f"Статистика отключена. Удалено каналов: {deleted}. Ошибок удаления: {failed}."
        )

    @stats_group.sub_command(name="сервер", description="Показать статистику сервера")
    async def server_stats(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.defer()
        guild = inter.guild
        metrics = self._compute_metrics(guild, include_statuses=True)

        embed = disnake.Embed(
            title=f"📊 Статистика сервера: {guild.name}",
            color=BRAND_COLOR,
            timestamp=disnake.utils.utcnow(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name="👥 Участники",
            value=(
                f"Всего: **{metrics['all_members']}**\n"
                f"Людей: **{metrics['members']}** | Ботов: **{metrics['bots']}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="📡 Онлайн-активность",
            value=(
                f"🟢 В сети: **{metrics['online']}** | 🌙 Отошли: **{metrics['idle']}**\n"
                f"⛔ Не беспокоить: **{metrics['dnd']}** | ⚫ Офлайн: **{metrics['offline']}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="🔊 Голосовые каналы",
            value=f"Сейчас общаются: **{metrics['voice']}** чел.",
            inline=False,
        )
        embed.add_field(
            name="💬 Структура",
            value=(
                f"Каналов: **{metrics['channels']}** "
                f"(текстовых: {len(guild.text_channels)}, голосовых: {len(guild.voice_channels)})\n"
                f"Ролей: **{metrics['roles']}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="🚀 Бусты",
            value=(
                f"Уровень: **{guild.premium_tier}**\n"
                f"Бустов: **{guild.premium_subscription_count or 0}**"
            ),
            inline=True,
        )
        embed.set_footer(text=UNIFIED_FOOTER)
        await inter.edit_original_response(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(Stats(bot))