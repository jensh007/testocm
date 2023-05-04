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
from ocm_builder import OcmBuilder

comp_vers = '1.0.0'
provider = 'ocm.integrationtest'
image_name = 'echo'
comp_name = f'{provider}/{image_name}'
label_key = 'mylabel'
label_value = 'Hello Label'
image_reference = 'gcr.io/google_containers/echoserver:1.10'
repo_url = 'github.com/open-component-model/ocm'
commit_id = 'e39625d6e919d33267da4778a1842670ce2bbf77'

ref_comp_name = f'{provider}/helper'
ref_comp_vers = '1.0.0'


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
    assert image.access.imageReference == image_reference
    assert len(image.labels) == 1
    assert image.labels[0].name == label_key
    assert image.labels[0].value == label_value
    assert len(cd.component.sources) == 1
    source = cd.component.sources[0]
    assert source.name == 'source'
    assert source.type == 'filesystem'
    assert source.version == comp_vers
    assert source.access.type == cm.AccessType.GITHUB
    assert type(source.access) == cm.GithubAccess
    assert source.access.commit == commit_id
    assert source.access.repoUrl == repo_url


def validate_ctf_dir(ctf_dir: Path):
    blob_dir = ctf_dir / 'blobs'
    index_file = ctf_dir / 'artifact-index.json'
    assert blob_dir.exists()
    assert index_file.exists()

    count = 0
    for child in blob_dir.iterdir():
        count += 1
        assert child.name.startswith('sha256.')


def validate_ctf(cli: ocm.OcmApplication):
    ctf_dir = cli.gen_ctf_dir
    validate_ctf_dir(ctf_dir)

    # retrieve component descriptor
    cd = find_component_descriptor(ctf_dir)
    assert cd
    verify_component_descriptor(cd)


def create_helper_component():
    testdata_dir = get_root_dir() / 'test-data'
    component_yaml = textwrap.dedent(f'''\
      components:
      - name: {ref_comp_name}
        version: {ref_comp_vers}
        provider:
            name: {provider}
        resources:
          - name: myfile
            type: blob
            input:
              type: file
              path: {str(testdata_dir)}/someresource.txt
        ''')
    ocm_builder = OcmBuilder('helper_component', get_root_dir())
    ocm_builder.create_ctf_from_component_spec(component_yaml)


def test_ctf_from_ca(ctx: OcmTestContext):
    # create an image with docker mime types and store it in oci registry
    testdata_dir = get_root_dir() / 'test-data'
    sources_yaml = textwrap.dedent(f'''\
        name: source
        type: filesystem
        access:
            type: github
            repoUrl: {repo_url}
            commit: {commit_id}
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
          - name: {label_key}
            value: {label_value}
        access:
            type: ociArtifact
            imageReference: {image_reference}
        ''')

    ocm_builder = OcmBuilder('test_ctf_from_ca', get_root_dir())
    cli = ocm_builder.create_ctf_from_resources_sources_references(
        comp_name=comp_name,
        comp_vers=comp_vers,
        provider=provider,
        resources_yaml=resources_yaml,
        sources_yaml=sources_yaml,
    )

    blob_dir = cli.gen_ca_dir / 'blobs'
    cd = cli.gen_ca_dir / 'component-descriptor.yaml'
    assert blob_dir.exists()
    count = 0
    for child in blob_dir.iterdir():
        count += 1
        assert child.name.startswith('sha256.')
    assert count == 1
    assert cd.exists()

    validate_ctf(cli)


def test_ctf_from_component_yaml():
    # create an image with docker mime types and store it in oci registry
    testdata_dir = get_root_dir() / 'test-data'
    component_yaml = textwrap.dedent(f'''\
      components:
      - name: {comp_name}
        version: {comp_vers}
        provider:
            name: {provider}
        resources:
          - name: chart
            type: helmChart
            input:
                type: helm
                path: {str(testdata_dir)}/echoserver-helmchart
          - name: image
            type: ociImage
            version: "1.10"
            labels:
            - name: {label_key}
              value: {label_value}
            access:
                type: ociArtifact
                imageReference: {image_reference}
        sources:
          - name: source
            type: filesystem
            access:
                type: github
                repoUrl: {repo_url}
                commit: {commit_id}
            version: {comp_vers}
        ''')

    ocm_builder = OcmBuilder('test_ctf_from_component', get_root_dir())
    cli = ocm_builder.create_ctf_from_component_spec(component_yaml)
    validate_ctf(cli)


def test_reference():
    component_yaml = textwrap.dedent(f'''\
      components:
      - name: {comp_name}
        version: {comp_vers}
        provider:
          name: {provider}
        componentReferences:
        - name: microblog
          componentName: {ref_comp_name}
          version: {ref_comp_vers}
      ''')
    create_helper_component()
    ocm_builder = OcmBuilder('test_reference', get_root_dir())
    cli = ocm_builder.create_ctf_from_component_spec(component_yaml)
    ctf_dir = cli.gen_ctf_dir
    validate_ctf_dir(ctf_dir)

    # retrieve component descriptor
    cd = find_component_descriptor(ctf_dir)
    assert cd
    assert cd.component.name == comp_name
    assert cd.component.version  == comp_vers
    assert len(cd.component.componentReferences) == 1
    ref = cd.component.componentReferences[0]
    assert ref.componentName == ref_comp_name
    assert ref.version == ref_comp_vers
