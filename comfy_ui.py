"""Windows desktop workbench for one ComfyUI API workflow."""

from pathlib import Path

from workbench.ui import launch


if __name__ == "__main__":
    launch(Path(__file__).resolve().parent)
