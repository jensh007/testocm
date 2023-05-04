from pathlib import Path
import json
import logging
import textwrap
import tarfile

import gci.componentmodel as cm
import oci.model as om
import yaml

import ocmcli as ocm
from cd_tools import OciFetcher
from ocm_fixture import ctx, OcmTestContext
from ocm_builder import OcmBuilder

logger = logging.getLogger(__name__)

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


def verify_root_elems(cd: cm.ComponentDescriptor):
    assert cd.meta.schemaVersion == cm.SchemaVersion.V2
    assert cd.component.name == comp_name
    assert cd.component.version  == comp_vers
    assert len(cd.component.resources) == 2
    assert len(cd.component.sources) == 1

def verify_chart(chart: cm.Resource):
    assert chart.name == 'chart'
    assert chart.type == cm.ArtefactType.HELM_CHART
    assert chart.relation == cm.ResourceRelation.LOCAL
    assert chart.version == '1.0.0'
    assert chart.access.type == cm.AccessType.LOCAL_BLOB
    assert type(chart.access) == cm.LocalBlobAccess
    assert chart.access.localReference.startswith('sha256:')
    assert chart.access.mediaType == 'application/vnd.oci.image.manifest.v1+tar+gzip'
    assert chart.access.referenceName == f'{provider}/echo/echoserver:0.1.0'

def verify_chart_remote(chart: cm.Resource, image_reference: str):
    assert chart.name == 'chart'
    assert chart.type == cm.ArtefactType.HELM_CHART
    assert chart.relation == cm.ResourceRelation.LOCAL
    assert chart.version == '1.0.0'
    assert chart.access.type == cm.AccessType.OCI_REGISTRY
    assert type(chart.access) == cm.OciAccess
    assert chart.access.imageReference == image_reference

def verify_image(image: cm.Resource):
    assert image.name == 'image'
    assert image.type == cm.ArtefactType.OCI_IMAGE
    assert image.version == '1.10'
    assert image.relation == cm.ResourceRelation.EXTERNAL
    assert type(image.access) == cm.OciAccess #  cm.AccessType.OCI_REGISTRY
    assert image.access.imageReference == image_reference
    assert len(image.labels) == 1
    assert image.labels[0].name == label_key
    assert image.labels[0].value == label_value

def verify_image_remote(image: cm.Resource, image_reference: str):
    assert image.name == 'image'
    assert image.type == cm.ArtefactType.OCI_IMAGE
    assert image.version == '1.10'
    assert image.relation == cm.ResourceRelation.EXTERNAL
    assert type(image.access) == cm.OciAccess
    assert image.access.type == cm.AccessType.OCI_REGISTRY
    assert image.access.imageReference == image_reference
    assert len(image.labels) == 1
    assert image.labels[0].name == label_key
    assert image.labels[0].value == label_value

def verify_source(source: cm.ComponentSource):
    assert source.name == 'source'
    assert source.type == 'filesystem'
    assert source.version == comp_vers
    assert source.access.type == cm.AccessType.GITHUB
    assert type(source.access) == cm.GithubAccess
    assert source.access.commit == commit_id
    assert source.access.repoUrl == repo_url


def verify_component_descriptor(cd: cm.ComponentDescriptor):
    verify_root_elems(cd)
    chart = cd.component.resources[0]
    verify_chart(chart)
    image = cd.component.resources[1]
    verify_image(image)
    assert len(cd.component.sources) == 1
    source = cd.component.sources[0]
    verify_source(source)


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


def create_test_ctf() -> ocm.OcmApplication:
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
    return ocm_builder.create_ctf_from_component_spec(component_yaml)

def test_ctf_from_component_yaml():
    # create an image with docker mime types and store it in oci registry
    cli = create_test_ctf()
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


def get_push_cli(repo_url):
    cli = create_test_ctf()
    cli.ocm_repo = repo_url
    return cli


def get_oci_client(ctx: OcmTestContext, repo_url: str):
    return OciFetcher(
        repo_url=repo_url,
        user_name=ctx.user_name,
        password=ctx.passwd,
    )

def get_remote_cd(oci: OciFetcher):
    cd = oci.get_component_descriptor_from_registry(comp_name, comp_vers)
    if logger.level <= logging.DEBUG:
        cd_yaml = oci.get_component_descriptor_from_registry(comp_name, comp_vers, as_yaml=True)
        logger.debug(cd_yaml)
    return cd


