"""Optional local fallback for a Telethon StringSession.

The admin panel is the normal path: Settings, نشست, then API ID, API hash,
phone, Telegram code and 2FA. Use this script only if the panel cannot reach
Telegram. Do not paste the printed string into a ticket or a log.
"""
from __future__ import annotations

import asyncio
import getpass


async def main() -> None:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    api_id = int(input("API ID: ").strip())
    api_hash = getpass.getpass("API hash: ").strip()
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        print("\nTG_SESSION_STRING=")
        print(client.session.save())
        me = await client.get_me()
        print(f"\nLogged in as {me.id} @{me.username or '-'} premium={bool(me.premium)}")


if __name__ == "__main__":
    asyncio.run(main())
