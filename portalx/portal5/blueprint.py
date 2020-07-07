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

from functools import wraps
from urllib.parse import SplitResult, quote, unquote, urljoin

from flask import Blueprint, Request, Response, abort, current_app, g, redirect, render_template, request

from .. import common, security
from . import config
from .portal5 import Portal5

APPNAME = 'portal5'

request: Request
portal5 = Blueprint(
    APPNAME, __name__,
    template_folder='templates', static_folder='static',
    subdomain=config.SUBDOMAIN,
)


@portal5.before_app_first_request
def codename():
    Portal5.VERSION = current_app.config.get_namespace('PORTAL5_')['worker_codename']


@portal5.before_request
def parse_p5():
    g.p5 = Portal5(request)


@portal5.url_value_preprocessor
def parse_url(endpoint, values):
    if 'requested' in values:
        values['requested'] = common.normalize_url(unquote(values['requested']))


def requires_worker(view_func):
    @wraps(view_func)
    @security.referrer_policy('no-referrer')
    def install(*args, **kwargs):
        p5: Portal5 = g.p5
        if not p5.valid:
            path = quote(request.full_path if request.query_string else request.path)
            return redirect(f'/init?continue={path}', 307)
        return view_func(*args, **kwargs)
    return install


def requires_identity(view_func):
    @wraps(view_func)
    def security_check(*args, **kwargs):
        p5: Portal5 = g.p5
        if not p5.id:
            return abort(401)
        return view_func(*args, **kwargs)
    return security_check


def revalidate_if_outdated(view_func):
    @wraps(view_func)
    def append(*args, **kwargs):
        p5: Portal5 = g.p5
        if not p5.up_to_date:
            p5.add_directive('revalidate-on-next-request')
        return view_func(*args, **kwargs)
    return append


@portal5.route('/')
@portal5.route('/index.html')
@security.access_control_allow_origin('*')
def home():
    return render_template(f'{APPNAME}/index.html')


@portal5.route('/favicon.ico')
@security.access_control_allow_origin('*')
def favicon():
    return portal5.send_static_file('favicon.ico')


@portal5.route('/init', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'))
@security.access_control_same_origin
@security.csp_recommendations
@security.csp_nonce('script-src')
@security.referrer_policy('no-referrer')
@Portal5.postprocess(g, 'p5')
def install_worker():
    p5: Portal5 = g.p5
    return p5.issue_new_token(f'{APPNAME}/init.html', request.remote_addr, 'init')


@portal5.route(Portal5.ENDPOINT_SETTINGS)
@requires_worker
@requires_identity
@revalidate_if_outdated
@security.access_control_same_origin
@security.csp_recommendations
@Portal5.postprocess(g, 'p5')
def get_prefs():
    p5: Portal5 = g.p5
    res = Response(render_template(
        f'{APPNAME}/preferences.html',
        prefs=p5.print_prefs(server_origin=g.server_origin),
    ))
    return res


@portal5.route(Portal5.ENDPOINT_SETTINGS, methods=('POST',))
@requires_worker
@requires_identity
# @requires_secret
@revalidate_if_outdated
@security.access_control_same_origin
@security.csp_recommendations
@security.csp_nonce('script-src')
@Portal5.postprocess(g, 'p5')
def save_prefs():
    p5: Portal5 = g.p5

    prefs = dict(**request.form)
    if p5.id != prefs.pop('id', None):
        return abort(401)

    if prefs.pop('action') == 'reset':
        p5.prefs = p5.make_default_prefs()
    else:
        p5.set_bitmask(p5.prefs_to_bitmask({k for k, v in prefs.items() if int(v)}))

    return p5.issue_new_token(f'{APPNAME}/update.html', request.remote_addr, 'update')


@portal5.route('/direct/<path:requested>', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'))
def direct_fetch(requested: SplitResult):
    return fetch(requested)


@portal5.route('/<path:requested>', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'))
@requires_worker
@revalidate_if_outdated
@Portal5.postprocess(g, 'p5')
def process_request(requested: SplitResult):
    return fetch(requested)


def fetch(requested: SplitResult):
    url_ = requested
    if not url_.path:
        url_ = SplitResult(*[*requested[:2], '/', *requested[3:]])

    guard = common.guard_incoming_url(g, url_, request)
    if guard:
        abort(guard)

    if url_ != requested:
        if request.query_string:
            url = urljoin(url_.geturl(), f'?{request.query_string.decode("utf8")}')
        else:
            url = url_.geturl()
        return redirect(f'{request.scheme}://{request.host}/{url}', 307)

    p5: Portal5 = g.p5

    outbound = common.prepare_request(**p5(url_, request))

    filters = current_app.config.get('PORTAL_URL_FILTERS')
    should_abort = filters.test(outbound)
    if should_abort:
        abort(should_abort)

    remote, response = common.pipe_request(outbound)
    p5.process_response(
        remote, response,
        server_origin=g.server_origin,
        server_domain=request.host,
    )

    return response


@portal5.route('/~reset')
def reset():
    res = Response('', status=204)
    res.headers['Clear-Site-Data'] = '"cache", "cookies", "storage"'
    return res


@portal5.route('/~uninstall')
def uninstall():
    return render_template(f'{APPNAME}/uninstall.html')
