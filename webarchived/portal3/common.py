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
from typing import Tuple
from urllib.parse import urljoin, urlsplit, unquote, SplitResult

import requests
from flask import Request, Response, stream_with_context, render_template, abort
from werkzeug.exceptions import HTTPException


def metadata_from_request(g, request, endpoint, values):
    g.request_url_parts = urlsplit(request.url)
    g.request_headers = dict(**request.headers)
    g.request_cookies = dict(**request.cookies)
    g.request_data = dict(**request.form) or request.data
    g.request_fetch_mode = g.request_headers.get('Sec-Fetch-Mode')

    referrer = g.request_headers.get('Referer')
    g.request_referrer = urlsplit(referrer) if referrer else None

    if 'remote' in values:
        g.remote_url_parts = normalize_url(unquote(values['remote']))

    g.server = f'{g.request_url_parts.scheme}://{g.request_url_parts.netloc}'
    g.prefix = f'/{request.blueprint}/'

    g.request_headers.pop('Referer', None)
    g.request_headers.pop('Host', None)


def normalize_url(url) -> SplitResult:
    url_parts = urlsplit(url)
    if not url_parts.netloc:
        split = url_parts.path.lstrip('/').split('/', 1)
        domain = split[0]
        path = split[1] if len(split) == 2 else ''
        return SplitResult(url_parts.scheme, domain, path, url_parts.query, url_parts.fragment)
    return url_parts


def guard_incoming_url(g, remote: SplitResult, flask_request: Request):
    if remote.scheme not in ('http', 'https'):
        if not remote.scheme:
            query = flask_request.query_string.decode("utf8")
            remote = f'https:{remote.geturl()}'
            if query:
                remote = f'{remote}?{query}'
            return Portal3MissingProtocol(g.server, g.prefix, remote)
        else:
            return Portal3BadRequest(f'Unsupported URL scheme "{remote.scheme}"')

    if not remote.netloc:
        return Portal3BadRequest(f'URL <code>{remote.geturl()}</code> missing website domain name or location.')

    return None


def pipe_request(url, *, method='GET', **request_kwargs) -> Tuple[requests.Response, Response]:
    try:
        remote_response = requests.request(method=method, url=url, allow_redirects=False, stream=True, **request_kwargs)

        def pipe(response: requests.Response):
            while True:
                chunk = response.raw.read(65536)
                if not chunk:
                    break
                yield chunk

        headers = dict(**remote_response.headers)
        headers.pop('Set-Cookie', None)
        flask_response = Response(
            stream_with_context(pipe(remote_response)),
            status=remote_response.status_code,
            headers=headers,
        )
        return remote_response, flask_response

    # except Exception as e:
    #     raise e
    except requests.HTTPError as e:
        return abort(int(e.response.status_code), f'Got HTTP {e.response.status_code} while accessing <code>{url}</code>')
    except requests.exceptions.TooManyRedirects:
        return abort(400, f'Unable to access <code>{url}</code><br/>Too many redirects.')
    except requests.exceptions.SSLError:
        return abort(502, f'Unable to access <code>{url}</code><br/>An SSL error occured, remote server may not support HTTPS.')
    except requests.ConnectionError:
        return abort(502, f'Unable to access <code>{url}</code><br/>Resource may not exist, or be available to the server, or outgoing traffic at the server may be disrupted.')
    except Exception as e:
        return abort(500, dedent(f"""
        <pre><code>An unhandled error occured while processing this request.
        Parsed URL: {url}
        Error name: {e.__class__.__name__}</code></pre>
        """))


def masquerade_urls(g, remote: requests.Response, response: Response) -> Tuple[list, dict]:
    request_url: SplitResult = g.request_url_parts
    remote_url: SplitResult = g.remote_url_parts
    cookie_jar = remote.cookies
    headers = dict(**response.headers)

    cookies = list()
    get_cookie_main = attrgetter('name', 'value', 'expires')
    get_cookie_secure = attrgetter('secure')
    get_cookie_rest = attrgetter('_rest')
    set_cookie_args = ('key', 'value', 'expires', 'path', 'domain', 'secure', 'httponly', 'samesite')

    for cookie in cookie_jar:
        cookie_main = get_cookie_main(cookie)
        cookie_is_secure = get_cookie_secure(cookie)
        _rest = get_cookie_rest(cookie)
        cookie_domain = request_url.netloc if cookie.domain_specified and 'localhost' not in request_url.netloc else None
        cookie_path = f'{g.prefix}{remote_url.scheme}://{remote_url.netloc}{cookie.path}'.rstrip('/') if cookie.path_specified else None
        cookie_rest = ('HttpOnly' in _rest, _rest.get('SameSite'))
        cookies.append(dict(zip(set_cookie_args, [*cookie_main, cookie_path, cookie_domain, cookie_is_secure, *cookie_rest])))

    if 'Location' in headers:
        headers['Location'] = f'{g.server}{g.prefix}{urljoin(remote_url.geturl(), headers["Location"])}'

    for cookie in cookies:
        response.set_cookie(**cookie)
    response.headers.update(headers)

    return cookies, headers


class Portal3Exception(Exception):
    pass


class Portal3HTTPException(HTTPException):
    def __init__(self, description=None, response=None, status=500, unsafe=False, **kwargs):
        super().__init__(description=description, response=response, **kwargs)
        self.code = status
        self.unsafe = unsafe

    def get_response(self, environ=None):
        return Response(render_template('httperr.html', statuscode=self.code, message=self.description or '', unsafe=self.unsafe), self.code)


class Portal3BadRequest(Portal3HTTPException):
    def __init__(self, description, response=None, **kwargs):
        super().__init__(description=description, response=response, **kwargs)
        self.code = 400


class Portal3MissingProtocol(Portal3BadRequest):
    def __init__(self, server, prefix, remote, **kwargs):
        super().__init__(None, **kwargs)
        self.server = server
        self.prefix = prefix
        self.remote = remote

    def get_response(self, environ=None):
        return Response(render_template('portal3/missing-protocol.html', server=self.server, prefix=self.prefix, remote=self.remote), self.code)
