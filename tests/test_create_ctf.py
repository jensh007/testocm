from pathlib import Path
import shutil
import textwrap
import pytest

import ocmcli as ocm
from ocm_fixture import ctx, OcmTestContext

comp_vers = '1.0.0'
provider = 'ocm.integrationtest'
image_name = 'echo'
comp_name = f'{provider}/{image_name}'

def get_root_dir() -> Path:
    path = Path(__file__)
    return path.parent.parent.absolute()

def test_ctf_from_ca(ctx: OcmTestContext):
    # create an image with docker mime types and store it in oci registry
    gen_dir = get_root_dir() / 'gen'
    testdata_dir = get_root_dir() / 'test-data'
    test_dir = gen_dir / 'test_ctf_from_ca'
    sources_yaml = textwrap.dedent(f'''\
        name: source
        type: filesytem
        access:
            type: github
            repoUrl: github.com/open-component-model/ocm
            commit: e39625d6e919d33267da4778a1842670ce2bbf77
        version: {comp_vers}
        ''')
    resources_yaml = textwrap.dedent(f'''\
        ---
        name: chart
        type: helmChart
        input:
            type: helm
            path: {str(testdata_dir)}/echoserver-helmchart
        ---
        name: image
        type: ociImage
        version: "1.10"
        labels:
          - name: mylabel
            value: Hello Label
        access:
            type: ociArtifact
            imageReference: gcr.io/google_containers/echoserver:1.10
        ''')

    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True)

    source_file = test_dir / 'sources.yaml'
    resource_file = test_dir / 'resources.yaml'
    with open(source_file, 'w') as f:
        f.write(sources_yaml)
    with open(resource_file, 'w') as f:
        f.write(resources_yaml)

    cli = ocm.OcmApplication(
        name=comp_name,
        gen_dir=test_dir
    )

    cv_spec = cli.get_component_version_spec_template()
    cv_spec.version = comp_vers
    cv_spec.provider = provider
    cv_spec.source_file = source_file
    cv_spec.resource_file = resource_file

    cli.create_ctf_from_component_version(cv_spec)

    blob_dir = test_dir / 'ca' / 'blobs'
    cd = test_dir / 'ca' / 'component-descriptor.yaml'
    assert blob_dir.exists()
    count = 0
    for child in blob_dir.iterdir():
        count += 1
        assert child.name.startswith('sha256.')
    assert count == 1
    assert cd.exists()

    blob_dir = test_dir / 'ctf' / 'blobs'
    index_file = test_dir / 'ctf' / 'artifact-index.json'
    assert blob_dir.exists()
    assert index_file.exists()

    count = 0
    for child in blob_dir.iterdir():
        count += 1
        assert child.name.startswith('sha256.')
