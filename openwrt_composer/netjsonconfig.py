import logging
from pathlib import Path

from netjsonconfig import OpenWrt
from netjsonconfig.backends.openwrt.parser import config_path, packages_pattern
from netjsonconfig.exceptions import ValidationError

from .exceptions import ConfigCreationError

logger = logging.getLogger(__name__)


class OpenWrtConfig(OpenWrt):
    """NetJSONConfig handler for router configuration.

    This class inherits from `netjsonconfig.OpenWrt` and adds convenience methods to
    dump the configuration.

    """

    def create_sysupgrade_tarball(
        self, archive_dir: Path, archive_name: str = "config"
    ) -> None:
        """Dump the configuration to a `sysupgrade` archive.

        This method renders the configuration to UCI configuration files in a tarball
        suitable for application suitable for use with `sysupgrade`.

        Args:
            archive_dir: Directory to write archive to.
            archive_name: File name of the archive without .tar.gz ending. Defaults to
                "config".

        Raises:
            ConfigCreationError: Raised if `files_dir` does not exist, of if a file that
                would be created already exists.

        """

        try:
            self.validate()
        except ValidationError:
            msg = "Configuration failed to validate"
            logger.exception(msg)
            raise ConfigCreationError(msg)

        if not archive_dir.is_dir():
            msg = f"{archive_dir.absolute()} does not exist"
            logger.error(msg)
            raise ConfigCreationError(msg)

        self.write(archive_name, str(archive_dir.resolve()))
        tarball = archive_dir / (archive_name + ".tar.gz")
        logger.info(f"Wrote sysupgrade tarball: {str(tarball.resolve())}")

    def create_files(self, files_dir: Path) -> None:
        """Dump configuration files to a directory.

        This method dumps the generated UCI configuration into files at a specified
        location. Those files can then be included in a OpenWRT firmware image.

        Args:
            files_dir: Directory to dump files to.

        Raises:
            ConfigCreationError: Raised if `files_dir` does not exist, of if a file that
                would be created already exists.

        """

        try:
            self.validate()
        except ValidationError:
            msg = "Configuration failed to validate"
            logger.exception(msg)
            raise ConfigCreationError(msg)

        if not files_dir.is_dir():
            msg = f"{files_dir.absolute()} does not exist"
            logger.error(msg)
            raise ConfigCreationError(msg)

        uci = self.render(files=False)

        packages = packages_pattern.split(uci)
        if "" in packages:
            packages.remove("")

        for package in packages:
            lines: str = package.split("\n")
            package_name: str = lines[0]
            contents: str = "\n".join(lines[2:])

            path: Path = files_dir / config_path / package_name
            if path.exists():
                msg = f"Error writing to {path.absolute()}: file already exists"
                logger.error(msg)
                raise ConfigCreationError(msg)

            parent = path.parents[0]
            try:
                parent.mkdir(parents=True)
            except IOError:
                logger.exception(f"Failed to create parent directory; {parent}")
                raise ConfigCreationError

            try:
                with open(path.absolute(), "w") as fp:
                    fp.write(contents)
                    logger.info(f"File written: {path.absolute()}")
                    logger.debug("Contents:")
                    logger.debug(contents)
            except IOError:
                msg = f"Failed to write to file: {path.absolute()}"
                logger.error(msg)
                raise ConfigCreationError(msg)
