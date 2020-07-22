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
from urllib.parse import SplitResult, quote, unquote, urljoin, urlsplit

from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, Request, Response, abort, current_app, g, redirect, render_template, request

from .. import common, security
from ..jwtkit import get_jwt
from . import config
from .portal5 import Portal5

APPNAME = 'portal5'

request: Request
portal5 = Blueprint(
    APPNAME, __name__,
    template_folder='templates', static_folder='static',
    subdomain=config.SUBDOMAIN,
)


def get_p5() -> Portal5:
    return getattr(g, 'p5', None)


@portal5.before_app_first_request
def setup():
    conf = current_app.config.get_namespace('PORTAL5_')

    Portal5.VERSION = conf['worker_codename']
    Portal5._fernet = Fernet(conf['secret_key'].encode())

    config.add_client_handler('/~disambiguate', 'disambiguate', virtual=True)

    config.collect_passthrough_urls()
    config.resolve_client_handlers(APPNAME)


@portal5.before_request
def parse_p5():
    g.p5 = Portal5(request)


@portal5.url_value_preprocessor
def parse_url(endpoint, values):
    if 'requested' in values:
        values['requested'] = common.normalize_url(unquote(values['requested']))


@security.referrer_policy('no-referrer')
def redirect_to_init(path=None):
    return redirect(f'/init?continue={path}' if path else '/init', 307)


def requires_worker(view_func):
    @wraps(view_func)
    def install(*args, **kwargs):
        p5 = get_p5()
        if not p5.valid:
            if request.accept_mimetypes.accept_html:
                path = quote(request.full_path if request.query_string else request.path)
                return redirect_to_init(path)
        return view_func(*args, **kwargs)
    return install


def requires_identity(view_func):
    @wraps(view_func)
    def check(*args, **kwargs):
        p5 = get_p5()
        if not p5.id:
            return abort(403)
        return view_func(*args, **kwargs)
    return check


def revalidate_if_outdated(view_func):
    @wraps(view_func)
    def append(*args, **kwargs):
        p5 = get_p5()
        if not p5.up_to_date:
            p5.set_signal('revalidate-on-next-request')
        return view_func(*args, **kwargs)
    return append


@portal5.route('/')
@portal5.route('/index.html')
# @config.client_side_handler('passthrough')
@security.access_control_allow_origin('*')
def home():
    return render_template(f'{APPNAME}/index.html')


@portal5.route('/favicon.ico')
@config.client_side_handler('passthrough')
@security.access_control_allow_origin('*')
def favicon():
    return portal5.send_static_file('favicon.ico')


@portal5.route('/init', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'))
@config.client_side_handler('passthrough')
@security.access_control_same_origin
@security.csp_protected
@security.referrer_policy('no-referrer')
def install_worker():
    return render_template(f'{APPNAME}/init.html')


@portal5.route('/settings', methods=('OPTIONS',))
@config.client_side_handler('passthrough')
@security.access_control_same_origin
def settings_options():
    res = Response('', 204)
    res.headers['Access-Control-Allow-Methods'] = 'GET, POST, HEAD, OPTIONS'
    res.headers['Access-Control-Allow-Headers'] = 'X-Portal5, Cookie'
    return res


@portal5.route('/settings')
@config.client_side_handler('restricted')
@requires_worker
@requires_identity
@revalidate_if_outdated
@security.access_control_same_origin
@security.csp_protected
def get_prefs():
    p5 = get_p5()

    csrf_token = p5._fernet.encrypt(p5.id.encode())
    res = Response(render_template(
        f'{APPNAME}/preferences.html',
        prefs=p5.print_prefs(server_origin=g.server_origin),
        csrf_token=csrf_token.decode('utf8'),
    ))

    p5.issue_new_token(request.remote_addr, 'nochange', expires=43200)
    return res


@portal5.route('/settings', methods=('POST',))
@config.client_side_handler('restricted')
@requires_worker
@requires_identity
@revalidate_if_outdated
@security.expects_jwt_in('cookies', key=Portal5.COOKIE_AUTH)
@security.rejects_jwt_where(
    security.jwt_has_invalid_subject,
    security.jwt_does_not_claim(_privilege='nochange'),
    Portal5.jwt_version_is_outdated,
)
@security.access_control_same_origin
@security.csp_protected
def save_prefs():
    p5 = get_p5()
    prefs = {**request.form}

    forbidden = True
    csrf_token = prefs.pop('csrf_token')
    if csrf_token:
        try:
            csrf_id = p5._fernet.decrypt(csrf_token.encode()).decode('utf8')
            if p5.id == csrf_id:
                forbidden = False
        except InvalidToken:
            pass
    if forbidden:
        p5.clear_tokens()
        return abort(403)

    if prefs.pop('action') == 'reset':
        prefs = p5.make_default_prefs()
        signals = {'nopref': 1}
    else:
        prefs = {k for k, v in prefs.items() if v.isnumeric() and int(v)}
        signals = {}

    p5.issue_new_token(
        request.remote_addr, 'update',
        session=get_jwt()['jti'],
        variant=p5.prefs_to_bitmask(prefs),
        signals=signals,
    )
    p5.persist_tokens()

    return render_template(f'{APPNAME}/update.html')


@portal5.route('/~multiple-choices', methods=('GET', 'POST'))
@config.client_side_handler('passthrough')
@requires_worker
@security.referrer_policy('no-referrer')
def multiple_choices():
    request_info = dict(**request.json) if request.json else get_p5().signals.get('disambiguate', {})
    try:
        candidates = request_info.get('candidates', [])
        candidates = {i['dest']: i for i in candidates}
        candidates = [{k: urlsplit(v) for k, v in candidate.items()} for candidate in candidates.values()]
        candidates = sorted(candidates, key=lambda d: d['dest'])
        return render_template(f'{APPNAME}/disambiguate.html', candidates=candidates, info=request_info), 300
    except KeyError:
        abort(400)


@portal5.route('/~deflect', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'))
@config.client_side_handler('passthrough')
@security.referrer_policy('no-referrer')
def deflect():
    destination = request.args.get('to')
    if not destination:
        return abort(400)
    return redirect(unquote(destination), 307)


@portal5.route('/direct/<path:requested>', methods=('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'))
def direct_fetch(requested: SplitResult):
    return fetch(resolve_url(requested, prefix='direct'))


@portal5.route('/<path:requested>', methods=('GET',))
@requires_worker
@revalidate_if_outdated
def request_with_worker(requested: SplitResult):
    return fetch(resolve_url(requested))


@portal5.route('/<path:requested>', methods=('POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'))
def request_no_worker(requested: SplitResult):
    return fetch(resolve_url(requested))


def resolve_url(requested: SplitResult, *, prefix=''):
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
        return redirect(f'{request.scheme}://{request.host}/{prefix}/{url}', 307)

    return url_


def fetch(url: SplitResult):
    if not isinstance(url, SplitResult):
        return url

    p5 = get_p5()
    outbound = common.prepare_request(**p5(url, request))

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
@config.client_side_handler('passthrough')
@security.clear_site_data()
def reset():
    res = Response('', status=204)
    return res


@portal5.route('/~uninstall')
@config.client_side_handler('passthrough')
def uninstall():
    return render_template(f'{APPNAME}/uninstall.html')


portal5.after_request(Portal5.postprocess(get_p5))
