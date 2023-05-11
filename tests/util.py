import random
import shutil
import string
from pathlib import Path

from cd_tools import OciFetcher
from ocm_fixture import OcmTestContext

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


def get_oci_client(ctx: OcmTestContext, repo_url: str):
    return OciFetcher(
        repo_url=repo_url,
        user_name=ctx.user_name,
        password=ctx.passwd,
    )


def get_root_dir() -> Path:
    path = Path(__file__)
    return path.parent.parent.absolute()


def get_gen_dir() -> Path:
    return get_root_dir() / 'gen'


def randomword(length: int):
   letters = string.ascii_lowercase
   return ''.join(random.choice(letters) for i in range(length))


def get_repo_url(ctx: OcmTestContext):
    return f'{ctx.repo_prefix}/inttest'
