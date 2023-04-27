import datetime
from enum import Enum, auto
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import sys

import oci.auth as oa
import oci.model as om
import oci.client as oc
import gci.componentmodel as cm
import requests

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

    IMAGE_CONFIG_MIME_TYPE_DOCKER = 'application/vnd.docker.container.image.v1+json'
    IMAGE_LAYER_MIME_TYPE_DOCKER = 'application/vnd.docker.image.rootfs.diff.tar.gzip'
    MANIFEST_MIME_TYPE_DOCKER = 'application/vnd.docker.distribution.manifest.v2+json'
    MULTI_ARCH_MANIFEST_MIME_TYPE_DOCKER = 'application/vnd.docker.distribution.manifest.list.v2+json'
    IMAGE_CONFIG_MIME_TYPE_OCI ='application/vnd.oci.image.config.v1+json'
    IMAGE_LAYER_MIME_TYPE_OCI = 'application/vnd.oci.image.layer.v1.tar+gzip'
    MANIFEST_MIME_TYPE_OCI = 'application/vnd.oci.image.manifest.v1+json'
    MULTI_ARCH_MANIFEST_MIME_TYPE_OCI = 'application/vnd.oci.image.index.v1+json'


    class Style(Enum):
        DOCKER_STYLE = auto(),
        OCI_STYLE = auto()


    def __init__(
        self, client: oc.Client,
        image_ref: str,
        out_dir: str | Path,
        style: Style = Style.DOCKER_STYLE
    ):
        self.client = client
        self.image_ref = image_ref
        self.out_dir = Path(out_dir)
        self.config_ref = None
        self.layer_digests = []
        self.blob_refs = []
        self.multi_arch_entries = []
        self.set_mime_types(style)
        util.prepare_or_clean_dir(self.out_dir)


    def set_mime_types(
        self,
        style: Style,
    ):
        # see: https://github.com/opencontainers/image-spec/blob/main/media-types.md
        if style == self.Style.DOCKER_STYLE:
            self.image_config_mime_type = self.IMAGE_CONFIG_MIME_TYPE_DOCKER
            self.image_layer_mime_type = self.IMAGE_LAYER_MIME_TYPE_DOCKER
            self.manifest_mime_type = self.MANIFEST_MIME_TYPE_DOCKER
            self.multi_arch_manifest_mime_type = self.MULTI_ARCH_MANIFEST_MIME_TYPE_DOCKER
        elif style == self.Style.OCI_STYLE:
            self.image_config_mime_type = self.IMAGE_CONFIG_MIME_TYPE_OCI
            self.image_layer_mime_type = self.IMAGE_LAYER_MIME_TYPE_OCI
            self.manifest_mime_type = self.MANIFEST_MIME_TYPE_OCI
            self.multi_arch_manifest_mime_type = self.MULTI_ARCH_MANIFEST_MIME_TYPE_OCI
        else:
            raise ValueError(f'Unknown Oci Image style {style}')

    def _create_tar_and_digest_from_dir(self, dir: Path, tar_file: str | Path) -> tuple[str, int]:
        temp_file = Path(tar_file).with_suffix('.tar')
        with tarfile.open(temp_file, 'w') as tar:
            for child in dir.iterdir():
                tar.add(child, arcname=dir.name + '/' + child.name)

        # create hash (we need uncompressed hash)
        uncompressed_digest = self.file_digest(temp_file)

        with open(temp_file, 'rb') as f_in:
            with gzip.open(tar_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        temp_file.unlink()

        return uncompressed_digest

    def file_digest(self, temp_file) -> str:
        py_version = sys.version_info
        if py_version.major >= 3 and py_version.minor >= 11:
            with open(temp_file, 'rb') as f:
                digest = hashlib.file_digest(f, 'sha256')
            hex_digest = digest.hexdigest()
        else:
            BUF_SIZE = 65536
            sha256 = hashlib.sha256()
            with open(temp_file, 'rb') as f:
                while True:
                    data = f.read(BUF_SIZE)
                    if not data:
                        break
                    sha256.update(data)
            hex_digest = sha256.hexdigest()

        return 'sha256:' + hex_digest

    def bytes_digest(self, data: bytes) -> str:
        sha256 = hashlib.sha256()
        sha256.update(data)
        hex_digest = sha256.hexdigest()
        return 'sha256:' + hex_digest

    def _get_manifest_dict(self, architecture: str, os: str, entrypoint: str) -> dict[str, str]:
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
                'diff_ids': self.layer_digests,
            }
        }

        return manifest

    def _upload_blob_from_file(
        self,
        file_name: Path | str,
        mimeType: str,
    ) -> om.OciBlobRef:

        man_size = file_name.stat().st_size
        hex_digest = self.file_digest(file_name)

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

    def _upload_blob_from_string(
        self,
        data: str,
        mimeType: str,
    ) -> om.OciBlobRef:
        return self._upload_blob_from_bytes(data.encode('utf-8'), mimeType)

    def _upload_blob_from_bytes(
        self,
        data: bytes,
        mimeType: str,
    ) -> om.OciBlobRef:
        size = len(data)
        hex_digest = self.bytes_digest(data)

        # upload to OCI registry
        self.client.put_blob(
            image_reference=self.image_ref,
            digest=hex_digest,
            mimetype=mimeType,
            data=data,
            octets_count=size,
        )

        return om.OciBlobRef(
            mediaType = mimeType,
            digest = hex_digest,
            size = size,
        )


    def create_and_upload_image_config(
        self,
        architecture: str,
        os: str,
        entrypoint: str,
    ) -> om.OciBlobRef:
        manifest = self._get_manifest_dict(
            architecture=architecture,
            os=os,
            entrypoint=entrypoint,
        )

        file_name = self.out_dir / 'config.json'
        with open(file_name, 'w') as f:
            f.write(json.dumps(manifest))

        self.config_ref = self._upload_blob_from_file(
            file_name=file_name,
            mimeType=self.image_config_mime_type
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
            mimeType=self.image_layer_mime_type
        )

        self.blob_refs.append(blob_ref)
        self.layer_digests.append(uncompressed_digest)
        tar_file_name.unlink()
        return (blob_ref, uncompressed_digest)


    def create_and_upload_manifest(
        self,
    ) -> tuple[requests.Response, om.OciImageManifest]:
        manifest = om.OciImageManifest(
            config = self.config_ref,
            layers = self.blob_refs,
            mediaType = self.manifest_mime_type,
        )
        manifest_str = json.dumps(manifest.as_dict())

        file_name = self.out_dir / 'manifest.json'

        with open(file_name, 'w') as f:
            f.write(manifest_str)

        response = self.client.put_manifest(
            image_reference=self.image_ref,
            manifest=manifest_str.encode('utf-8'),
        )

        return response, manifest

    def upload_architecture(self, platform: om.OciPlatform):
        # safe current child manifest as blob:
        _, manifest = self.create_and_upload_manifest()

        manifest_bytes = json.dumps(manifest.as_dict()).encode('utf-8')
        size = len(manifest_bytes)
        hex_digest = self.bytes_digest(manifest_bytes)

        self.create_and_upload_manifest()

        # save next list entry for multi_arch:
        entry = om.OciImageManifestListEntry(
            digest=hex_digest,
            mediaType=manifest.mediaType,
            size=size,
            platform=platform,
        )
        print(f'Uploaded multi-arch child manifest: {platform.architecture}: {hex_digest}')
        self.multi_arch_entries.append(entry)
        self.config_ref = None
        self.layer_digests = []
        self.blob_refs = []

        util.prepare_or_clean_dir(self.out_dir)

    def create_and_upload_multiarch_manifest(self):
        manifest = om.OciImageManifestList(
            manifests=self.multi_arch_entries,
            mediaType=self.multi_arch_manifest_mime_type
        )
        manifest_list_as_json = json.dumps(manifest.as_dict())
        response = self.client.put_manifest(
            image_reference=self.image_ref,
            manifest=manifest_list_as_json.encode('utf-8'),
        )
        return response

