from pathlib import Path
import json
import pprint
import shutil
import textwrap
import pytest
import tarfile

import gci.componentmodel as cm
import oci.model as om
import yaml

import ocmcli as ocm
from ocm_fixture import ctx, OcmTestContext

comp_vers = '1.0.0'
provider = 'ocm.integrationtest'
image_name = 'echo'
comp_name = f'{provider}/{image_name}'

def get_root_dir() -> Path:
    path = Path(__file__)
    return path.parent.parent.absolute()


def find_component_descriptor(ctf_dir: Path) -> cm.ComponentDescriptor:
    index_file = ctf_dir / 'artifact-index.json'
    with open(index_file) as f:
        ind = json.load(f)
    digest:str = ind['artifacts'][0]['digest']
    manifest_file = ctf_dir / 'blobs' / digest.replace('sha256:', 'sha256.')
    with open(manifest_file) as f:
        oci_manifest = json.load(f)
    assert oci_manifest['mediaType'] == 'application/vnd.oci.image.manifest.v1+json'
    assert oci_manifest['layers'][0]['mediaType'] == 'application/vnd.ocm.software.component-descriptor.v2+yaml+tar'
    cd_digest = oci_manifest['layers'][0]['digest']
    cd_tar_file =  ctf_dir / 'blobs' / cd_digest.replace('sha256:', 'sha256.')
    extract_dir = ctf_dir.parent / 'extracted'
    with tarfile.open(cd_tar_file, 'r') as tar:
        name = tar.next()
        print(f'extracting file {name}')
        tar.extractall(extract_dir)
    cd_file = extract_dir / name.name
    cd_file.chmod(0o644)
    with open(cd_file) as f:
        cd_dict = yaml.safe_load(f)
    cd = cm.ComponentDescriptor.from_dict(cd_dict, cm.ValidationMode.NONE)
    return cd


def verify_component_descriptor(cd: cm.ComponentDescriptor):
    assert cd.meta.schemaVersion == cm.SchemaVersion.V2
    assert cd.component.name == comp_name
    assert cd.component.version  == comp_vers
    assert len(cd.component.resources) == 2
    assert len(cd.component.sources) == 1
    chart = cd.component.resources[0]
    assert chart.name == 'chart'
    assert chart.type == cm.ArtefactType.HELM_CHART
    assert chart.relation == cm.ResourceRelation.LOCAL
    assert chart.version == '1.0.0'
    assert chart.access.type == cm.AccessType.LOCAL_BLOB
    print(f'{type(chart.access)=}')
    # does not work at this time:
    # assert type(chart.access) == cm.LocalBlobAccess
    # assert chart.access.localReference.startswith('sha256:')
    # assert chart.access.mediaType == 'application/vnd.oci.image.manifest.v1+tar+gzip'
    # assert chart.access.referenceName == f'{provider}/echo/echoserver:0.1.0'
    image = cd.component.resources[1]
    assert image.name == 'image'
    assert image.type == cm.ArtefactType.OCI_IMAGE
    assert image.version == '1.10'
    assert image.relation == cm.ResourceRelation.EXTERNAL
    assert type(image.access) == cm.OciAccess #  cm.AccessType.OCI_REGISTRY
    assert image.access.imageReference == 'gcr.io/google_containers/echoserver:1.10'
    assert len(image.labels) == 1
    assert image.labels[0].name == 'mylabel'
    assert image.labels[0].value == 'Hello Label'
    assert len(cd.component.sources) == 1
    source = cd.component.sources[0]
    assert source.name == 'source'
    assert source.type == 'filesystem'
    assert source.version == comp_vers
    assert source.access.type == cm.AccessType.GITHUB
    assert type(source.access) == cm.GithubAccess
    assert source.access.commit == 'e39625d6e919d33267da4778a1842670ce2bbf77'
    assert source.access.repoUrl == 'github.com/open-component-model/ocm'

def test_ctf_from_ca(ctx: OcmTestContext):
    # create an image with docker mime types and store it in oci registry
    gen_dir = get_root_dir() / 'gen'
    testdata_dir = get_root_dir() / 'test-data'
    test_dir = gen_dir / 'test_ctf_from_ca'
    sources_yaml = textwrap.dedent(f'''\
        name: source
        type: filesystem
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

    ctf_dir = test_dir / 'ctf'
    blob_dir = ctf_dir / 'blobs'
    index_file = ctf_dir / 'artifact-index.json'
    assert blob_dir.exists()
    assert index_file.exists()

    count = 0
    for child in blob_dir.iterdir():
        count += 1
        assert child.name.startswith('sha256.')

    # retrieve component descriptor
    cd = find_component_descriptor(ctf_dir)
    assert cd
    verify_component_descriptor(cd)
