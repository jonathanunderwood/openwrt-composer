"""Custom Exceptions for OpenWRT Composer."""


class OpenWRTComposerException(Exception):
    """Top level exception for OpenWRT Composer exceptions."""


class FirmwareBuildFailure(OpenWRTComposerException):
    """Raised when a firmware build fails."""


class ImageBuildFailure(OpenWRTComposerException):
    """Raised when a container image build fails."""


class BaseImageBuildFailure(ImageBuildFailure):
    """Raised when a base container image build fails."""


class BuilderImageBuildFailure(ImageBuildFailure):
    """Raised when a firmware buider container image build fails."""


class ManifestError(OpenWRTComposerException):
    """Raised when an error is found with a manifest."""


class ImageBuilderRetrievalFailure(OpenWRTComposerException):
    """Raised when an attempt to retrieve an OpenWRT image builder fails."""


class ContextDirectoryCreationFailure(OpenWRTComposerException):
    """Raised when creating a context directory for an image build fails."""


class ConfigCreationError(OpenWRTComposerException):
    """Raised when an error occurs creating config files."""
