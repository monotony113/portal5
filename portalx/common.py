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
from textwrap import dedent
from typing import Tuple, Dict
from urllib.parse import urljoin, urlsplit, unquote, SplitResult

import requests
from flask_babel import _
from flask import current_app, Request, Response, stream_with_context, abort
from werkzeug.datastructures import Headers, MultiDict
from werkzeug.exceptions import HTTPException

from . import exception
from .security import RequestTest


def metadata_from_request(g, request: Request, endpoint, values):
    g.request_headers = Headers(request.headers)
    g.request_params = MultiDict(request.args)
    g.request_cookies = MultiDict(request.cookies)
    g.request_fetch_mode = g.request_headers.get('Sec-Fetch-Mode')

    g.request_referrer = urlsplit(request.referrer) if request.referrer else None

    if 'requested' in values:
        g.urlsplit_requested = normalize_url(unquote(values['requested']))

    g.request_headers.pop('Referer', None)
    g.request_headers.pop('Host', None)

    g.request_metadata = dict(headers=g.request_headers, params=g.request_params, cookies=g.request_cookies)
    g.request_payload = request.stream if request.content_length else None


def normalize_url(url) -> SplitResult:
    url_parts = urlsplit(url)
    if not url_parts.netloc:
        split = url_parts.path.lstrip('/').split('/', 1)
        domain = split[0]
        path = split[1] if len(split) == 2 else ''
        return SplitResult(url_parts.scheme, domain, path, url_parts.query, url_parts.fragment)
    return url_parts


def guard_incoming_url(g, requested: SplitResult, flask_request: Request):
    if requested.scheme not in ('http', 'https'):
        if not requested.scheme:
            query = flask_request.query_string.decode("utf8")
            requested = f'https:{requested.geturl()}'
            if query:
                requested = f'{requested}?{query}'
            return exception.PortalMissingProtocol(requested)
        else:
            return exception.PortalBadRequest(_('Unsupported URL scheme "%(scheme)s"', scheme=requested.scheme))

    if not requested.netloc:
        return exception.PortalBadRequest(_('URL <code>%(url)s</code> missing website domain name or location.', url=requested.geturl()))

    return None


def pipe_request(url, *, method='GET', **requests_kwargs) -> Tuple[requests.Response, Response]:
    try:
        # Annoying
        # https://github.com/psf/requests/issues/1648
        # https://github.com/psf/requests/pull/3897
        outbound = requests.Request(method=method, url=url, **requests_kwargs).prepare()
        if 'Content-Length' in outbound.headers:
            outbound.headers.pop('Transfer-Encoding', None)

        tests = current_app.config.get('PORTAL_URL_FILTERS', set())
        for t in tests:
            t: RequestTest
            should_abort = False
            try:
                should_abort = t(outbound)
            except Exception:
                pass
            if should_abort:
                abort(exception.PortalSelfProtect(url, t))

        remote_response = requests.session().send(outbound, allow_redirects=False, stream=True)

        def pipe(response: requests.Response):
            while True:
                chunk = response.raw.read(1024)
                if not chunk:
                    break
                yield chunk

        flask_response = Response(
            stream_with_context(pipe(remote_response)),
            status=remote_response.status_code,
        )
        return remote_response, flask_response

    # except Exception as e:
    #     raise e
    except HTTPException as e:
        raise e
    except requests.HTTPError as e:
        return abort(int(e.response.status_code), _('Got HTTP %(code)d while accessing <code>%(url)s</code>', code=e.response.status_code, url=url))
    except requests.exceptions.TooManyRedirects:
        return abort(400, _('Unable to access <code>%(url)s</code><br/>Too many redirects.', url=url))
    except requests.exceptions.SSLError:
        return abort(502, _('Unable to access <code>%(url)s</code><br/>An TLS/SSL error occured, remote server may not support HTTPS.', url=url))
    except requests.ConnectionError:
        return abort(502, _('Unable to access <code>%(url)s</code><br/>Resource may not exist, or be available to the server, or outgoing traffic at the server may be disrupted.', url=url))
    except Exception as e:
        return abort(500, dedent(_("""
        <pre><code>An unhandled error occured while processing this request.
        Parsed URL: %(url)s
        Error name: %(errname)s</code></pre>
        """, url=url, errname=e.__class__.__name__)))


def conceal_origin(find, replace, url: SplitResult, **multidicts: MultiDict) -> Tuple[SplitResult, Dict[str, MultiDict]]:
    path = url.path.replace(find, replace)
    query = url.query.replace(find, replace)
    url = SplitResult(url.scheme, url.netloc, path, query, url.fragment)

    for name in multidicts:
        dict_ = multidicts[name]
        multidicts[name] = type(dict_)({
            k: list(map(lambda v: v.replace(find, replace), dict_.getlist(k, type=str))) for k in dict_.keys()
        })

    return url, multidicts


def copy_headers(remote: requests.Response, response: Response, *, server_origin) -> Headers:
    remote_url: SplitResult = urlsplit(remote.url)
    headers = Headers(remote.headers.items())

    headers.pop('Set-Cookie', None)
    headers.pop('Transfer-Encoding', None)
    response.headers = headers

    if 'Location' in headers:
        headers['Location'] = f'{server_origin}/{urljoin(remote_url.geturl(), headers["Location"])}'

    response.headers.update(headers)
    return headers


def copy_cookies(remote: requests.Response, response: Response, *, server_domain) -> list:
    remote_url: SplitResult = urlsplit(remote.url)
    cookie_jar = remote.cookies

    cookies = list()
    get_cookie_main = attrgetter('name', 'value', 'expires')
    get_cookie_secure = attrgetter('secure')
    get_cookie_rest = attrgetter('_rest')
    set_cookie_args = ('key', 'value', 'expires', 'path', 'domain', 'secure', 'httponly', 'samesite')

    for cookie in cookie_jar:
        cookie_main = get_cookie_main(cookie)
        cookie_is_secure = get_cookie_secure(cookie)
        _rest = get_cookie_rest(cookie)
        cookie_domain = server_domain if cookie.domain_specified and server_domain not in ('localhost', '127.0.0.1') else None
        cookie_path = f'{remote_url.scheme}://{remote_url.netloc}{cookie.path}'.rstrip('/') if cookie.path_specified else None
        cookie_rest = ('HttpOnly' in _rest, _rest.get('SameSite', None))
        cookies.append({
            k: v
            for k, v in dict(
                zip(set_cookie_args, [*cookie_main, cookie_path, cookie_domain, cookie_is_secure, *cookie_rest])
            ).items()
            if v is not None
        })

    for cookie in cookies:
        response.set_cookie(**cookie)

    return cookies


def enforce_cors(remote: requests.Response, response: Response, *, request_origin, server_origin) -> None:
    allow_origin = remote.headers.get('Access-Control-Allow-Origin', None)
    if not allow_origin or allow_origin == '*':
        return

    if allow_origin != request_origin:
        response.headers.pop('Access-Control-Allow-Origin', None)
        return

    response.headers['Access-Control-Allow-Origin'] = server_origin
