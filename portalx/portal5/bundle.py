# javascript.py
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

from functools import wraps

from flask import Blueprint, Response, current_app, g, render_template, request
from flask_jwt_extended import get_jwt_claims, get_raw_jwt

from .. import common, security
from . import config
from .portal5 import Portal5

APPNAME = 'p5bundle'
p5bundle = Blueprint(
    APPNAME, __name__, url_prefix='/~', static_url_path='/static',
    template_folder='bundle', static_folder='bundle/static',
    subdomain=config.SUBDOMAIN,
)


@p5bundle.before_request
def parse_p5():
    g.p5 = Portal5(request)


def mimetype(mime_):
    types = {
        'css': 'text/css',
        'js': 'application/javascript',
        'json': 'application/json',
    }

    def wrapper(view_func, mime=mime_):
        if mime not in types:
            return view_func
        mime = types[mime]

        @wraps(view_func)
        def add_type(*args, **kwargs):
            out = common.wrap_response(view_func(*args, **kwargs))
            if out.status_code < 300:
                out.mimetype = mime
            return out

        return add_type
    return wrapper


@p5bundle.route('/access/<string:jwt>/service-worker.js')
@security.requires_jwt_in('path', allow_expired=True)
@security.rejects_jwt_where(security.jwt_is_invalid)
@security.rejects_jwt_where(security.jwt_has_expired, response=lambda **_: ('', 304))
@security.rejects_jwt_where(Portal5.jwt_has_invalid_claim(reasons=('init', 'update')))
@security.rejects_jwt_where(security.jwt_has_unauthorized_subject)
@mimetype('js')
def service_worker():
    variant = get_jwt_claims()['variant']
    p5: Portal5 = g.p5
    p5.set_bitmask(variant)
    worker_settings = p5.make_worker_settings(get_raw_jwt()['jti'], request, current_app, g)
    worker = Response(
        render_template('scripts/service-worker.js', settings=worker_settings, requires_bundle=p5.requires_bundle),
        headers={'Service-Worker-Allowed': '/'},
    )
    worker.set_cookie(p5.PREFS_COOKIE, str(p5.get_bitmask()), path='/', secure=True, httponly=True)
    return worker


@p5bundle.route('/scripts/responsive/preferences.js')
@mimetype('js')
def preferences():
    p5: Portal5 = g.p5
    return render_template('scripts/responsive/preferences.js', **p5.make_dependency_dicts())


@p5bundle.route('/scripts/<path:file>')
@mimetype('js')
def scripts(file):
    return render_template(f'scripts/{file}')
