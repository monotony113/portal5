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
from urllib.parse import SplitResult, urljoin, urlsplit

import requests
from flask import Request, Response, abort, stream_with_context
from werkzeug.datastructures import Headers, MultiDict
from werkzeug.wrappers.response import Response as BaseResponse

from . import exceptions


def extract_request_info(request: Request):
    return {
        'headers': Headers(request.headers),
        'params': MultiDict(request.args),
        'cookies': MultiDict(request.cookies),
    }


def stream_request_body(request: Request):
    return request.stream if request.content_length else None


def normalize_url(url) -> SplitResult:
    url_parts = urlsplit(url)
    if not url_parts.netloc:
        split = url_parts.path.lstrip('/').split('/', 1)
        domain = split[0]
        path = split[1] if len(split) == 2 else ''
        return SplitResult(url_parts.scheme, domain, path, url_parts.query, url_parts.fragment)
    return url_parts


def guard_incoming_url(g, requested: SplitResult, flask_request: Request):
    if requested.scheme not in {'http', 'https'}:
        if not requested.scheme:
            query = flask_request.query_string.decode('utf8')
            requested = f'https:{requested.geturl()}'
            if query:
                requested = f'{requested}?{query}'
            return exceptions.PortalMissingProtocol(requested)
        return exceptions.PortalBadRequest(f'Unsupported URL scheme "{requested.scheme}"')
    if not requested.netloc:
        return exceptions.PortalBadRequest(f'URL <code>{requested.geturl()}</code> missing website domain name or location.')

    return None


def prepare_request(url, *, method='GET', filters=None, **requests_kwargs) -> requests.PreparedRequest:
    # Annoying
    # https://github.com/psf/requests/issues/1648
    # https://github.com/psf/requests/pull/3897
    outbound = requests.Request(method=method, url=url, **requests_kwargs).prepare()
    if 'Content-Length' in outbound.headers:
        outbound.headers.pop('Transfer-Encoding', None)
    return outbound


def _pipe(response: requests.Response):
    while True:
        chunk = response.raw.read(1024)
        if not chunk:
            break
        yield chunk


def pipe_request(outbound: requests.PreparedRequest) -> Tuple[requests.Response, Response]:
    try:
        remote_response = requests.session().send(outbound, allow_redirects=False, stream=True)

        flask_response = Response(
            stream_with_context(_pipe(remote_response)),
            status=remote_response.status_code,
        )
        return remote_response, flask_response

    # except Exception as e:
    #     raise e
    # except HTTPException as e:
    #     raise e
    except requests.HTTPError as e:
        return abort(int(e.response.status_code), f'Got HTTP {e.response.status_code} while accessing <code>{outbound.url}</code>')
    except requests.exceptions.TooManyRedirects:
        return abort(400, f'Unable to access <code>{outbound.url}</code><br/>Too many redirects.')
    except requests.exceptions.SSLError:
        return abort(502, f'Unable to access <code>{outbound.url}</code><br/>An TLS/SSL error occured, remote server may not support HTTPS.')
    except requests.ConnectionError:
        return abort(502, f'Unable to access <code>{outbound.url}</code><br/>Resource may not exist, or be available to the server, or outgoing traffic at the server may be disrupted.')
    except Exception as e:
        return abort(500, dedent(f"""
        <pre><code>An unhandled error occured while processing this request.
        Parsed URL: {outbound.url}
        Error name: {e.__class__.__name__}</code></pre>
        """))


def copy_headers(remote: requests.Response, response: Response, *, server_origin, **kwargs) -> Headers:
    remote_url: SplitResult = urlsplit(remote.url)
    headers = Headers(remote.headers.items())

    headers.pop('Set-Cookie', None)
    headers.pop('Transfer-Encoding', None)
    response.headers = headers

    if 'Location' in headers:
        headers['Location'] = f'{server_origin}/{urljoin(remote_url.geturl(), headers["Location"])}'

    response.headers.update(headers)
    return headers


def copy_cookies(remote: requests.Response, response: Response, *, server_domain, **kwargs) -> list:
    remote_url: SplitResult = urlsplit(remote.url)
    cookie_jar = remote.cookies

    cookies = []
    get_cookie_main = attrgetter('name', 'value', 'expires')
    get_cookie_secure = attrgetter('secure')
    get_cookie_rest = attrgetter('_rest')
    set_cookie_args = ('key', 'value', 'expires', 'path', 'domain', 'secure', 'httponly', 'samesite')

    for cookie in cookie_jar:
        cookie_main = get_cookie_main(cookie)
        cookie_is_secure = get_cookie_secure(cookie)
        _rest = get_cookie_rest(cookie)
        cookie_domain = server_domain if cookie.domain_specified and server_domain not in {'localhost', '127.0.0.1'} else None
        cookie_path = f'{remote_url.scheme}://{remote_url.netloc}{cookie.path}'.rstrip('/') if cookie.path_specified else None
        cookie_rest = ('HttpOnly' in _rest, _rest.get('SameSite', None))
        cookies.append({
            k: v
            for k, v in dict(
                zip(set_cookie_args, [*cookie_main, cookie_path, cookie_domain, cookie_is_secure, *cookie_rest]),
            ).items()
            if v is not None
        })

    for cookie in cookies:
        response.set_cookie(**cookie)

    return cookies


def wrap_response(out):
    if isinstance(out, BaseResponse):
        return out
    if isinstance(out, tuple):
        return Response(*out)
    return Response(out)
