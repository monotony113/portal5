# features.py
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

import json
import uuid
from datetime import timedelta
from functools import reduce
from urllib.parse import SplitResult, urlsplit

from cryptography.fernet import Fernet
from flask import Request, Response

from .. import common, security
from ..jwtkit import JWTKit, get_all_jwts, get_private_claims
from .bitmasklib import mask_to_bits, bits_to_mask, constrain_ones

APPNAME = 'portal5'


class PreferenceMixin:
    __slots__ = ()

    def __init__(self):
        if self.prefs is not None:
            self.set_bitmask(self.prefs)
        else:
            self.set_bitmask(bits_to_mask(self._defaults))

        self.register_action(self.write_prefs_cookie)

    def get_bitmask(self):
        mask = self.prefs_to_bitmask(self.prefs)
        mask_ = self.resolve_dependencies(mask)
        if mask != mask_:
            self.set_bitmask(mask_)
            mask = mask_
        return mask

    def set_bitmask(self, mask):
        self.prefs = self.bitmask_to_prefs(self.resolve_dependencies(mask))

    @classmethod
    def resolve_dependencies(cls, mask):
        return reduce(lambda m, s: m | constrain_ones(m, s[0], s[1]), cls._dependencies.items(), mask)

    @classmethod
    def bitmask_to_prefs(cls, mask):
        return set(filter(None, {cls._keys.get(k, None) for k in mask_to_bits(mask)}))

    @classmethod
    def prefs_to_bitmask(cls, prefs):
        bits = {cls._values.get(k, -1) for k in prefs}
        bits.discard(-1)
        return bits_to_mask(bits)

    @classmethod
    def make_default_prefs(cls):
        return {*cls.bitmask_to_prefs(bits_to_mask(cls._defaults))}

    @classmethod
    def write_prefs_cookie(cls, p5, response):
        response.set_cookie(cls.COOKIE_PREFS, str(p5.get_bitmask()), max_age=cls.COOKIE_MAX_AGE, path='/', secure=True, httponly=True)

    def print_prefs(self, **kwargs):
        prefs = {}
        for v in FEATURES_KEYS.values():
            option = {}
            option['enabled'] = v in self.prefs
            option.update(FEATURES_TEXTS.get(v, {'name': v}))
            if 'desc' in option:
                option['desc'] = [line % kwargs for line in option['desc']]
            section = prefs.setdefault(v.split('_')[0], {})
            section[v] = option
        return prefs

    def make_client_prefs(self):
        bitmask = self.get_bitmask()
        prefs = {
            'value': bitmask,
            'local': {FEATURES_KEYS[k]: 1 for k in mask_to_bits(bitmask) & FEATURES_CLIENT_SPECIFIC},
        }
        return {'prefs': prefs}

    def make_dependency_dicts(self):
        return dict(zip(
            ('dep', 'req'),
            [
                {FEATURES_KEYS[k].replace('_', '-'): [FEATURES_KEYS[v].replace('_', '-') for v in l] for k, l in d.items()}
                for d in (FEATURES_DEPENDENCIES, FEATURES_REQUIREMENTS)
            ],
        ))

    @property
    def requires_bundle(self):
        bitmask = self.get_bitmask()
        return bool(bits_to_mask(FEATURES_BUNDLE_REQUIRING) & bitmask)


class FeaturesMixin:
    __slots__ = ()

    def process_response(self, remote, response: Response, **kwargs):
        kwargs.update({f'request_{k}': getattr(self, k) for k in self.__slots__})

        if 'basic_set_headers' in self.prefs:
            common.copy_headers(remote, response, **kwargs)
        elif 'Content-Encoding' in remote.headers:
            response.headers['Content-Encoding'] = remote.headers['Content-Encoding']

        if 'basic_set_cookies' in self.prefs:
            common.copy_cookies(remote, response, **kwargs)

        if 'security_enforce_cors' in self.prefs:
            security.enforce_cors(remote, response, **kwargs)

        if 'security_break_csp' in self.prefs:
            security.break_csp(remote, response, **kwargs)

        if 'security_clear_cookies_on_navigate' in self.prefs:
            security.add_clear_site_data_header(remote, response, **kwargs)


class JWTMixin:
    __slots__ = ()

    def __init__(self, request):
        self.tokens = []
        self.register_action(self.write_auth_cookie)
        if request.cookies.get(self.COOKIE_AUTH, None) is None:
            self.tokens = ['']

    def issue_new_token(self, identity, privilege, expires=180, **claims):
        user_claims = {
            'version': self.VERSION,
            'variant': self.get_bitmask(),
            'privilege': privilege,
            **claims,
        }
        token = JWTKit.get_jwtkit().create_token(
            sub=identity, exp=timedelta(seconds=expires) if isinstance(expires, int) else None,
            **user_claims,
        )
        self.tokens.append(token)
        return token

    @classmethod
    def write_auth_cookie(cls, p5, response):
        if p5.tokens:
            response.set_cookie(cls.COOKIE_AUTH, ' '.join(p5.tokens), max_age=cls.COOKIE_MAX_AGE, path='/', secure=True, httponly=True)

    def persist_tokens(self):
        jwtkit = JWTKit.get_jwtkit()
        self.tokens.extend([jwtkit.encode_token(token) for token in get_all_jwts()])

    def clear_tokens(self):
        self.tokens = ['']

    @classmethod
    def jwt_version_is_outdated(cls, jwt, *args, **kwargs):
        return get_private_claims(jwt).get('version') != cls.VERSION


