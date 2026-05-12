"""Quick test: upload CSV using a pre-existing JWT token.

Usage:
    1. Login via Google OAuth in the browser
    2. Copy the JWT token from the URL or localStorage
    3. Set TOKEN below, then run: python test_upload.py
"""
import httpx, asyncio, json

BASE = "http://localhost:8000"
TOKEN = "PASTE_YOUR_JWT_HERE"  # Get from browser after OAuth login


async def main():
    if TOKEN == "PASTE_YOUR_JWT_HERE":
        print("ERROR: Set TOKEN to a valid JWT before running.")
        print("Login via browser → copy token from /auth/callback URL.")
        return

    headers = {"Authorization": f"Bearer {TOKEN}"}

    # Verify auth works
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.get(f"{BASE}/auth/me", headers=headers)
        print(f"Auth check: {r.status_code}")
        if r.status_code != 200:
            print("Auth failed:", r.text)
            return
        print(f"Logged in as: {r.json().get('full_name')} ({r.json().get('email')})")

        # Upload CSV
        csv_path = r"c:\Users\eshla\Downloads\prag_project\new_attendance_with_holidays.csv"
        with open(csv_path, "rb") as f:
            r2 = await c.post(
                f"{BASE}/admin/upload-csv",
                files={"file": ("new_attendance_with_holidays.csv", f, "text/csv")},
                headers=headers,
            )
        print(f"Upload: {r2.status_code}")
        print(json.dumps(r2.json(), indent=2))

asyncio.run(main())
