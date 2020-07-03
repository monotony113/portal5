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
from urllib.parse import SplitResult, unquote, urljoin

from flask import Blueprint, Request, Response, abort, current_app, g, redirect, render_template, request

from .. import common, security
from . import config
from .portal5 import Portal5Request

APPNAME = 'portal5'

request: Request
portal5 = Blueprint(
    APPNAME, __name__,
    template_folder='templates', static_folder='static',
    subdomain=config.SUBDOMAIN,
)


@portal5.before_request
def parse_p5():
    g.p5 = Portal5Request(request)


@portal5.url_value_preprocessor
def parse_url(endpoint, values):
    if 'requested' in values:
        values['requested'] = common.normalize_url(unquote(values['requested']))


@portal5.route('/')
@portal5.route('/index.html')
@security.access_control_allow_origin('*')
def home():
    return render_template(f'{APPNAME}/index.html')


@portal5.route('/favicon.ico')
@security.access_control_allow_origin('*')
def favicon():
    return portal5.send_static_file('favicon.ico')


@portal5.route('/init')
@security.csp_no_frame_ancestor
def install_worker():
    return render_template(f'{APPNAME}/init.html')


def requires_worker(view_func):
    @wraps(view_func)
    def install(*args, **kwargs):
        p5: Portal5Request = g.p5
        if not p5.up_to_date:
            return install_worker()
        return view_func(*args, **kwargs)
    return install


def requires_identity(view_func):
    @wraps(view_func)
    def security_check(*args, **kwargs):
        p5: Portal5Request = g.p5
        if not p5.id:
            return abort(401)
        return view_func(*args, **kwargs)
    return security_check


@portal5.route(Portal5Request.SETTINGS_ENDPOINT)
@requires_worker
@requires_identity
@security.csp_no_frame_ancestor
def get_prefs():
    p5: Portal5Request = g.p5
    return render_template(
        f'{APPNAME}/preferences.html',
        prefs=p5.print_prefs(server_origin=g.server_origin),
    )


@portal5.route(Portal5Request.SETTINGS_ENDPOINT, methods=('POST',))
@requires_worker
@requires_identity
@security.access_control_same_origin
@security.csp_no_frame_ancestor
def save_prefs():
    p5: Portal5Request = g.p5

    prefs = dict(**request.form)
    if p5.id != prefs.pop('id', None):
        return abort(401)

    if prefs.pop('action') == 'reset':
        p5.prefs = p5.make_default_prefs()
    else:
        p5.set_bitmask(p5.prefs_to_bitmask({k for k, v in prefs.items() if int(v)}))

    return render_template(f'{APPNAME}/update.html')


@portal5.route('/direct/<path:requested>', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'))
def direct_fetch(requested: SplitResult):
    return fetch(requested)


@portal5.route('/<path:requested>', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'))
@requires_worker
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

    p5: Portal5Request = g.p5

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
