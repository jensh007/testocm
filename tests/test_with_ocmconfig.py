import os
from pathlib import Path
import time
import pytest
from ocm_fixture import ocm_config

import ocmcli as ocm
from ocm_fixture import ctx, OcmTestContext
import util


pytestmark = pytest.mark.usefixtures("ocm_config")

def test_config(ctx: OcmTestContext):
    util.print_ocm_config()
    ocm.execute_ocm(f'transfer artifacts gcr.io/google-containers/pause:3.2 {ctx.repo_dir}/images/pause:3.2', capture_output=True)
