"""Build anthropic exception instances for offline tests without an HTTP response object."""
import anthropic


def api_error(cls: type, message: str) -> Exception:
    e = cls.__new__(cls)
    Exception.__init__(e, message)
    e.message = message
    return e
