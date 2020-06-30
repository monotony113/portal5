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

from functools import reduce


def read_cookie(cookie_value):
    cookie_value = int(cookie_value)
    return {FEATURES_KEYS[k]: bool(cookie_value & 2 ** k) for k in FEATURES_KEYS}


def make_cookie(settings):
    reverse_lookup = {v: k for k, v in FEATURES_KEYS.items()}
    return reduce(lambda x, y: x | y, [2 ** reverse_lookup[k] * int(v) for k, v in settings.items()])


FEATURES_KEYS = {
    0: 'basic_rewrite_crosssite',
    1: 'basic_set_headers',
    2: 'basic_set_cookies',
    3: 'security_enforce_cors',
    4: 'security_break_csp',
    5: 'security_remove_httponly_flag',
    6: 'experimental_client_side_rewrite',
}

FEATURES_DEFAULTS = {
    'basic_rewrite_crosssite': True,
    'basic_set_headers': True,
    'basic_set_cookies': True,
    'security_enforce_cors': True,
    'security_break_csp': False,
    'security_remove_httponly_flag': False,
    'experimental_client_side_rewrite': False,
}

FEATURES_HUMAN_READABLE = {
    'basic_rewrite_crosssite': dict(
        name='Redirect cross-site requests',
        desc='Let Service Worker intercept and redirect cross-site requests (those to a different domain) through this tool.'
    ),
    'basic_set_headers': dict(
        name='Forward HTTP headers',
        desc='Forward HTTP headers received from the remote server.'
    ),
    'basic_set_cookies': dict(
        name='Forward cookies',
        desc='Forward cookies received from the remote server, changing their domain and path values as appropriate.<br>'
        'Note: This does not affect cookies set by scripts on the webpage. These cookies may not be set with proper domains/paths.'
    ),
    'security_enforce_cors': dict(
        name='Enforce CORS <code>Access-Control-Allow-Origin</code> header',
        desc='Recommended. If enabled, <em>modify the <code>Access-Control-Allow-Origin</code> header following these rules:</em></p>'
        '<ul>'
        '<li>If it is set to <code>*</code>, it is kept unmodified</li>'
        '<li>If it is set to a particular origin, then check if such origin matches the origin who requested the resource (e.g. the webpage); '
        'if it matches, the header is set to <code>%(server_origin)s</code> so that the resource will be accepted by browsers, '
        'and if it does not match, drop the <code>Access-Control-Allow-Origin</code> header so that the resource will be rejected by browsers.</li>'
        '</ul>'
        '<p>If disabled, the <code>Access-Control-Allow-Origin</code> is transmitted unmodified.'
    ),
    'security_break_csp': dict(
        name='Bypass Content Security Policy (CSP) protection',
        desc='NOT recommended. If enabled, <em>append <code>%(server_origin)s</code> to all CSP directives that specify sources,</em> except for '
        'those that specify <code>\'none\'</code>. Doing so ensures that browsers can load resources as if the webpage is not '
        'proxied by this tool. <br><strong>However, doing so entirely defeats the purpose of CSP,</strong> '
        'as (potentially malicious) contents that would otherwise be forbidden by CSP will now also be loaded.<br>'
        'If enabled, CSP headers will be transmitted unmodified, and resources protected by CSP directives may not load.',
        color='yellow'
    ),
    'security_remove_httponly_flag': dict(
        name='Remove <code>HttpOnly</code> flag on cookies',
        desc='NOT recommended. If enabled, <em>remove the <code>HttpOnly</code> flag from cookies sent by the remote server.</em><br>'
        'HttpOnly cookies cannot be accessed by scripts, which includes Service Workers. This means that requests made by Service Workers '
        '(which this tool relies on) will not send these cookies. Removing the <code>HttpOnly</code> flag allows these cookies to be sent again, which '
        'recovers some functionalities such as logins. '
        '<strong>However, this opens up these cookies, many of which sensitive, to access by scripts, allowing tracking and attacks.</strong>',
        color='yellow'
    ),
    'experimental_client_side_rewrite': dict(
        name='Enable in-browser URL preprocessing',
        desc='Experimental feature. If enabled, allow Service Worker to prefetch an HTML document and rewrite all URLs in the document '
        'before serving it to the browser. This mainly has two benefits:</p>'
        '<ul>'
        '<li><em>This allows user-initiated navigations to go through this tool.</em> Before, if you click on a link on a webpage that '
        'goes to a different domain, your browser will visit that domain directly, bypassing Service Worker altogether, and you will '
        'exit this tool. Rewriting these URLs makes sure you stay on <code>%(server_origin)s</code>.</li>'
        '<li><em>This allows requests to embedded contents such as <code>iframe</code>s to go through this tool.</em> Same as above: '
        'without rewriting their URLs, requests to these contents will bypass Service Worker, which means that they may not load correctly.</li>'
        '</ul>'
        '<p>Note: This feature currently looks for all <code>href</code>, <code>src</code>, <code>data-href</code>, and <code>data-src</code> '
        'attributes. If the webpage you are visiting uses other non-conventional attributes for URLs, they will not be rewritten. '
        'The same goes for URLs generated dynamically by scripts.',
        color='blue'
    )
}
