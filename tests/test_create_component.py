import logging
from pathlib import Path
import textwrap

import pytest

import ocmcli as ocm
from cd_tools import OciFetcher
from ocm_fixture import ctx, ocm_config, OcmTestContext
import util
from create_comp import TestData
import create_comp

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.usefixtures("ocm_config")

comp_name = TestData.comp_name
comp_vers = TestData.comp_vers
provider = TestData.provider
ref_comp_name = TestData.ref_comp_name
ref_comp_vers = TestData.ref_comp_vers
image_reference = TestData.echo_image_reference
label_key = TestData.label_key
label_value = TestData.label_value
commit_id = TestData.commit_id
repo_url = TestData.repo_url

root_dir = util.get_root_dir()


def validate_ctf(cli: ocm.OcmApplication):
    ctf_dir = cli.gen_ctf_dir
    td = TestData()
    create_comp.validate_ctf_dir(ctf_dir)

    # retrieve component descriptor
    cd = td.find_component_descriptor(ctf_dir)
    assert cd
    td.verify_component_descriptor(cd)


def test_ctf_from_ca(ctx: OcmTestContext):
    # create an image with docker mime types and store it in oci registry
    testdata_dir = root_dir / 'test-data'
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

    TestData.prepare_test_env()
    cli = create_comp.create_ctf_from_resources_sources_references(
        test_dir=TestData.test_dir,
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
    td = TestData()
    return td.create_ctf()


def test_ctf_from_component_yaml():
    # create an image with docker mime types and store it in oci registry
    cli = create_test_ctf()
    validate_ctf(cli)


def test_reference():
    td = TestData()
    td.with_reference_yaml()
    cli =  td.create_ctf()
    ctf_dir = cli.gen_ctf_dir
    create_comp.validate_ctf_dir(ctf_dir)

    # retrieve component descriptor
    cd = td.find_component_descriptor(ctf_dir)
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


def get_remote_cd(oci: OciFetcher):
    cd = oci.get_component_descriptor_from_registry(comp_name, comp_vers)
    if logger.level <= logging.DEBUG:
        cd_yaml = oci.get_component_descriptor_from_registry(comp_name, comp_vers, as_yaml=True)
        logger.debug(cd_yaml)
    return cd



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
    repo_url = util.get_repo_url(ctx)
    cli = get_push_cli(repo_url)
    cli.push(force=True)

    # get uploaded component descriptor
    oci = util.get_oci_client(ctx, repo_url)
    cd = get_remote_cd(oci)

    chart_reference=f'{repo_url}/{provider}/echo/echoserver:0.1.0'
    td = TestData()
    td.verify_root_elems(cd)
    chart = cd.component.resources[0]
    td.verify_chart_remote(chart, image_reference=chart_reference)
    image = cd.component.resources[1]
    td.verify_image(image)
    assert len(cd.component.sources) == 1
    source = cd.component.sources[0]
    td.verify_source(source)

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
    repo_url = util.get_repo_url(ctx)
    cli = get_push_cli(repo_url)
    cli.push(force=True, by_value=True, )

    # check that contained artifacts are uploaded:
    oci = util.get_oci_client(ctx, repo_url)
    cd = get_remote_cd(oci)

    chart_reference=f'{repo_url}/{provider}/echo/echoserver:0.1.0'
    image_reference=f'{repo_url}/google_containers/echoserver:1.10'

    td = TestData()
    td.verify_root_elems(cd)
    chart = cd.component.resources[0]
    td.verify_chart_remote(chart, image_reference=chart_reference)
    image = cd.component.resources[1]
    td.verify_image_remote(image,image_reference=image_reference)
    assert len(cd.component.sources) == 1
    source = cd.component.sources[0]
    td.verify_source(source)

    # check that contained artifacts are uploaded:
    assert oci.exists(chart_reference)
    assert oci.exists(image_reference)
