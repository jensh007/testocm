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

class OciImageCreator:
    """
    Test helper class to create and upload OCI images for testing.
    This class expects and input dir and creates an OCI image layer for it
    (create_and_upload_image_config). This step can be repeated multiple times for each needed layer.
    In the last step the image configuration file is created and uploaded
    (create_and_upload_image_config).
    Finally the image manifest will be created for the given image reference
    (create_and_upload_manifest).
    The out_dir will be recursively deleted on init and will contain the created image config file
    and the manifest after manifest uploaded (for debugging purposes)
    """


    def __init__(self, client: oc.Client, image_ref: str, out_dir: str | Path):
        self.client = client
        self.image_ref = image_ref
        self.out_dir = Path(out_dir)
        self.config_ref = None
        self.layer_digests = []
        self.blob_refs = []
        self.layers = 0
        util.prepare_or_clean_dir(self.out_dir)


    def _create_tar_and_digest_from_dir(self, dir: Path, tar_file: str | Path) -> tuple[str, int]:
        temp_file = Path(tar_file).with_suffix('.tar')
        with tarfile.open(temp_file, 'w') as tar:
            for child in dir.iterdir():
                tar.add(child, arcname=dir.name + '/' + child.name)

        # create hash (we need uncompressed hash)
        with open(temp_file, 'rb') as f:
            digest = hashlib.file_digest(f, 'sha256')

        uncompressed_digest = digest.hexdigest()
        # uncompressed_size = temp_file.stat().st_size

        with open(temp_file, 'rb') as f_in:
            with gzip.open(tar_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        temp_file.unlink()

        return 'sha256:' + uncompressed_digest


    def _get_manifest_dict(self, architecture: str, os: str, entrypoint: str, layer_digests: list[str]) -> dict[str, str]:
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

    def _upload_blob_from_file(
        self,
        file_name: Path | str,
        mimeType: str,
    ) -> om.OciBlobRef:

        man_size = file_name.stat().st_size
        with open(file_name, 'rb') as f:
            digest = hashlib.file_digest(f, 'sha256')
        hex_digest = 'sha256:' + digest.hexdigest()

        # upload to OCI registry
        with open(file_name, 'rb') as data_input:
            self.client.put_blob(
                image_reference=self.image_ref,
                digest=hex_digest,
                mimetype=mimeType,
                data=data_input,
                octets_count=man_size,
                max_chunk=4096,
            )
        return om.OciBlobRef(
            mediaType = mimeType,
            digest = hex_digest,
            size = man_size,
        )


    def create_and_upload_image_config(
        self,
        architecture: str,
        os: str,
        entrypoint: str,
        layer_digests: list[str],
    ) -> om.OciBlobRef:
        manifest = self._get_manifest_dict(
            architecture=architecture,
            os=os,
            entrypoint=entrypoint,
            layer_digests=layer_digests
        )

        file_name = self.out_dir / 'config.json'
        with open(file_name, 'w') as f:
            f.write(json.dumps(manifest))

        self.config_ref = self._upload_blob_from_file(
            file_name=file_name,
            mimeType='application/vnd.docker.container.image.v1+json'
        )

        return self.config_ref


    def create_and_upload_layer_from_dir(
        self,
        dir: Path,
    ) -> tuple[om.OciBlobRef, str]:
        """
        create an image layer from a local directory and upload it as tgz blob, return the
        uncompressed sha256- hash
        """
        tar_file_name = self.out_dir / 'layer.tgz'
        uncompressed_digest = self._create_tar_and_digest_from_dir(dir, tar_file_name)
        print(f'File {tar_file_name} written')
        blob_ref = self._upload_blob_from_file(
            file_name=tar_file_name,
            mimeType='application/vnd.docker.image.rootfs.diff.tar.gzip'
        )

        self.blob_refs.append(blob_ref)
        self.layer_digests.append(uncompressed_digest)
        tar_file_name.unlink()
        return (blob_ref, uncompressed_digest)


    def create_and_upload_manifest(
        self,
        mimeType: str,
    ):
        manifest = om.OciImageManifest(
            config = self.config_ref,
            layers = self.blob_refs,
            mediaType = mimeType,
        )
        manifest_str = json.dumps(manifest.as_dict())

        file_name = self.out_dir / 'manifest.json'

        with open(file_name, 'w') as f:
            f.write(manifest_str)

        response = self.client.put_manifest(
            image_reference=self.image_ref,
            manifest=manifest_str.encode('utf-8'),
        )

        return response
