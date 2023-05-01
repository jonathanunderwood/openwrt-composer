"""Pydantic schemas used for validation of data."""

import logging
from pathlib import Path
from typing import Literal, Optional

from pydantic import AnyUrl, BaseModel, BaseSettings, HttpUrl

from openwrt_composer.exceptions import ConfigCreationError

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class PackagesSpec(BaseModel):
    add: list[str] = []
    remove: list[str] = []

    def as_string(self) -> str:
        """Create packages list suitable for building firmware image.

        Returns:
            A string with all package names from the ``add`` list, and all
                packages from the ``remove`` list prefixed with a "``-``".
                This string is suitable for passing to the
                ``make PACKAGES=<str>`` invocation when building a firmware
                image with the OpenWRT firmware builder.

        """
        packages_list = self.add + [f"-{pkg}" for pkg in self.remove]
        packages_str = " ".join(packages_list)

        return packages_str


class FileContentsSpec(BaseModel):
    path: str
    contents: str

    def create_file_at_location(self, location: Path) -> None:
        """Write file to disk at a specifed root location.

        Args:
            location: Location to write the file contents to. The contents
                will be written to `location`/`self.path`.


        Raises:
            IOError: Raised if an error occurs creating a file.
            ConfigCreationError: Raised if `location` does not exist, if the
               file that would be created already exists, or if the file cannot
               be created.

        """

        if not location.is_dir():
            msg = f"{location.absolute()} does not exist"
            logger.error(msg)
            raise ConfigCreationError(msg)

        full_path = location / Path(self.path).relative_to("/")

        if full_path.exists():
            msg = f"Error writing to {full_path.absolute()}: file already exists"
            logger.error(msg)
            raise ConfigCreationError(msg)

        parent = full_path.parents[0]
        try:
            parent.mkdir(parents=True)
        except IOError:
            logger.exception(f"Failed to create parent directory: {parent}")
            raise ConfigCreationError

        try:
            with open(full_path, mode="w") as fp:
                fp.write(self.contents)
        except IOError:
            logger.exception(f"Failed to write to file: {full_path.absolute()}")
            raise ConfigCreationError


class FirmwareSpecification(BaseModel):
    target: str
    sub_target: str
    profile: str
    version: str
    extra_name: Optional[str]
    packages: Optional[PackagesSpec] = None
    files: Optional[list[FileContentsSpec]] = None

    def create_file_tree_at_location(self, location: Path) -> None:
        """Write all files to a directory tree at a specified root location.

        Args:
            location: Location to write the directory tree to.

        """
        if self.files is not None:
            for file_ in self.files:
                try:
                    file_.create_file_at_location(location)
                except ConfigCreationError:
                    logger.exception(f"Failed to create file: {file_}")
                    raise


class Firmware(BaseModel):
    firmware: FirmwareSpecification


class PodmanUrl(AnyUrl):
    host_required = False


class PodmanConfig(BaseModel):
    uri: PodmanUrl = "unix:///run/user/1000/podman/podman.sock"  # type:ignore


class Config(BaseSettings):
    container_engine: Literal["podman", "docker"] = "podman"
    # Type checkers will complain about setting these from a
    # literal, but this will be fixed in Pydantic 2.0. See:
    # https://github.com/pydantic/pydantic/issues/1684
    openwrt_base_url: HttpUrl = "https://downloads.openwrt.org/"  # type:ignore
    work_dir: Optional[Path] = None
    podman: Optional[PodmanConfig] = None

    class Config:
        env_prefix = "OPENWRT_COMPOSER_"
