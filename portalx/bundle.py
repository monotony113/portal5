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

import base64
import json
from functools import wraps

from flask import Blueprint, Response, abort, g, render_template, request

from . import endpoints, i18n
from .app import get_p5
from .portal5 import Portal5
from .utils import fetch, security
from .utils.jwtkit import get_jwt, get_private_claims, verify_claims

APPNAME = 'bundle'
bundle = Blueprint(
    APPNAME, __name__, url_prefix='/~', template_folder='bundle',
    static_folder=None, static_url_path=None,
)


@bundle.before_app_first_request
def setup():
    endpoints.resolve_client_handlers(APPNAME)


@bundle.before_request
def parse_p5():
    g.p5 = Portal5(request)
    i18n.override_language(g.p5.get_lang())


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
            out = fetch.wrap_response(view_func(*args, **kwargs))
            if out.status_code < 300:
                out.mimetype = mime
            return out

        return add_type
    return wrapper


def get_public_path(prefix='public'):
    prefix = prefix + '/' if prefix else ''
    return f'{prefix}{request.path[3:]}'


@bundle.route('/client/init.js')
@security.clear_site_data('cookies', 'storage')
@mimetype('js')
def init_with_token():
    p5 = get_p5()
    p5.issue_new_token(request.remote_addr, 'init')
    return render_template(get_public_path())


@bundle.route('/sw.js')
@security.expects_jwt_in('cookies', key=Portal5.COOKIE_AUTH)
@security.rejects_jwt_where(security.jwt_is_not_supplied, respond_with=lambda *__, **_: ('', 304))
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
        p5.signals = access_claims.get('signals')
    else:
        return abort(401)

    settings, rules = p5.make_worker_settings(None, g.server_map['origins']['main'])
    response = Response(
        render_template(
            get_public_path(),
            settings=settings,
            url_rules=rules,
        ),
        headers={'Service-Worker-Allowed': '/'},
    )
    p5.clear_tokens()
    return response


@bundle.route('/client/preferences.js')
@mimetype('js')
def preferences():
    return render_template(get_public_path(), **get_p5().make_dependency_dicts())


@bundle.route('/client/injection.js')
@endpoints.client_side_handler('passthrough', mode=('no-cors',), referrer=None)
@mimetype('js')
def dispatch_observer():
    try:
        args = json.loads(base64.b64decode(request.args.get('args')).decode())
    except (TypeError, ValueError, json.JSONDecodeError):
        return abort(400)
    return render_template(get_public_path(), **args)


@bundle.route('/injection-manager.html')
@bundle.route('/injection-manager~fonts.html')
@endpoints.client_side_handler('passthrough', mode=('same-origin',), referrer=None)
def injection_manager_template():
    return render_template(get_public_path('www'))


@bundle.route('/client/<path:file>')
@bundle.route('/client/async-css.js')
@endpoints.client_side_handler('passthrough', mode=('no-cors',), referrer=None)
@mimetype('js')
def scripts(file=None):
    return Response(render_template(get_public_path()))


bundle.after_request(Portal5.postprocess(get_p5))
