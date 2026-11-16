import re
import asyncio
import disnake
from disnake.ext import commands
from typing import Dict, Set, Optional
from api import api
from config import BRAND_COLOR, UNIFIED_FOOTER


def format_voice_room_name(custom_text: str, template: Optional[str], generator_name: str = "") -> str:
    """Формирует имя комнаты по шаблону из БД или автоматически под стиль канала-генератора."""
    if template and template.strip():
        tpl = template.strip()
        if "{user}" in tpl:
            return tpl.replace("{user}", custom_text)[:40]
        return f"{tpl} {custom_text}".strip()[:40]

    if generator_name.startswith(("╔", "╠", "╚")) and "〘" in generator_name:
        return f"╠ 〘🔊〙 {custom_text}"[:40]

    return f"🔊 Комната {custom_text}"[:40]


class RenameVoiceModal(disnake.ui.Modal):
    def __init__(self, channel: disnake.VoiceChannel, template: Optional[str], generator_name: str):
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
        super().__init__(title="✏️ Переименовать голосовой канал", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        raw_name = inter.text_values["new_voice_name"].strip()
        if raw_name.startswith(("╠", "╚", "╔")):
            new_name = raw_name[:40]
        else:
            new_name = format_voice_room_name(raw_name, self.template, self.generator_name)
        try:
            await self.channel.edit(name=new_name)
            await inter.response.send_message(f"✅ Канал переименован в **{new_name}**!", ephemeral=True)
        except disnake.HTTPException:
            await inter.response.send_message("⚠️ Discord разрешает менять название канала не чаще 2 раз за 10 минут.", ephemeral=True)


class VoiceControlView(disnake.ui.View):
    """Персистентная панель управления приватной комнатой (работает даже после перезапуска бота)."""
    def __init__(self, is_locked: bool = False):
        super().__init__(timeout=None)
        self.add_item(disnake.ui.Button(
            label="Закрыть / Открыть",
            style=disnake.ButtonStyle.danger if is_locked else disnake.ButtonStyle.secondary,
            emoji="🔓" if is_locked else "🔒",
            custom_id="voice_ctrl_lock",
            row=0,
        ))
        self.add_item(disnake.ui.Button(
            label="Переименовать",
            style=disnake.ButtonStyle.primary,
            emoji="✏️",
            custom_id="voice_ctrl_rename",
            row=0,
        ))
        self.add_item(disnake.ui.Button(
            label="Выгнать участника",
            style=disnake.ButtonStyle.danger,
            emoji="👢",
            custom_id="voice_ctrl_kick",
            row=0,
        ))
        self.add_item(disnake.ui.Select(
            placeholder="👥 Установить лимит участников...",
            custom_id="voice_ctrl_limit",
            row=1,
            options=[
                disnake.SelectOption(label="Без лимита ( ∞ )", value="0", emoji="♾️"),
                disnake.SelectOption(label="2 участника", value="2", emoji="👥"),
                disnake.SelectOption(label="3 участника", value="3", emoji="☘️"),
                disnake.SelectOption(label="5 участников", value="5", emoji="🖐️"),
                disnake.SelectOption(label="10 участников", value="10", emoji="🔟"),
            ],
        ))


class VoiceHub(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.temp_channels: Dict[int, int] = {}
        self.deleted_temp_ids: Set[int] = set()
        self._startup_synced = False

    def _find_room_owner(
        self,
        channel: disnake.VoiceChannel,
        message: Optional[disnake.Message] = None
    ) -> Optional[int]:
        if channel.id in self.temp_channels:
            return self.temp_channels[channel.id]

        for target, overwrite in channel.overwrites.items():
            if isinstance(target, disnake.Member) and overwrite.manage_channels and overwrite.priority_speaker:
                return target.id

        if message and message.embeds:
            desc = message.embeds[0].description or ""
            match = re.search(r"\*\*Владелец:\*\*\s*<@!?(\d+)>", desc)
            if match:
                return int(match.group(1))

        return None

    async def _is_mirei_temp_room(self, vc: disnake.VoiceChannel, generator_id: int) -> Optional[int]:
        if vc.id == generator_id or vc == vc.guild.afk_channel:
            return None

        owner_id = None
        for target, overwrite in vc.overwrites.items():
            if isinstance(target, disnake.Member) and overwrite.manage_channels and overwrite.priority_speaker:
                owner_id = target.id
                break

        if owner_id is None:
            return None

        try:
            async for msg in vc.history(limit=10):
                if (
                    self.bot.user
                    and msg.author.id == self.bot.user.id
                    and msg.embeds
                    and "Управление комнатой" in (msg.embeds[0].title or "")
                ):
                    return owner_id
        except disnake.HTTPException:
            pass

        return None

    @commands.Cog.listener()
    async def on_ready(self):
        if self._startup_synced:
            return
        self._startup_synced = True

        for guild in self.bot.guilds:
            cfg = await api.get_guild_config(str(guild.id)) or {}
            gen_id_str = (cfg.get("voice") or {}).get("generatorChannelId")
            if not gen_id_str or not str(gen_id_str).isdigit():
                continue

            gen_id = int(gen_id_str)
            gen_ch = guild.get_channel(gen_id)
            if not isinstance(gen_ch, disnake.VoiceChannel):
                continue

            channels_to_scan = gen_ch.category.voice_channels if gen_ch.category else guild.voice_channels
            for vc in list(channels_to_scan):
                owner_id = await self._is_mirei_temp_room(vc, gen_id)
                if owner_id is None:
                    continue

                humans = [m for m in vc.members if not m.bot]
                if len(humans) == 0:
                    self.deleted_temp_ids.add(vc.id)
                    try:
                        await vc.delete(reason="Очистка пустой приватной комнаты после перезапуска бота")
                        await asyncio.sleep(0.5)
                    except disnake.HTTPException:
                        pass
                else:
                    self.temp_channels[vc.id] = owner_id

    def _has_room_access(self, inter: disnake.MessageInteraction, channel: disnake.VoiceChannel) -> bool:
        if inter.author.guild_permissions.administrator:
            return True
        owner_id = self._find_room_owner(channel, inter.message)
        return owner_id is not None and inter.author.id == owner_id

    @commands.Cog.listener("on_button_click")
    async def on_voice_button(self, inter: disnake.MessageInteraction):
        cid = inter.component.custom_id
        if cid not in ("voice_ctrl_lock", "voice_ctrl_rename", "voice_ctrl_kick"):
            return

        channel = inter.channel
        if not isinstance(channel, disnake.VoiceChannel):
            await inter.response.send_message("⚠️ Эта панель работает только в голосовом канале.", ephemeral=True)
            return

        if not self._has_room_access(inter, channel):
            await inter.response.send_message("❌ Только владелец комнаты может управлять этой панелью.", ephemeral=True)
            return

        if cid == "voice_ctrl_lock":
            default_ow = channel.overwrites_for(inter.guild.default_role)
            new_locked = not (default_ow.connect is False)

            await channel.set_permissions(inter.guild.default_role, connect=not new_locked)
            await channel.set_permissions(inter.author, connect=True, manage_channels=True, move_members=True, priority_speaker=True)

            status_text = (
                "🔒 **Комната закрыта!** Вход для остальных ограничен."
                if new_locked
                else "🔓 **Комната открыта** для всех участников."
            )
            await inter.response.edit_message(view=VoiceControlView(is_locked=new_locked))
            await inter.followup.send(status_text, ephemeral=True)

        elif cid == "voice_ctrl_rename":
            cfg = await api.get_guild_config(str(inter.guild_id)) or {}
            voice_cfg = cfg.get("voice") or {}
            gen_id = voice_cfg.get("generatorChannelId")
            gen_ch = inter.guild.get_channel(int(gen_id)) if (gen_id and str(gen_id).isdigit()) else None
            gen_name = gen_ch.name if gen_ch else ""
            await inter.response.send_modal(RenameVoiceModal(channel, voice_cfg.get("roomTemplate"), gen_name))

        elif cid == "voice_ctrl_kick":
            targets = [m for m in channel.members if m.id != inter.author.id and not m.bot]
            if not targets:
                await inter.response.send_message("ℹ️ В голосовом канале сейчас нет других участников.", ephemeral=True)
                return

            options = [disnake.SelectOption(label=m.display_name[:80], value=str(m.id), emoji="👤") for m in targets[:25]]
            select = disnake.ui.Select(placeholder="Выберите, кого отключить от канала...", options=options)

            async def select_callback(select_inter: disnake.MessageInteraction):
                target_id = int(select.values[0])
                target_member = inter.guild.get_member(target_id)
                if target_member and target_member.voice and target_member.voice.channel == channel:
                    await target_member.move_to(None, reason=f"Отключен владельцем комнаты {inter.author}")
                    await channel.set_permissions(target_member, connect=False)
                    await select_inter.response.edit_message(content=f"👢 Участник {target_member.mention} отключен от комнаты.", view=None)
                else:
                    await select_inter.response.edit_message(content="⚠️ Участник уже покинул канал.", view=None)

            select.callback = select_callback
            temp_view = disnake.ui.View(timeout=30)
            temp_view.add_item(select)
            await inter.response.send_message("Выберите участника для отключения:", view=temp_view, ephemeral=True)

    @commands.Cog.listener("on_dropdown")
    async def on_voice_limit_select(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id != "voice_ctrl_limit":
            return

        channel = inter.channel
        if not isinstance(channel, disnake.VoiceChannel):
            return

        if not self._has_room_access(inter, channel):
            await inter.response.send_message("❌ Только владелец комнаты может менять лимит.", ephemeral=True)
            return

        limit = int(inter.values[0])
        await channel.edit(user_limit=limit)
        limit_str = "Без ограничений" if limit == 0 else f"{limit} чел."
        await inter.response.send_message(f"👥 Лимит комнаты установлен: **{limit_str}**", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: disnake.Member, before: disnake.VoiceState, after: disnake.VoiceState):
        if member.bot:
            return

        guild = member.guild
        cfg = await api.get_guild_config(str(guild.id)) or {}
        voice_cfg = cfg.get("voice") or {}
        gen_id_str = voice_cfg.get("generatorChannelId")

        if after.channel and gen_id_str and str(after.channel.id) == str(gen_id_str):
            category = after.channel.category
            overwrites = {
                guild.default_role: disnake.PermissionOverwrite(connect=True, view_channel=True),
                member: disnake.PermissionOverwrite(connect=True, manage_channels=True, move_members=True, priority_speaker=True),
            }
            if guild.me:
                overwrites[guild.me] = disnake.PermissionOverwrite(connect=True, manage_channels=True, move_members=True, view_channel=True)

            room_name = format_voice_room_name(
                custom_text=member.display_name,
                template=voice_cfg.get("roomTemplate"),
                generator_name=after.channel.name
            )

            try:
                new_channel = await guild.create_voice_channel(
                    name=room_name,
                    category=category,
                    position=after.channel.position + 1,
                    overwrites=overwrites,
                    reason=f"Приватная комната для {member}"
                )
                self.temp_channels[new_channel.id] = member.id
                await member.move_to(new_channel)

                embed = disnake.Embed(
                    title=f"🎛️ Управление комнатой: {member.display_name}",
                    description=(
                        f"**Владелец:** {member.mention}\n\n"
                        "Используйте панель ниже для закрытия комнаты, установки лимита участников или переименования.\n"
                        "*Канал будет автоматически удален после выхода всех участников.*"
                    ),
                    color=BRAND_COLOR
                )
                embed.set_footer(text=UNIFIED_FOOTER)
                await new_channel.send(embed=embed, view=VoiceControlView(is_locked=False))
            except disnake.HTTPException:
                pass

        if before.channel and before.channel.id in self.temp_channels:
            if len([m for m in before.channel.members if not m.bot]) == 0:
                self.temp_channels.pop(before.channel.id, None)
                self.deleted_temp_ids.add(before.channel.id)
                try:
                    await before.channel.delete(reason="Приватная комната опустела")
                except disnake.HTTPException:
                    pass


def setup(bot: commands.Bot):
    bot.add_cog(VoiceHub(bot))