"""Plugin loader for RetailOS.

Discovers and loads plugins from the plugins/ directory or from
RETAILOS_PLUGINS environment variable (comma-separated module paths).

Each plugin must expose:
    register(app: FastAPI, context: PluginContext) -> None

Example plugin (plugins/my_plugin.py):
    from fastapi import APIRouter
    router = APIRouter(prefix="/api/my-plugin", tags=["my-plugin"])

    @router.get("/hello")
    async def hello():
        return {"message": "Hello from plugin!"}

    def register(app, context):
        app.include_router(router)
        context.on_event("order.created", handle_order)

    async def handle_order(event_name, payload):
        print(f"New order: {payload}")
"""

import importlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine

from fastapi import FastAPI

logger = logging.getLogger(__name__)

EventHandler = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


@dataclass
class PluginContext:
    """Context object passed to each plugin's register() function."""

    app: FastAPI
    _event_handlers: dict[str, list[EventHandler]] = field(default_factory=dict)
    _plugins_loaded: list[str] = field(default_factory=list)

    def on_event(self, event_name: str, handler: EventHandler):
        """Register a handler for a RetailOS event (e.g. 'order.created')."""
        self._event_handlers.setdefault(event_name, []).append(handler)
        logger.info("Plugin event handler registered: %s", event_name)

    async def dispatch_event(self, event_name: str, payload: dict[str, Any]):
        """Dispatch an event to all registered plugin handlers."""
        handlers = self._event_handlers.get(event_name, [])
        for handler in handlers:
            try:
                await handler(event_name, payload)
            except Exception as e:
                logger.warning("Plugin event handler error for %s: %s", event_name, e)

    @property
    def loaded_plugins(self) -> list[str]:
        return list(self._plugins_loaded)


def discover_plugins() -> list[str]:
    """Find plugin modules to load."""
    modules: list[str] = []

    # From environment variable
    env_plugins = os.environ.get("RETAILOS_PLUGINS", "")
    if env_plugins:
        modules.extend(p.strip() for p in env_plugins.split(",") if p.strip())

    # Auto-discover from plugins/ directory
    plugins_dir = Path(__file__).parent
    for path in sorted(plugins_dir.glob("*.py")):
        if path.name.startswith("_") or path.name == "loader.py":
            continue
        module_name = f"plugins.{path.stem}"
        if module_name not in modules:
            modules.append(module_name)

    return modules


def load_plugins(app: FastAPI) -> PluginContext:
    """Discover, load, and register all plugins."""
    context = PluginContext(app=app)
    modules = discover_plugins()

    for module_path in modules:
        try:
            mod = importlib.import_module(module_path)
            if not hasattr(mod, "register"):
                logger.warning("Plugin %s has no register() function, skipping", module_path)
                continue
            mod.register(app, context)
            context._plugins_loaded.append(module_path)
            logger.info("Plugin loaded: %s", module_path)
        except Exception as e:
            logger.error("Failed to load plugin %s: %s", module_path, e)

    logger.info("Loaded %d plugin(s): %s", len(context._plugins_loaded), context._plugins_loaded)
    return context
