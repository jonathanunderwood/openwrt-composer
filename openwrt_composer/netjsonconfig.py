import logging
from pathlib import Path

from netjsonconfig import OpenWrt
from netjsonconfig.backends.openwrt.parser import config_path, packages_pattern

from .excpetions import ConfigCreationError

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

        """
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
                msg = f"Error writing to {path}: file already exists"
                logger.error(msg)
                raise ConfigCreationError(msg)

            with open(path.absolute(), "w") as fp:
                fp.write(contents)
                logger.info(f"File written: {path}")
                logger.debug(contents)
