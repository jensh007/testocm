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


pytestmark = pytest.mark.usefixtures("ocm_config")


def test_image_transfer_docker_style(ctx: OcmTestContext):
    print(f'{ctx=}')
    # create an image with docker mime types and store it in oci registry
    image_name = 'hello:0.1.0'
    image_ref = f'{ctx.repo_dir}/images/{image_name}'
    client = upload_image.get_oci_client()
    upload_image.upload_image(client, image_ref)
    target_image_ref = f'{ctx.repo_dir}/image-test/{image_name}'
    ocm.execute_ocm(f'transfer artifacts {image_ref} {target_image_ref}', capture_output=True)
    # retrieve image and analyse it
    blob_ref = client.head_manifest(image_ref, accept=om.MimeTypes.prefer_multiarch)
    manifest: om.OciImageManifest = client.manifest(
        image_reference=image_ref,
        absent_ok=False,
        accept=blob_ref.mediaType
    )
    assert manifest.schemaVersion == 2
    assert manifest.mediaType == 'application/vnd.docker.distribution.manifest.v2+json'
    assert manifest.config.mediaType == 'application/vnd.docker.container.image.v1+json'
    assert len(manifest.layers) == 2
    for layer in manifest.layers:
        assert layer.mediaType == 'application/vnd.docker.image.rootfs.diff.tar.gzip'
        assert layer.size > 0


