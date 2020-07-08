# blueprint.py
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

from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

from flask import Blueprint, Request, abort, current_app, g, redirect, render_template, request

from .. import common

APPNAME = 'portal3'
request: Request
portal3 = Blueprint(APPNAME, __name__, template_folder='templates', subdomain=APPNAME)


@portal3.route('/')
@portal3.route('/index.html')
def home():
    return render_template(f'{APPNAME}/index.html')


@portal3.url_value_preprocessor
def parse_url(endpoint, values):
    if 'requested' in values:
        values['requested'] = common.normalize_url(unquote(values['requested']))


@portal3.route('/<path:requested>', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD'))
@portal3.route('/direct/<path:requested>', defaults={'direct_request': True}, methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD'))
def forward(requested, direct_request=False):
    url_ = requested

    fetch_mode = request.headers.get('Sec-Fetch-Mode', None)
    referrer = urlsplit(request.referrer) if request.referrer else None

    direct_request = direct_request or request.cookies.get(f'{APPNAME}-remote-redirect', False)

    base_scheme = request.cookies.get(f'{APPNAME}-remote-scheme')
    base_domain = request.cookies.get(f'{APPNAME}-remote-domain')
    referred_by = request.cookies.get(f'{APPNAME}-remote-referrer')
    referred_by = referred_by and urlsplit(referred_by)
    if base_scheme and referrer and not referred_by:
        referrer = request.referrer[len(g.server_origin):]
        referred_by = urlsplit(referrer)

    if (
        not direct_request
        and (not fetch_mode or fetch_mode not in {'navigate', 'nested-navigate'})
        and referred_by and referred_by.scheme and referred_by.netloc
        and url_.netloc != base_domain
    ):
        urlsplit_base = urlsplit(urljoin(referred_by.geturl(), '.'))
        subpath = f'{url_.netloc}/{url_.path}'.strip('/')
        url_ = urlsplit(urljoin(urlsplit_base.geturl(), subpath))

    if not url_.scheme and base_scheme:
        path = f'/{base_scheme}://{base_domain}{urlsplit(request.url).path}'
        if request.args:
            path = f'{path}?{request.query_string.decode("utf8")}'
        res = redirect(path, 307)
        set_cookies(res, path=path, redirect='true', max_age=30)
        return res

    guard = common.guard_incoming_url(g, url_, request)
    if guard:
        abort(guard)

    if url_ == requested:
        url = url_.geturl()
        kwargs = {
            'data': common.stream_request_body(request),
            **common.extract_request_info(request)
        }

        headers = kwargs['headers']
        headers.pop('Referer', None)
        headers.pop('Host', None)

        outbound_request = common.prepare_request(url, method=request.method, **kwargs)

        filters = current_app.config.get('PORTAL_URL_FILTERS')
        should_abort = filters.test(outbound_request)
        if should_abort:
            abort(should_abort)

        remote, response = common.pipe_request(outbound_request)

        common.copy_headers(remote, response, server_origin=g.server_origin)
        common.copy_cookies(remote, response, server_domain=request.host)

        if not direct_request:
            set_cookies(response, scheme=url_.scheme, domain=url_.netloc, max_age=1800)
            set_cookies(response, path=f'{urljoin(url, ".")}', referrer=url_.geturl(), max_age=1800)

        return response

    return redirect(urlunsplit((
        *urlsplit(f'{request.scheme}://{request.host}/{url_.geturl()}')[:3],
        request.query_string.decode('utf8'), '',
    )), 307)


def set_cookies(res, *, path='/', max_age=180, **cookies):
    for k, v in cookies.items():
        opts = {'key': f'{APPNAME}-remote-{k}', 'value': v, 'path': path, 'max_age': max_age}
        res.set_cookie(**opts)
