# filter.py
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

import time
import secrets
from functools import wraps
from typing import Dict, Union
from urllib.parse import SplitResult, urlsplit

import requests
from flask import Request, Response, abort, g, request, _app_ctx_stack
from flask_jwt_extended import JWTManager, decode_token, get_jwt_identity, get_raw_jwt, verify_jwt_in_request
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt.exceptions import PyJWTError
from werkzeug.datastructures import MultiDict

from . import common

request: Request

jwt = JWTManager()


def setup_jwt(app):
    jwt.init_app(app)


def requires_jwt_authorization(view_func):
    @wraps(view_func)
    def decode(*args, **kwargs):
        try:
            verify_jwt_in_request()
            g.jwt = get_raw_jwt()
            return view_func(*args, **kwargs)
        except (JWTExtendedException, PyJWTError) as e:
            return abort(401, e)
    return decode


def requires_jwt_in(where, allow_expired=False):
    getters = {
        'path': lambda kwargs: kwargs.pop('jwt', None),
        'params': lambda _=None: request.args.get('jwt'),
        'form': lambda _=None: request.form.get('jwt'),
    }
    if where not in getters:
        raise ValueError(f'Cannot get JWT from "{where}"')

    def wrapper(view_func):
        @wraps(view_func)
        def decode(*args, **kwargs):
            jwt = getters[where](kwargs)
            if not jwt:
                token = dict(exception=ValueError(f'No token found in {where}'))
            else:
                try:
                    token = decode_token(jwt, allow_expired=allow_expired)
                except (JWTExtendedException, PyJWTError) as e:
                    token = dict(exception=e)

            g.jwt = token
            _app_ctx_stack.top.jwt = g.jwt
            _app_ctx_stack.top.jwt_header = f'Bearer {jwt}'

            return view_func(*args, **kwargs)
        return decode

    return wrapper


def rejects_jwt_where(*tests, aborts_with=(401,), response=None):
    def wrapper(view_func):
        @wraps(view_func)
        def verify(*args, **kwargs):
            if any((t(*args, **kwargs) for t in tests)):
                return response(*args, **kwargs) if response else abort(*aborts_with)
            return view_func(*args, **kwargs)
        return verify
    return wrapper


def jwt_is_invalid(*args, **kwargs):
    return isinstance(get_raw_jwt().get('exception', None), Exception)


def jwt_has_unauthorized_subject(*args, **kwargs):
    return get_jwt_identity() != request.remote_addr


def jwt_has_expired(*args, **kwargs):
    return time.time() >= get_raw_jwt()['exp']


def access_control_same_origin(view_func):
    @wraps(view_func)
    def postprocess(*args, **kwargs):
        out = common.wrap_response(view_func(*args, **kwargs))
        out.headers['Access-Control-Allow-Origin'] = g.server_origin
        return out
    return postprocess


def access_control_allow_origin(origin):
    def wrapper(view_func):
        @wraps(view_func)
        def postprocess(*args, **kwargs):
            out = common.wrap_response(view_func(*args, **kwargs))
            out.headers['Access-Control-Allow-Origin'] = origin
            return out
        return postprocess
    return wrapper


def csp_no_frame_ancestor(view_func):
    @wraps(view_func)
    def postprocess(*args, **kwargs):
        out = common.wrap_response(view_func(*args, **kwargs))
        out.headers.add('X-Frame-Options', 'DENY')
        update_csp(out, "frame-ancestors 'none'", g_=g)
        return out
    return postprocess


def csp_directives(*directives):
    def wrapper(view_func):
        @wraps(view_func)
        def postprocess(*args, **kwargs):
            out = common.wrap_response(view_func(*args, **kwargs))
            update_csp(out, *directives, g_=g)
            return out
        return postprocess
    return wrapper


def csp_recommendations(view_func):
    @wraps(view_func)
    def add_csp(*args, **kwargs):
        out = common.wrap_response(view_func(*args, **kwargs))
        update_csp(
            out,
            "default-src 'self'", "img-src 'self' data:",
            'font-src fonts.gstatic.com', "frame-ancestors 'none'",
            f"style-src 'self' static.{g.sld} fonts.googleapis.com",
            "script-src 'self'", g_=g,
        )
        return out
    return add_csp


