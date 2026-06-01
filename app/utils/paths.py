import platform

_is_windows = platform.system() == "Windows"

def win_path(win: str, unix: str) -> str:
    """Return the appropriate path depending on the OS.
    Args:
        win: Path to use on Windows (e.g., "c:/HellenCommerce").
        unix: Path to use on Unix-like systems (e.g., "/app").
    """
    return win if _is_windows else unix

# Base directories
BASE_HC = win_path("c:/HellenCommerce", "/app")
BASE_DATA = win_path("c:/HellenData", "HellenData")

def hc_path(relative: str) -> str:
    """Return a path inside the HellenCommerce project.
    Example: hc_path('app/prompts') -> 'c:/HellenCommerce/app/prompts' on Windows.
    """
    rel = relative.lstrip('/')
    return f"{BASE_HC}/{rel}"

def data_path(relative: str) -> str:
    """Return a path inside the HellenData directory.
    Example: data_path('sqlite_store/hellencommerce.db')
    """
    rel = relative.lstrip('/')
    return f"{BASE_DATA}/{rel}"
