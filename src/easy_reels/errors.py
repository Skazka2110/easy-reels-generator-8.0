class EasyReelsError(Exception):
    """Base error with a user-facing Russian message."""


class ProjectError(EasyReelsError):
    pass


class SettingsError(EasyReelsError):
    pass


class WorkbookError(EasyReelsError):
    pass


class MediaError(EasyReelsError):
    pass


class TextLayoutError(EasyReelsError):
    pass


class RenderError(EasyReelsError):
    def __init__(self, message: str, *, technical_detail: str | None = None):
        super().__init__(message)
        self.technical_detail = technical_detail or message


class LicenseError(EasyReelsError):
    pass


class LicenseConfigurationError(LicenseError):
    pass


class LicenseValidationError(LicenseError):
    pass


class LicenseActivationError(LicenseError):
    def __init__(self, message: str, *, code: str = "activation_failed"):
        super().__init__(message)
        self.code = code
