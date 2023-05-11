import os
from pathlib import Path
import shutil

import oci.auth as oa
import oci.client as oc
import oci.model as om

import oci_image
import util

def create_upload_layers_and_config(
    image_handler: oci_image.OciImageCreator,
    architecture: str,
    work_dir: Path,
):
    module_dir = util.get_root_dir()
    bin_file_in = module_dir / 'local' / f'hello.{architecture}'
    bin_file_out = 'hello'
    version_file = 'VERSION'
    # create first layer with hello folder and binary
    dest_dir = 'hello'
    util.prepare_or_clean_dir(work_dir)
    print(f'{work_dir}')
    Path.mkdir(work_dir / dest_dir)
    src_file = module_dir / bin_file_in
    dest_file = work_dir / dest_dir / bin_file_out
    shutil.copy(src_file, dest_file)

    # create first layer:
    image_handler.create_and_upload_layer_from_dir(work_dir / dest_dir)

    # create second layer with version file
    util.prepare_or_clean_dir(work_dir)
    Path.mkdir(work_dir / dest_dir)
    src_file = util.get_root_dir() / version_file
    dest_file = work_dir / dest_dir / version_file
    shutil.copy(src_file, dest_file)

    image_handler.create_and_upload_layer_from_dir(work_dir / dest_dir)

    # add config layer with hello folder and version file
    image_handler.create_and_upload_image_config(
        architecture=architecture,
        os='linux',
        entrypoint='/hello/hello',
    )

def upload_image(client: oc.Client, image_ref: str, style: oci_image.OciImageCreator.Style):
    root_dir = util.get_root_dir()
    work_dir = root_dir / 'image'
    out_dir = util.get_gen_dir() / 'image-out'
    image_handler = oci_image.OciImageCreator(
        client,
        image_ref,
        out_dir,
        style,
    )

    create_upload_layers_and_config(image_handler, 'arm64', work_dir)

    response, _ = image_handler.create_and_upload_manifest()
    shutil.rmtree(work_dir)
    print(f'response manifest upload: {response.status_code}')


def upload_multi_arch_image(client: oc.Client, image_ref: str, style: oci_image.OciImageCreator.Style):
    root_dir = util.get_root_dir()
    work_dir = root_dir / 'image'
    out_dir = util.get_gen_dir() / 'image-out'
    image_handler = oci_image.OciImageCreator(
        client,
        image_ref,
        out_dir,
        style,
    )

    os = 'linux'
    architecture = 'arm64'
    create_upload_layers_and_config(image_handler, architecture, work_dir)
    platform = om.OciPlatform(architecture=architecture, os=os)
    image_handler.upload_architecture(platform)

    architecture = 'amd64'
    create_upload_layers_and_config(image_handler, architecture, work_dir)
    platform = om.OciPlatform(architecture=architecture, os=os)
    image_handler.upload_architecture(platform)

    response = image_handler.create_and_upload_multiarch_manifest()
    shutil.rmtree(work_dir)
    print(f'response manifest upload: {response.status_code}')


def get_oci_client() -> oc.Client:
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
        elif gcr_key and 'eu.gcr.io/sap-cp-k8s-ocm-gcp-eu30-dev' in image_reference:
            return oa.OciBasicAuthCredentials(
                    username='_json_key',
                    password=gcr_key,
                )
        else:
            return None

    # setup credentials:
    user_name = os.getenv('USER_NAME')
    passwd = os.getenv('PASSWD')
    gcr_key_file = Path('local/gcr-key.json')
    gcr_key = None
    if gcr_key_file.exists():
        print('adding GCR key file')
        with open(gcr_key_file) as f:
            gcr_key = f.read()

    # create and upload image:
    return oc.Client(
        credentials_lookup=_credentials_lookup,
        routes=oc.OciRoutes(oc.base_api_url),
    )

def main():
    client = get_oci_client()
    image_ref = 'eu.gcr.io/sap-cp-k8s-ocm-gcp-eu30-dev/dev/d058463/images/hello-arm64:0.1.0'
    # image_ref = 'TDT7W57RPY.fritz.box:4430/hello-amd64:0.1.0'
    # upload_image(client, image_ref, style=oci_image.OciImageCreator.Style.DOCKER_STYLE)

    image_ref = 'eu.gcr.io/sap-cp-k8s-ocm-gcp-eu30-dev/dev/d058463/images/hello-multi:0.1.0'
    upload_multi_arch_image(client, image_ref, style=oci_image.OciImageCreator.Style.OCI_STYLE)

    # tags = client.tags(image_ref)
    # print(f'{tags=}')
    # res = client.delete_manifest(image_ref, purge=True)
    # print(res.status_code)
    # res.raise_for_status()

if __name__ == '__main__':
    main()