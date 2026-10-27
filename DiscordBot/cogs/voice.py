import disnake
from disnake.ext import commands
from typing import Dict, Set
from api import api
from config import P3_BLUE, UNIFIED_FOOTER

class RenameVoiceModal(disnake.ui.Modal):
    def __init__(self, channel: disnake.VoiceChannel):
        self.channel = channel
        components = [
            disnake.ui.TextInput(
                label="Новое название канала",
                placeholder="Например: 🔊 Комната для игр",
                custom_id="new_voice_name",
                style=disnake.TextInputStyle.short,
                min_length=2,
                max_length=40,
            )
        ]
        super().__init__(title="✏️ Переименовать голосовой канал", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        new_name = inter.text_values["new_voice_name"].strip()
        try:
            await self.channel.edit(name=new_name)
            await inter.response.send_message(f"✅ Канал переименован в **{new_name}**!", ephemeral=True)
        except disnake.HTTPException:
            await inter.response.send_message("⚠️ Discord разрешает менять название канала не чаще 2 раз за 10 минут.", ephemeral=True)


class VoiceControlView(disnake.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.is_locked = False

    def _check_owner(self, inter: disnake.MessageInteraction) -> bool:
        return inter.author.id == self.owner_id or inter.author.guild_permissions.administrator

    @disnake.ui.button(label="Закрыть / Открыть", style=disnake.ButtonStyle.secondary, emoji="🔒")
    async def toggle_lock(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if not self._check_owner(inter):
            await inter.response.send_message("❌ Только владелец комнаты может управлять этой панелью.", ephemeral=True)
            return

        channel = inter.channel
        if not isinstance(channel, disnake.VoiceChannel):
            return

        self.is_locked = not self.is_locked
        await channel.set_permissions(inter.guild.default_role, connect=not self.is_locked)
        await channel.set_permissions(inter.author, connect=True, manage_channels=True, move_members=True)

        status_text = "🔒 **Комната закрыта!** Вход для остальных ограничен." if self.is_locked else "🔓 **Комната открыта** для всех участников."
        button.style = disnake.ButtonStyle.danger if self.is_locked else disnake.ButtonStyle.secondary
        button.emoji = "🔓" if self.is_locked else "🔒"

        await inter.response.edit_message(view=self)
        await inter.followup.send(status_text, ephemeral=True)

    @disnake.ui.button(label="Переименовать", style=disnake.ButtonStyle.primary, emoji="✏️")
    async def rename_room(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if not self._check_owner(inter):
            await inter.response.send_message("❌ Только владелец комнаты может управлять этой панелью.", ephemeral=True)
            return
        if isinstance(inter.channel, disnake.VoiceChannel):
            await inter.response.send_modal(RenameVoiceModal(inter.channel))

    @disnake.ui.button(label="Выгнать участника", style=disnake.ButtonStyle.danger, emoji="👢")
    async def kick_member(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if not self._check_owner(inter):
            await inter.response.send_message("❌ Только владелец комнаты может управлять этой панелью.", ephemeral=True)
            return

        channel = inter.channel
        if not isinstance(channel, disnake.VoiceChannel):
            return

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

    @disnake.ui.select(
        placeholder="👥 Установить лимит участников...",
        options=[
            disnake.SelectOption(label="Без лимита ( ∞ )", value="0", emoji="♾️"),
            disnake.SelectOption(label="2 участника", value="2", emoji="👥"),
            disnake.SelectOption(label="3 участника", value="3", emoji="☘️"),
            disnake.SelectOption(label="5 участников", value="5", emoji="🖐️"),
            disnake.SelectOption(label="10 участников", value="10", emoji="🔟"),
        ]
    )
    async def limit_select(self, select: disnake.ui.Select, inter: disnake.MessageInteraction):
        if not self._check_owner(inter):
            await inter.response.send_message("❌ Только владелец комнаты может менять лимит.", ephemeral=True)
            return

        limit = int(select.values[0])
        if isinstance(inter.channel, disnake.VoiceChannel):
            await inter.channel.edit(user_limit=limit)
            limit_str = "Без ограничений" if limit == 0 else f"{limit} чел."
            await inter.response.send_message(f"👥 Лимит комнаты установлен: **{limit_str}**", ephemeral=True)


class VoiceHub(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.temp_channels: Dict[int, int] = {}
        self.deleted_temp_ids: Set[int] = set()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: disnake.Member, before: disnake.VoiceState, after: disnake.VoiceState):
        if member.bot:
            return

        guild = member.guild
        cfg = await api.get_guild_config(str(guild.id))
        gen_id_str = cfg.get("voiceGeneratorChannelId") if cfg else None

        if after.channel and gen_id_str and str(after.channel.id) == str(gen_id_str):
            category = after.channel.category
            overwrites = {
                guild.default_role: disnake.PermissionOverwrite(connect=True, view_channel=True),
                member: disnake.PermissionOverwrite(connect=True, manage_channels=True, move_members=True, priority_speaker=True),
            }
            if guild.me:
                overwrites[guild.me] = disnake.PermissionOverwrite(connect=True, manage_channels=True, move_members=True, view_channel=True)

            try:
                new_channel = await guild.create_voice_channel(
                    name=f"🔊 Комната {member.display_name}"[:40],
                    category=category,
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
                    color=P3_BLUE
                )
                embed.set_footer(text=UNIFIED_FOOTER)
                await new_channel.send(embed=embed, view=VoiceControlView(owner_id=member.id))
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