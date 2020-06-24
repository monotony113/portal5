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

from flask import Blueprint, Request, render_template, g, abort, current_app
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
def home():
    return render_template('portal5/index.html', protocol=g.request_url_parts.scheme, domain=g.request_url_parts.netloc)


@portal5.route('/index.js')
def index_js():
    return portal5.send_static_file('portal5/index.js')


@portal5.route('/style.css')
def style_css():
    return current_app.send_static_file('twu/styles/style.css')


@portal5.route('/service-worker.js')
def service_worker():
    if g.request_headers.get('Service-Worker') != 'script':
        return abort(403)
    worker = portal5.send_static_file('portal5/service-worker.js')
    worker.headers['Service-Worker-Allowed'] = '/'
    return worker


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


@portal5.route('/<path:remote>', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'))
def rewrite(remote):
    remote_parts = g.remote_url_parts
    guard = common.guard_incoming_url(g, remote_parts, request)
    if guard:
        abort(guard)

    url = remote_parts.geturl()
    request_kwargs = dict(headers=g.request_headers, params=request.args, data=g.request_data, cookies=g.request_cookies)

    def direct_response():
        remote, response = common.pipe_request(url, method=request.method, **request_kwargs)
        common.masquerade_urls(g, remote, response)

        return response

    def update_worker():
        return render_template(
            'portal5/worker-install.html', server=g.server, remote=remote_parts.geturl(),
        )

    worker_ver = g.request_worker_ver
    if worker_ver:
        if worker_ver == WORKER_VERSION:
            return direct_response()
        else:
            return update_worker()

    else:
        head, _ = common.pipe_request(url, method='HEAD', **request_kwargs)
        print(url, head.headers.get('Content-Type', ''))
        if 'text/html' in head.headers.get('Content-Type', ''):
            return update_worker()
        else:
            return direct_response()
