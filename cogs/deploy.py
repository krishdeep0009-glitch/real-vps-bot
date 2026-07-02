import asyncio
import time

import discord
from discord.ext import commands

from config import config
from utils import database as db
from utils import proxmox
from utils.checks import is_admin
from utils.timeparse import parse_duration, humanize_remaining


class Deploy(commands.Cog):
    """Provision and manage real KVM virtual machines on Blined Cloud."""

    def __init__(self, bot):
        self.bot = bot

    # ---------------------------------------------------------------
    # .deploy [user] [memory] [core] [disk] [suspend time]
    # ---------------------------------------------------------------
    @commands.command(name="deploy")
    async def deploy(self, ctx, user: discord.Member = None, memory: int = None,
                      core: int = None, disk: int = None, suspend_time: str = "never"):
        """Deploy a real VPS. Usage: .deploy @user <memory_mb> <cores> <disk_gb> <suspend_time>"""
        if not is_admin(ctx.author):
            return await ctx.reply("❌ You don't have permission to deploy VPS instances.")

        if None in (user, memory, core, disk):
            return await ctx.reply(
                f"❌ Missing arguments.\nUsage: `{config.COMMAND_PREFIX}deploy <@user> "
                f"<memory_mb> <cores> <disk_gb> <suspend_time>`\n"
                f"Example: `{config.COMMAND_PREFIX}deploy @Bob 2048 2 20 30d`"
            )

        if memory < 256 or core < 1 or disk < 5:
            return await ctx.reply(
                "❌ Invalid specs. Minimum: 256 MB RAM, 1 core, 5 GB disk."
            )

        try:
            suspend_at = parse_duration(suspend_time)
        except ValueError as e:
            return await ctx.reply(f"❌ {e}")

        vmid = db.next_free_vmid(config.VMID_RANGE_START, config.VMID_RANGE_END)
        if vmid is None:
            return await ctx.reply("❌ No free VMIDs left in the configured range.")

        hostname = f"blined-{user.name}-{vmid}".lower().replace(" ", "-")

        status_msg = await ctx.reply(
            f"🚀 Deploying real VPS `{hostname}` (VMID `{vmid}`) for {user.mention}...\n"
            f"RAM: {memory}MB | Cores: {core} | Disk: {disk}GB | "
            f"Suspends: {suspend_time}\n⏳ This provisions an actual KVM virtual machine, "
            f"please wait..."
        )

        try:
            result = await asyncio.to_thread(
                proxmox.create_vps, vmid, hostname, memory, core, disk
            )
        except Exception as e:
            await status_msg.edit(content=f"❌ Deployment failed: `{e}`")
            return

        db.add_vps(
            vmid=vmid,
            discord_id=user.id,
            hostname=hostname,
            memory_mb=memory,
            cores=core,
            disk_gb=disk,
            ip_address=result["ip_address"],
            root_password=result["root_password"],
            suspend_at=suspend_at,
        )

        embed = discord.Embed(
            title=f"✅ {config.HOSTING_NAME} — VPS Deployed",
            color=discord.Color.green(),
        )
        embed.add_field(name="Hostname", value=hostname, inline=True)
        embed.add_field(name="VMID", value=str(vmid), inline=True)
        embed.add_field(name="Owner", value=user.mention, inline=True)
        embed.add_field(name="RAM", value=f"{memory} MB", inline=True)
        embed.add_field(name="Cores", value=str(core), inline=True)
        embed.add_field(name="Disk", value=f"{disk} GB", inline=True)
        embed.add_field(name="IP Address", value=result["ip_address"], inline=True)
        embed.add_field(name="Root Password", value=f"||{result['root_password']}||", inline=True)
        embed.add_field(
            name="Auto-Suspend",
            value=humanize_remaining(suspend_at),
            inline=True,
        )
        embed.set_footer(text=f"{config.HOSTING_NAME} · Real KVM VPS, not a container")

        await status_msg.edit(content=None, embed=embed)

        try:
            dm_embed = embed.copy()
            dm_embed.title = f"🎉 Your VPS is ready on {config.HOSTING_NAME}"
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        if config.LOG_CHANNEL_ID:
            log_channel = self.bot.get_channel(config.LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(
                    f"📦 `{ctx.author}` deployed VMID `{vmid}` for `{user}`."
                )

    # ---------------------------------------------------------------
    # .create [user] [memory] [cpu] [disk] [os] [custom cpu name] [suspend days]
    # ---------------------------------------------------------------
    @commands.command(name="create")
    async def create(self, ctx, user: discord.Member = None, memory: int = None,
                      cpu: int = None, disk: int = None, os_name: str = None,
                      cpu_name: str = None, suspend_days: float = None):
        """
        Deploy a real VPS with OS + custom CPU model selection.
        Usage: .create <@user> <memory_mb> <cpu_cores> <disk_gb> <os> [cpu_name] [suspend_days]
        os: one of the configured PVE_OS_TEMPLATES keys (e.g. ubuntu20, ubuntu22, ubuntu24)
        cpu_name: optional Proxmox CPU model to expose to the guest (default: host)
        suspend_days: optional, number of days until auto-suspend (omit/0 = never)
        """
        if not is_admin(ctx.author):
            return await ctx.reply("❌ You don't have permission to create VPS instances.")

        if None in (user, memory, cpu, disk, os_name):
            available = ", ".join(sorted(config.PVE_OS_TEMPLATES.keys())) or "(none configured)"
            return await ctx.reply(
                f"❌ Missing arguments.\nUsage: `{config.COMMAND_PREFIX}create <@user> "
                f"<memory_mb> <cpu_cores> <disk_gb> <os> [cpu_name] [suspend_days]`\n"
                f"Available OS: `{available}`\n"
                f"Example: `{config.COMMAND_PREFIX}create @Bob 2048 2 20 ubuntu22 host 30`"
            )

        if memory < 256 or cpu < 1 or disk < 5:
            return await ctx.reply("❌ Invalid specs. Minimum: 256 MB RAM, 1 core, 5 GB disk.")

        os_key = os_name.strip().lower()
        template_id = config.PVE_OS_TEMPLATES.get(os_key)
        if template_id is None:
            available = ", ".join(sorted(config.PVE_OS_TEMPLATES.keys())) or "(none configured)"
            return await ctx.reply(
                f"❌ Unknown OS `{os_name}`. Available options: `{available}`\n"
                f"(Configure more in `.env` → `PVE_OS_TEMPLATES`)"
            )

        cpu_type = (cpu_name or config.PVE_DEFAULT_CPU_TYPE).strip()

        if suspend_days is None or suspend_days <= 0:
            suspend_at = None
            suspend_display = "never"
        else:
            suspend_at = int(time.time() + suspend_days * 86400)
            suspend_display = f"{suspend_days:g}d"

        vmid = db.next_free_vmid(config.VMID_RANGE_START, config.VMID_RANGE_END)
        if vmid is None:
            return await ctx.reply("❌ No free VMIDs left in the configured range.")

        hostname = f"blined-{user.name}-{vmid}".lower().replace(" ", "-")

        status_msg = await ctx.reply(
            f"🚀 Creating real VPS `{hostname}` (VMID `{vmid}`) for {user.mention}...\n"
            f"OS: **{os_key}** | RAM: {memory}MB | vCPUs: {cpu} ({cpu_type}) | Disk: {disk}GB | "
            f"Suspends in: {suspend_display}\n⏳ Provisioning an actual KVM virtual machine..."
        )

        try:
            result = await asyncio.to_thread(
                proxmox.create_vps, vmid, hostname, memory, cpu, disk,
                template_id, cpu_type,
            )
        except Exception as e:
            await status_msg.edit(content=f"❌ Creation failed: `{e}`")
            return

        db.add_vps(
            vmid=vmid,
            discord_id=user.id,
            hostname=hostname,
            memory_mb=memory,
            cores=cpu,
            disk_gb=disk,
            ip_address=result["ip_address"],
            root_password=result["root_password"],
            suspend_at=suspend_at,
        )

        embed = discord.Embed(
            title=f"✅ {config.HOSTING_NAME} — VPS Created",
            color=discord.Color.green(),
        )
        embed.add_field(name="Hostname", value=hostname, inline=True)
        embed.add_field(name="VMID", value=str(vmid), inline=True)
        embed.add_field(name="Owner", value=user.mention, inline=True)
        embed.add_field(name="OS", value=os_key, inline=True)
        embed.add_field(name="CPU", value=f"{cpu} vCPU ({cpu_type})", inline=True)
        embed.add_field(name="RAM", value=f"{memory} MB", inline=True)
        embed.add_field(name="Disk", value=f"{disk} GB", inline=True)
        embed.add_field(name="IP Address", value=result["ip_address"], inline=True)
        embed.add_field(name="Root Password", value=f"||{result['root_password']}||", inline=True)
        embed.add_field(name="Auto-Suspend", value=humanize_remaining(suspend_at), inline=True)
        embed.set_footer(text=f"{config.HOSTING_NAME} · Real KVM VPS, not a container")

        await status_msg.edit(content=None, embed=embed)

        try:
            dm_embed = embed.copy()
            dm_embed.title = f"🎉 Your VPS is ready on {config.HOSTING_NAME}"
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        if config.LOG_CHANNEL_ID:
            log_channel = self.bot.get_channel(config.LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(
                    f"📦 `{ctx.author}` created VMID `{vmid}` ({os_key}) for `{user}`."
                )

    # ---------------------------------------------------------------
    @commands.command(name="list")
    async def list_vps(self, ctx, user: discord.Member = None):
        """List all VPS instances, or just those belonging to a user."""
        rows = db.list_vps(discord_id=user.id if user else None)
        if not rows:
            return await ctx.reply("No VPS instances found.")

        lines = []
        for r in rows:
            state = "🔴 Suspended" if r["suspended"] else "🟢 Running"
            lines.append(
                f"`{r['vmid']}` **{r['hostname']}** — <@{r['discord_id']}> — "
                f"{r['memory_mb']}MB/{r['cores']}c/{r['disk_gb']}GB — {state} — "
                f"suspends in {humanize_remaining(r['suspend_at'])}"
            )

        embed = discord.Embed(
            title=f"{config.HOSTING_NAME} — VPS List",
            description="\n".join(lines[:25]),
            color=discord.Color.blurple(),
        )
        await ctx.reply(embed=embed)

    # ---------------------------------------------------------------
    @commands.command(name="info")
    async def info(self, ctx, vmid: int):
        """Show detailed info for a single VPS."""
        row = db.get_vps(vmid)
        if not row:
            return await ctx.reply("❌ No VPS with that VMID.")

        if not is_admin(ctx.author) and ctx.author.id != row["discord_id"]:
            return await ctx.reply("❌ You can only view your own VPS.")

        embed = discord.Embed(title=f"VPS `{vmid}` — {row['hostname']}", color=discord.Color.blurple())
        embed.add_field(name="Owner", value=f"<@{row['discord_id']}>", inline=True)
        embed.add_field(name="RAM", value=f"{row['memory_mb']} MB", inline=True)
        embed.add_field(name="Cores", value=str(row["cores"]), inline=True)
        embed.add_field(name="Disk", value=f"{row['disk_gb']} GB", inline=True)
        embed.add_field(name="IP", value=row["ip_address"] or "unknown", inline=True)
        embed.add_field(name="Status", value=row["status"], inline=True)
        embed.add_field(name="Auto-Suspend", value=humanize_remaining(row["suspend_at"]), inline=True)
        await ctx.reply(embed=embed)

    # ---------------------------------------------------------------
    @commands.command(name="suspend")
    async def suspend(self, ctx, vmid: int):
        """Manually suspend (stop) a VPS."""
        if not is_admin(ctx.author):
            return await ctx.reply("❌ You don't have permission to do that.")
        row = db.get_vps(vmid)
        if not row:
            return await ctx.reply("❌ No VPS with that VMID.")
        try:
            await asyncio.to_thread(proxmox.suspend_vps, vmid)
        except Exception as e:
            return await ctx.reply(f"❌ Failed to suspend: `{e}`")
        db.set_suspended(vmid, True)
        await ctx.reply(f"🔴 VPS `{vmid}` suspended.")

    # ---------------------------------------------------------------
    @commands.command(name="unsuspend")
    async def unsuspend(self, ctx, vmid: int):
        """Resume a suspended VPS."""
        if not is_admin(ctx.author):
            return await ctx.reply("❌ You don't have permission to do that.")
        row = db.get_vps(vmid)
        if not row:
            return await ctx.reply("❌ No VPS with that VMID.")
        try:
            await asyncio.to_thread(proxmox.resume_vps, vmid)
        except Exception as e:
            return await ctx.reply(f"❌ Failed to resume: `{e}`")
        db.set_suspended(vmid, False)
        await ctx.reply(f"🟢 VPS `{vmid}` resumed.")

    # ---------------------------------------------------------------
    @commands.command(name="renew")
    async def renew(self, ctx, vmid: int, suspend_time: str):
        """Update the auto-suspend timer for a VPS, e.g. .renew 10005 30d"""
        if not is_admin(ctx.author):
            return await ctx.reply("❌ You don't have permission to do that.")
        row = db.get_vps(vmid)
        if not row:
            return await ctx.reply("❌ No VPS with that VMID.")
        try:
            suspend_at = parse_duration(suspend_time)
        except ValueError as e:
            return await ctx.reply(f"❌ {e}")
        db.update_suspend_at(vmid, suspend_at)
        await ctx.reply(f"✅ VPS `{vmid}` will now suspend: {humanize_remaining(suspend_at)}")

    # ---------------------------------------------------------------
    @commands.command(name="delete")
    async def delete(self, ctx, vmid: int):
        """Permanently delete a VPS."""
        if not is_admin(ctx.author):
            return await ctx.reply("❌ You don't have permission to do that.")
        row = db.get_vps(vmid)
        if not row:
            return await ctx.reply("❌ No VPS with that VMID.")

        confirm_msg = await ctx.reply(
            f"⚠️ This will **permanently delete** VPS `{vmid}` ({row['hostname']}). "
            f"React with ✅ within 15s to confirm."
        )
        await confirm_msg.add_reaction("✅")

        def check(reaction, reactor):
            return (
                reactor.id == ctx.author.id
                and str(reaction.emoji) == "✅"
                and reaction.message.id == confirm_msg.id
            )

        try:
            await self.bot.wait_for("reaction_add", timeout=15.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.reply("❌ Deletion cancelled (no confirmation).")

        try:
            await asyncio.to_thread(proxmox.delete_vps, vmid)
        except Exception as e:
            return await ctx.reply(f"❌ Failed to delete: `{e}`")

        db.delete_vps(vmid)
        await ctx.reply(f"🗑️ VPS `{vmid}` deleted permanently.")


async def setup(bot):
    await bot.add_cog(Deploy(bot))
