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

# TODO: settings for rewrites, cookies (httponly), cors, csp, iframe

from urllib.parse import SplitResult, urlsplit, urljoin

from flask import Blueprint, Request, Response, request, current_app, g, render_template, abort, redirect

from . import features
from .. import common, security

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
@security.access_control_allow_origin('*')
def home():
    return render_template(f'{APPNAME}/index.html')


@portal5.route('/favicon.ico')
@security.access_control_same_origin
def index_js():
    return portal5.send_static_file('favicon.ico')


@portal5.route('/service-worker.js')
@security.access_control_same_origin
def service_worker():
    if g.request_headers.get('Service-Worker') != 'script':
        return abort(403)

    service_domains = {
        f'{rule.subdomain}.{g.sld}'
        for rule in current_app.url_map.iter_rules()
        if rule.subdomain
    }
    passthru_domains = current_app.config.get_namespace('PORTAL5_PASSTHRU_').get('domains', set())
    passthru_urls = current_app.config.get_namespace('PORTAL5_PASSTHRU_').get('urls', set())

    worker_settings = dict(
        version=WORKER_VERSION,
        protocol=request.scheme,
        host=request.host,
        passthru=dict(
            domains={k: True for k in ({g.sld} | service_domains | passthru_domains)},
            urls={k: True for k in passthru_urls}
        )
    )
    worker = Response(
        render_template(f'{APPNAME}/scripts/service-worker.js', settings=worker_settings),
        headers={'Service-Worker-Allowed': '/'}, mimetype='application/javascript'
    )
    return worker


@portal5.route('/settings', methods=('GET', 'POST'))
@security.access_control_same_origin
def settings():
    if request.method == 'POST':
        settings = dict(**request.form)
        if settings.pop('action') == 'reset':
            g.settings = features.FEATURES_DEFAULTS
        else:
            g.settings = {k: bool(int(v)) for k, v in settings.items()}

    settings = dict()
    for k, v in g.settings.items():
        option = dict()
        option['enabled'] = v
        option.update({k_: v % {'server_origin': g.server_origin} for k_, v in features.FEATURES_HUMAN_READABLE[k].items()})
        section = settings.setdefault(k.split('_')[0], dict())
        section[k] = option

    res = Response(render_template('portal5/settings.html', settings=settings, updated=request.method == 'POST'))
    if request.method == 'POST':
        res.set_cookie(
            'portal5_settings', str(features.make_cookie(g.settings)),
            path='/', domain=request.host,
            secure=True, httponly=True
        )

    return res


@portal5.url_value_preprocessor
def preprocess(endpoint, values):
    common.metadata_from_request(g, request, endpoint, values)
    headers: dict = g.request_headers

    worker_ver = headers.pop('X-Portal5-Worker-Version', None)
    try:
        g.request_worker_ver = int(worker_ver)
    except (TypeError, ValueError):
        g.request_worker_ver = None

    settings = g.request_cookies.pop('portal5_settings', None)
    g.settings = features.read_cookie(settings) if settings is not None else features.FEATURES_DEFAULTS

    referrer = headers.pop('X-Portal5-Referrer', None)
    if referrer:
        headers['Referer'] = referrer

    headers.pop('Origin', None)
    origin = headers.pop('X-Portal5-Origin', None)
    fetch_mode = headers.pop('X-Portal5-Mode', None)
    if origin and (fetch_mode == 'cors' or request.method not in {'GET', 'HEAD'}):
        headers['Origin'] = origin
    g.request_origin = origin

    origin_domain = None
    if origin:
        origin_domain = urlsplit(origin).netloc
    elif referrer and not origin:
        origin_domain = urlsplit(referrer).netloc

    if origin_domain:
        g.urlsplit_requested, g.request_metadata = common.conceal_origin(
            request.host, origin_domain, g.urlsplit_requested, **g.request_metadata
        )


@portal5.route('/<path:requested>', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'))
def forward(requested):
    urlsplit_requested = g.urlsplit_requested
    if not urlsplit_requested.path:
        urlsplit_requested = SplitResult(*[*urlsplit_requested[:2], '/', *urlsplit_requested[3:]])
        g.urlsplit_requested = urlsplit_requested

    guard = common.guard_incoming_url(g, urlsplit_requested, request)
    if guard:
        abort(guard)

    url = urlsplit_requested.geturl()

    if url != requested:
        if request.query_string:
            url = urljoin(url, f'?{request.query_string.decode("utf8")}')
        return redirect(f'{request.scheme}://{request.host}/{url}', 307)

    requests_kwargs = dict(**g.request_metadata, data=g.request_payload)

    worker_ver = g.request_worker_ver
    if worker_ver:
        if worker_ver == WORKER_VERSION:
            return fetch(url, **requests_kwargs)
        else:
            return install_worker(url)

    else:
        head, _ = common.pipe_request(url, method='HEAD', **requests_kwargs)
        if head.status_code == 405:
            head, _ = common.pipe_request(url, **requests_kwargs)
        if 'text/html' in head.headers.get('Content-Type', ''):
            return install_worker(url)
        else:
            return fetch(url, **requests_kwargs)


def install_worker(url):
    return render_template(
        f'{APPNAME}/worker-install.html',
        remote=url,
        browser_additional='MicroMessenger' in request.user_agent.string,
    )


def fetch(url, **kwargs):
    remote, response = common.pipe_request(url, method=request.method, **kwargs)
    common.copy_headers(remote, response, server_origin=g.server_origin)
    common.copy_cookies(remote, response, server_domain=request.host)
    security.enforce_cors(remote, response, request_origin=g.request_origin, server_origin=g.server_origin)
    security.break_csp(remote, response, server_origin=g.server_origin)
    return response
