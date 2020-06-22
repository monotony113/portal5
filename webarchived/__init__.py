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

from dotenv import load_dotenv
from flask import Flask, request, render_template

from . import portal3, _debug

load_dotenv()


def index():
    return render_template('index.html')


def handle_not_found(remote):
    if 'portal3-remote-scheme' in request.cookies:
        return portal3.from_absolute_path()
    return handle_error(remote)


def handle_error(e):
    return render_template('httperr.html', statuscode=e.code, message=e.description, unsafe=getattr(e, 'unsafe', False)), e.code


def create_app(*, config=None) -> Flask:
    app = Flask(
        __name__,
        instance_relative_config=True,
    )
    app.secret_key = secrets.token_urlsafe(20)

    app.route('/')(index)
    app.route('/index.html')(index)

    app.register_blueprint(portal3.portal3)
    app.register_blueprint(_debug._debug)

    app.register_blueprint(_debug._debug)

    app.register_error_handler(404, handle_not_found)
    for exc in (400, 403, 451, 500, 502):
        app.register_error_handler(exc, handle_error)

    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.strip_trailing_newlines = False

    return app


app = create_app()
