from setuptools import Command
from datetime import datetime
from pathlib import Path
from shutil import copy


class Copier(Command):
    """A custom command to copy required files to a Pico"""

    description = 'File Copier Blah'
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        project_root = Path(__file__).parent.resolve()
        circuit_py = Path('/media/edwin/CIRCUITPY')  # TODO: Could make this dynamic
        circuit_py = Path('/tmp/foo')  # TODO: Could make this dynamic
        package_on_pico = circuit_py / 'sensing'
        current_time_stamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        backup_root_dir = Path('/tmp/sensing_backups')
        backup_root_dir.mkdir(exist_ok=True)
        backup_dir = backup_root_dir / current_time_stamp
        backup_dir.mkdir()
        copy_operations = [
            ('code.py', 'code.py', False),
            ('sensing.py', 'sensing.py', True),
            ('settings.toml', 'settings.toml', False),
        ]
        if not package_on_pico.exists():
            package_on_pico.mkdir()
            init_file = package_on_pico / '__init__.py'
            init_file.touch()
        for copy_operation in copy_operations:
            file_name = copy_operation[0]
            new_file_name = copy_operation[1]
            in_sensing_dir = copy_operation[2]
            print(f"Processing file: {file_name}")
            tentative_version_on_pico = circuit_py / file_name
            if in_sensing_dir:
                tentative_version_on_pico = circuit_py / 'sensing' / file_name
            if tentative_version_on_pico.exists():
                copy(tentative_version_on_pico, backup_dir)
                print(f"Files backed up from {tentative_version_on_pico} to {backup_dir}")
                tentative_version_on_pico.unlink()
            else:
                print("File does not exist on Pico, not backing up")
            project_version = project_root / file_name
            if in_sensing_dir:
                copy(project_version, package_on_pico / new_file_name)
            else:
                copy(project_version, circuit_py / new_file_name)
            print(f"File copied to Pico from {project_version} to {circuit_py}:")
