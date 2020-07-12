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

from flask import Blueprint, Response, abort, g, render_template, request

from .. import common, security
from ..jwtkit import get_jwt, get_private_claims, verify_claims
from . import config
from .blueprint import get_p5
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


@p5bundle.route('/scripts/controls/init.js')
@mimetype('js')
def init_with_token():
    p5 = get_p5()
    p5.issue_new_token(request.remote_addr, 'init')
    return render_template('scripts/controls/init.js')


@p5bundle.route('/access/service-worker.js')
@security.expects_jwt_in('cookies', key=Portal5.COOKIE_AUTH)
@security.rejects_jwt_where(security.jwt_is_not_supplied, respond_with=lambda *_, **__: ('', 304))
@security.rejects_jwt_where(security.jwt_has_invalid_subject, Portal5.jwt_version_is_outdated)
@mimetype('js')
def service_worker():
    p5 = get_p5()

    access_token = get_jwt()
    access_claims = get_private_claims(access_token)
    privilege = access_claims.get('privilege')
    if privilege == 'init':
        if not verify_claims(access_token, _variant=p5.get_bitmask()):
            return abort(401)
    elif privilege == 'nochange':
        return '', 304
    elif privilege == 'update':
        session_id = get_jwt(_privilege='nochange')['jti']
        session_claim = access_claims.get('session')
        if session_id != session_claim:
            return abort(401)
        p5.set_bitmask(access_claims.get('variant'))
    else:
        return abort(401)

    worker_settings = p5.make_worker_settings(None, g.server_origin)
    response = Response(
        render_template('scripts/service-worker.js', settings=worker_settings, requires_bundle=p5.requires_bundle),
        headers={'Service-Worker-Allowed': '/'},
    )
    p5.clear_tokens()
    return response


@p5bundle.route('/scripts/responsive/preferences.js')
@mimetype('js')
def preferences():
    return render_template('scripts/responsive/preferences.js', **get_p5().make_dependency_dicts())


@p5bundle.route('/scripts/<path:file>')
@mimetype('js')
def scripts(file):
    res = Response(render_template(f'scripts/{file}'))
    res.headers['Cache-Control'] = 'no-store'
    # res.add_etag()
    return res


p5bundle.after_request(Portal5.postprocess(get_p5))
