import io
import sys
import tarfile
import zipfile
from pathlib import Path


def iter_asset_files(app_dir: Path):
    main_path = app_dir / "main.py"
    if not main_path.is_file():
        raise FileNotFoundError(f"Missing entry point: {main_path}")

    yield main_path, Path("assets/main.py")

    audio_dir = app_dir / "audio"
    if audio_dir.is_dir():
        for asset_path in sorted(audio_dir.rglob("*")):
            if asset_path.is_file():
                yield asset_path, Path("assets/audio") / asset_path.relative_to(audio_dir)


def write_apk(app_dir: Path, output_path: Path):
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_path, archive_path in iter_asset_files(app_dir):
            archive.write(source_path, archive_path.as_posix())


def write_targz(app_dir: Path, output_path: Path):
    with tarfile.open(output_path, "w:gz") as archive:
        for source_path, archive_path in iter_asset_files(app_dir):
            archive.add(source_path, arcname=archive_path.as_posix())


def main(argv):
    if len(argv) != 3:
        raise SystemExit("Usage: repack-flight-game-v3.py <app_dir> <build_web_dir>")

    app_dir = Path(argv[1]).resolve()
    build_web_dir = Path(argv[2]).resolve()
    build_web_dir.mkdir(parents=True, exist_ok=True)

    write_apk(app_dir, build_web_dir / "flight-game-v3.apk")
    write_targz(app_dir, build_web_dir / "flight-game-v3.tar.gz")

    print(f"Repacked web archives from {app_dir} into {build_web_dir}")


if __name__ == "__main__":
    main(sys.argv)