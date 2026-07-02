import discord
from discord.ext import commands

from config import config


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.remove_command("help")

    @commands.command(name="help")
    async def help(self, ctx):
        p = config.COMMAND_PREFIX
        embed = discord.Embed(
            title=f"{config.HOSTING_NAME} — Command List",
            description="Real KVM VPS deployment & management bot.",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name=f"`{p}create <@user> <memory_mb> <cpu_cores> <disk_gb> <os> [cpu_name] [suspend_days]`",
            value=(
                "Deploy a real VPS with OS + custom CPU model selection.\n"
                f"Example: `{p}create @Bob 4096 2 40 ubuntu22 host 30`\n"
                "`os`: `ubuntu20`, `ubuntu22`, `ubuntu24` (or whatever's configured in `.env`).\n"
                "`cpu_name`: optional Proxmox CPU model (e.g. `host`, `kvm64`). Defaults to `host`.\n"
                "`suspend_days`: optional number of days until auto-suspend. Omit or `0` = never."
            ),
            inline=False,
        )
        embed.add_field(
            name=f"`{p}deploy <@user> <memory_mb> <cores> <disk_gb> <suspend_time>`",
            value=(
                "Older/simpler deploy command (no OS/CPU choice, default template).\n"
                f"Example: `{p}deploy @Bob 4096 2 40 30d`"
            ),
            inline=False,
        )
        embed.add_field(
            name=f"`{p}list [@user]`",
            value="List all VPS instances, or filter to one user's instances.",
            inline=False,
        )
        embed.add_field(
            name=f"`{p}info <vmid>`",
            value="Show detailed specs, IP, and status for one VPS.",
            inline=False,
        )
        embed.add_field(
            name=f"`{p}suspend <vmid>`",
            value="Manually stop/suspend a VPS.",
            inline=False,
        )
        embed.add_field(
            name=f"`{p}unsuspend <vmid>`",
            value="Resume a suspended VPS.",
            inline=False,
        )
        embed.add_field(
            name=f"`{p}renew <vmid> <suspend_time>`",
            value="Change/reset the auto-suspend timer on a VPS.",
            inline=False,
        )
        embed.add_field(
            name=f"`{p}delete <vmid>`",
            value="Permanently delete a VPS (requires ✅ confirmation).",
            inline=False,
        )
        embed.add_field(
            name=f"`{p}help`",
            value="Show this menu.",
            inline=False,
        )
        embed.set_footer(text=f"{config.HOSTING_NAME} · Powered by Proxmox VE (real KVM VMs)")
        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(Help(bot))
