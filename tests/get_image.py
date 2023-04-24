import datetime
import hashlib
import json
import os
from pathlib import Path
import pprint
import shutil
import tarfile
import time
import typing
import oci.auth as oa
import oci.model as om
import oci.client as oc
import gci.componentmodel as cm


def get_module_dir() -> Path:
    path = Path(__file__)
    return path.parent.parent.absolute()

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
    root_dir = 'image'
    work_dir = get_module_dir() / root_dir
    prepare_work_dir(work_dir)
    # write manifest to file:
    manifest_file = work_dir / 'manifest.json'
    with open(manifest_file, 'w') as f:
        f.write(json.dumps(manifest.as_dict()))

    # Download config:
    print(f'  Downloading config: {manifest.config.digest}, {manifest.config.mediaType}')
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

def prepare_work_dir(folder: str):
    sub_folder = Path(folder)
    if sub_folder.exists():
        shutil.rmtree(sub_folder)
    Path.mkdir(sub_folder)


def _create_tar_and_digest_from_dir(dir: Path, tar_file: str | Path) -> tuple[str, int]:
    with tarfile.open(tar_file, 'w:gz') as tar:
        for child in dir.iterdir():
            tar.add(child, arcname=dir.name + '/' + child.name)
    # create hash
    with open(tar_file, 'rb') as f:
        digest = hashlib.file_digest(f, 'sha256')

    tar_size = tar_file.stat().st_size

    return 'sha256:' + digest.hexdigest(), tar_size

def get_manifest_dict(architecture: str, os: str, entrypoint: str, layer_digests: list[str]) -> dict[str, str]:
    now_as_iso_str = datetime.datetime.now().isoformat() + 'Z'
    manifest = {
        'architecture': architecture,
        'os': f'{os}',
        'config' : {
            'Env': ['PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'],
            'Entrypoint': [ entrypoint ],
            'WorkingDir': '/',
            'OnBuild': None,
        },
        'created': now_as_iso_str,
        'history' : [{
            'created': now_as_iso_str,
            'created_by': 'OCM Integration Tests',
            'comment': 'python3',
        }],
        'rootfs': {
            'type': 'layers',
            'diff_ids': layer_digests,
        }
    }

    return manifest


def upload_image(client: oc.Client, image_ref: str):
    bin_file = 'hello.arm64'
    version_file = 'VERSION'
    module_dir = get_module_dir()
    work_dir = module_dir / 'image'
    layer_digests = []
    # create first layer with hello folder and binary
    dest_dir = 'hello'
    prepare_work_dir(work_dir)
    print(f'{work_dir}')
    Path.mkdir(work_dir / dest_dir)
    src_file = module_dir / bin_file
    dest_file = work_dir / dest_dir / bin_file
    shutil.copy(src_file, dest_file)
    # create gzipped tar:
    tar_file_name = work_dir / 'layer_1.tgz'
    hex_digest, tar_size =  _create_tar_and_digest_from_dir(work_dir / dest_dir, tar_file_name)
    print(f'File {tar_file_name} written, SHA-256 digest is: {hex_digest}, Size: {tar_size}')
    blob_ref1 = om.OciBlobRef(
        mediaType = 'application/vnd.docker.image.rootfs.diff.tar.gzip',
        digest = hex_digest,
        size = tar_size,
    )
    layer_digests.append(hex_digest)
    with open(tar_file_name, 'rb') as data_input:
        client.put_blob(
            image_reference=image_ref,
            digest=blob_ref1.digest,
            mimetype=blob_ref1.mediaType,
            data=data_input,
            octets_count=blob_ref1.size,
            max_chunk=4096,
            )

    # create second layer with hello folder and version file
    shutil.rmtree(work_dir / dest_dir)
    Path.mkdir(work_dir / dest_dir)
    src_file = module_dir / version_file
    dest_file = work_dir / dest_dir / version_file
    shutil.copy(src_file, dest_file)
    tar_file_name = work_dir / 'layer_2.tgz'
    hex_digest, tar_size =  _create_tar_and_digest_from_dir(work_dir / dest_dir, tar_file_name)
    print(f'File {tar_file_name} written, SHA-256 digest is: {hex_digest}, Size: {tar_size}')
    blob_ref2 = om.OciBlobRef(
        mediaType = 'application/vnd.docker.image.rootfs.diff.tar.gzip',
        digest = hex_digest,
        size = tar_size,
    )
    layer_digests.append(hex_digest)
    with open(tar_file_name, 'rb') as data_input:
        client.put_blob(
            image_reference=image_ref,
            digest=blob_ref2.digest,
            mimetype=blob_ref2.mediaType,
            data=data_input,
            octets_count=blob_ref2.size,
            max_chunk=4096,
            )

    # add config layer with hello folder and version file
    manifest = get_manifest_dict('arm64', os='linux', entrypoint='/hello/hello', layer_digests=layer_digests)
    pprint.pprint(manifest)
    man_file = work_dir / 'config.json'
    with open(man_file, 'w') as f:
        f.write(json.dumps(manifest))
    man_size = man_file.stat().st_size
    with open(man_file, 'rb') as f:
        digest = hashlib.file_digest(f, 'sha256')
    hex_digest = 'sha256:' + digest.hexdigest()
    print(f'Config file {man_file} written,  SHA-256 digest is: {hex_digest}, Size: {tar_size}')
    with open(man_file, 'rb') as data_input:
        client.put_blob(
            image_reference=image_ref,
            digest=hex_digest,
            mimetype='application/vnd.docker.container.image.v1+json',
            data=data_input,
            octets_count=blob_ref2.size,
            max_chunk=4096,
            )

    config = om.OciBlobRef(
        mediaType = "application/vnd.docker.container.image.v1+json",
        digest = hex_digest,
        size = man_size,
    )
    manifest = om.OciImageManifest(
        config = config,
        layers = (blob_ref1, blob_ref2),
        mediaType = 'application/vnd.docker.distribution.manifest.v2+json',
        # mediaType = om.OCI_MANIFEST_SCHEMA_V2_MIME,
    )
    manifest_str = json.dumps(manifest.as_dict())
    with open(work_dir / 'manifest.json', 'w') as f:
        f.write(manifest_str)

    response = client.put_manifest(
        image_reference=image_ref,
        manifest=manifest_str.encode('utf-8'),
    )
    print(f'response manifest upload: {response.status_code}, msg: {response.content}')

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
    image_ref1 = 'gcr.io/google-containers/pause:3.2'
    image_ref = 'eu.gcr.io/sap-cp-k8s-ocm-gcp-eu30-dev/dev/d058463/images/hello-amd64:0.1.0'
    with open('local/gcr-key.json') as f:
        gcr_key = f.read()

    client = oc.Client(
        credentials_lookup=_credentials_lookup,
        routes=oc.OciRoutes(oc.base_api_url),
    )

    # download_image(client, image_ref)
    upload_image_ref = 'eu.gcr.io/sap-cp-k8s-ocm-gcp-eu30-dev/dev/d058463/images/helloupload-arm64:0.1.0'
    # upload_image_ref = 'TDT7W57RPY.fritz.box:4430/helloupload-arm64:0.1.0'
    upload_image(client, upload_image_ref)


if __name__ == '__main__':
    main()