from pathlib import Path
import logging

import pytest

import ocmcli as ocm
from ocm_fixture import ctx, ocm_config, OcmTestContext
import util
from create_comp import TestData

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.usefixtures("ocm_config")

signature_name = 'inttest-sig'

def gen_key_pair(priv_key_path, pub_key_path):
    if not priv_key_path.exists() and not pub_key_path.exists():
        print('generating new key-pair')
        ocm.execute_ocm(f'create rsakeypair {priv_key_path} {pub_key_path}')

@pytest.fixture
def setup() -> tuple[str, str]:
    gen_dir = util.get_gen_dir()
    priv_key_path = gen_dir / 'priv.key'
    pub_key_path = gen_dir / 'public.key'
    gen_key_pair(priv_key_path, pub_key_path)
    return priv_key_path, pub_key_path


def test_sign_ctf(ctx: OcmTestContext, setup: tuple[str, str]):
    priv_key_path, pub_key_path = setup
    # create ctf archive
    td = TestData()
    cli = td.create_ctf()
    cli.sign(signature_name, priv_key_path)
    cli.verify(signature_name, pub_key_path)


def test_sign_remote(ctx: OcmTestContext, setup: tuple[str, str]):
    priv_key_path, pub_key_path = setup
    # create ctf archive
    td = TestData()
    cli = td.create_ctf()
    cli.ocm_repo = util.get_repo_url(ctx)
    cli.push()
    cli.sign(signature_name, priv_key_path, remote=True)
    cli.verify(signature_name, pub_key_path, remote=True)


def test_sign_with_reference(ctx: OcmTestContext, setup: tuple[str, str]):
    priv_key_path, pub_key_path = setup
    # create ctf archive
    td = TestData()
    td.with_reference_yaml()
    logger.debug(td.component_yaml)
    cli = td.create_ctf()
    cli.ocm_repo = util.get_repo_url(ctx)
    cli.push()
    cli.sign(signature_name, priv_key_path, recursive=True, remote=True)
    cli.verify(signature_name, pub_key_path, remote=True)


def test_wrong_key(ctx: OcmTestContext, setup: tuple[str, str]):
    priv_key_path, pub_key_path = setup
    gen_dir = util.get_gen_dir()
    wrong_priv_key_path = gen_dir / 'priv_wrong.key'
    wrong_pub_key_path = gen_dir / 'public_wrong.key'
    gen_key_pair(wrong_priv_key_path, wrong_pub_key_path)
    # create ctf archive
    td = TestData()
    cli = td.create_ctf()
    cli.sign(signature_name, priv_key_path)
    with pytest.raises(ocm.OcmCliException, match='signature verification failed') as excinfo:
        cli.verify(signature_name, wrong_pub_key_path)