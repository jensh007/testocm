import os
import shutil
from pathlib import Path

def prepare_or_clean_dir(dir: Path | str):
    dir = Path(dir)
    if dir.exists():
        shutil.rmtree(dir)
    dir.mkdir(parents=True)
