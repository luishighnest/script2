import sys
import os
import asyncio
from dazn_navigator2.main import app

if __name__ == "__main__":
    try:
        app()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    except Exception:
        pass
    finally:
        os._exit(0)
