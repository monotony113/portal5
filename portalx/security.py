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

from functools import wraps
from typing import Dict, Union
from urllib.parse import SplitResult, urlsplit

import requests
from flask import Response, abort, g, request
from werkzeug.datastructures import MultiDict

from . import common


def access_control_same_origin(view_func):
    @wraps(view_func)
    def postprocess(*args, **kwargs):
        out = common.ensure_response(view_func(*args, **kwargs))
        out.headers['Access-Control-Allow-Origin'] = g.server_origin
        return out
    return postprocess


def access_control_allow_origin(origin):
    def wrapper(view_func):
        @wraps(view_func)
        def postprocess(*args, **kwargs):
            out = common.ensure_response(view_func(*args, **kwargs))
            out.headers['Access-Control-Allow-Origin'] = origin
            return out
        return postprocess
    return wrapper


def csp_no_frame_ancestor(view_func):
    @wraps(view_func)
    def postprocess(*args, **kwargs):
        out = common.ensure_response(view_func(*args, **kwargs))
        out.headers.add('X-Frame-Options', 'DENY')
        out.headers.add('Content-Security-Policy', "frame-ancestors 'none';")
        return out
    return postprocess


def csp_directives(*directives):
    def wrapper(view_func):
        @wraps(view_func)
        def postprocess(*args, **kwargs):
            out = common.ensure_response(view_func(*args, **kwargs))
            out.headers['Content-Security-Policy'] = '; '.join(directives)
            return out
        return postprocess
    return wrapper


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
