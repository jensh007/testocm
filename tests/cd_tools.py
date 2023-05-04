# Module with helper classes for component-descriptors

from dataclasses import dataclass
import io
import json
import tarfile

import dacite

import gci.componentmodel as cm
import gci.oci
import oci.auth as oa
import oci.client as oc


@dataclass(frozen=True)
class ComponentVersion:
    name: str
    version: str

    @staticmethod
    def from_component_descriptor(cd: cm.ComponentDescriptor):
        return ComponentVersion(name=cd.component.name, version=cd.component.version)


class OciFetcher:

    def __init__(self, repo_url: str, user_name: str = None, password: str = None):
        self.repo_url = repo_url
        self.user_name = user_name
        self.password = password

        self.ctx_repo = cm.OciRepositoryContext(baseUrl=repo_url)

        routes = oc.OciRoutes(self._base_api_lookup)
        self.client = oc.Client(
            credentials_lookup=self._credentials_lookup,
            routes=routes,
        )


    def get_component_descriptor_from_registry(
        self,
        component_name: str,
        component_version: str,
        as_yaml: bool = False,
    ) -> cm.ComponentDescriptor | str:

        component_name = self._normalise_component_name(component_name)
        cd_url = '/'.join([
            self.ctx_repo.baseUrl,
            'component-descriptors',
            f'{component_name}:{component_version}',
        ])
        print(f'Retrieving component-descriptor from {cd_url}')

        manifest = self.client.manifest(
            image_reference=cd_url,
            absent_ok=False,
        )

        # Note original code catches exception and has some fallback
        cfg_dict = json.loads(
            self.client.blob(
                image_reference=cd_url,
                digest=manifest.config.digest,
            ).text
        )
        cfg = dacite.from_dict(
            data_class=gci.oci.ComponentDescriptorOciCfg,
            data=cfg_dict,
        )
        layer_digest = cfg.componentDescriptorLayer.digest
        layer_mimetype = cfg.componentDescriptorLayer.mediaType

        if not layer_mimetype in gci.oci.component_descriptor_mimetypes:
            print(f'Warning: Unexpected {layer_mimetype} MIME-type, expected one of '
                f'{gci.oci.component_descriptor_mimetypes}')

        blob_res = self.client.blob(
            image_reference=cd_url,
            digest=layer_digest,
            stream=False, # manifests are typically small - do not bother w/ streaming
        )
        # wrap in fobj
        blob_fobj = io.BytesIO(blob_res.content)
        if as_yaml:
            with tarfile.open(fileobj=blob_fobj, mode='r') as tf:
                component_descriptor_info = tf.getmember(gci.oci.component_descriptor_fname)
                component_descriptor = tf.extractfile(component_descriptor_info).read()
                component_descriptor = component_descriptor.decode()
        else:
            component_descriptor = gci.oci.component_descriptor_from_tarfileobj(
                fileobj=blob_fobj,
            )
        return component_descriptor


    def get_component_descriptors_from_registry(
        self,
        component_name: str,
        component_version: str,
    ) -> dict[ComponentVersion, cm.ComponentDescriptor]:
        components = {}
        cd = self.get_component_descriptor_from_registry(
            component_name,
            component_version,
        )
        cv = ComponentVersion.from_component_descriptor(cd)
        components[cv] = cd
        for ref in cd.component.componentReferences:
            ref_cv = ComponentVersion(name=ref.componentName, version=ref.version)
            if not ref_cv in components:
                recursive_references = self.get_component_descriptors_from_registry(
                    component_name=ref_cv.name,
                    component_version=ref_cv.version,
                )
                components |= recursive_references # merge result dict
        return components


    def exists(self, image_reference: str) -> bool:
        blob_ref = self.client.head_manifest(image_reference, absent_ok = True)
        return blob_ref is not None


    @staticmethod
    def _base_api_lookup(image_reference):
        return oc.base_api_url(image_reference)


    @staticmethod
    def _normalise_component_name(component_name:str) -> str:
        return component_name.lower()  # oci-spec allows only lowercase


    def _credentials_lookup(
        self,
        image_reference: str,
        privileges: oa.Privileges=oa.Privileges.READONLY,
        absent_ok: bool=True,
    ):
        if self.password and self.user_name:
            return oa.OciBasicAuthCredentials(
                    username=self.user_name,
                    password=self.password,
                )
        else:
            return None
