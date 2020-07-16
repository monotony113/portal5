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

import secrets
from functools import wraps
from typing import Dict, Union
from urllib.parse import SplitResult, urlsplit

import requests
from flask import Request, Response, abort, g, request
from jwt import InvalidTokenError
from werkzeug.datastructures import MultiDict

from . import common
from .jwtkit import JWTKit, get_jwt, verify_claims, verify_exp

request: Request

jwt_kit = JWTKit()


def setup_jwt(app):
    jwt_kit.init_app(app)


def expects_jwt_in(where, *, key='jwt', **jwtkit_kwargs):
    getters = {
        'path': lambda kwargs: kwargs.pop(key, None),
        'params': lambda _=None: request.args.get(key),
        'form': lambda _=None: request.form.get(key),
        'cookies': lambda _=None: request.cookies.get(key),
    }

    if where in getters:
        getter = getters[where]
    elif callable(where):
        getter = where
    else:
        raise ValueError(f'Cannot get JWT from "{where}"')

    def wrapper(view_func):
        @wraps(view_func)
        def decode(*args, **kwargs):
            jwtkit = JWTKit.get_jwtkit()
            jwt = getter(kwargs) or ''
            for token in jwt.split(' '):
                try:
                    jwtkit.decode_token(token.strip(), **jwtkit_kwargs)
                except InvalidTokenError:
                    pass
            return view_func(*args, **kwargs)
        return decode
    return wrapper


def rejects_jwt_where(*tests, respond_with=(401,), **query):
    def wrapper(view_func):
        @wraps(view_func)
        def verify(*args, **kwargs):
            jwt = get_jwt(**query)
            if any((test(jwt, *args, **kwargs) for test in tests)):
                return respond_with(*args, **kwargs) if callable(respond_with) else abort(*respond_with)
            return view_func(*args, **kwargs)
        return verify
    return wrapper


def jwt_is_not_supplied(jwt, *args, **kwargs):
    return not jwt


def jwt_has_invalid_subject(jwt, *args, **kwargs):
    return jwt.get('sub') != request.remote_addr


def jwt_has_expired(jwt, *args, **kwargs):
    return not verify_exp(jwt)


def jwt_does_not_claim(**claims):
    def check(jwt, *args, **kwargs):
        return not verify_claims(jwt, **claims)
    return check


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


def csp_protected(view_func):
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

    return {'url': url, **multidicts}


def enforce_cors(remote: requests.Response, response: Response, *, request_mode, request_origin, server_origin, **kwargs) -> None:
    remote_origin = urlsplit(remote.url)
    remote_origin = f'{remote_origin.scheme}://{remote_origin.netloc}'
    allow_origin = remote.headers.get('Access-Control-Allow-Origin', None)
    if allow_origin == '*' or not allow_origin and request_mode != 'cors':
        return

    if allow_origin and allow_origin != request_origin:
        response.headers.pop('Access-Control-Allow-Origin', None)
        return

    if not allow_origin and request_mode == 'cors' and request_origin != remote_origin:
        return abort(403)

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
            if not directive:
                continue
            if directive in non_source_directives:
                continue
            if "'strict-dynamic'" in options:
                continue
            if "'none'" not in options:
                options.add(server_origin)
            if "'self'" in options:
                options.add(request_origin)

        broken_csp = '; '.join([' '.join([k, *filter(None, v)]) for k, v in policies.items()])
        response.headers[header] = broken_csp


def add_clear_site_data_header(remote: requests.Response, response: Response, *, request_mode, request_origin, **kwargs):
    remote_url = urlsplit(remote.url)
    remote_origin = f'{remote_url.scheme}://{remote_url.netloc}'
    if request_mode == 'navigate' and request_origin != remote_origin:
        response.headers.add('Clear-Site-Data', '"cookies"')


def clear_site_data(*types):
    if not types:
        types = ('cache', 'cookies', 'storage')

    def wrapper(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            out = common.wrap_response(view_func(*args, **kwargs))
            out.headers['Clear-Site-Data'] = ', '.join([f'"{t}"' for t in types])
            return out
        return wrapper
    return wrapper