class PostprocessingMixin:
    __slots__ = ()

    def __init__(self):
        self.late_actions = []

    def register_action(self, action):
        self.late_actions.append(action)

    @classmethod
    def postprocess(cls, getter):
        def process(response):
            p5: cls = getter()
            for action in p5.late_actions:
                action(p5, response)
            return response
        return process


class DirectiveMixin:
    __slots__ = ()

    def __init__(self):
        self.actions = set(self.actions.split(',')) if self.actions else set()
        self.directives = set()
        self.register_action(Portal5.set_directive_header)

    def add_directive(self, directive):
        self.directives.add(directive)

    def set_directive_header(self, response):
        response.headers['X-Portal5-Directive'] = json.dumps({k: 1 for k in self.directives})


FEATURES_KEYS = {
    0: 'basic_rewrite_crosssite',
    1: 'basic_set_headers',
    2: 'basic_set_cookies',
    3: 'security_enforce_cors',
    4: 'security_break_csp',
    5: 'security_clear_cookies_on_navigate',
    6: 'injection_dom_hijack',
}
FEATURES_VALUES = {v: k for k, v in FEATURES_KEYS.items()}

FEATURES_DEFAULTS = {0, 1, 2, 3}

FEATURES_DEPENDENCIES = {
    3: {1},
    4: {1},
    6: {0, 4},
}
FEATURES_DEPENDENCIES = {k: reduce(lambda x, y: x | FEATURES_DEPENDENCIES.get(y, set()), v, v) for k, v in FEATURES_DEPENDENCIES.items()}

FEATURES_REQUIREMENTS = {}
for k, v in FEATURES_DEPENDENCIES.items():
    for r in v:
        req = FEATURES_REQUIREMENTS.setdefault(r, set())
        req.add(k)

FEATURES_CLIENT_SPECIFIC = {0, 6}
FEATURES_BUNDLE_REQUIRING = {6}


class Portal5(PostprocessingMixin, DirectiveMixin, JWTMixin, PreferenceMixin, FeaturesMixin):
    __slots__ = (
        'id', 'version', 'prefs',
        'mode', 'referrer', 'origin',
        'directives', 'actions',
        'tokens', 'tokens_max_age',
        'late_actions',
    )

    VERSION = None

    HEADER = 'X-Portal5'
    COOKIE_PREFS = 'portal5prefs'
    COOKIE_AUTH = 'portal5auth'

    ENDPOINT_INIT = '/init'
    ENDPOINT_SETTINGS = '/settings'
    ENDPOINT_UNINSTALL = '/~uninstall'
    ENDPOINT_RESET = '/~reset'
    ENDPOINT_DISAMBIGUATE = '/~disambiguate'

    COOKIE_MAX_AGE = 86400 * 365

    _keys = FEATURES_KEYS
    _values = FEATURES_VALUES
    _defaults = FEATURES_DEFAULTS
    _dependencies = FEATURES_DEPENDENCIES

    _fernet: Fernet = None
    _passthru_conf: dict = None

    def __init__(self, request: Request):
        PostprocessingMixin.__init__(self)
        JWTMixin.__init__(self, request)

        try:
            fetch = json.loads(request.headers.get(self.HEADER, '{}'))
        except Exception:
            fetch = {}

        for k in self.__slots__:
            if not hasattr(self, k):
                setattr(self, k, fetch.get(k, None))

        if self.prefs is None:
            self.prefs = request.cookies.get(self.COOKIE_PREFS, None, int)

        PreferenceMixin.__init__(self)
        DirectiveMixin.__init__(self)

    @property
    def valid(self):
        return 'revalidate' not in self.actions and self.version is not None

    @property
    def up_to_date(self):
        return self.VERSION == self.version

    @property
    def origin_domain(self):
        if self.origin:
            return urlsplit(self.origin).netloc
        if self.referrer:
            return urlsplit(self.referrer).netloc
        return None

    def __call__(self, url: SplitResult, request: Request, **overrides):
        info = common.extract_request_info(request)

        headers = info['headers']
        headers.pop('Host', None)
        headers.pop('Origin', None)
        headers.pop('Referer', None)
        headers.pop(self.HEADER, None)

        cookies = info['cookies']
        cookies.pop(self.COOKIE_PREFS, None)

        if self.referrer:
            headers['Referer'] = self.referrer

        if self.origin and (self.mode == 'cors' or request.method not in {'GET', 'HEAD'}):
            headers['Origin'] = self.origin

        if self.origin_domain:
            kwargs = security.conceal_origin(request.host, self.origin_domain, url, **info)
        else:
            kwargs = {'url': url, **info}

        kwargs['method'] = request.method
        kwargs['url'] = kwargs['url'].geturl()
        kwargs['data'] = common.stream_request_body(request)
        kwargs.update(overrides)

        return kwargs

    def make_worker_settings(self, identity, server):
        settings = {**self.make_client_prefs(), 'passthru': self._passthru_conf}

        settings['endpoints'] = {
            self.ENDPOINT_INIT: 'passthru',
            self.ENDPOINT_SETTINGS: 'restricted',
            self.ENDPOINT_UNINSTALL: 'passthru',
            self.ENDPOINT_RESET: 'passthru',
            self.ENDPOINT_DISAMBIGUATE: 'disambiguate',
        }

        settings['id'] = identity or self.id or str(uuid.uuid4())
        settings['version'] = self.VERSION
        settings['origin'] = server

        return settings


