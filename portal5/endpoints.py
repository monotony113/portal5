# config.py
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


from flask import current_app

endpoints = {}
endpoint_handlers = {}
passthrough_rules = {}


def collect_passthrough_urls():
    sibling_domains = {
        f'{rule.subdomain}.{current_app.config["SERVER_SLD"]}'
        for rule in current_app.url_map.iter_rules()
        if rule.subdomain
    }

    passthrough = current_app.config.get_namespace('PORTAL5_PASSTHROUGH_')
    passthrough_domains = passthrough.get('domains', set())
    passthrough_urls = passthrough.get('urls', set())

    passthrough_rules['domains'] = {k: 1 for k in sibling_domains | passthrough_domains}
    passthrough_rules['urls'] = {k: 1 for k in passthrough_urls}


def client_side_handler(handler_name, **kwargs):
    def collector(view_func):
        add_client_handler(view_func.__name__, handler_name, virtual=False, **kwargs)
        return view_func
    return collector


def add_client_handler(path, handler_name, virtual=True, **fetch_params):
    fetch_params = {
        'mode': ('navigate',),
        'method': ('GET', 'POST'),
        'referrer': ('',),
        **fetch_params,
    }
    rule = {
        'handler': handler_name,
        'test': {param: {value: 1 for value in values} for param, values in fetch_params.items() if values},
    }
    if virtual:
        endpoint_handlers[path] = rule
    else:
        endpoints[path] = rule


def resolve_client_handlers(blueprint_name):
    prefix = blueprint_name + '.'
    for rule in current_app.url_map.iter_rules():
        if rule.endpoint.startswith(prefix):
            view_func = rule.endpoint[len(prefix):]
            handler_conf = endpoints.get(view_func, None)
            if handler_conf:
                endpoint_handlers[rule.rule] = handler_conf
