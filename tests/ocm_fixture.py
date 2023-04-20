import dataclasses
import os
import pytest
from pathlib import Path

@dataclasses.dataclass(frozen=True)
class OcmTestContext:
    repo_prefix: str
    repo_host: str
    repo_dir: str
    user_name: str
    passwd: str


@pytest.fixture(scope="session")
def ctx():
    repo_prefix = os.getenv('FDQN_NAME')
    repo_host = repo_prefix[0:repo_prefix.find(':')] if ':' in repo_prefix else repo_prefix
    repo_dir = repo_prefix
    user_name = os.getenv('USER_NAME')
    passwd = os.getenv('PASSWD')
    return OcmTestContext(
        repo_prefix=repo_prefix,
        repo_host=repo_host,
        repo_dir=repo_dir,
        user_name=user_name,
        passwd=passwd
    )

@pytest.fixture()
def ocm_config(ctx):
    test_config = f'''\
type: generic.config.ocm.software/v1
configurations:
  - type: credentials.config.ocm.software
    consumers:
      - identity:
          type: OCIRegistry
          hostname: {ctx.repo_host}
        credentials:
          - type: Credentials
            properties:
              username: {ctx.user_name}
              password: {ctx.passwd}
'''
    backup_file = Path(os.getenv('HOME')) / '.ocmconfig.bak'
    config_path = Path(os.getenv('HOME')) / '.ocmconfig'
    if backup_file.exists():
        backup_file.unlink()
    config_path.rename(backup_file)
    with config_path.open('w') as f:
        f.write(test_config)
    yield None
    config_path.unlink()
    backup_file.rename(config_path)
