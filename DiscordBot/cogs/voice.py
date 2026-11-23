import asyncio
import re
from typing import Dict, Optional, Set

import disnake
from disnake.ext import commands

from api import api
from config import BRAND_COLOR, UNIFIED_FOOTER, log


def format_voice_room_name(
    custom_text: str,
    template: Optional[str],
    generator_name: str = "",
) -> str:
    if template and template.strip():
        template = template.strip()
        if "{user}" in template:
            return template.replace("{user}", custom_text)[:40]
        return f"{template} {custom_text}".strip()[:40]

    if generator_name.startswith(("╔", "╠", "╚")) and "〘" in generator_name:
        return f"╠ 〘🔊〙 {custom_text}"[:40]

    return f"🔊 Комната {custom_text}"[:40]


class RenameVoiceModal(disnake.ui.Modal):
    def __init__(
        self,
        channel: disnake.VoiceChannel,
        template: Optional[str],
        generator_name: str,
    ):
        self.channel = channel
        self.template = template
        self.generator_name = generator_name

        components = [
            disnake.ui.TextInput(
                label="Новое название канала",
                placeholder="Например: Играем в Valorant",
                custom_id="new_voice_name",
                style=disnake.TextInputStyle.short,
                min_length=2,
                max_length=30,
            )
        ]
        super().__init__(
            title="✏️ Переименовать голосовой канал",
            components=components,
        )

    async def callback(self, inter: disnake.ModalInteraction):
        raw_name = inter.text_values["new_voice_name"].strip()
        if raw_name.startswith(("╠", "╚", "╔")):
            new_name = raw_name[:40]
        else:
            new_name = format_voice_room_name(
                raw_name, self.template, self.generator_name
            )

        try:
            await self.channel.edit(name=new_name)
            await inter.response.send_message(
                f"✅ Канал переименован в **{new_name}**.", ephemeral=True
            )
        except disnake.HTTPException:
            await inter.response.send_message(
                "⚠️ Discord не подтвердил переименование. Проверь права бота и повтори позже.",
                ephemeral=True,
            )


class VoiceControlView(disnake.ui.View):
    def __init__(self, is_locked: bool = False):
        super().__init__(timeout=None)
        self.add_item(
            disnake.ui.Button(
                label="Закрыть / Открыть",
                style=disnake.ButtonStyle.danger if is_locked else disnake.ButtonStyle.secondary,
                emoji="🔓" if is_locked else "🔒",
                custom_id="voice_ctrl_lock",
                row=0,
            )
        )
        self.add_item(
            disnake.ui.Button(
                label="Переименовать",
                style=disnake.ButtonStyle.primary,
                emoji="✏️",
                custom_id="voice_ctrl_rename",
                row=0,
            )
        )
        self.add_item(
            disnake.ui.Button(
                label="Выгнать участника",
                style=disnake.ButtonStyle.danger,
                emoji="👢",
                custom_id="voice_ctrl_kick",
                row=0,
            )
        )
        self.add_item(
            disnake.ui.Select(
                placeholder="👥 Установить лимит участников",
                custom_id="voice_ctrl_limit",
                row=1,
                options=[
                    disnake.SelectOption(label="Без лимита", value="0", emoji="♾️"),
                    disnake.SelectOption(label="2 участника", value="2", emoji="👥"),
                    disnake.SelectOption(label="3 участника", value="3", emoji="☘️"),
                    disnake.SelectOption(label="5 участников", value="5", emoji="🖐️"),
                    disnake.SelectOption(label="10 участников", value="10", emoji="🔟"),
                ],
            )
        )


