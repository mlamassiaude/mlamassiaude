from flask import Flask


def register_blueprints(app: Flask) -> None:
    from . import auth, core, documents, itinerary, roster, shows

    for module in (auth, core, roster, shows, documents, itinerary):
        app.register_blueprint(module.bp)
