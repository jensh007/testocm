from dataclasses import dataclass
import io
import json
import logging
from pathlib import Path
import tarfile
import textwrap

import gci.componentmodel as cm
import ocmcli as ocm
import util
import yaml

@dataclass
class TestData:
    __test__ = False
    comp_vers = '1.0.0'
    provider = 'ocm.integrationtest'
    image_name = 'echo'
    comp_name = f'{provider}/{image_name}'
    label_key = 'mylabel'
    label_value = 'Hello Label'
    echo_image_reference = 'gcr.io/google_containers/echoserver:1.10'
    pause_image_reference = 'gcr.io/google_containers/pause:3.2'

    repo_url = 'github.com/open-component-model/ocm'
    commit_id = 'e39625d6e919d33267da4778a1842670ce2bbf77'

    ref_comp_name = f'{provider}/helper'
    ref_comp_vers = '1.0.0'
    root_dir = util.get_root_dir()
    testdata_dir = root_dir / 'test-data'
    test_dir =  util.get_gen_dir()

    reference_yaml = textwrap.dedent(f'''\
    componentReferences:
      - name: childcomp
        componentName: {ref_comp_name}
        version: {ref_comp_vers}
    ''')

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
            access:
                type: ociArtifact
                imageReference: {echo_image_reference}
            labels:
            - name: {label_key}
              value: {label_value}
        sources:
          - name: source
            type: filesystem
            access:
                type: github
                repoUrl: {repo_url}
                commit: {commit_id}
            version: {comp_vers}
    ''')

    child_component_yaml = textwrap.dedent(f'''\
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
                    imageReference: {pause_image_reference}
    ''')

    def __post_init__(self):
        # create directory for generated files
        self.prepare_test_env()

    @classmethod
    def prepare_test_env(clazz):
        clazz.test_dir.mkdir(parents=True, exist_ok=True)

    def with_reference_yaml(self):
        ref = yaml.safe_load(io.BytesIO(self.reference_yaml.encode()))
        dict = yaml.safe_load(io.BytesIO(self.component_yaml.encode()))
        child = yaml.safe_load(io.BytesIO(self.child_component_yaml.encode()))
        dict['components'][0]['componentReferences'] = ref['componentReferences']
        dict['components'].insert(0, child['components'][0])
        self.component_yaml = yaml.safe_dump(dict)

    def create_child_ctf(self) -> ocm.OcmApplication:
        return create_ctf_from_component_spec(self.test_dir, self.child_component_yaml)

    def create_ctf(self) -> ocm.OcmApplication:
        return create_ctf_from_component_spec(self.test_dir, self.component_yaml)

    def find_component_descriptor(self, ctf_dir: Path) -> cm.ComponentDescriptor:
        index_file = ctf_dir / 'artifact-index.json'
        with open(index_file) as f:
            ind = json.load(f)
        digest:str = ind['artifacts'][0]['digest']
        manifest_file = ctf_dir / 'blobs' / digest.replace('sha256:', 'sha256.')
        with open(manifest_file) as f:
            oci_manifest = json.load(f)
        assert oci_manifest['mediaType'] == 'application/vnd.oci.image.manifest.v1+json'
        assert oci_manifest['layers'][0]['mediaType'] == 'application/vnd.ocm.software.component-descriptor.v2+yaml+tar'
        cd_digest = oci_manifest['layers'][0]['digest']
        cd_tar_file =  ctf_dir / 'blobs' / cd_digest.replace('sha256:', 'sha256.')
        extract_dir = ctf_dir.parent / 'extracted'
        with tarfile.open(cd_tar_file, 'r') as tar:
            name = tar.next()
            print(f'extracting file {name}')
            tar.extractall(extract_dir)
        cd_file = extract_dir / name.name
        cd_file.chmod(0o644)
        with open(cd_file) as f:
            cd_dict = yaml.safe_load(f)
        cd = cm.ComponentDescriptor.from_dict(cd_dict, cm.ValidationMode.NONE)
        return cd

    def verify_root_elems(self, cd: cm.ComponentDescriptor):
        assert cd.meta.schemaVersion == cm.SchemaVersion.V2
        assert cd.component.name == self.comp_name
        assert cd.component.version  == self.comp_vers
        assert len(cd.component.resources) == 2
        assert len(cd.component.sources) == 1

    def verify_chart(self, chart: cm.Resource):
        assert chart.name == 'chart'
        assert chart.type == cm.ArtefactType.HELM_CHART
        assert chart.relation == cm.ResourceRelation.LOCAL
        assert chart.version == '1.0.0'
        assert chart.access.type == cm.AccessType.LOCAL_BLOB
        assert type(chart.access) == cm.LocalBlobAccess
        assert chart.access.localReference.startswith('sha256:')
        assert chart.access.mediaType == 'application/vnd.oci.image.manifest.v1+tar+gzip'
        assert chart.access.referenceName == f'{self.provider}/echo/echoserver:0.1.0'

    def verify_chart_remote(self, chart: cm.Resource, image_reference: str):
        assert chart.name == 'chart'
        assert chart.type == cm.ArtefactType.HELM_CHART
        assert chart.relation == cm.ResourceRelation.LOCAL
        assert chart.version == '1.0.0'
        assert chart.access.type == cm.AccessType.OCI_REGISTRY
        assert type(chart.access) == cm.OciAccess
        assert chart.access.imageReference == image_reference

    def verify_image(self, image: cm.Resource):
        assert image.name == 'image'
        assert image.type == cm.ArtefactType.OCI_IMAGE
        assert image.version == '1.10'
        assert image.relation == cm.ResourceRelation.EXTERNAL
        assert type(image.access) == cm.OciAccess #  cm.AccessType.OCI_REGISTRY
        assert image.access.imageReference == self.echo_image_reference
        assert len(image.labels) == 1
        assert image.labels[0].name == self.label_key
        assert image.labels[0].value == self.label_value

    def verify_image_remote(self, image: cm.Resource, image_reference: str):
        assert image.name == 'image'
        assert image.type == cm.ArtefactType.OCI_IMAGE
        assert image.version == '1.10'
        assert image.relation == cm.ResourceRelation.EXTERNAL
        assert type(image.access) == cm.OciAccess
        assert image.access.type == cm.AccessType.OCI_REGISTRY
        assert image.access.imageReference == image_reference
        assert len(image.labels) == 1
        assert image.labels[0].name == self.label_key
        assert image.labels[0].value == self.label_value

    def verify_source(self, source: cm.ComponentSource):
        assert source.name == 'source'
        assert source.type == 'filesystem'
        assert source.version == self.comp_vers
        assert source.access.type == cm.AccessType.GITHUB
        assert type(source.access) == cm.GithubAccess
        assert source.access.commit == self.commit_id
        assert source.access.repoUrl == self.repo_url


    def verify_component_descriptor(self, cd: cm.ComponentDescriptor):
        self.verify_root_elems(cd)
        chart = cd.component.resources[0]
        self.verify_chart(chart)
        image = cd.component.resources[1]
        self.verify_image(image)
        assert len(cd.component.sources) == 1
        source = cd.component.sources[0]
        self.verify_source(source)


def validate_ctf_dir(ctf_dir: Path):
    blob_dir = ctf_dir / 'blobs'
    index_file = ctf_dir / 'artifact-index.json'
    assert blob_dir.exists()
    assert index_file.exists()

    count = 0
    for child in blob_dir.iterdir():
        count += 1
        assert child.name.startswith('sha256.')


def create_ctf_from_resources_sources_references(
    test_dir: str,
    comp_name: str,
    comp_vers: str,
    provider: str,
    resources_yaml: str,
    sources_yaml: str = None,
    references_yaml: str = None,
) -> ocm.OcmApplication:
    sources_file = None
    references_file = None
    resource_file = test_dir / 'resources.yaml'

    with open(resource_file, 'w') as f:
        f.write(resources_yaml)

    if sources_yaml:
        sources_file = test_dir / 'sources.yaml'
        with open(sources_file, 'w') as f:
            f.write(sources_yaml)

    if references_yaml:
        references_file = test_dir / 'references.yaml'
        with open(references_file, 'w') as f:
            f.write(references_yaml)

    cli = ocm.OcmApplication(
        name=comp_name,
        gen_dir=test_dir
    )

    cv_spec = cli.get_component_version_spec_template()
    cv_spec.name = comp_name
    cv_spec.version = comp_vers
    cv_spec.provider = provider
    cv_spec.source_file = sources_file
    cv_spec.resource_file = resource_file
    cv_spec.reference_file = references_file

    cli.create_ctf_from_component_version(cv_spec)
    return cli


def create_ctf_from_component_spec(
    test_dir: str,
    components_yaml: str,
) -> ocm.OcmApplication:
    comp_file = test_dir / 'component.yaml'
    with open(comp_file, 'w') as f:
        f.write(components_yaml)

    cli = ocm.OcmApplication(
        gen_dir=test_dir
    )
    cli.create_ctf_from_spec(str(comp_file), None)
    return cli


def build_application(app: ocm.OcmApplication):
    app.clean()
    app.makedirs()
    # dyn_settings_file = str(app.gen_dir / 'dynamic_settings.yaml')
    # write_dynamic_settings_file(app, dyn_settings_file)
    app.create_ctf_from_spec(
        components_file_name='components.yaml',
        settings_files=['static_settings.yaml'],
    )
    app.descriptor()


def get_comp_descr(app: ocm.OcmApplication):
    app.descriptor()

