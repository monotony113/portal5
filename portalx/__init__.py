# __init__.py
# Copyright (C) 2020  Tony Wu <tony[dot]wu(at)nyu[dot]edu>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import secrets
from importlib import import_module
from pkgutil import iter_modules

from dotenv import load_dotenv
from flask import Flask, g, request, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from . import config, security, i18n

load_dotenv()


def load_blueprints(app: Flask):
    for importer, name, ispkg in iter_modules(__path__):
        if ispkg:
            module_ = import_module(f'.{name}', __name__)
            bp = getattr(module_, 'bp', None)
            if bp:
                app.register_blueprint(bp)


def setup_error_handling(app: Flask):
    def handle_error(e):
        return render_template('error.html', statuscode=e.code, message=e.description, unsafe=getattr(e, 'unsafe', False)), e.code

    for exc in (400, 403, 404, 451, 500, 502, 503):
        app.register_error_handler(exc, handle_error)


def setup_urls(app: Flask):
    app.add_url_rule(
        '/<path:filename>', subdomain='static',
        endpoint='static', view_func=app.send_static_file
    )

    @app.url_value_preprocessor
    def derive_server_info(endpoint, values):
        g.sld = '.'.join(request.host.split('.')[-2:])


def setup_debug(app: Flask):
    if not app.debug:
        return

    app.wsgi_app = ProxyFix(app.wsgi_app)


def setup_jinja(app: Flask):
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.strip_trailing_newlines = False


def create_app(*, override=None) -> Flask:
    app = Flask(
        __name__,
        instance_relative_config=True,
    )
    app.secret_key = secrets.token_urlsafe(20)
    app.config.from_object(config)
    app.config.from_object(override or dict())
    app.config.from_pyfile('config.py', silent=True)

    load_blueprints(app)
    setup_urls(app)
    setup_error_handling(app)
    setup_jinja(app)
    setup_debug(app)

    security.setup_filters(app)
    i18n.setup_languages(app)

    return app


app = create_app()
