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

from flask import Flask, g, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from . import config, i18n
from .app import portal5
from .bundle import bundle
from .utils import blacklist, security


def load_blueprints(app: Flask):
    app.register_blueprint(portal5)
    app.register_blueprint(bundle)


def setup_error_handling(app: Flask):
    def handle_error(e):
        return render_template('exceptions/error.html', statuscode=e.code, message=e.description, unsafe_markup=getattr(e, 'unsafe_markup', False)), e.code

    for exc in (400, 401, 403, 404, 451, 500, 502, 503):
        app.register_error_handler(exc, handle_error)


def setup_urls(app: Flask):
    app.static_folder = 'bundle/static'
    app.add_url_rule(
        '/<path:filename>', subdomain='static',
        endpoint='static', view_func=app.send_static_file,
    )

    @app.route('/favicon.ico')
    def favicon():
        return app.send_static_file('favicon.ico')


def setup_context(app: Flask):
    @app.before_first_request
    def derive_server_info():
        main = app.config['SERVER_NAME']
        server_map = {
            'domains': {
                'main': main,
                'static': f'static.{main}',
                'googleapis': '*.googleapis.com',
                'gstatic': '*.gstatic.com',
            },
        }
        server_map['origins'] = {k: f'{request.scheme}://{v}' for k, v in server_map['domains'].items()}

        app.config['SERVER_MAP'] = server_map

    @app.before_request
    def supply_server_info():
        g.server_map = app.config['SERVER_MAP']


def setup_jinja(app: Flask):
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.strip_trailing_newlines = False


def create_app(*, override=None) -> Flask:
    app = Flask(
        __name__,
        instance_relative_config=True,
        static_folder=None,
        static_url_path=None,
    )
    app.secret_key = secrets.token_urlsafe(20)
    app.config.from_object(config)
    app.config.from_pyfile('config.py', silent=True)
    app.config.from_json('secrets.json', silent=True)
    app.config.from_object(override or {})

    app.wsgi_app = ProxyFix(app.wsgi_app)

    setup_context(app)
    setup_jinja(app)

    security.setup_jwt(app)
    blacklist.setup_filters(app)
    i18n.setup_languages(app)

    setup_urls(app)
    setup_error_handling(app)
    load_blueprints(app)

    return app


app = create_app()
