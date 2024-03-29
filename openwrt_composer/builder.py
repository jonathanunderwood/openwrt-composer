"""Abstract base class and helpers for firmware building classes"""
import logging
import textwrap
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests

from openwrt_composer.exceptions import (
    ContextDirectoryCreationFailure,
    ImageBuilderRetrievalFailure,
)

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name
logger.addHandler(logging.NullHandler())


def _prepare_context_dir(
    context_dir: Path, containerfile: str, files: Optional[Dict[str, str]]
) -> None:
    """Prepare a context directory for a container image build

    Args:
        context_dir: The Path of the context directory to create and prepare.
        containerfile: The contents of the Containerfile to create.
        files: A dictionary of files to create in the context directory. The
            dictionary keys are the filenames, and the values are the contents.

    Raises:
        RuntimeError: Raised if the `context_dir` exists but is not a directory.
        OSError: Raised if creating the `context_dir` fails.

    """
    if context_dir.exists():
        if not context_dir.is_dir():
            msg = "Context exists but is not a directory: {context_dir}"
            logger.error(msg)
            raise ContextDirectoryCreationFailure(msg)
    else:
        try:
            logger.info(f"Creating context directory: {context_dir}")
            context_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            msg = f"Failed to create directory: {context_dir}"
            logger.exception(msg)
            raise ContextDirectoryCreationFailure(msg)

    logger.info(f"Creating {context_dir}/Containerfile")
    with open(context_dir / "Containerfile", "w") as fp:
        logger.debug("Containerfile contents:")
        logger.debug(containerfile)
        fp.write(containerfile)

    if files is not None:
        for file, contents in files.items():
            logger.info(f"Creating {context_dir/file}")
            with open(context_dir / file, "w") as fp:
                logger.debug("Contents:")
                logger.debug(contents)
                fp.write(contents)


_ENTRYPOINT_SCRIPT: str = textwrap.dedent(
    """\
    #!/bin/bash
    set -e
    exec "$@"
    """
)
_ENTRYPOINT_SCRIPT_NAME: str = "entrypoint.sh"

_BASE_CONTAINERFILE: str = textwrap.dedent(
    f"""\
    FROM fedora:39
    RUN dnf -y install \
      @c-development \
      @development-tools \
      @development-libs \
      zlib-static \
      which \
      diffutils \
      python2 \
      wget \
      xz \
      rsync \
      perl-FindBin \
      time && dnf clean all
    COPY {_ENTRYPOINT_SCRIPT_NAME} /{_ENTRYPOINT_SCRIPT_NAME}
    RUN chmod 755 /{_ENTRYPOINT_SCRIPT_NAME}
    ENTRYPOINT ["/{_ENTRYPOINT_SCRIPT_NAME}"]
    CMD ["/bin/bash"]
    """
)

_BASE_IMAGE_TAG: str = "openwrt-composer-base"

_BUILDER_CONTAINERFILE: str = textwrap.dedent(
    """\
    FROM openwrt-composer-base
    COPY {entrypoint_script_name} /{entrypoint_script_name}
    RUN chmod 755 /{entrypoint_script_name}
    RUN groupadd openwrt && useradd -g openwrt openwrt
    RUN mkdir /openwrt && chown openwrt:openwrt /openwrt
    WORKDIR /openwrt
    COPY --chown=openwrt:openwrt {archive_file} .
    USER openwrt
    RUN tar -xf {archive_file}
    WORKDIR /openwrt/{archive_dir}
    ENTRYPOINT ["/{entrypoint_script_name}"]
    CMD ["/bin/bash"]
    """  # noqa: E501
)


