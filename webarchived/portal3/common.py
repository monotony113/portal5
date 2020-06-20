# common.py
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

from operator import attrgetter
from typing import Tuple
from urllib.parse import urljoin, urlsplit, SplitResult

from flask import request, g
from requests.cookies import RequestsCookieJar


def metadata_from_request():
    g.req_url_parts = urlsplit(request.url)
    g.req_headers = dict(**request.headers)
    g.req_cookies = dict(**request.cookies)
    g.req_data = dict(**request.form) or request.data
    g.req_fetch_mode = g.req_headers.get('Sec-Fetch-Mode')
    g.server = f'{g.req_url_parts.scheme}://{g.req_url_parts.netloc}'

    referrer = g.req_headers.get('Referer')
    g.req_referrer = urlsplit(referrer) if referrer else None

    return referrer


def masquerade_urls(cookie_jar: RequestsCookieJar, headers: dict) -> Tuple[list, dict]:
    request: SplitResult = g.req_url_parts
    remote: SplitResult = g.remote_url_parts
    headers = dict(**headers)
    cookies = list()

    get_cookie_main = attrgetter('name', 'value', 'expires')
    get_cookie_secure = attrgetter('secure')
    get_cookie_rest = attrgetter('_rest')
    set_cookie_args = ('key', 'value', 'expires', 'path', 'domain', 'secure', 'httponly', 'samesite')

    for cookie in cookie_jar:
        cookie_main = get_cookie_main(cookie)
        cookie_is_secure = get_cookie_secure(cookie)
        _rest = get_cookie_rest(cookie)
        cookie_domain = request.netloc if cookie.domain_specified else None
        cookie_path = f'{g.prefix}{remote.scheme}://{remote.netloc}{cookie.path}'.rstrip('/') if cookie.path_specified else None
        cookie_rest = ('HttpOnly' in _rest, _rest.get('SameSite'))
        cookies.append(dict(zip(set_cookie_args, [*cookie_main, cookie_path, cookie_domain, cookie_is_secure, *cookie_rest])))

    if 'Location' in headers:
        headers['Location'] = f'{g.server}{g.prefix}{urljoin(remote.geturl(), headers["Location"])}'

    return cookies, headers
