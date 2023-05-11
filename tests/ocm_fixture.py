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
    user_name = os.getenv('USER_NAME')
    passwd = os.getenv('PASSWD')
    assert repo_prefix and user_name and passwd, \
        'OCM Integration tests, reqiure FQDN_NAME, USER_NAME, PASSWD variables'
    repo_host = repo_prefix[0:repo_prefix.find(':')] if ':' in repo_prefix else repo_prefix
    repo_dir = repo_prefix
    return OcmTestContext(
        repo_prefix=repo_prefix,
        repo_host=repo_host,
        repo_dir=repo_dir,
        user_name=user_name,
        passwd=passwd
    )


@pytest.fixture(scope="module")
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
              password: "{ctx.passwd}"
'''
    backup_file = Path(os.getenv('HOME')) / '.ocmconfig.bak'
    config_file = Path(os.getenv('HOME')) / '.ocmconfig'
    # backup .ocmconfig if it exists
    if backup_file.exists():
        backup_file.unlink()
    if config_file.exists():
        config_file.rename(backup_file)
    with config_file.open('w') as f:
        f.write(test_config)
    yield None
    # restore original .ocmconfig if it existed after tests are run
    config_file.unlink()
    if backup_file.exists():
        backup_file.rename(config_file)


@pytest.fixture(scope="module")
def ocm_no_config(ctx):
#     test_config = f'''\
# type: generic.config.ocm.software/v1
# configurations:
#   - type: credentials.config.ocm.software
#     consumers:
#       - identity:
#           type: OCIRegistry
#           hostname: {ctx.repo_host}
#         credentials: []
# '''
    test_config = f'''\
type: generic.config.ocm.software/v1
configurations: []
'''
    backup_file = Path(os.getenv('HOME')) / '.ocmconfig.bak'
    config_file = Path(os.getenv('HOME')) / '.ocmconfig'
    # backup .ocmconfig if it exists
    if backup_file.exists():
        backup_file.unlink()
    if config_file.exists():
        config_file.rename(backup_file)
    with config_file.open('w') as f:
        f.write(test_config)
    yield None
    # restore original .ocmconfig if it existed after tests are run
    config_file.unlink()
    if backup_file.exists():
        backup_file.rename(config_file)
