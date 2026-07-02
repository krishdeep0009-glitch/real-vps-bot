from config import config


def is_admin(member) -> bool:
    """Allow everyone if ADMIN_ROLE_IDS is empty (open mode), else require a role."""
    if not config.ADMIN_ROLE_IDS:
        return True
    if getattr(member, "guild_permissions", None) and member.guild_permissions.administrator:
        return True
    member_role_ids = {r.id for r in getattr(member, "roles", [])}
    return bool(member_role_ids.intersection(config.ADMIN_ROLE_IDS))
