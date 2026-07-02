"""Download the u2net_human_seg model once so the app works fully offline."""
from photoclaude.core.background import get_session

if __name__ == "__main__":
    print("Downloading/locating u2net_human_seg model (~176 MB)…")
    get_session()
    print("Model ready in ~/.u2net")
