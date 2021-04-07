import re
import sys
import traceback

import aiohttp
import discord
import humanize
import prettify_exceptions
from discord.ext import commands

from utils.default import Blacklisted, Maintenance
from utils.eco import NotRegistered
from utils.fuzzy import finder


class CommandErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, Maintenance):
            return await ctx.send(embed=ctx.embed(title='⚠️ Maintenence mode is active.'))

        if isinstance(error, Blacklisted):
            reason = self.bot.blacklist.get(ctx.author.id, "No reason, you probably did something dumb.")
            embed = ctx.embed(title='⚠️ You are blacklisted.',
                              description=f'**Blacklisted For:** {reason}'
                                          f'\n\nYou can join the support server [here]({self.bot.support_invite}) if you feel this is a mistake.')

            try:
                return await ctx.author.send(embed=embed)
            except discord.Forbidden:
                await ctx.send(embed=embed)

        if not isinstance(error, (commands.CommandNotFound, commands.CommandOnCooldown)):
            ctx.command.reset_cooldown(ctx)

        if isinstance(error, NotRegistered):
            return await ctx.send(str(error))

        # This prevents any entry with local handlers being handled here in on_command_error.
        if hasattr(ctx.command, 'on_error'):
            return

        # This prevents any cogs with an overwritten cog_command_error being handled here.
        cog = ctx.cog
        if cog and cog._get_overridden_method(cog.cog_command_error) is not None:
            return

        # ignored = (entry.CommandNotFound,)  # if you want to not send error messages
        ignored = ()

        # Allows us to check for original exceptions raised and sent to CommandInvokeError.
        # If nothing is found. We keep the exception passed to on_command_error.
        error = getattr(error, 'original', error)

        # Anything in ignored will return and prevent anything happening.
        if isinstance(error, ignored):
            return

        if isinstance(error, commands.CommandNotFound):
            failed_command = re.match(rf"^({ctx.prefix})\s*(.*)", ctx.message.content, flags=re.IGNORECASE).group(2)
            matches = finder(failed_command, self.bot.command_list, lazy=False)
            if not matches:
                return
            match = None
            for command in matches:
                cmd = self.bot.get_command(command)
                if not await cmd.can_run(ctx):
                    return
                match = command
                break
            return await ctx.send(embed=ctx.embed(
                description=f"No command called `{failed_command}` found. Did you mean `{match}`?"
            ))

        command = ctx.command.qualified_name

        if isinstance(error, commands.CheckFailure):
            return await ctx.send(embed=ctx.embed(
                description=f'You do not have the correct permissions for `{command}`'
            ))

        if isinstance(error, discord.Forbidden):
            return await ctx.send(embed=ctx.embed(
                description=f'I do not have the correct permissions for `{command}`'
            ))

        if isinstance(error, commands.CommandOnCooldown):
            retry = humanize.precisedelta(error.retry_after, minimum_unit='seconds')
            cd = error.cooldown
            embed = ctx.embed(
                description=f"<a:countdown:827916388659363870> **{command}** is on cooldown. Try again in {retry}.\n"
                            f"You can use this command **{cd.rate} {ctx.plural('time(s)', cd.rate)} every {humanize.precisedelta(cd.per, minimum_unit='seconds')}.\n"
                            f"Type: {cd.type.name}"
            )

            return await ctx.send(embed=embed)

        if isinstance(error, commands.NoPrivateMessage):
            try:
                return await ctx.author.send(embed=ctx.embed(description=f"{ctx.invoked_with} cannot be used in DM's"))
            except discord.HTTPException:
                pass

        if isinstance(error, commands.MissingRequiredArgument):
            errors = str(error).split(" ", maxsplit=1)
            return await ctx.send(embed=ctx.embed(
                description=f'`{errors[0]}` {errors[1]}\n'
                            f'You can view the help for this command with `{ctx.clean_prefix}help` `{command}`'
            ))

        if isinstance(error, commands.DisabledCommand):
            return await ctx.send(embed=ctx.embed(description=f'`{command}` has been disabled.'))

        if isinstance(error, commands.BadArgument):
            return await ctx.send(embed=ctx.embed(title=str(error),
                                                  description=f'You provided a bad argument to `{command}`! View `{ctx.clean_prefix}help {command}` for more info on how to use this command.'))

        if isinstance(error, aiohttp.ServerTimeoutError):
            return await ctx.send(embed=ctx.embed(description=f"{command} timed out."))

        print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
        traceback.print_exception(type(error),
                                  error,
                                  error.__traceback__,
                                  file=sys.stderr)

        formatted = traceback.format_exception(type(error), error, error.__traceback__)
        pretty_traceback = "".join(
            prettify_exceptions.DefaultFormatter().format_exception(type(error), error, error.__traceback__)
        )
        desc = (
            f"Command: {ctx.invoked_with}\n"
            f"Full content: {ctx.escape(ctx.message.content)}\n"
            f"Guild: {ctx.guild.name} ({ctx.guild.id})\n"
            f"Channel: {ctx.channel.name} ({ctx.channel.id})\n"
            f"User: {ctx.author.name} ({ctx.author.id})\n"
            f"Jump URL: {ctx.message.jump_url}"
        )
        embed = ctx.embed(title='AN ERROR OCCURED', url=await ctx.mystbin(pretty_traceback) + '.py', description=desc)
        await self.bot.error_webhook.send(f"```py\n{''.join(formatted)}```", embed=embed)

        error = "".join(formatted)
        if len(error) > 1700:
            error = await ctx.mystbin(str(error)) + ".py"

        await ctx.send(
            f"Something has gone wrong while executing `{command}`. You should not be seeing this, I have contacted my developer with information about this error.\n"
            f"```py\n{error}\n```")


def setup(bot):
    bot.add_cog(CommandErrorHandler(bot))