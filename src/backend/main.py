from __future__ import annotations

import os

from dotenv import load_dotenv
from supabase import create_client


def main() -> None:
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set in .env."
        )

    try:
        supabase = create_client(url, key)
        response = supabase.table("swpc_endpoint_state").select("endpoint").limit(1).execute()
        print("Connection successful!")
        print(f"Rows visible: {len(response.data or [])}")
    except Exception as exc:
        print("Connection failed.")
        print(exc)


if __name__ == "__main__":
    main()
