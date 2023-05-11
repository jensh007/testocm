import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import pprint
import shutil
import tarfile
import oci.auth as oa
import oci.model as om
import oci.client as oc
import gci.componentmodel as cm

import util

def download_image(client: oc.Client, image_ref: str):
    # get MIME type:
    blob_ref = client.head_manifest(image_ref, accept=om.MimeTypes.prefer_multiarch)
    print(f'Found MIME-type: {blob_ref.mediaType} with annotations: {blob_ref.annotations}')

    manifest = client.manifest(
            image_reference=image_ref,
            absent_ok=False,
            accept=blob_ref.mediaType
        )

    print(f'{type(manifest)=}')
    pprint.pprint(manifest.as_dict())
    work_dir = util.get_gen_dir() / 'image-out'
    util.prepare_or_clean_dir(work_dir)
    # write manifest to file:
    manifest_file = work_dir / 'manifest.json'
    with open(manifest_file, 'w') as f:
        f.write(json.dumps(manifest.as_dict()))

    # Download config:
    print(f'Downloading config: {manifest.config.digest}, {manifest.config.mediaType}')
    fname = work_dir / manifest.config.digest.replace(':','.')
    with open(fname, 'wb') as f:
        response = client.blob(image_ref, manifest.config.digest)
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    # Download all layers
    for layer in manifest.layers:
        print(f'  Downloading layer: {layer.digest}, {layer.mediaType}')
        fname = Path('image') / layer.digest.replace(':','.')
        with open(fname, 'wb') as f:
            response = client.blob(image_ref, layer.digest)
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print('Done')

def main():
    def _credentials_lookup(
            image_reference: str,
            privileges: oa.Privileges=oa.Privileges.READONLY,
            absent_ok: bool=True,
        ):
            if not 'gcr.io' in image_reference:
                return oa.OciBasicAuthCredentials(
                        username=user_name,
                        password=passwd,
                    )
            elif 'eu.gcr.io/sap-cp-k8s-ocm-gcp-eu30-dev' in image_reference:
                return oa.OciBasicAuthCredentials(
                        username='_json_key',
                        password=gcr_key,
                    )
            else:
                return None

    user_name = os.getenv('USER_NAME')
    passwd = os.getenv('PASSWD')
    # Multiarch image:
    # image_ref = 'gcr.io/google-containers/pause:3.2'
    # single arch image
    image_ref = 'eu.gcr.io/sap-cp-k8s-ocm-gcp-eu30-dev/dev/d058463/images/hello-amd64:0.1.0'

    with open('local/gcr-key.json') as f:
        gcr_key = f.read()

    client = oc.Client(
        credentials_lookup=_credentials_lookup,
        routes=oc.OciRoutes(oc.base_api_url),
    )

    download_image(client, image_ref)


if __name__ == '__main__':
    main()