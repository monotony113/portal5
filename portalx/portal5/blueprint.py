# portal5.py
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

from urllib.parse import SplitResult, urlsplit, urljoin

from flask import Blueprint, Request, render_template, g, abort, redirect, current_app
from flask import request

from .. import common

APPNAME = 'portal5'
request: Request
portal5 = Blueprint(
    APPNAME, __name__,
    template_folder='templates', static_folder='static',
    subdomain=APPNAME
)

WORKER_VERSION = 2


@portal5.route('/')
@portal5.route('/index.html')
def home():
    return render_template(f'{APPNAME}/index.html')


@portal5.route('/install.js')
def index_js():
    return portal5.send_static_file(f'{APPNAME}/install.js')


@portal5.route('/localforage.min.js')
def localforage():
    return portal5.send_static_file(f'{APPNAME}/localforage.min.js')


@portal5.route('/service-worker.js')
def service_worker():
    if g.request_headers.get('Service-Worker') != 'script':
        return abort(403)
    worker = portal5.send_static_file(f'{APPNAME}/service-worker.js')
    worker.headers['Service-Worker-Allowed'] = '/'
    return worker


@portal5.route('/service-worker-reinstall')
def service_worker_reinstall():
    return render_template(f'{APPNAME}/worker-reinstall.html')


@portal5.url_value_preprocessor
def preprocess(endpoint, values):
    common.metadata_from_request(g, request, endpoint, values)

    worker_ver = g.request_headers.pop('X-Portal5-Worker-Version', None)
    try:
        g.request_worker_ver = int(worker_ver)
    except (TypeError, ValueError):
        g.request_worker_ver = None

    referrer = g.request_headers.pop('X-Portal5-Referrer', None)
    if referrer:
        g.request_headers['Referer'] = referrer

    origin = g.request_headers.pop('X-Portal5-Origin', None)
    if origin:
        g.request_headers['Origin'] = origin
    else:
        g.request_headers.pop('Origin', None)

    origin_domain = None
    if origin:
        origin_domain = urlsplit(origin).netloc
    elif referrer and not origin:
        origin_domain = urlsplit(referrer).netloc

    if origin_domain:
        g.remote_url_parts, g.request_metadata = common.conceal_origin(request.host, origin_domain, g.remote_url_parts, **g.request_metadata)


@portal5.route('/<path:remote>', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'))
def rewrite(remote):
    remote_parts = g.remote_url_parts
    if not remote_parts.path:
        remote_parts = SplitResult(*[*remote_parts[:2], '/', *remote_parts[3:]])
        g.remote_url_parts = remote_parts

    guard = common.guard_incoming_url(g, remote_parts, request)
    if guard:
        abort(guard)

    url = remote_parts.geturl()
    if url != remote:
        if request.query_string:
            url = urljoin(url, f'?{request.query_string.decode("utf8")}')
        return redirect(f'{request.scheme}://{request.host}/{url}', 307)

    requests_kwargs = dict(**g.request_metadata, data=g.request_payload)

    def fetch():
        remote, response = common.pipe_request(url, method=request.method, **requests_kwargs)
        common.copy_headers(request, remote, response)
        common.copy_cookies(request, remote, response)
        common.guard_cors(request, remote, response)
        return response

    def install_worker():
        service_domains = {
            f'{rule.subdomain}.{g.sld}'
            for rule in current_app.url_map.iter_rules()
            if rule.subdomain
        }
        passthru_domains = current_app.config.get_namespace('PORTAL5_PASSTHRU_').get('domains', set())
        passthru_urls = current_app.config.get_namespace('PORTAL5_PASSTHRU_').get('urls', set())

        return render_template(
            f'{APPNAME}/worker-install.html',
            remote=remote_parts.geturl(),
            worker_settings=dict(
                version=WORKER_VERSION,
                protocol=request.scheme,
                host=request.host,
                passthru=dict(
                    domains={k: True for k in ({g.sld} | service_domains | passthru_domains)},
                    urls={k: True for k in passthru_urls}
                )
            )
        )

    worker_ver = g.request_worker_ver
    if worker_ver:
        if worker_ver == WORKER_VERSION:
            return fetch()
        else:
            return install_worker()

    else:
        head, _ = common.pipe_request(url, method='HEAD', **requests_kwargs)
        if 'text/html' in head.headers.get('Content-Type', ''):
            return install_worker()
        else:
            return fetch()
