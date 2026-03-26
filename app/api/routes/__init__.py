from .bootstrap import register_bootstrap_routes
from .channels import register_channel_routes
from .health import register_health_routes
from .logs import register_log_routes
from .settings import register_settings_routes

__all__ = [
    "register_bootstrap_routes",
    "register_channel_routes",
    "register_health_routes",
    "register_log_routes",
    "register_settings_routes",
]
