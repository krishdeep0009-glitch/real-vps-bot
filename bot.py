import asyncio
import logging

import discord
from discord.ext import commands, tasks

from config import config
from utils import database as db
from utils import proxmox

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("blined-cloud")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents, help_command=None)


@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} ({bot.user.id})")
    log.info(f"{config.HOSTING_NAME} deployer online. Prefix: {config.COMMAND_PREFIX}")
    if not auto_suspend_loop.is_running():
        auto_suspend_loop.start()
    await bot.change_presence(
        activity=discord.Game(name=f"{config.COMMAND_PREFIX}help | {config.HOSTING_NAME}")
    )


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(f"❌ Missing argument. Try `{config.COMMAND_PREFIX}help` for usage.")
    elif isinstance(error, commands.BadArgument):
        await ctx.reply("❌ Invalid argument type. Check the value you passed (e.g. mention, numbers).")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        log.exception("Command error", exc_info=error)
        await ctx.reply(f"❌ Unexpected error: `{error}`")


@tasks.loop(minutes=1)
async def auto_suspend_loop():
    """Background job: suspend any VPS whose timer has expired."""
    due = db.due_for_suspension()
    for row in due:
        vmid = row["vmid"]
        try:
            await asyncio.to_thread(proxmox.suspend_vps, vmid)
            db.set_suspended(vmid, True)
            log.info(f"Auto-suspended VMID {vmid} ({row['hostname']})")

            if config.LOG_CHANNEL_ID:
                channel = bot.get_channel(config.LOG_CHANNEL_ID)
                if channel:
                    await channel.send(
                        f"⏰ VPS `{vmid}` ({row['hostname']}) auto-suspended — timer expired."
                    )
        except Exception as e:
            log.error(f"Failed to auto-suspend {vmid}: {e}")


async def main():
    db.init_db()
    async with bot:
        await bot.load_extension("cogs.deploy")
        await bot.load_extension("cogs.help")
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")
    asyncio.run(main())
