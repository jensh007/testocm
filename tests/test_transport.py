from pathlib import Path
import json
import logging
import random
import string
import textwrap

import gci.componentmodel as cm
import pytest
import oci.model as om

import ocmcli as ocm
from cd_tools import OciFetcher
from ocm_fixture import ctx, ocm_config, OcmTestContext
from ocm_builder import OcmBuilder
import util
import test_create_component as tcc

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.usefixtures("ocm_config")

comp_vers = '1.0.0'
provider = 'ocm.integrationtest'
image_name = 'echo'
comp_name = f'{provider}/{image_name}'
label_key = 'mylabel'
label_value = 'Hello Label'
image_reference = 'gcr.io/google_containers/echoserver:1.10'
pause_reference = 'gcr.io/google_containers/pause:3.2'
commit_id = 'e39625d6e919d33267da4778a1842670ce2bbf77'
src_repo_url = 'github.com/open-component-model/ocm'

ref_comp_name = f'{provider}/helper'
ref_comp_vers = '1.0.0'

def get_root_dir() -> Path:
    path = Path(__file__)
    return path.parent.parent.absolute()


def randomword(length: int):
   letters = string.ascii_lowercase
   return ''.join(random.choice(letters) for i in range(length))

def create_child_component(repo_url: str) -> ocm.OcmApplication:
    testdata_dir = get_root_dir() / 'test-data'
    component_yaml = textwrap.dedent(f'''\
      components:
      - name: {ref_comp_name}
        version: {ref_comp_vers}
        provider:
            name: {provider}
        resources:
          - name: pause_image
            type: ociImage
            version: 3.2.0
            access:
                type: ociArtifact
                imageReference: {pause_reference}
        ''')
    ocm_builder = OcmBuilder('helper_component', get_root_dir())
    cli = ocm_builder.create_ctf_from_component_spec(component_yaml)
    cli.ocm_repo = repo_url
    cli.push(force=True, by_value=True)
    return cli


def create_parent_component(repo_url: str) -> ocm.OcmApplication:
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
                repoUrl: {src_repo_url}
                commit: {commit_id}
            version: {comp_vers}
        componentReferences:
        - name: childcomp
          componentName: {ref_comp_name}
          version: {ref_comp_vers}
        ''')
    ocm_builder = OcmBuilder('test_reference', get_root_dir())
    cli = ocm_builder.create_ctf_from_component_spec(component_yaml)
    cli.ocm_repo = repo_url
    cli.push(force=True, by_value=True)
    return cli


def do_transport_and_get_cd(ctx: OcmTestContext, target_repo_url: str, by_value: bool, recursive: bool):
    repo_url = f'{ctx.repo_prefix}/src'
    create_child_component(repo_url)
    oci = util.get_oci_client(ctx, repo_url)
    cd = oci.get_component_descriptor_from_registry(ref_comp_name, ref_comp_vers)
    assert cd
    cli = create_parent_component(repo_url)
    oci = util.get_oci_client(ctx, repo_url)
    cd = oci.get_component_descriptor_from_registry(comp_name, comp_vers)
    assert cd
    src_spec = f'{repo_url}//{comp_name}:{comp_vers}'
    cli.transport(src_spec, target_repo_url, force=True, by_value=True, recursive=recursive)
    oci = util.get_oci_client(ctx, target_repo_url)
    cd = oci.get_component_descriptor_from_registry(comp_name, comp_vers)
    # debugging
    cd_yaml = oci.get_component_descriptor_from_registry(comp_name, comp_vers, as_yaml=True)
    print(cd_yaml)

    assert cd
    # check that image references are adjusted to target location
    chart_reference=f'{target_repo_url}/{provider}/echo/echoserver:0.1.0'
    chart = cd.component.resources[0]
    tcc.verify_chart_remote(chart, image_reference=chart_reference)
    image = cd.component.resources[1]
    image_reference = f'{target_repo_url}/google_containers/echoserver:1.10'
    tcc.verify_image_remote(image, image_reference=image_reference)
    return oci


def test_transport_by_value(ctx: OcmTestContext):
    target_repo_url = f'{ctx.repo_prefix}/target-{randomword(4)}'
    print(f'{target_repo_url=}')

    oci = do_transport_and_get_cd(ctx, target_repo_url, True, False)
    # check that referenced component was not transferred
    cd_yaml = oci.get_component_descriptor_from_registry(comp_name, comp_vers, as_yaml=True)
    with pytest.raises(om.OciImageNotFoundException, match='404') as excinfo:
      oci.get_component_descriptor_from_registry(ref_comp_name, ref_comp_vers)


def test_transport_with_reference(ctx: OcmTestContext):
    target_repo_url = f'{ctx.repo_prefix}/target-{randomword(4)}'
    print(f'{target_repo_url=}')

    oci = do_transport_and_get_cd(ctx, target_repo_url, True, True)
    # check that referenced component was not transferred
    cd_yaml = oci.get_component_descriptor_from_registry(comp_name, comp_vers, as_yaml=True)
    cd = oci.get_component_descriptor_from_registry(comp_name, comp_vers)
    assert cd
    # check that image references are adjusted to target location
    ref = cd.component.componentReferences[0]
    assert ref.componentName == ref_comp_name
    assert ref.version == ref_comp_vers
    cd = oci.get_component_descriptor_from_registry(ref_comp_name, ref_comp_vers)
    ref_image = cd.component.resources[0]
    new_location = f'{target_repo_url}/google_containers/pause:3.2'
    assert ref_image.access.imageReference == new_location
    assert ref_image.name == 'pause_image'
    assert ref_image.type == cm.ArtefactType.OCI_IMAGE
    assert ref_image.version == '3.2.0'
    assert ref_image.relation == cm.ResourceRelation.EXTERNAL
    assert type(ref_image.access) == cm.OciAccess
    assert ref_image.access.type == cm.AccessType.OCI_REGISTRY
    assert ref_image.access.imageReference == new_location
