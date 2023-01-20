"""Podman based container image builder"""
# Unfortunately the Python podman bindings are broken and seemingly
# unmaintained, so here we resort to calling the podman and buildah command
# line tools. In the future, if the podman bindings become usable, we should
# switch to using those.
# https://github.com/containers/python-podman/issues/51
# https://github.com/containers/python-podman/pull/60
# https://github.com/varlink/python/issues/23

import logging
from pathlib import Path
from typing import List, Optional

from podman import PodmanClient
from podman.errors import APIError, BuildError, ContainerError, ImageNotFound
from requests.exceptions import RequestException

from openwrt_composer.builder import Builder
from openwrt_composer.exceptions import (
    BaseImageBuildFailure,
    BuilderImageBuildFailure,
    FirmwareBuildFailure,
    OpenWRTComposerException,
)

logger = logging.getLogger(__name__).addHandler(logging.NullHandler())

# FIXME: this is hard coded for now, but needs to be a configuration parameter
uri = "unix:///run/user/1000/podman/podman.sock"


class PodmanException(OpenWRTComposerException):
    """Raised when a Podman operation fails."""


class PodmanBuilder(Builder):
    """A firmware builder class that uses Podman.

    This firmware builder utilizes Podman to build firmware
    images. Connectivity with Podman is via the REST API that Podman
    provides.

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
        self.podman_uri = uri

    def _create_base_image(self):
        """Create base image for all firmware builder images

        Raises:
            BaseImageBuildFailure: Raised if the build fails.

        """

        with PodmanClient(base_url=self.podman_uri) as client:
            try:
                _, log = client.images.build(
                    path=self._base_context_dir.absolute(),
                    tag=self._base_image_tag,
                    dockerfile=self._base_context_dir.absolute() / "Containerfile",
                )
            except BuildError as exc:
                logger.exception(exc)
                msg = "Builder image build failed"
                raise BaseImageBuildFailure(msg) from exc
            except APIError as exc:
                logger.exception(exc)
                msg = "Podman API service returned an error"
                raise BaseImageBuildFailure(msg) from exc
            else:
                logger.info(log)

    def _image_exists(self, tag: str):
        """Check that image exists for a given tag.

        Args:
            tag: Image tag to check existence of.

        Returns:
            ``True`` if the image is available, ``False`` otherwise.
        """

        with PodmanClient(base_url=self.podman_uri) as client:
            try:
                exists = client.images.exists(tag)
            except RequestException as exc:
                logger.exception(exc)
                raise PodmanException from exc
            else:
                return exists

    def _base_image_build_needed(self):
        """Check whether base image needs to be built.

        Returns:
            ``False`` if the image is available, ``True`` otherwise.
        """

        return not self._image_exists(self._base_image_tag)

    def _builder_image_build_needed(self):
        """Check whether builder image needs to be built.

        Returns:
            ``False`` if the image is available, ``True`` otherwise.
        """

        return not self._image_exists(self._builder_image_tag)

    def _create_builder_image(self):
        """Create firmware builder image.

        Raises:
            BuilderImageBuildFailure: Raised if the image build fails.

        """

        with PodmanClient(base_url=self.podman_uri) as client:
            try:
                _, log = client.images.build(
                    path=self._builder_context_dir.absolute(),
                    tag=self._builder_image_tag,
                    dockerfile=self._builder_context_dir.absolute() / "Containerfile",
                )
            except BuildError as exc:
                logger.exception(exc)
                msg = "Builder image build failed"
                raise BuilderImageBuildFailure(msg) from exc
            except APIError as exc:
                logger.exception(exc)
                msg = "Podman API service returned an error"
                raise BuilderImageBuildFailure(msg) from exc
            else:
                logger.info(log)

    def _build_firmware(
        self,
        build_cmd: List[str],
        output_dir: Path,
        files_dir: Optional[Path] = None,
    ):
        """Builds a firmware image.

        Args:
            build_cmd: The OpenWRT builder command line to build the firmware image.
            output_dir: Directory where the resulting firmware image files will be
                written.
            files_dir: Directory containing files to be included in the firmware image.

        Raises:
            FirmwareBuildFailure: Raised if the firmware build fails.

        """

        mounts = [
            {
                "type": "bind",
                "source": f"{output_dir.absolute()}",
                "target": "/openwrt/result",
                "read_only": False,
                "relabel": "Z",
            },
        ]

        if files_dir is not None:
            mounts.append(
                {
                    "type": "bind",
                    "source": f"{files_dir.absolute()}",
                    "target": "/openwrt/files",
                    "read_only": True,
                    "relabel": "Z",
                }
            )

        with PodmanClient(base_url=self.podman_uri) as client:
            logger.info(
                f"Starting firmware build using image tag: {self._builder_image_tag}"
            )
            try:
                out = client.containers.run(
                    image=self._builder_image_tag,
                    mounts=mounts,
                    remove=True,
                    stdout=True,
                    stderr=True,
                )
            except ContainerError as exc:
                logger.exception(exc)
                msg = "Container exited with non-zero error code"
                raise FirmwareBuildFailure(msg) from exc
            except ImageNotFound as exc:
                logger.exception(exc)
                msg = "Image not found"
                raise FirmwareBuildFailure(msg) from exc
            except APIError as exc:
                logger.exception(exc)
                msg = "Podman API service returned an error"
                raise FirmwareBuildFailure(msg) from exc

        # Write stdout and stderr from running the container to log
        for msg in out:
            logger.info(msg)
