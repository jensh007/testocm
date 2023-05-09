import logging

import gci.componentmodel as cm
import pytest
import oci.model as om

from create_comp import TestData
import ocmcli as ocm
from ocm_fixture import ctx, ocm_config, OcmTestContext
import util

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.usefixtures("ocm_config")

root_dir = util.get_root_dir()

comp_name = TestData.comp_name
comp_vers = TestData.comp_vers
provider = TestData.provider
ref_comp_name = TestData.ref_comp_name
ref_comp_vers = TestData.ref_comp_vers


def create_child_component(repo_url: str) -> ocm.OcmApplication:
    td = TestData()
    cli = td.create_child_ctf()
    cli.ocm_repo = repo_url
    cli.push(force=True, by_value=True)
    return cli


def create_parent_component(repo_url: str) -> ocm.OcmApplication:
    td = TestData()
    td.with_reference_yaml()
    cli = td.create_ctf()
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
    cli.transport(src_spec, target_repo_url, force=True, by_value=by_value, recursive=recursive)
    oci = util.get_oci_client(ctx, target_repo_url)
    cd = oci.get_component_descriptor_from_registry(comp_name, comp_vers)

    # debugging
    if logger.level <= logging.DEBUG:
        cd_yaml = oci.get_component_descriptor_from_registry(comp_name, comp_vers, as_yaml=True)
        logger.debug(cd_yaml)

    assert cd
    # check that image references are adjusted to target location
    if by_value:
      image_reference = f'{target_repo_url}/google_containers/echoserver:1.10'
      chart_reference=f'{target_repo_url}/{provider}/echo/echoserver:0.1.0'
    else:
      image_reference = f'{repo_url}/google_containers/echoserver:1.10'
      chart_reference=f'{repo_url}/{provider}/echo/echoserver:0.1.0'

    td = TestData()
    chart = cd.component.resources[0]
    td.verify_chart_remote(chart, image_reference=chart_reference)
    image = cd.component.resources[1]
    td.verify_image_remote(image, image_reference=image_reference)
    return oci


def test_transport_plain(ctx: OcmTestContext):
    target_repo_url = f'{ctx.repo_prefix}/target-{util.randomword(4)}'
    logger.info(f'{target_repo_url=}')

    oci = do_transport_and_get_cd(ctx, target_repo_url, False, False)
    if logger.level <= logging.DEBUG:
        cd_yaml = oci.get_component_descriptor_from_registry(comp_name, comp_vers, as_yaml=True)
        logger.debug(cd_yaml)

    # check that referenced component was not transferred
    with pytest.raises(om.OciImageNotFoundException, match='404') as excinfo:
      oci.get_component_descriptor_from_registry(ref_comp_name, ref_comp_vers)


def test_transport_by_value(ctx: OcmTestContext):
    target_repo_url = f'{ctx.repo_prefix}/target-{util.randomword(4)}'
    logger.info(f'{target_repo_url=}')

    oci = do_transport_and_get_cd(ctx, target_repo_url, True, False)
    # check that referenced component was not transferred
    cd_yaml = oci.get_component_descriptor_from_registry(comp_name, comp_vers, as_yaml=True)
    with pytest.raises(om.OciImageNotFoundException, match='404') as excinfo:
      oci.get_component_descriptor_from_registry(ref_comp_name, ref_comp_vers)


def test_transport_with_reference(ctx: OcmTestContext):
    target_repo_url = f'{ctx.repo_prefix}/target-{util.randomword(4)}'
    logger.info(f'{target_repo_url=}')

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
