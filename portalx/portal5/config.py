from flask import current_app

SUBDOMAIN = 'portal5'


def collect_passthru_urls():
    sibling_domains = {
        f'{rule.subdomain}.{current_app.config["SERVER_SLD"]}'
        for rule in current_app.url_map.iter_rules()
        if rule.subdomain and rule.subdomain != SUBDOMAIN
    }

    passthru = current_app.config.get_namespace('PORTAL5_PASSTHRU_')
    passthru_domains = passthru.get('domains', set())
    passthru_urls = passthru.get('urls', set())

    conf = {}
    conf['domains'] = {k: 1 for k in {current_app.config['SERVER_SLD']} | sibling_domains | passthru_domains}
    conf['urls'] = {k: 1 for k in passthru_urls}
    return conf
