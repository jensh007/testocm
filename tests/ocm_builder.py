from pathlib import Path
import shutil

import ocmcli as ocm

class OcmBuilder:
    def __init__(self,  test_name: str, root_dir: Path):
        self.test_name = test_name
        self.root_dir = root_dir
        self.gen_dir = self.root_dir / 'gen'
        self.testdata_dir = self.root_dir / 'test-data'
        self.test_dir = self.gen_dir / test_name

        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir(parents=True)

    def create_ctf_from_resources_sources_references(
        self,
        comp_name: str,
        comp_vers: str,
        provider: str,
        resources_yaml: str,
        sources_yaml: str = None,
        references_yaml: str = None,
    ) -> ocm.OcmApplication:
        sources_file = None
        references_file = None
        resource_file = self.test_dir / 'resources.yaml'

        with open(resource_file, 'w') as f:
            f.write(resources_yaml)

        if sources_yaml:
            sources_file = self.test_dir / 'sources.yaml'
            with open(sources_file, 'w') as f:
                f.write(sources_yaml)

        if references_yaml:
            references_file = self.test_dir / 'references.yaml'
            with open(references_file, 'w') as f:
                f.write(references_yaml)

        cli = ocm.OcmApplication(
            name=comp_name,
            gen_dir=self.test_dir
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
        self,
        components_yaml: str,
    ) -> ocm.OcmApplication:
        comp_file = self.test_dir / 'component.yaml'
        with open(comp_file, 'w') as f:
            f.write(components_yaml)

        cli = ocm.OcmApplication(
            name=self.test_name,
            gen_dir=self.test_dir
        )
        cli.create_ctf_from_spec(str(comp_file), None)
        return cli