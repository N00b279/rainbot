import copy
import json
import typing

import discord
from discord.ext import commands
from discord.ext.commands import Cog

from ext.errors import BotMissingPermissionsInChannel
from ext.utils import get_command_level, lower
from ext.command import command, group, RainGroup


class Setup(commands.Cog):
    """Setting up rainbot: https://github.com/fourjr/rainbot/wiki/Setting-up-rainbot"""

    def __init__(self, bot):
        self.bot = bot
        self.order = 2

    @Cog.listener()
    async def on_guild_join(self, guild):
        await self.bot.db.create_new_config(guild.id)

    @command(6, aliases=['view_config', 'view-config'])
    async def viewconfig(self, ctx):
        """View the current guild configuration"""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        del guild_config['_id']
        try:
            await ctx.send(f'```json\n{json.dumps(guild_config, indent=2)}\n```')
        except discord.HTTPException:
            async with self.bot.session.post('https://hasteb.in/documents', data=json.dumps(guild_config, indent=4)) as resp:
                data = await resp.json()
                await ctx.send(f"Your server's current configuration: https://hasteb.in/{data['key']}")

    @command(10, aliases=['import_config', 'import-config'])
    async def importconfig(self, ctx, *, url):
        """Imports a new guild configuration.

        Generate one from https://fourjr.github.io/rainbot/"""
        if url.startswith('http'):
            if url.startswith('https://hasteb.in') and 'raw' not in url:
                url = 'https://hasteb.in/raw/' + url[18:]

            async with self.bot.session.get(url) as resp:
                data = await resp.json(content_type=None)
        else:
            data = url
        data['guild_id'] = str(ctx.guild.id)
        await self.bot.db.update_guild_config(ctx.guild.id, {'$set': data})
        await ctx.send(self.bot.accept)

    @command(10, aliases=['reset_config', 'reset-config'])
    async def resetconfig(self, ctx):
        """Resets configuration to default"""
        await ctx.invoke(self.viewconfig)
        data = copy.copy(self.default)
        data['guild_id'] = str(ctx.guild.id)
        await self.bot.db.update_guild_config(ctx.guild.id, {'$set': data})
        await ctx.send('All configuration reset')

    @command(10, alises=['set_log', 'set-log'])
    async def setlog(self, ctx, log_name: lower, channel: discord.TextChannel=None):
        """Sets the log channel for various types of logging

        Valid types: all, message_delete, message_edit, member_join, member_remove, member_ban, member_unban, vc_state_change, channel_create, channel_delete, role_create, role_delete
        """
        valid_logs = self.default['logs'].keys()
        channel_id = None
        if channel:
            try:
                await channel.send('Testing the logs')
            except discord.Forbidden:
                raise BotMissingPermissionsInChannel(['send_messages'], channel)
            channel_id = str(channel.id)

        if log_name == 'all':
            for i in valid_logs:
                await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'logs.{i}': channel_id}})
        else:
            if log_name not in valid_logs:
                raise commands.BadArgument('Invalid log name, pick one from below:\n' + ', '.join(valid_logs))

            await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'logs.{log_name}': channel_id}})
        await ctx.send(self.bot.accept)

    @command(10, alises=['set_modlog', 'set-modlog'])
    async def setmodlog(self, ctx, log_name: lower, channel: discord.TextChannel=None):
        """Sets the log channel for various types of logging

        Valid types: all, member_warn, member_mute, member_unmute, member_kick, member_ban, member_unban, member_softban, message_purge, channel_lockdown, channel_slowmode
        """
        channel_id = None
        if channel:
            try:
                await channel.send('Testing the logs')
            except discord.Forbidden:
                raise BotMissingPermissionsInChannel(['send_messages'], channel)
            channel_id = str(channel.id)

        valid_logs = self.default['modlog'].keys()
        if log_name == 'all':
            for i in valid_logs:
                await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'modlog.{i}': channel_id}})
        else:
            if log_name not in valid_logs:
                raise commands.BadArgument('Invalid log name, pick one from below:\n' + ', '.join(valid_logs))

            await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'modlog.{log_name}': channel_id}})
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_perm_level', 'set-perm-level'])
    async def setpermlevel(self, ctx, perm_level: int, *, role: discord.Role):
        """Sets a role's permission level"""
        if perm_level < 0:
            raise commands.BadArgument(f'{perm_level} is below 0')

        if perm_level == 0:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$unset': {f'perm_levels.{role.id}': ''}})
        else:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'perm_levels.{role.id}': perm_level}})
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_command_level', 'set-command-level'])
    async def setcommandlevel(self, ctx, perm_level: typing.Union[int, str], *, command: lower):
        """Changes a command's required permission level

        Examples:
        - !!setcommandlevel reset ban
        - !!setcommandlevel 8 warn add
        """
        if isinstance(perm_level, int) and (perm_level < 0 or perm_level > 15):
            raise commands.BadArgument(f'{perm_level} is an invalid level, valid levels: 0-15')

        cmd = self.bot.get_command(command)
        if not cmd:
            raise commands.BadArgument(f'No command with name "{command}" found')

        if isinstance(cmd, RainGroup):
            raise commands.BadArgument('Cannot override a command group')

        name = cmd.qualified_name.replace(' ', '_')

        if perm_level == 'reset':
            perm_level = cmd.perm_level
        
        levels = {f'command_levels.{name}': perm_level}
        action = "unset" if perm_level == cmd.perm_level else "set"

        if cmd.parent:
            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            parent_level = get_command_level(cmd.parent, guild_config)
            if perm_level < parent_level:
                levels[f'command_levels.{cmd.parent.name}'] = perm_level
            elif perm_level > parent_level:
                cmd_level = get_command_level(cmd, guild_config)
                all_levels = [get_command_level(c, guild_config) for c in cmd.parent.commands]

                all_levels.remove(cmd_level)
                all_levels.append(perm_level)

                lowest = min(all_levels)
                if lowest > parent_level:
                    levels[f'command_levels.{cmd.parent.name}'] = lowest

            await self.bot.db.update_guild_config(ctx.guild.id, {f'${action}': levels})

        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_prefix', 'set-prefix'])
    async def setprefix(self, ctx, new_prefix):
        """Sets the guild prefix"""
        await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {'prefix': new_prefix}})
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_offset', 'set-offset'])
    async def setoffset(self, ctx, offset: int):
        """Sets the time offset from UTC"""
        if not -12 < offset < 14:
            raise commands.BadArgument(f'{offset} has to be between -12 and 14.')

        await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {'time_offset': offset}})
        await ctx.send(self.bot.accept)

    @command(10, aliases=['set_detection', 'set-detection'])
    async def setdetection(self, ctx, detection_type: lower, value):
        """Sets or toggle the auto moderation types

        Valid types: block_invite, mention_limit, spam_detection, repetitive_message
        """
        if detection_type == 'block_invite':
            await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {'detections.block_invite': commands.core._convert_to_bool(value)}})
            await ctx.send(self.bot.accept)
        elif detection_type in ('mention_limit', 'spam_detection', 'repetitive_message'):
            try:
                if int(value) <= 0:
                    raise ValueError
                await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'detections.{detection_type}': int(value)}})
            except ValueError as e:
                raise commands.BadArgument(f'{value} (`value`) is not a valid number above 0') from e
            await ctx.send(self.bot.accept)
        else:
            raise commands.BadArgument('Invalid log name, pick one from below:\nblock_invite, mention_limit, spam_detection, repetitive_message')

    @command(10, aliases=['set-guild-whitelist', 'set_guild_whitelist'])
    async def setguildwhitelist(self, ctx, guild_id: int=None):
        """Adds a server to the whitelist.

        Invite detection will not trigger when this guild's invite is sent.
        The current server is always whitelisted.

        Run without arguments to clear whitelist
        """
        if guild_id is None:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$unset': {'whitelisted_guilds': ''}})

        await self.bot.db.update_guild_config(ctx.guild.id, {'$push': {'whitelisted_guilds': str(guild_id)}})
        await ctx.send(self.bot.accept)

    @group(8, name='filter', invoke_without_command=True)
    async def filter_(self, ctx):
        """Controls the word filter"""
        await ctx.invoke(self.bot.get_command('help'), command_or_cog='filter')

    @filter_.command(8)
    async def add(self, ctx, *, word: lower):
        """Add blacklisted words into the word filter"""
        await self.bot.db.update_guild_config(ctx.guild.id, {'$push': {'detections.filters': word}})
        await ctx.send(self.bot.accept)

    @filter_.command(8)
    async def remove(self, ctx, *, word: lower):
        """Removes blacklisted words from the word filter"""
        await self.bot.db.update_guild_config(ctx.guild.id, {'$pull': {'detections.filters': word}})
        await ctx.send(self.bot.accept)

    @filter_.command(8, name='list')
    async def list_(self, ctx):
        """Lists the full word filter"""
        guild_config = await self.db.get_guild_config(ctx.guild.id)
        await ctx.send(f"Filters: {', '.join([f'`{i}`' for i in guild_config.detections.filters])}")

    @command(10, aliases=['set-warn-punishment', 'set_warn_punishment'])
    async def setwarnpunishment(self, ctx, limit: int, punishment=None):
        """Sets punishment after certain number of warns.
        Punishments can be "kick", "ban" or "none".

        Example: !!setwarnpunishment 5 kick

        It is highly encouraged to add a final "ban" condition
        """
        if punishment not in ('kick', 'ban', 'none'):
            raise commands.BadArgument('Invalid punishment, pick from `kick`, `ban`, `none`.')

        if punishment == 'none' or punishment is None:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$unset': {f'warn_punishments.{limit}': ''}})
        else:
            await self.bot.db.update_guild_config(ctx.guild.id, {'$set': {f'warn_punishments.{limit}': punishment}})

        await ctx.send(self.bot.accept)


def setup(bot):
    bot.add_cog(Setup(bot))
