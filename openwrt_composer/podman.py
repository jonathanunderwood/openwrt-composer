"""Podman based container image builder"""
# Unfortunately the Python podman bindings are broken and seemingly
# unmaintained, so here we resort to calling the podman and buildah command
# line tools. In the future, if the podman bindings become usable, we should
# switch to using those.
# https://github.com/containers/python-podman/issues/51
# https://github.com/containers/python-podman/pull/60
# https://github.com/varlink/python/issues/23

import logging
import subprocess
from pathlib import Path
from typing import List, Optional

from .builder import Builder
from .exceptions import (
    BaseImageBuildFailure,
    BuilderImageBuildFailure,
    FirmwareBuildFailure,
)

logger = logging.getLogger(__name__)


class PodmanBuilder(Builder):
    """A firmware builder class that uses Podman for building firmware images

    This builder wraps the Podman CLI to do its work. When the Python bindings mature,
    this class will use those bindings.

    """

    def __init__(
        self,
        version: str,
        target: str,
        sub_target: str,
        profile: str,
        work_dir: Path,
        openwrt_base_url: str,
    ):
        super().__init__(
            version=version,
            target=target,
            sub_target=sub_target,
            profile=profile,
            work_dir=work_dir,
            openwrt_base_url=openwrt_base_url,
        )

    def _create_base_image(self):
        """Create base image for all firmware builder images

        Raises:
            BaseImageBuildFailure: Raised if the build fails.

        """

        out = subprocess.run(
            ["podman", "build", "-t", self._base_image_tag, "."],
            cwd=self._base_context_dir.absolute(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        logger.info(out.stdout)

        if out.returncode != 0:
            msg = "Failed to build base builder image"
            logger.error(msg)
            raise BaseImageBuildFailure(msg)

    def _image_exists(self, tag: str):
        """Check that image exists for a given tag

        Returns:
            ``True`` if the image is available, ``False`` otherwise
        """

        o = subprocess.run(["podman", "image", "exists", tag])

        if o.returncode == 0:
            return True
        else:
            return False

    def _base_image_build_needed(self):
        """Check whether base image needs to be built

        Returns:
            ``False`` if the image is available, ``True`` otherwise
        """

        return not self._image_exists(self._base_image_tag)

    def _builder_image_build_needed(self):
        """Check whether builder image needs to be built

        Returns:
            ``False`` if the image is available, ``True`` otherwise
        """

        return not self._image_exists(self._builder_image_tag)

    def _create_builder_image(self):
        """Create firmware builder image

        Raises:
            BuilderImageBuildFailure: Raised if the image build fails.

        """

        out = subprocess.run(
            ["podman", "build", "-t", self._builder_image_tag, "."],
            cwd=self._builder_context_dir.absolute(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        logger.info(out.stdout)

        if out.returncode != 0:
            msg = f"Failed to build builder image: {self._builder_image_tag}"
            logger.error(msg)
            raise BuilderImageBuildFailure(msg)

    def _build_firmware(
        self, build_cmd: List[str], output_dir: Path, files_dir: Optional[Path] = None,
    ):
        """Build firmware image

        Args:
            build_cmd: The OpenWRT builder command line to build the firmware image.
            output_dir: Directory where the resulting firmware image files will be
                written.
            files_dir: Directory containing files to be included in the firmware image.

        Raises:
            FirmwareBuildFailure: Raised if the firmware build fails.

        """

        podman_cmd = [
            "podman",
            "run",
            "--rm",
            "-v",
            f"{output_dir.absolute()}:/openwrt/result:Z",
        ]

        if files_dir is not None:
            podman_cmd.extend(["-v", f"{files_dir.absolute()}:/openwrt/files:Z"])

        # build_cmd = ["ls"]
        podman_cmd.extend(["-t", self._builder_image_tag])

        podman_cmd.extend(build_cmd)

        logger.info(
            f"Starting firmware build using image tag: {self._builder_image_tag}"
        )
        logger.info(f"Build command: {podman_cmd}")

        out = subprocess.run(podman_cmd, capture_output=True, text=True)
        logger.info(out.stdout)

        if out.returncode != 0:
            msg = "Firmware build failed"
            logger.error(out.stdout)
            logger.error(out.stderr)
            logger.error(msg)
            raise FirmwareBuildFailure(msg)
