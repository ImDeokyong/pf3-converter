"""Application identity, shared by GUI, CLI and Adobe profile exporter."""

APP_NAME = "PF3 Converter"
APP_VERSION = "1.1"
APP_AUTHOR = "ImDeokyong"
XMP_GROUP = APP_NAME


def display_name() -> str:
    return f"{APP_NAME} v{APP_VERSION}"
