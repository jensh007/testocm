import os
from pathlib import Path
import time
import pytest
from ocm_fixture import ocm_config

import ocmcli as ocm
import oci.auth as oa
import oci.model as om
import oci.client as oc
import gci.componentmodel as cm

from ocm_fixture import ctx, OcmTestContext
import upload_image
from oci_image import OciImageCreator


pytestmark = pytest.mark.usefixtures("ocm_config")


def do_image_transfer(client, image_ref, target_image_ref) -> om.OciImageManifest:
    ocm.execute_ocm(f'transfer artifacts {image_ref} {target_image_ref}', capture_output=True)
    # retrieve image and analyse it
    blob_ref = client.head_manifest(image_ref, accept=om.MimeTypes.prefer_multiarch)
    manifest: om.OciImageManifest = client.manifest(
        image_reference=image_ref,
        absent_ok=False,
        accept=blob_ref.mediaType
    )
    return manifest


def test_image_transfer_docker_style(ctx: OcmTestContext):
    # create an image with docker mime types and store it in oci registry
    image_name = 'hello:0.1.0'
    image_ref = f'{ctx.repo_dir}/images/{image_name}'
    target_image_ref = f'{ctx.repo_dir}/image-test/{image_name}'
    client = upload_image.get_oci_client()
    upload_image.upload_image(client, image_ref, OciImageCreator.Style.DOCKER_STYLE)
    manifest = do_image_transfer(client, image_ref, target_image_ref)
    assert manifest.schemaVersion == 2
    assert manifest.mediaType == OciImageCreator.MANIFEST_MIME_TYPE_DOCKER
    assert manifest.config.mediaType == OciImageCreator.IMAGE_CONFIG_MIME_TYPE_DOCKER
    assert len(manifest.layers) == 2
    for layer in manifest.layers:
        assert layer.mediaType == OciImageCreator.IMAGE_LAYER_MIME_TYPE_DOCKER
        assert layer.size > 0


def test_image_transfer_oci_style(ctx: OcmTestContext):
    # create an image with oci mime types and store it in oci registry
    image_name = 'hello:0.1.0'
    image_ref = f'{ctx.repo_dir}/images/{image_name}'
    target_image_ref = f'{ctx.repo_dir}/image-test/{image_name}'
    client = upload_image.get_oci_client()
    upload_image.upload_image(client, image_ref, OciImageCreator.Style.OCI_STYLE)
    manifest = do_image_transfer(client, image_ref, target_image_ref)
    assert manifest.schemaVersion == 2
    assert manifest.mediaType == OciImageCreator.MANIFEST_MIME_TYPE_OCI
    assert manifest.config.mediaType == OciImageCreator.IMAGE_CONFIG_MIME_TYPE_OCI
    assert len(manifest.layers) == 2
    for layer in manifest.layers:
        assert layer.mediaType == OciImageCreator.IMAGE_LAYER_MIME_TYPE_OCI
        assert layer.size > 0

def _check_architectures_in_manifest(manifest):
    assert len(manifest.manifests) == 2
    architectures = {'amd64', 'arm64'}
    for m in manifest.manifests:
        assert m.platform.architecture in architectures
        architectures.remove(m.platform.architecture)
    assert len(architectures) == 0

def test_multi_arch_image_transfer_docker_style(ctx: OcmTestContext):
    image_name = 'hello-multi:0.1.0'
    image_ref = f'{ctx.repo_dir}/images/{image_name}'
    target_image_ref = f'{ctx.repo_dir}/image-test/{image_name}'
    client = upload_image.get_oci_client()
    upload_image.upload_multi_arch_image(client, image_ref, OciImageCreator.Style.DOCKER_STYLE)
    manifest = do_image_transfer(client, image_ref, target_image_ref)
    assert manifest.schemaVersion == 2
    assert manifest.mediaType == OciImageCreator.MULTI_ARCH_MANIFEST_MIME_TYPE_DOCKER
    _check_architectures_in_manifest(manifest)

def test_multi_arch_image_transfer_oci_style(ctx: OcmTestContext):
    image_name = 'hello-multi:0.1.0'
    image_ref = f'{ctx.repo_dir}/images/{image_name}'
    target_image_ref = f'{ctx.repo_dir}/image-test/{image_name}'
    client = upload_image.get_oci_client()
    upload_image.upload_multi_arch_image(client, image_ref, OciImageCreator.Style.OCI_STYLE)
    manifest = do_image_transfer(client, image_ref, target_image_ref)
    assert manifest.schemaVersion == 2
    assert manifest.mediaType == OciImageCreator.MULTI_ARCH_MANIFEST_MIME_TYPE_OCI
    _check_architectures_in_manifest(manifest)