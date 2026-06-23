#!/usr/bin/env python3
"""Admin utility to create a user account (since public signup is disabled).

Usage:
  docker compose exec backend python3 create_user.py <email> <password>
"""
import asyncio
import sys

import bcrypt
import db


async def main():
    if len(sys.argv) != 3:
        print("Usage: python3 create_user.py <email> <password>")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    password = sys.argv[2]

    if len(password) < 8:
        print("Error: password must be at least 8 characters")
        sys.exit(1)

    await db.init_pool()
    existing = await db.get_user_by_email(email)
    if existing:
        print(f"Error: user '{email}' already exists")
        await db.close_pool()
        sys.exit(1)

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = await db.create_user(email, pw_hash)
    if user:
        print(f"Created user: id={user['id']} email={user['email']}")
    else:
        print("Error: could not create user")
        sys.exit(1)

    await db.close_pool()


asyncio.run(main())