class VoiceHub(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.temp_channels: Dict[int, int] = {}
        self.deleted_temp_ids: Set[int] = set()
        self._startup_synced = False

    def _find_room_owner(
        self,
        channel: disnake.VoiceChannel,
        message: Optional[disnake.Message] = None,
    ) -> Optional[int]:
        if channel.id in self.temp_channels:
            return self.temp_channels[channel.id]

        for target, overwrite in channel.overwrites.items():
            if (
                isinstance(target, disnake.Member)
                and overwrite.manage_channels
                and overwrite.priority_speaker
            ):
                return target.id

        if message and message.embeds:
            description = message.embeds[0].description or ""
            match = re.search(r"\*\*Владелец:\*\*\s*<@!?(\d+)>", description)
            if match:
                return int(match.group(1))

        return None

    async def _is_mirei_temp_room(
        self, channel: disnake.VoiceChannel, generator_id: int
    ) -> Optional[int]:
        if channel.id == generator_id or channel == channel.guild.afk_channel:
            return None

        owner_id = None
        for target, overwrite in channel.overwrites.items():
            if (
                isinstance(target, disnake.Member)
                and overwrite.manage_channels
                and overwrite.priority_speaker
            ):
                owner_id = target.id
                break

        if owner_id is None:
            return None

        try:
            async for message in channel.history(limit=10):
                if (
                    self.bot.user
                    and message.author.id == self.bot.user.id
                    and message.embeds
                    and "Управление комнатой" in (message.embeds[0].title or "")
                ):
                    return owner_id
        except disnake.HTTPException:
            pass

        return None

    async def _sync_guild_voice_rooms(
        self, guild: disnake.Guild, semaphore: asyncio.Semaphore
    ):
        async with semaphore:
            config = await api.get_guild_config(str(guild.id)) or {}
            generator_id = (config.get("voice") or {}).get("generatorChannelId")
            if not generator_id or not str(generator_id).isdigit():
                return

            generator = guild.get_channel(int(generator_id))
            if not isinstance(generator, disnake.VoiceChannel):
                return

            channels = (
                generator.category.voice_channels
                if generator.category
                else guild.voice_channels
            )
            for channel in list(channels):
                owner_id = await self._is_mirei_temp_room(channel, generator.id)
                if owner_id is None:
                    continue

                if any(not member.bot for member in channel.members):
                    self.temp_channels[channel.id] = owner_id
                    continue

                self.deleted_temp_ids.add(channel.id)
                try:
                    await channel.delete(reason="Очистка пустой комнаты после перезапуска")
                    await asyncio.sleep(0.5)
                except disnake.HTTPException:
                    self.deleted_temp_ids.discard(channel.id)
                    log.exception("Не удалось очистить комнату %s после перезапуска", channel.id)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._startup_synced:
            return
        self._startup_synced = True

        semaphore = asyncio.Semaphore(10)
        jobs = [
            self._sync_guild_voice_rooms(guild, semaphore)
            for guild in list(self.bot.guilds)
        ]
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)

    def _has_room_access(
        self, inter: disnake.MessageInteraction, channel: disnake.VoiceChannel
    ) -> bool:
        if not isinstance(inter.author, disnake.Member):
            return False
        if inter.author.guild_permissions.administrator:
            return True

        owner_id = self._find_room_owner(channel, inter.message)
        return owner_id is not None and inter.author.id == owner_id

    @commands.Cog.listener("on_button_click")
    async def on_voice_button(self, inter: disnake.MessageInteraction):
        custom_id = inter.component.custom_id
        if custom_id not in ("voice_ctrl_lock", "voice_ctrl_rename", "voice_ctrl_kick"):
            return

        channel = inter.channel
        if not isinstance(channel, disnake.VoiceChannel):
            await inter.response.send_message(
                "⚠️ Эта панель работает только в голосовом канале.", ephemeral=True
            )
            return

        if not self._has_room_access(inter, channel):
            await inter.response.send_message(
                "❌ Только владелец комнаты или администратор может управлять панелью.",
                ephemeral=True,
            )
            return

        if custom_id == "voice_ctrl_lock":
            await inter.response.defer()
            default_role = channel.guild.default_role
            overwrite = channel.overwrites_for(default_role)
            new_locked = overwrite.connect is not False
            overwrite.connect = False if new_locked else None

            await channel.set_permissions(
                default_role,
                overwrite=None if overwrite.is_empty() else overwrite,
            )
            status = (
                "🔒 Вход для роли `@everyone` ограничен."
                if new_locked
                else "🔓 Ограничение входа для роли `@everyone` снято."
            )
            await inter.edit_original_response(view=VoiceControlView(is_locked=new_locked))
            await inter.followup.send(status, ephemeral=True)

        elif custom_id == "voice_ctrl_rename":
            config = await api.get_guild_config(str(inter.guild_id)) or {}
            voice = config.get("voice") or {}
            generator_id = voice.get("generatorChannelId")
            generator = (
                channel.guild.get_channel(int(generator_id))
                if generator_id and str(generator_id).isdigit()
                else None
            )
            await inter.response.send_modal(
                RenameVoiceModal(
                    channel,
                    voice.get("roomTemplate"),
                    generator.name if generator else "",
                )
            )

        elif custom_id == "voice_ctrl_kick":
            targets = [
                member
                for member in channel.members
                if member.id != inter.author.id and not member.bot
            ]
            if not targets:
                await inter.response.send_message(
                    "ℹ️ В голосовом канале сейчас нет других участников.",
                    ephemeral=True,
                )
                return

            options = [
                disnake.SelectOption(
                    label=member.display_name[:80], value=str(member.id), emoji="👤"
                )
                for member in targets[:25]
            ]
            select = disnake.ui.Select(
                placeholder="Выбери, кого отключить от канала", options=options
            )

            async def select_callback(select_inter: disnake.MessageInteraction):
                target = channel.guild.get_member(int(select.values[0]))
                if not target or not target.voice or target.voice.channel != channel:
                    await select_inter.response.edit_message(
                        content="⚠️ Участник уже покинул канал.", view=None
                    )
                    return

                await target.move_to(
                    None, reason=f"Отключён из комнаты пользователем {inter.author}"
                )
                overwrite = channel.overwrites_for(target)
                overwrite.connect = False
                await channel.set_permissions(target, overwrite=overwrite)
                await select_inter.response.edit_message(
                    content=f"👢 {target.mention} отключён от комнаты.", view=None
                )

            select.callback = select_callback
            view = disnake.ui.View(timeout=30)
            view.add_item(select)
            await inter.response.send_message(
                "Выбери участника для отключения.", view=view, ephemeral=True
            )

    @commands.Cog.listener("on_dropdown")
    async def on_voice_limit_select(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id != "voice_ctrl_limit":
            return

        channel = inter.channel
        if not isinstance(channel, disnake.VoiceChannel):
            return

        if not self._has_room_access(inter, channel):
            await inter.response.send_message(
                "❌ Только владелец комнаты или администратор может менять лимит.",
                ephemeral=True,
            )
            return

        limit = int(inter.values[0])
        await channel.edit(user_limit=limit)
        label = "без ограничений" if limit == 0 else f"{limit} чел."
        await inter.response.send_message(
            f"👥 Лимит комнаты: **{label}**.", ephemeral=True
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: disnake.Member, before: disnake.VoiceState, after: disnake.VoiceState
    ):
        if member.bot or before.channel == after.channel:
            return

        guild = member.guild
        config = await api.get_guild_config(str(guild.id)) or {}
        voice = config.get("voice") or {}
        generator_id = voice.get("generatorChannelId")

        if after.channel and str(after.channel.id) == str(generator_id):
            generator = after.channel
            overwrites = generator.overwrites
            for target in (member, guild.me):
                if target is None:
                    continue

                overwrite = overwrites.get(target, disnake.PermissionOverwrite())
                overwrite.update(
                    view_channel=True,
                    connect=True,
                    manage_channels=True,
                    move_members=True,
                )
                if target == member:
                    overwrite.priority_speaker = True
                overwrites[target] = overwrite

            name = format_voice_room_name(
                member.display_name, voice.get("roomTemplate"), generator.name
            )

            try:
                room = await guild.create_voice_channel(
                    name=name,
                    category=generator.category,
                    position=generator.position + 1,
                    overwrites=overwrites,
                    reason=f"Временная комната для {member}",
                )
                self.temp_channels[room.id] = member.id
                try:
                    await member.move_to(room)
                except disnake.HTTPException:
                    try:
                        await room.delete(reason="Не удалось переместить владельца")
                    except disnake.HTTPException:
                        log.exception("Не удалось удалить пустую комнату %s", room.id)
                    else:
                        self.temp_channels.pop(room.id, None)
                else:
                    await self._send_room_panel(room, member)
            except disnake.HTTPException:
                log.exception("Не удалось создать комнату на сервере %s", guild.id)

        old_room = before.channel
        if old_room and old_room.id in self.temp_channels:
            if not any(not occupant.bot for occupant in old_room.members):
                self.deleted_temp_ids.add(old_room.id)
                try:
                    await old_room.delete(reason="Временная комната опустела")
                except disnake.HTTPException:
                    self.deleted_temp_ids.discard(old_room.id)
                    log.exception("Не удалось удалить комнату %s", old_room.id)
                else:
                    self.temp_channels.pop(old_room.id, None)

    async def _send_room_panel(
        self, channel: disnake.VoiceChannel, member: disnake.Member
    ):
        embed = disnake.Embed(
            title=f"🎛️ Управление комнатой: {member.display_name}",
            description=(
                f"**Владелец:** {member.mention}\n\n"
                "Используй панель ниже, чтобы закрыть комнату, "
                "установить лимит участников или переименовать канал.\n"
                "*Комната удаляется, когда в ней не остаётся участников.*"
            ),
            color=BRAND_COLOR,
        )
        embed.set_footer(text=UNIFIED_FOOTER)

        try:
            locked = channel.overwrites_for(channel.guild.default_role).connect is False
            await channel.send(embed=embed, view=VoiceControlView(is_locked=locked))
        except disnake.HTTPException:
            log.exception("Не удалось отправить панель комнаты %s", channel.id)


def setup(bot: commands.Bot):
    bot.add_cog(VoiceHub(bot))