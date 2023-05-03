#! /usr/bin/env python3
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Final

def error_exit(error_msg: str):
    print(f'Error: {error_msg}')
    sys.exit(1)


def get_root_dir() -> Path:
    path = Path(__file__)
    return path.parent.absolute()


def execute_ocm(args: str, **kwargs):
    cmd = ['ocm']
    # to preserve quoted strings: re.findall(r'(\w+|".*?")', args)
    cmd.extend(args.split(' '))
    print(f'Running: {cmd}')
    subprocess.run(cmd, check=True, **kwargs)


def get_version():
    version_file = get_root_dir() / 'VERSION'
    with open(version_file) as f:
        content = f.readlines()
    for line in content:
        if not line.lstrip().startswith('#'):
            line = line.strip()
            return line
    error_exit(f'no version number found in: {version_file}')


def get_latest_git_commit():
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, check=True, text=True)
    commit = result.stdout.strip()
    print(f'Found commit in git: {commit}')
    return commit

def get_dummy_commit():
    return "dummydummydummydummydummydummydummydummy"

def _tag_compatible_arch(arch: str) -> str:
    return arch.replace('/', '-')


@dataclass
class ComponentVersionSpec:
    name: str
    version: str
    provider: str
    source_file: str | Path | None = None
    resource_file: str | Path | None = None
    reference_file: str | Path | None = None


class OcmApplication:
    def __init__(
        self,
        name: str,
        build_settings: dict[str, any]={},
        gen_dir: str = None,
        ocm_repo: str = None,
    ):
        self.name = name
        self.build_settings = build_settings
        self.gen_dir = Path(gen_dir) if gen_dir else self._generate_gen_dir()
        self.gen_ctf_dir = Path(self.gen_dir) / 'ctf'
        self.gen_ca_dir= Path(self.gen_dir) / 'ca'
        self.ocm_repo = ocm_repo
        print(f'Generating in {self.gen_dir}')

    ARCHITECTURES: Final[str] = 'architectures'
    VERSION: Final[str] = 'version'
    COMMIT: Final[str] = 'commit'

    def get_setting(self, param: str) -> any:
        if param in self.build_settings:
            return self.build_settings[param]

    def get_version(self) -> str | None:
        return self.get_setting(self.VERSION)

    def get_architectures(self) -> list[str] | None:
        return self.get_setting(self.ARCHITECTURES)

    def get_commit(self) -> str | None:
        return self.get_setting(self.COMMIT)

    def _generate_gen_dir(self, gen_name: str= 'gen'):
        return get_root_dir() / gen_name / self.name

    def makedirs(self):
        os.makedirs(self.gen_dir, exist_ok=True)

    def download_helm_charts(self, settings_file: str):
        pass

    def get_component_version_spec_template(self) -> ComponentVersionSpec:
        return ComponentVersionSpec(self.name, self.get_version(), None)

    def create_ctf_from_component_version(
        self,
        comp_vers: ComponentVersionSpec,
    ):
        if self.gen_ca_dir.exists():
            shutil.rmtree(self.gen_ca_dir)
        self.makedirs()
        print(f'Generating transport archive in {self.gen_ca_dir}')
        self.gen_ca_dir.mkdir()

        cmd_line = f'create componentarchive -f {comp_vers.name} {comp_vers.version} --provider {comp_vers.provider} --file {self.gen_ca_dir}'
        execute_ocm(cmd_line)
        if comp_vers.source_file:
            cmd_line = f'add sources {str(self.gen_ca_dir)} {comp_vers.source_file}'
            execute_ocm(cmd_line)
        if comp_vers.resource_file:
            cmd_line = f'add resources {str(self.gen_ca_dir)} {comp_vers.resource_file}'
            execute_ocm(cmd_line)
        if comp_vers.reference_file:
            cmd_line = f'add references {str(self.gen_ca_dir)} {comp_vers.reference_file}'
            execute_ocm(cmd_line)

        cmd_line = f'transfer componentarchive {str(self.gen_ca_dir)} {str(self.gen_ctf_dir)}'
        execute_ocm(cmd_line)

    def create_ctf_from_spec(
        self,
        components_file_name: str = 'components.yaml',
        settings_files: str | list[str]='settings.yaml'
    ):
        print(f'Generating transport archive in {self.gen_ctf_dir}')
        if not self.gen_ctf_dir:
            error_exit('This command requires setting a ctf directory')
        self.makedirs()

        self.download_helm_charts(settings_files)

        cmd_line = f'ocm add componentversions --create --file {str(self.gen_ctf_dir)}'
        if type(settings_files) is str:
            cmd_line.extend(['--settings', settings_files])
        else:
            for s in settings_files:
                cmd_line.extend(['--settings', s])
        cmd_line.append(components_file_name)
        print(f'Calling ocm: {" ".join(cmd_line)}')
        subprocess.run(cmd_line, check=True)

    def clean(self):
        if self.gen_dir.exists():
            print(f'Deleting gen dir: {self.gen_dir}')
            shutil.rmtree(self.gen_dir)

    def descriptor(self, format_version: str = 'v3alpha1'):
        if self.gen_ctf_dir.exists():
            cmd_line = f'get component -S {format_version} -o yaml {self.gen_ctf_dir}'
            execute_ocm(cmd_line)
        else:
            print('Cannot display component-descriptor, not yet build')

    def build_docker(
        self,
        dockerfile_path: str = 'Dockerfile',
        ctx_dir: str = '.'):

        for arch in self.get_architectures():
            version = self.get_version()
            arch_tag = _tag_compatible_arch(arch)
            tag = f'{self.name}:{version}-{arch_tag}'
            cmd_line = ['docker', 'buildx', 'build', '--load', '-t', tag, '--platform', arch,
                '--file', dockerfile_path, ctx_dir]
            print(f'Building: {" ".join(cmd_line)}')
            subprocess.run(cmd_line, check=True)

    def push(self, force: bool):
        if self.gen_ctf_dir.exists():
            if force:
                execute_ocm(f'-X keeplocalblob=true transfer ctf -f {str(self.gen_ctf_dir)} {self.ocm_repo}')
            else:
                execute_ocm(f'-X keeplocalblob=true transfer ctf {str(self.gen_ctf_dir)} {self.ocm_repo}')
        else:
            error_exit('No transport archive found, must be build first')

    def pack(self, force: bool):
        target_dir = self.gen_dir / 'ctf-full'
        if self.gen_ctf_dir.exists():
            if force:
                # execute_ocm(f'transfer ctf --copy-resources -f {str(self.gen_ctf_dir)} {str(target_dir)}')
                execute_ocm(f'transfer ctf -f {str(self.gen_ctf_dir)} {str(target_dir)}')
            else:
                # execute_ocm(f'transfer ctf --copy-resources {str(self.gen_ctf_dir)} {str(target_dir)}')
                execute_ocm(f'transfer ctf {str(self.gen_ctf_dir)} {str(target_dir)}')
            old_dir = self.gen_dir / 'ctf-old'
            if old_dir.exists():
                shutil.rmtree(old_dir)
            self.gen_ctf_dir.rename(old_dir)
            self.gen_ctf_dir = target_dir.rename(self.gen_ctf_dir)
            shutil.rmtree(old_dir)
        else:
            error_exit('No transport archive found, must be build first')