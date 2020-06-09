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


from operator import attrgetter
from typing import Tuple
from textwrap import dedent
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote, SplitResult

import requests
from requests.cookies import RequestsCookieJar
from flask import stream_with_context, Blueprint, Flask, Request, Response, make_response, render_template, redirect, g
from flask import request as req

current_app: Flask
req: Request
portal3 = Blueprint('portal3', __name__, template_folder='templates')


@portal3.route('/')
def home():
    return render_template('portal3/index.html', protocol=g.req_url_parts.scheme, domain=g.req_url_parts.netloc)


@portal3.url_value_preprocessor
def collect_data_from_request(endpoint, values: dict):
    g.req_url_parts = urlsplit(req.url)
    g.req_headers = dict(**req.headers)
    g.req_cookies = dict(**req.cookies)
    g.req_data = dict(**req.form) or req.data
    g.req_fetch_mode = g.req_headers.get('Sec-Fetch-Mode')
    g.req_referrer = urlsplit(g.req_headers.get('Referer', ''))

    if 'remote' in values:
        g.remote_url_parts = normalize_url(unquote(values['remote']))

        g.base_scheme = g.req_cookies.get('portal3-remote-scheme')
        g.base_domain = g.req_cookies.get('portal3-remote-domain')
        g.referred_by = g.req_cookies.get('portal3-remote-referrer')
        g.referred_by = g.referred_by and urlsplit(g.referred_by)

        g.direct_request = g.req_cookies.get('portal3-remote-redirect', False)
        g.server = f'{g.req_url_parts.scheme}://{g.req_url_parts.netloc}'
        g.prefix = '/portal3/'

        g.req_headers.pop('Host', None)
        g.req_headers.pop('Referer', None)


@portal3.route('/direct/<path:remote>', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD'))
def forward_direct(remote):
    g.direct_request = True
    g.prefix = '/portal3/direct/'
    return forward(remote)


@portal3.route('/<path:remote>', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD'))
def forward(remote):
    remote_parts = g.remote_url_parts

    if (
        not g.direct_request
        and (not g.req_fetch_mode or g.req_fetch_mode not in ('navigate', 'nested-navigate'))
        and g.referred_by
        and remote_parts.netloc != g.base_domain
    ):
        base_url_parts = urlsplit(urljoin(g.referred_by.geturl(), '.'))
        subpath = f'{g.remote_url_parts.netloc}/{g.remote_url_parts.path}'.lstrip('/')
        remote_parts = urlsplit(urljoin(base_url_parts.geturl(), subpath))

    if remote_parts.scheme not in ('http', 'https'):
        if not remote_parts.scheme:
            query = req.query_string.decode("utf8")
            remote = f'https://{remote}'
            if query:
                remote = f'{remote}?{query}'
            return render_template('portal3/missing-protocol.html', server=g.server, prefix=g.prefix, remote=remote), 400
        else:
            return f'Unsupported URL scheme "{remote_parts.scheme}"', 400
    if not remote_parts.netloc:
        return 'No website specified.', 400

    if g.remote_url_parts is remote_parts:
        url = remote_parts.geturl()
        try:
            requests_res, res = pipe_request(
                url,
                method=req.method,
                headers=g.req_headers,
                params=req.args, data=g.req_data, cookies=g.req_cookies
            )
        # except Exception as e:
        #     raise e
        except requests.HTTPError as e:
            return make_response(f'Got HTTP {e.response.status_code} while accessing {url}', e.response.status_code)
        except requests.exceptions.TooManyRedirects:
            return make_response(f'Unable to access {url}; too many redirects.', 302)
        except requests.exceptions.SSLError:
            return make_response(f'Unable to access {url}; an SSL error occured, remote server may not support HTTPS.', 404)
        except requests.ConnectionError:
            return make_response(f'Unable to access {url}; resource may not exist, or be available to the server, or outgoing traffic at the server may be disrupted.', 404)
        except requests.RequestException:
            return make_response(f'Unable to access {url}; an unspecified error occured while connecting to resource.', 500)
        except Exception as e:
            return make_response(dedent(f"""
            <code><pre>
            An unspecified error occured while server was processing this request.
            Parsed URL: {url}
            Error name: {e.__class__.__name__}
            </pre></code>
            """), 500)

        cookies, headers = masquerade(requests_res.cookies, res.headers)
        for cookie in cookies:
            res.set_cookie(**cookie)
        res.headers.update(headers)

        if not g.direct_request:
            set_cookies(res, scheme=remote_parts.scheme, domain=remote_parts.netloc, max_age=None)
            set_cookies(res, path=f'{g.prefix}{urljoin(url, ".")}', referrer=remote_parts.geturl())

        return res

    return redirect(urlunsplit(tuple([
        *urlsplit(f'{g.server}{g.prefix}{remote_parts.geturl()}')[:3],
        req.query_string.decode('utf8'), ''
    ])), 307)


def masquerade(cookie_jar: RequestsCookieJar, headers: dict) -> Tuple[list, dict]:
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
        cookie_path = f'{g.get("prefix")}{remote.scheme}://{remote.netloc}{cookie.path}'.rstrip('/') if cookie.path_specified else None
        cookie_rest = ('HttpOnly' in _rest, _rest.get('SameSite'))
        cookies.append(dict(zip(set_cookie_args, [*cookie_main, cookie_path, cookie_domain, cookie_is_secure, *cookie_rest])))

    if 'Location' in headers:
        location = urlsplit(headers['Location'])
        if location.scheme:
            headers['Location'] = f'{g.get("prefix")}{headers["Location"]}'

    return cookies, headers


def set_cookies(res, *, path='/', max_age=180, **cookies):
    for k, v in cookies.items():
        opts = dict(key=f'portal3-remote-{k}', value=v, path=path, max_age=max_age)
        res.set_cookie(**opts)


def pipe_request(url, *, method='GET', **request_kwargs) -> Tuple[requests.Response, Response]:
    remote_response = requests.request(method=method, url=url, allow_redirects=False, stream=True, **request_kwargs)

    def pipe(response: requests.Response):
        while True:
            chunk = response.raw.read(128)
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


def normalize_url(url) -> SplitResult:
    url_parts = urlsplit(url)
    if not url_parts.netloc:
        split = url_parts.path.lstrip('/').split('/', 1)
        domain = split[0]
        path = split[1] if len(split) == 2 else ''
        return SplitResult(url_parts.scheme, domain, path, url_parts.query, url_parts.fragment)
    return url_parts


def from_absolute_path():
    cookies = dict(**req.cookies)
    headers = {**req.headers}
    headers.pop('Host', None)
    res = make_response('', 404)

    if 'portal3-remote-scheme' in req.cookies:
        remote_scheme = cookies.get('portal3-remote-scheme')
        remote_domain = cookies.get('portal3-remote-domain')
        path = f'/portal3/{remote_scheme}://{remote_domain}{urlsplit(req.url).path}'
        if req.args:
            path = f'{path}?{req.query_string.decode("utf8")}'
        res = redirect(path, 307)
        set_cookies(res, path=path, redirect='true', max_age=30)

    return res
