import distutils.cmd
from datetime import datetime
from pathlib import Path
from shutil import copy


class Copier(distutils.cmd.Command):
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
        current_time_stamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        backup_root_dir = Path('/tmp/sensing_backups')
        backup_root_dir.mkdir(exist_ok=True)
        backup_dir = backup_root_dir / current_time_stamp
        backup_dir.mkdir()

        file_names_to_copy = ['code.py', 'sensing.py', 'settings.toml']
        backed_up_files = []
        copied_files = []
        for file_name in file_names_to_copy:
            tentative_version_on_pico = circuit_py / file_name
            if tentative_version_on_pico.exists():
                copy(tentative_version_on_pico, backup_dir)
                backed_up_files.append(file_name)
            tentative_version_on_pico.unlink()
            project_version = project_root / file_name
            copy(project_version, circuit_py)
            copied_files.append(file_name)

        if backed_up_files:
            print(f"Files backed up from {circuit_py} to {backup_dir}:")
            for b in backed_up_files:
                print(f"\t{b}")
        else:
            print(f"No files were found/backed up from {circuit_py}")

        print("Files copied to pico:")
        for c in copied_files:
            print(f"\t{c}")
