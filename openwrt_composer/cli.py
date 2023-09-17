import logging
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from typer import Option, Typer

from openwrt_composer.exceptions import ConfigCreationError, FirmwareBuildFailure
from openwrt_composer.podman import PodmanBuilder
from openwrt_composer.schemas import Config, Firmware

LOG_LEVELS = {
    "none": logging.CRITICAL + 1,
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}

LOG_FORMAT = "%(message)s"

app = Typer()
console = Console()


@app.command()
def build(
    manifest: Path,
    configuration: Optional[Path] = Option(
        None,
        "--config",
        "-c",
        help="Specify a configuration file. If this is not specified, configuration will be taken from the environment.",
    ),
    log_level: str = Option(
        "none",
        "--log-level",
        "-l",
        help="Specify log level. This is used for debugging, and defaults to 'none' to prevent logs from being emitted.",
    ),
) -> None:
    # Setup logging
    logging.basicConfig(
        level=LOG_LEVELS[log_level],
        format=LOG_FORMAT,
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )

    # log = logging.getLogger("openwrt-composer")

    # Read configuration from a file if specified on the command line,
    # otherwise set from the environment and defaults.
    if configuration is not None:
        with open(configuration, "rb") as fp:
            config_dict = tomllib.load(fp)
        config = Config.parse_obj(config_dict["openwrt_composer"])
    else:
        config = Config()

    with open(manifest, "rb") as fp:
        spec = tomllib.load(fp)

    firmware_specification = Firmware.parse_obj(spec).firmware

    table = Table(show_header=False)
    table.add_row("Target", f"{firmware_specification.target}")
    table.add_row("Sub-target", f"{firmware_specification.sub_target}")
    table.add_row("Profile", f"{firmware_specification.profile}")
    table.add_row("Extra name", f"{firmware_specification.extra_name or '<None>'}")
    table.add_row("OpenWRT version", f"{firmware_specification.version}")

    work_dir = config.work_dir or Path.cwd() / "openwrt-composer"
    table.add_row("Working directory", f"{work_dir}")

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        console.print(
            f"Failed to create work directory: {work_dir.absolute()}. Exiting."
        )
        console.print_exception(show_locals=True)
        sys.exit(-1)

    # Create build directory for firmware creation. Also create
    # subdirectories for storing the files for inclusion in the
    # firmware, and for the produced firmware.
    try:
        build_dir = tempfile.mkdtemp(prefix="build-", dir=work_dir)
    except BlockingIOError:
        console.print("Failed to create build directory. Exiting.")
        console.print_exception(show_locals=True)
        sys.exit(-1)

    build_dir = Path(build_dir)
    table.add_row("Build directory", f"{build_dir}")

    files_dir = build_dir / "files"
    output_dir = build_dir / "firmware"

    for directory in [files_dir, output_dir]:
        try:
            directory.mkdir(parents=True)
        except OSError:
            console.print(
                f"Failed to create directory: {directory.absolute()}. Exiting."
            )
            console.print_exception(show_locals=True)
            sys.exit(-1)

    table.add_row("Files directory", f"{files_dir}")
    table.add_row("Output directory", f"{output_dir}")

    console.print(table)

    # Create files for inclusion in firmware
    try:
        firmware_specification.create_file_tree_at_location(files_dir)
    except ConfigCreationError:
        console.print(
            "Failed to create files for inclusion in firmware image. Exiting."
        )
        console.print_exception(show_locals=True)
        sys.exit(-1)

    console.print(f"Files for inclusion created at {files_dir}")

    # Create package list
    if firmware_specification.packages is not None:
        packages = firmware_specification.packages.as_string()
    else:
        packages = None

    # Build the firmware
    console.print("Building firmware with OpenWRT ImageBuilder...")

    if config.container_engine == "podman":
        if config.podman is not None:
            builder = PodmanBuilder(
                version=firmware_specification.version,
                target=firmware_specification.target,
                sub_target=firmware_specification.sub_target,
                profile=firmware_specification.profile,
                work_dir=work_dir,
                openwrt_base_url=config.openwrt_base_url,
                podman_uri=config.podman.uri,
            )
        else:
            console.print(
                "podman container engine specified but podman configuration not found. Exiting."
            )
            sys.exit(-1)
    else:
        console.print(
            "No supported container engine specified in configuration. Exiting."
        )
        sys.exit(-1)

    try:
        builder.build_firmware(
            output_dir, packages, files_dir, firmware_specification.extra_name
        )
    except FirmwareBuildFailure:
        console.print("Firmware build failed. Exiting.")
        console.print_exception(show_locals=True)
        sys.exit(-1)

    console.print(f"Firmware written to: {output_dir.absolute()}")
