class AtlassianAutomationError(Exception):
    """Base exception untuk semua error di project ini."""
    def __init__(self, message: str, error_type: str = "UNKNOWN_ERROR"):
        super().__init__(message)
        self.error_type = error_type

class LoginError(AtlassianAutomationError):
    """Gagal login ke Atlassian."""
    pass

class ScrapingError(AtlassianAutomationError):
    """Gagal mengambil data dari halaman web."""
    pass

class TokenRenewalError(AtlassianAutomationError):
    """Gagal melakukan renewal API token."""
    pass

class NavigationError(AtlassianAutomationError):
    """Gagal navigasi ke halaman tertentu."""
    pass