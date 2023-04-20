import os
import subprocess

import ocmcli as ocm
import pytest

repo_prefix = os.getenv('FDQN_NAME')
repo_host = repo_prefix[0:repo_prefix.find(':')] if ':' in repo_prefix else repo_prefix
repo_dir = repo_prefix
user_name = os.getenv('USER_NAME')
passwd = os.getenv('PASSWD')

def test_transfer_without_credentials():
    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        ocm.execute_ocm(f'transfer artifacts gcr.io/google-containers/pause:3.2 {repo_dir}/images/pause:3.2', capture_output=True)
    assert excinfo.value.stderr.decode('utf-8').find('401 Unauthorized') >= 0


def test_transfer_with_credentials():
    credential_options = f'--cred :type=OCIRegistry --cred :hostname={repo_host} --cred username={user_name} --cred password={passwd}'
    ocm.execute_ocm(f'{credential_options} transfer artifacts gcr.io/google-containers/pause:3.2 {repo_dir}/images/pause:3.2')


if __name__ == '__main__':
    print('First test!')
    test_transfer_without_credentials()
    print('Second test!')
    test_transfer_with_credentials()