import os
import shutil
from pathlib import Path

def prepare_or_clean_dir(dir: Path | str):
    dir = Path(dir)
    if dir.exists():
        shutil.rmtree(dir)
    dir.mkdir(parents=True)


def print_ocm_config():
    from pathlib import Path
    import os
    config_path = Path(os.getenv('HOME')) / '.ocmconfig'
    if config_path.exists():
        with open(config_path) as f:
            cfg = f.read()
        print(f'OCM configuration file read from: {config_path}:')
        print(cfg)
    else:
        print(f'OCM configuration file: {config_path} does not exist.')