class Builder(ABC):
    """An abstract base class for a firmware builder class

    The concrete class should call the constructor of this base class via `super()`.

    Args:
        version: The OpenWRT release this builder will use when building a firmware
            image.
        target: The target architecture for this firmware builder.
        sub_target: The architecture sub-target for this firmware builder.
        profile: The device profile for this firmware builder.
        work_dir: The directory that will be used by this builder for storing files.
        openwrt_base_url: The base URL for OpenWRT firmware builder archives.

    """

    @abstractmethod
    def __init__(
        self,
        version: str,
        target: str,
        sub_target: str,
        profile: str,
        work_dir: Path,
        openwrt_base_url: str,
    ) -> None:
        self.version = version
        self.target = target
        self.sub_target = sub_target
        self.profile = profile
        self.work_dir = work_dir

        self._builder_image_tag = (
            f"openwrt-composer-{version}-{target}-{sub_target}"  # noqa: E501
        )
        self._base_image_tag = _BASE_IMAGE_TAG

        if not openwrt_base_url.endswith("/"):
            self.openwrt_base_url: str = openwrt_base_url + "/"
        else:
            self.openwrt_base_url: str = openwrt_base_url

        self._archive_dir = (
            f"openwrt-imagebuilder-{version}-{target}-{sub_target}.Linux-x86_64"
        )
        self._archive_file = f"{self._archive_dir}.tar.xz"
        self._base_context_dir = self.work_dir / "base"
        self._builder_context_dir = (
            self.work_dir / self.version / self.target / self.sub_target
        )
        self._base_containerfile = _BASE_CONTAINERFILE
        self._builder_containerfile = _BUILDER_CONTAINERFILE.format(
            archive_file=self._archive_file,
            archive_dir=self._archive_dir,
            entrypoint_script_name=_ENTRYPOINT_SCRIPT_NAME,
        )

    def _prepare_base_context(self) -> None:
        """Prepare a context directory for building the base image"""

        _prepare_context_dir(
            context_dir=self._base_context_dir,
            containerfile=self._base_containerfile,
            files={_ENTRYPOINT_SCRIPT_NAME: _ENTRYPOINT_SCRIPT},
        )

    def _prepare_builder_context(self) -> None:
        """Prepare a context directory for building the builder image"""

        _prepare_context_dir(
            context_dir=self._builder_context_dir,
            containerfile=self._builder_containerfile,
            files={_ENTRYPOINT_SCRIPT_NAME: _ENTRYPOINT_SCRIPT},
        )

    def _retrieve_builder_archive(self) -> None:
        """Retrieve OpenWRT image builder archive

        The file is stored in the context directory suitable for building the firmware
        builder image. If the builder archive is already present in the builder context,
        then the retrieval is skipped.

        Raises:
            ImageBuilderRetrievalFailure: Raised if retrieving the builder archive
                fails.

        """
        builder_archive = self._builder_context_dir / self._archive_file

        if builder_archive.exists():
            return

        url = urljoin(
            self.openwrt_base_url,
            f"releases/{self.version}/targets/{self.target}/{self.sub_target}/{self._archive_file}",  # noqa: E501
        )
        res = requests.get(url)

        if res.ok:
            with open(builder_archive, "wb") as fp:
                for block in res.iter_content(1024):
                    if block:
                        fp.write(block)
                        fp.flush()
        else:
            msg = f"Failed to retrieve {url}"
            logger.error(msg)
            raise ImageBuilderRetrievalFailure(msg)

    @abstractmethod
    def _create_base_image(self) -> None:
        """Create the base container image

        The base image is used for creation of all firmware builder images.

        """

        pass

    @abstractmethod
    def _base_image_build_needed(self) -> None:
        """Determine if the base image needs building"""

        pass

    @abstractmethod
    def _builder_image_build_needed(self) -> None:
        """Determine if the base image needs building"""

        pass

    @abstractmethod
    def _create_builder_image(self) -> None:
        """Create the firmware builder image

        Firmware builder images are specific to each version, target, and sub_target.

        """
        pass

    @abstractmethod
    def _build_firmware(
        self, build_cmd: List[str], output_dir: Path, files_dir: Optional[Path]
    ) -> None:
        """Build a firmware image

        Args:
            build_cmd: Firmware build command line with arguments.
            output_dir: Path to directory for writing the resulting firmware to.
            files_dir: Path to directory containing files to include in the firmware.
        """

        pass

    def build_firmware(
        self,
        output_dir: Path,
        packages: Optional[str] = None,
        files_dir: Optional[Path] = None,
        extra_name: Optional[str] = None,
    ) -> None:
        """Build a firmware image

        Args:
            output_dir: Path to directory for writing the resulting firmware to.
            packages: Optional string specifying packages to include or remove from the
                firmware image.
            files_dir: Path to directory containing files to include in the firmware.
            extra_name: Extra name to embed in the firmware image file name.

        """

        if self._base_image_build_needed():
            logger.info("Building base image")
            self._prepare_base_context()
            self._create_base_image()
        else:
            logger.info("Base image found.")

        if self._builder_image_build_needed():
            logger.info(f"Building builder image: {self._builder_image_tag}.")
            self._prepare_builder_context()
            self._retrieve_builder_archive()
            self._create_builder_image()
        else:
            logger.info("Builder image found.")

        firmware = (
            f"openwrt-{self.version}-{self.target}-{self.sub_target}-{self.profile}"
        )
        logger.info(f"Building firmware: {firmware}")

        build_cmd = [
            "make",
            "image",
            f"PROFILE={self.profile}",
            "BIN_DIR=/openwrt/result",
        ]

        if packages is not None:
            build_cmd.append(f"PACKAGES={packages}")

        if files_dir is not None:
            build_cmd.append("FILES=/openwrt/files")

        if extra_name is not None:
            build_cmd.append(f"EXTRA_IMAGE_NAME={extra_name}")

        self._build_firmware(build_cmd, output_dir, files_dir)
