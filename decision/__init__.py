"""Decision runtime: select the locked package before constructing any site zone."""
from decision.timezone_authority import configure as _configure_time_authority

_configure_time_authority()
del _configure_time_authority