def csp_nonce(*directives):
    def wrapper(view_func):
        @wraps(view_func)
        def supply_nonce(*args, **kwargs):
            nonce = {d: secrets.token_hex(8) for d in directives}
            g.csp_nonce = nonce
            out = common.wrap_response(view_func(*args, **kwargs))
            update_csp(out, '; '.join([f"{k} 'nonce-{v}'" for k, v in nonce.items()]), g_=g)
            return out
        return supply_nonce
    return wrapper


def referrer_policy(policy):
    def wrapper(view_func):
        @wraps(view_func)
        def referrer(*args, **kwargs):
            out = common.wrap_response(view_func(*args, **kwargs))
            out.headers['Referrer-Policy'] = policy
            return out
        return referrer
    return wrapper


def update_csp(response, *directives, method=set.union, g_=None, report_only=False):
    header = 'Content-Security-Policy' if not report_only else 'Content-Security-Policy-Report-Only'
    policies = None
    if g_:
        policies = getattr(g_, 'csp', None)
    if not policies:
        csp = response.headers.get(header, None)
        if csp:
            policies = [p.strip().split(' ') for p in csp.split(';') if p]
            policies = {p[0]: set(p[1:]) for p in policies}
        else:
            policies = {}
    directives = [d.strip().split(' ') for d in directives if d]
    updates = {d[0]: set(d[1:]) for d in directives}
    for k, v in updates.items():
        values = policies.setdefault(k, set())
        policies[k] = method(v, values)
    g_.csp = policies
    response.headers[header] = '; '.join([' '.join([k, *v]) for k, v in policies.items()])


def allow_referrer(*urls, allow_self=True, samesite=True):
    urls = set(urls)

    def wrapper(view_func):
        @wraps(view_func)
        def guard(*args, **kwargs):
            if allow_self and request.referrer == request.url:
                return view_func(*args, **kwargs)
            referrer = urlsplit(request.referrer)
            referrer = referrer.path if samesite else referrer.geturl()
            if referrer not in urls:
                abort(403)
            return view_func(*args, **kwargs)
        return guard
    return wrapper


def conceal_origin(find, replace, url: SplitResult, **multidicts: MultiDict) -> Dict[str, Union[SplitResult, MultiDict]]:
    path = url.path.replace(find, replace)
    query = url.query.replace(find, replace)
    url = SplitResult(url.scheme, url.netloc, path, query, url.fragment)

    for name in multidicts:
        dict_ = multidicts[name]
        multidicts[name] = type(dict_)({
            k: list(map(lambda v: v.replace(find, replace), dict_.getlist(k, type=str))) for k in dict_.keys()
        })

    return dict(url=url, **multidicts)


def enforce_cors(remote: requests.Response, response: Response, *, request_origin, server_origin, **kwargs) -> None:
    allow_origin = remote.headers.get('Access-Control-Allow-Origin', None)
    if not allow_origin or allow_origin == '*':
        return

    if allow_origin != request_origin:
        response.headers.pop('Access-Control-Allow-Origin', None)
        return

    response.headers['Access-Control-Allow-Origin'] = server_origin


def break_csp(remote: requests.Response, response: Response, *, server_origin, request_origin, **kwargs) -> None:
    non_source_directives = {
        'plugin-types', 'sandbox',
        'block-all-mixed-content', 'referrer',
        'require-sri-for', 'require-trusted-types-for',
        'trusted-types', 'upgrade-insecure-requests',
    }
    adverse_directives = {'report-uri', 'report-to'}

    for header in {'Content-Security-Policy', 'Content-Security-Policy-Report-Only'}:
        csp = remote.headers.get(header, None)
        if not csp:
            continue

        policies = [p.strip().split(' ') for p in csp.split(';')]
        policies = {p[0]: set(p[1:]) for p in policies if p[0] not in adverse_directives}

        for directive, options in policies.items():
            if directive in non_source_directives:
                continue
            if "'none'" not in options:
                options.add(server_origin)
            if "'self'" in options:
                options.add(request_origin)

        broken_csp = '; '.join([' '.join([k, *v]) for k, v in policies.items()])
        response.headers[header] = broken_csp


def add_clear_site_data_header(remote: requests.Response, response: Response, *, request_mode, request_origin, **kwargs):
    remote_url = urlsplit(remote.url)
    remote_origin = f'{remote_url.scheme}://{remote_url.netloc}'
    if request_mode == 'navigate' and request_origin != remote_origin:
        response.headers.add('Clear-Site-Data', '"cookies"')
