// rewriter.js
// Copyright (C) 2020  Tony Wu <tony[dot]wu(at)nyu[dot]edu>
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

/* {% set retain_import_exports = False %} */
/* {% if retain_import_exports %} */
const { Utils } = require('./utils')
/* {% endif %} */

class Rewriters {
    static async synthesizeURL(requested, referrer, client, savedClients, prefix) {
        let location = null
        let represented = null
        let synthesized = {
            referrer: null,
            url: new URL('http://example.org'),
        }

        if (client) {
            location = new URL(client.url)
            try {
                represented = new URL(location.pathname.substr(1))
            } catch (e) {
                if (savedClients) {
                    let stored = savedClients.get(client.id)
                    if (stored) {
                        represented = new URL(stored.represented)
                        represented.pathname = location.pathname
                    }
                }
            }
            if (represented) {
                represented.search = location.search
                represented.hash = location.hash
            }
        }

        if (savedClients && represented) savedClients.add(client.id, represented.href)

        if (!represented) represented = referrer
        if (!referrer) referrer = represented

        if (referrer) {
            try {
                synthesized.referrer = new URL(referrer.pathname.substr(1))
                synthesized.referrer.search = referrer.search
                synthesized.referrer.hash = referrer.hash
            } catch (e) {
                if (represented) {
                    synthesized.referrer = referrer
                    synthesized.referrer.protocol = represented.protocol
                    synthesized.referrer.host = represented.host
                }
            }
        }

        if (prefix != requested.origin) {
            synthesized.url = new URL(requested)
        } else {
            try {
                synthesized.url = new URL(requested.pathname.substr(1))
            } catch (e) {
                if (synthesized.referrer) {
                    synthesized.url = new URL(synthesized.referrer)
                } else {
                    synthesized.url = new URL(prefix)
                }
                synthesized.url.pathname = requested.pathname
            }
        }

        synthesized.url.search = requested.search
        synthesized.url.hash = requested.hash

        try {
            synthesized.url = new URL(Utils.trimPrefix(synthesized.url.href, prefix + '/'), prefix)
        } catch (e) {
            ;() => {}
        }

        return synthesized
    }

    static rewriteURLAttributes(node, server, base) {
        if (!node.attrs) return
        const target = { href: true, src: true, 'data-href': true, 'data-src': true }
        node.attrs.forEach((attr) => {
            if (attr.name in target)
                try {
                    let url = new URL(attr.value, base)
                    let derived = new URL(server)
                    derived.pathname = '/' + url.href
                    attr.value = derived.href
                } catch (e) {
                    ;() => {}
                }
        })
    }
}

/* {% if retain_import_exports %} */
module.exports = { Rewriters }
/* {% endif %} */