FEATURES_TEXTS = {
    'basic_rewrite_crosssite': dict(
        name='Redirect cross-site requests',
        desc=[
            'Let Service Worker intercept and redirect cross-site requests (those to a different domain) through this tool.',
        ],
    ),
    'basic_set_headers': dict(
        name='Forward HTTP headers',
        desc=[
            'Forward HTTP headers received from the remote server.',
        ],
    ),
    'basic_set_cookies': dict(
        name='Forward cookies',
        desc=[
            'Forward cookies received from the remote server, changing their domain and path values as appropriate.',
            'Note: This does not affect cookies set by scripts on the webpage. These cookies may not be set with proper domains/paths.',
        ],
    ),
    'security_enforce_cors': dict(
        name='Enforce CORS <code>Access-Control-Allow-Origin</code> header',
        desc=[
            'Recommended. <em>Modify the <code>Access-Control-Allow-Origin</code> header following these rules:</em>',
            '<ul>'
            '<li>If it is set to <code>*</code>, it is kept unmodified</li>'
            '<li>If it is set to a particular origin, then check if such origin matches the origin who requested the resource (e.g. the webpage); '
            'if it matches, the header is set to <code>%(server_origin)s</code> so that the resource will be accepted by browsers, '
            'and if it does not match, drop the <code>Access-Control-Allow-Origin</code> header so that the resource will be rejected by browsers.</li>'
            '</ul>',
            'If disabled, the <code>Access-Control-Allow-Origin</code> is transmitted unmodified.',
        ],
    ),
    'security_break_csp': dict(
        name='Bypass Content Security Policy (CSP) protection',
        desc=[
            'NOT recommended. <em>Append <code>%(server_origin)s</code> to all CSP directives that specify sources,</em> except for '
            "those that specify <code>'none'</code>. Doing so ensures that browsers can load resources as if the webpage is not "
            'proxied by this tool.',
            '<strong>However, doing so entirely defeats the purpose of CSP,</strong> '
            'as (potentially malicious) contents that would otherwise be forbidden by CSP will now also be loaded.',
            'If disabled, CSP headers will be transmitted unmodified, and resources protected by CSP directives may not load.',
        ],
        color='yellow',
    ),
    'security_clear_cookies_on_navigate': dict(
        name='Clear cookies between cross-site visits',
        desc=[
            '<em>Delete all cookies when you navigate from one page to another page on a different domain.</em> '
            'One major security caveats of this tool is that website cookies that would otherwise be separated under different domains '
            'will now all stored under the same domain. Keeping cookies separate by domains ensures that one website cannot get cookies that '
            'may contain sensitive information, such as login info, of another website. When using this tool, all websites you visit may see '
            'cookies of other sites.',
            'This option mitigates this security concern by asking your browser to clear out all cookies between visits to different websites. '
            'Visits that stay within the same site are not affected. The drawback is that you may lose some functionalities on some websites. '
            'Additionally, this option takes effect on all windows/tabs that are open, meaning that if you have multiple tabs open, and one of them '
            'navigates to a different site, cookies on all tabs will be cleared, and you may notice inconsistencies in the behaviors of the webpages you are visiting.',
            'Note: This option relies on the <code>Clear-Site-Data</code> header to work, which is not supported by all browsers.',
        ],
    ),
    'injection_dom_hijack': dict(
        name='Enable DOM script injection',
        desc=[
            'Experimental feature. <em>Allow Service Worker to <strong>inject scripts</strong> into an HTML document, granting this tool '
            'the ability to modify all contents on a webpage.</em>',
            '<ul>'
            '<li><em>This allows user-initiated navigations to go through this tool.</em> Before, if you click on a link on a webpage that '
            'goes to a different domain, your browser will visit that domain directly, bypassing Service Worker altogether, and you will '
            'exit this tool. Rewriting these URLs makes sure you stay on <code>%(server_origin)s</code>.</li>'
            '<li><em>This allows requests to embedded contents such as <code>iframe</code>s to go through this tool.</em> Same as above: '
            'without rewriting their URLs, requests to these contents will bypass Service Worker, which means that they may not load correctly.</li>'
            '</ul>',
            'Note: This feature currently looks for all <code>href</code>, <code>src</code>, <code>data-href</code>, and <code>data-src</code> '
            'attributes. If the webpage you are visiting uses other non-conventional attributes for URLs, they will not be rewritten. '
            'The same goes for URLs generated dynamically by scripts.',
        ],
        color='red',
    ),
}
