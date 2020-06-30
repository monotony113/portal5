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

import requests
from flask import g, Response

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


def enforce_cors(remote: requests.Response, response: Response, *, request_origin, server_origin) -> None:
    allow_origin = remote.headers.get('Access-Control-Allow-Origin', None)
    if not allow_origin or allow_origin == '*':
        return

    if allow_origin != request_origin:
        response.headers.pop('Access-Control-Allow-Origin', None)
        return

    response.headers['Access-Control-Allow-Origin'] = server_origin


def break_csp(remote: requests.Response, response: Response, *, server_origin) -> None:
    non_source_directives = {
        'plugin-types', 'sandbox',
        'block-all-mixed-content', 'referrer',
        'require-sri-for', 'require-trusted-types-for',
        'trusted-types', 'upgrade-insecure-requests'
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

        broken_csp = '; '.join([' '.join([k, *v]) for k, v in policies.items()])
        response.headers[header] = broken_csp