def get_repo_url(ctx: OcmTestContext):
    return f'{ctx.repo_prefix}/inttest'

# plain:
# component:
#   componentReferences: []
#   name: ocm.integrationtest/echo
#   provider: ocm.integrationtest
#   repositoryContexts:
#   - baseUrl: TDT7W57RPY.fritz.box:4430
#     componentNameMapping: urlPath
#     subPath: inttest
#     type: OCIRegistry
#   resources:
#   - access:
#       imageReference: TDT7W57RPY.fritz.box:4430/inttest/ocm.integrationtest/echo/echoserver:0.1.0
#       type: ociArtifact
#     name: chart
#     relation: local
#     type: helmChart
#     version: 1.0.0
#   - access:
#       imageReference: gcr.io/google_containers/echoserver:1.10
#       type: ociArtifact
#     labels:
#     - name: mylabel
#       value: Hello Label
#     name: image
#     relation: external
#     type: ociImage
#     version: "1.10"
#   sources:
#   - access:
#       commit: e39625d6e919d33267da4778a1842670ce2bbf77
#       repoUrl: github.com/open-component-model/ocm
#       type: github
#     name: source
#     type: filesystem
#     version: 1.0.0
#   version: 1.0.0
# meta:
#   schemaVersion: v2

def test_push_plain(ctx: OcmTestContext):
    repo_url = get_repo_url(ctx)
    cli = get_push_cli(repo_url)
    cli.push(force=True)

    # get uploaded component descriptor
    oci = get_oci_client(ctx, repo_url)
    cd = get_remote_cd(oci)

    chart_reference=f'{repo_url}/{provider}/echo/echoserver:0.1.0'
    verify_root_elems(cd)
    chart = cd.component.resources[0]
    verify_chart_remote(chart, image_reference=chart_reference)
    image = cd.component.resources[1]
    verify_image(image)
    assert len(cd.component.sources) == 1
    source = cd.component.sources[0]
    verify_source(source)

    # check that contained artifacts are uploaded:
    assert oci.exists(chart_reference)



# by value:
# component:
#   componentReferences: []
#   name: ocm.integrationtest/echo
#   provider: ocm.integrationtest
#   repositoryContexts:
#   - baseUrl: TDT7W57RPY.fritz.box:4430
#     componentNameMapping: urlPath
#     subPath: inttest
#     type: OCIRegistry
#   resources:
#   - access:
#       imageReference: TDT7W57RPY.fritz.box:4430/inttest/ocm.integrationtest/echo/echoserver:0.1.0
#       type: ociArtifact
#     name: chart
#     relation: local
#     type: helmChart
#     version: 1.0.0
#   - access:
#       imageReference: TDT7W57RPY.fritz.box:4430/inttest/google_containers/echoserver:1.10
#       type: ociArtifact
#     labels:
#     - name: mylabel
#       value: Hello Label
#     name: image
#     relation: external
#     type: ociImage
#     version: "1.10"
#   sources:
#   - access:
#       commit: e39625d6e919d33267da4778a1842670ce2bbf77
#       repoUrl: github.com/open-component-model/ocm
#       type: github
#     name: source
#     type: filesystem
#     version: 1.0.0
#   version: 1.0.0
# meta:
#   schemaVersion: v2

def test_push_by_value(ctx: OcmTestContext):
    repo_url = get_repo_url(ctx)
    cli = get_push_cli(repo_url)
    cli.push(force=True, by_value=True, )

    # check that contained artifacts are uploaded:
    oci = get_oci_client(ctx, repo_url)
    cd = get_remote_cd(oci)

    chart_reference=f'{repo_url}/{provider}/echo/echoserver:0.1.0'
    image_reference=f'{repo_url}/google_containers/echoserver:1.10'

    verify_root_elems(cd)
    chart = cd.component.resources[0]
    verify_chart_remote(chart, image_reference=chart_reference)
    image = cd.component.resources[1]
    verify_image_remote(image,image_reference=image_reference)
    assert len(cd.component.sources) == 1
    source = cd.component.sources[0]
    verify_source(source)

    # check that contained artifacts are uploaded:
    assert oci.exists(chart_reference)
    assert oci.exists(image_reference)
