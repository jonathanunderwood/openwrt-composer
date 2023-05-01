import logging
from pathlib import Path
from typing import Dict, List, Optional

from openwrt_composer.exceptions import ConfigCreationError
from openwrt_composer.schemas import PackagesSpec

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def create_files(files: List[Dict[str, str]], files_dir: Path) -> None:
    """Write files to disk as a tree for firmware building.

    This function processes a list of dictionaries, each entry of
    which specifies the path and contents of a file, and creates the
    corresponding directory tree and file contents on disk at a specified
    location. This directory tree can then be added to a firmware build.

    Args:
        files: A list of dictionaries. Each list item must have a ``path`` key
            and a ``contents`` key. The ``path`` key defines where in the
            firmware image the file should be placed. The ``contents`` key
            specifies the contents of the file.
        files_dir: Location to write the files and directory tree to.

    Returns:
        The Path to the directory containing the files.

    Raises:
        KeyError: Raised if a files dict is missing a key.
        IOError: Raised if an error occurs creating a file.
        ConfigCreationError: Raised if `files_dir` does not exist, of if a file
            that would be created already exists.

    """

    if not files_dir.is_dir():
        msg = f"{files_dir.absolute()} does not exist"
        logger.error(msg)
        raise ConfigCreationError(msg)

    for file in files:
        try:
            path = files_dir / Path(file["path"]).relative_to("/")
            contents = file["contents"]
        except KeyError as exc:
            logger.exception(f"Missing key for file: {exc.args[0]}")
            raise

        if path.exists():
            msg = f"Error writing to {path.absolute()}: file already exists"
            logger.error(msg)
            raise ConfigCreationError(msg)

        parent = path.parents[0]
        try:
            parent.mkdir(parents=True)
        except IOError:
            logger.exception(f"Failed to create parent directory: {parent}")
            raise ConfigCreationError

        try:
            with open(path, mode="w") as fp:
                fp.write(contents)
                logger.debug(f"File written: {path.absolute()}")
                logger.debug("Contents:")
                logger.debug(contents)
        except IOError:
            logger.exception(f"Failed to write to file: {path.absolute()}")
            raise


def create_package_list(packages: PackagesSpec) -> str:
    """Create packages list suitable for building firmware image.

    Args:
        packages: A PackagesSpec instance.

    Returns:
        A string with all package names from the ``add`` list, and all packages
            from the ``remove`` list prefixed with a "``-``". This string is
            suitable for passing to the ``make PACKAGES=<str>`` invocation when
            building a firmware image with the OpenWRT firmware builder.

    """
    packages_list: List[str] = packages.add + [f"-{pkg}" for pkg in packages.remove]
    packages_str = " ".join(packages_list)

    logger.debug(f"packages string:\n{packages_str}")

    return packages_str
