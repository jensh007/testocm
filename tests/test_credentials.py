import subprocess
import time

import pytest

import ocmcli as ocm
from ocm_fixture import ctx, ocm_no_config, OcmTestContext
import util


pytestmark = pytest.mark.usefixtures("ocm_no_config")  # explicitely set no credentials to avoid auto fallback to docker confi
def test_transfer_without_credentials(ctx: OcmTestContext):
    with pytest.raises(ocm.OcmCliException, match='401 Unauthorized') as excinfo:
        ocm.execute_ocm(f'transfer artifacts gcr.io/google-containers/pause:3.2 {ctx.repo_dir}/images/pause:3.2')


def test_transfer_with_credentials(ctx: OcmTestContext):
    credential_options = f'--cred :type=OCIRegistry --cred :hostname={ctx.repo_host} --cred username={ctx.user_name} --cred password={ctx.passwd}'
    util.print_ocm_config()
    ocm.execute_ocm(f'{credential_options} transfer artifacts gcr.io/google-containers/pause:3.2 {ctx.repo_dir}/images/pause:3.2')


