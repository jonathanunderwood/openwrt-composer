import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

import click
import click_log
from ruamel.yaml import YAML

from . import podman

logger = logging.getLogger(__name__)
click_log.basic_config()


def load_yaml_file(filename: str) -> dict:
    """Parse a YAML file and return a dictionary of contents

    Args:
        filename: Name of file to parse.

    Returns:
        A dictionary representing the YAML file.

    Raises:
        IOError: Raised if an I/O error occurs when reading the file.

    """

    yaml = YAML(typ="safe")

    try:
        with open(filename) as fp:
            d = yaml.load(fp)
    except IOError as exc:
        logger.excception(
            "I/O error({0}) loading {1}: {2}".format(exc.errno, filename, exc.strerror)
        )
        raise exc

    return d


def create_files(files: List[Dict[str, str]], files_dir: Path) -> None:
    """Write files to disk for firmware building

    Args:
        files: A list of dictionaries. Each list item must have a ``path`` key and
            a ``contents`` key. The ``path`` key defines where in the firmware
            image the file should be placed. The ``contents`` key specifies the
            contents of the file.

    Returns:
        The Path to the directory containing the files.

    Raises:
        KeyError: Raised if a files dict is missing a key.
        IOError: Raised if an error occurs creating a file.

    """

    for file in files:
        try:
            path = files_dir / Path(file["path"]).relative_to("/")
            contents = file["contents"]
        except KeyError as exc:
            logger.exception(f"Missing key for file: {exc.args[0]}.")
            raise

        path.parents[0].mkdir(parents=True, exist_ok=True)

        logger.debug(f"Writing file: {path}")
        logger.debug("Contents:")
        logger.debug(contents)

        try:
            with open(path, mode="w") as fp:
                fp.write(contents)
        except IOError:
            logger.exception(f"Failed to write to file: {path.absolute()}.")
            raise


def create_package_list(packages: Dict[str, List]) -> str:
    """Create packages list suitable for building firmware image

    Args:
        packages: A dictionary with two keys: ``add`` and ``remove``. The value of
            both is a list of package names as strings.

    Returns:
        A string with all package names from the ``add`` list, and all packages
            from the ``remove`` list prefixed with a "``-``". This string is
            suitable for passing to the ``make PACKAGES=<str>`` invocation when
            building a firmware image with the OpenWRT firmware builder.

    """
    packages_add: List[str] = packages.get("add", [])
    packages_remove: List[str] = packages.get("remove", [])
    packages: List[str] = packages_add + ["-{0}".format(pkg) for pkg in packages_remove]

    return " ".join(packages)


@click.command()
@click_log.simple_verbosity_option(logger)
@click.argument("config_file")
@click.argument("manifest_file")
def build(config_file: str, manifest_file: str) -> None:
    """Build firmware images for a given manifest"""

    config: dict = load_yaml_file(config_file)
    manifest: dict = load_yaml_file(manifest_file)

    work_dir = config.get("work_dir", os.path.join(os.getcwd(), "openwrt-composer"))
    work_dir = Path(work_dir)

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.exception(f"Failed to create work directory: {work_dir.absolute()}")
        sys.exit(exc.errno)

    try:
        version = manifest["version"]
    except KeyError as exc:
        logger.exception("Missing value in manifest: release")
        sys.exit(exc.errno)

    try:
        packages = create_package_list(manifest["packages"])
    except KeyError:
        packages = []

    # Create a build directory for each firmware run
    logger.info(f"Creating build directory.")
    try:
        build_dir = tempfile.mkdtemp(prefix="build-", dir=work_dir)
    except IOError as exc:
        logger.exception("Failed to create build directory.")
        sys.exit(exc.errno)
    else:
        logger.info(f"Created build directory: {Path(build_dir).absolute()}.")

    build_dir = Path(build_dir)

    # Set up files and output directories under the build directory
    files_dir: Path = build_dir / "files"
    output_dir: Path = build_dir / "firmware"

    for directory in [files_dir, output_dir]:
        try:
            directory.mkdir()
        except IOError as exc:
            logger.exception(f"Failed to create directory {directory.absolute()}.")
            sys.exit(exc.errno)
        else:
            logger.info(f"Created directory: {directory.absolute()}.")

    # Create files for inclusion in firmware
    files = manifest.get("files", [])

    try:
        create_files(files, files_dir)
    except (IOError, KeyError) as exc:
        logger.exception("Failed to create files for firmware.")
        files_dir.rmdir()
        output_dir.rmdir()
        sys.exit(exc.errno)

    # Build firmwares
    openwrt_base_url = config.get("openwrt_base_url", "https://downloads.openwrt.org/")

    for target_dict in manifest["targets"]:
        target = target_dict["target"]
        sub_target = target_dict["sub_target"]
        profile = target_dict["profile"]
        logger.info("Building firmware:")
        logger.info(f"    Target: {target}.")
        logger.info(f"    Sub-target: {sub_target}.")
        logger.info(f"    Profile: {profile}.")

        builder = podman.PodmanBuilder(
            version=version,
            target=target,
            sub_target=sub_target,
            profile=profile,
            work_dir=work_dir,
            openwrt_base_url=openwrt_base_url,
        )

        builder.build_firmware(packages, output_dir, files_dir)
        logger.info(f"Firmware written to: {output_dir.absolute()}.")


if __name__ == "__main__":
    build()
