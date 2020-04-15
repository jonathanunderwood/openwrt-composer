import logging
from pathlib import Path

from netjsonconfig import OpenWrt
from netjsonconfig.backends.openwrt.parser import config_path, packages_pattern
from netjsonconfig.exceptions import ValidationError

from .exceptions import ConfigCreationError

logger = logging.getLogger(__name__)


class OpenWrtConfig(OpenWrt):
    """NetJSONConfig handler for router configuration

    This class inherits from `netjsonconfig.OpenWrt` and adds a method to dump the
    configuration into files at a specified location.

    """

    def create_files(self, files_dir: Path):
        """Dump configuration files to a location

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
