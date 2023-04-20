import os
from pathlib import Path
import time
import pytest
from ocm_fixture import ocm_config

import ocmcli as ocm
from ocm_fixture import ctx, OcmTestContext

pytestmark = pytest.mark.usefixtures("ocm_config")

def test_config(ctx: OcmTestContext):
    config_path = Path(os.getenv('HOME')) / '.ocmconfig'
    with open(config_path) as f:
        cfg = f.read()
    print(cfg)
    ocm.execute_ocm(f'transfer artifacts gcr.io/google-containers/pause:3.2 {ctx.repo_dir}/images/pause:3.2', capture_output=True)
    time.sleep(10.0)
    print('After')