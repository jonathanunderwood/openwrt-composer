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
            logger.info(f"File read: {filename}")
            logger.debug(f"Contents:")
            logger.debug(f"{d}")
    except IOError as exc:
        logger.excception(
            "I/O error({0}) loading {1}: {2}".format(exc.errno, filename, exc.strerror)
        )
        raise exc

    return d


def valid_manifest(manifest: dict):
    """Perform some sanity checks on the manifest

    Currently this checks:

    - That each (target, sub_target, profile, version, name) is unique so that firmwares
      are not overwritten.

    Args:
        manifest: A dictionary resulting from parsing the manifest file.

    Returns:
        ``True`` if the manifest is valid, ``False`` otherwise.

    Raises:
        KeyError: Raised if any firmware specified lacks ``target``, ``sub_target``,
            ``profile`` or ``version`` fields.
    """
    try:
        firmwares = [
            (
                f["target"],
                f["sub_target"],
                f["profile"],
                f["version"],
                f.get("name", None),
            )
            for f in manifest["firmwares"]
        ]
    except KeyError as exc:
        logger.exception(f"Missing field in manifest: {exc.args[0]}")
        return False

    # dupes = [f for f in set(firmwares) if firmwares.count(f) > 1]
    seen = set()
    dupes = set(f for f in firmwares if f in seen or seen.add(f))

    if len(dupes) > 0:
        logger.error(f"Duplicate firmwares specified: {dupes}")
        return False

    return True


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
    packages_list: List[str] = packages_add + [
        "-{0}".format(pkg) for pkg in packages_remove
    ]
    packages: str = " ".join(packages_list)
    logger.debug("Packages list: {packages}")

    return packages


@click.command()
@click_log.simple_verbosity_option(logger)
@click.argument("config_file")
@click.argument("manifest_file")
def build(config_file: str, manifest_file: str) -> None:
    """Build firmware images for a given manifest"""

    config: dict = load_yaml_file(config_file)
    manifest: dict = load_yaml_file(manifest_file)

    if not valid_manifest(manifest):
        logger.error("Manifest not valid. Exiting.")
        sys.exit(1)

    work_dir = config.get("work_dir", os.path.join(os.getcwd(), "openwrt-composer"))
    work_dir = Path(work_dir)

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.exception(f"Failed to create work directory: {work_dir.absolute()}")
        sys.exit(exc.errno)

    # Create a build directory for each firmware run
    try:
        build_dir = tempfile.mkdtemp(prefix="build-", dir=work_dir)
    except IOError as exc:
        logger.exception("Failed to create build directory.")
        sys.exit(exc.errno)
    else:
        logger.info(f"Created build directory: {Path(build_dir).absolute()}.")

    build_dir = Path(build_dir)

    # Build firmwares
    openwrt_base_url = config.get("openwrt_base_url", "https://downloads.openwrt.org/")

    try:
        firmwares = manifest["firmwares"]
    except KeyError as exc:
        logger.error("No firmwares specified")
        sys.excit(exc.errno)

    for fw in firmwares:
        try:
            target = fw["target"]
            sub_target = fw["sub_target"]
            profile = fw["profile"]
            version = fw["version"]
        except KeyError as exc:
            logger.exception(f"Missing value in manifest: {exc.args[0]}")
            sys.exit(exc.errno)

        logger.info("Building firmware:")
        logger.info(f"    Target: {target}.")
        logger.info(f"    Sub-target: {sub_target}.")
        logger.info(f"    Profile: {profile}.")
        logger.info(f"    OpenWRT version: {version}.")

        try:
            extra_name = fw["name"]
        except KeyError:
            extra_name = None

        logger.info(f"    Name: {extra_name or '<None>'}.")

        try:
            packages = create_package_list(fw["packages"])
        except KeyError:
            packages = None

        # Set up files and output directories under the build directory
        files_dir: Path = build_dir / target / sub_target / profile / "files"
        output_dir: Path = build_dir / target / sub_target / profile / "firmware"

        for directory in [files_dir, output_dir]:
            try:
                directory.mkdir(parents=True)
            except IOError as exc:
                logger.exception(f"Failed to create directory {directory.absolute()}.")
                sys.exit(exc.errno)
            else:
                logger.info(f"Created directory: {directory.absolute()}.")

        # Create files for inclusion in firmware
        files = fw.get("files", [])

        try:
            create_files(files, files_dir)
        except (IOError, KeyError) as exc:
            logger.exception("Failed to create files for firmware.")
            files_dir.rmdir()
            output_dir.rmdir()
            sys.exit(exc.errno)

        builder = podman.PodmanBuilder(
            version=version,
            target=target,
            sub_target=sub_target,
            profile=profile,
            work_dir=work_dir,
            openwrt_base_url=openwrt_base_url,
        )

        try:
            builder.build_firmware(output_dir, packages, files_dir, extra_name)
        except Exception as exc:
            logger.exception("Failed to build firmware")
            sys.exit(exc.errno)
        else:
            logger.info(f"Firmware written to: {output_dir.absolute()}.")


if __name__ == "__main__":
    build()
