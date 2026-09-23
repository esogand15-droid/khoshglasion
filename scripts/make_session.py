"""Create a Telethon StringSession for premium emoji edits.

Run this on your own computer, not on Railway:

    pip install telethon
    python scripts/make_session.py

Then put the printed string in Railway as TG_SESSION_STRING, with TG_API_ID
and TG_API_HASH from https://my.telegram.org. The account must be an admin of
the channel and should have Telegram Premium.
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
