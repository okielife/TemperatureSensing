from datetime import datetime
from pathlib import Path
from shutil import copy
from sys import argv


def run(circuit_py: Path):
    project_root = Path(__file__).parent.resolve()
    backup_root_dir = Path('/tmp/sensing_backups')
    backup_root_dir.mkdir(exist_ok=True)
    backup_dir = backup_root_dir / datetime.now().strftime("%Y-%m-%d-%H-%M-%S.%f")
    backup_dir.mkdir()
    for file_name in ['main.py', 'sensing.py', 'settings.toml']:
        print(f"Processing file: {file_name}")
        tentative_version_on_pico = circuit_py / file_name
        if tentative_version_on_pico.exists():
            copy(tentative_version_on_pico, backup_dir)
            print(f"Files backed up from {tentative_version_on_pico} to {backup_dir}")
            tentative_version_on_pico.unlink()
        else:
            print("File does not exist on Pico, not backing up")
        project_version = project_root / file_name
        copy(project_version, circuit_py / file_name)
        print(f"File copied to Pico from {project_version} to {circuit_py}:")


if __name__ == "__main__":  # pragma: no cover
    if len(argv) > 1:
        target_dir = Path(argv[1])
    else:
        target_dir = Path('/media/edwin/CIRCUITPY')
    run(target_dir)
