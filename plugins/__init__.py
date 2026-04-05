"""RetailOS Plugin System.

Plugins are Python packages that can register additional API routes,
event handlers, and background tasks with RetailOS.

To create a plugin, create a module with a `register(app, context)` function.
"""
