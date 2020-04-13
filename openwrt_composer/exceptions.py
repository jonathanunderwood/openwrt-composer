"""Custom Exceptions"""


class FirmwareBuildFailure(Exception):
    """Raised when a firmware build fails"""


class ImageBuildFailure(Exception):
    """Raised when a container image build fails"""


class BaseImageBuildFailure(ImageBuildFailure):
    """Raised when a base container image build fails"""


class BuilderImageBuildFailure(ImageBuildFailure):
    """Raised when a firmware buider container image build fails"""


class ManifestError(Exception):
    """Raised when an error is found with a manifest"""


class ImageBuilderRetrievalFailure(Exception):
    """Raised when an attempt to retrieve an OpenWRT image builder fails"""


class ContextDirectoryCreationFailure(Exception):
    """Raised when creating a context directory for an image build fails"""
