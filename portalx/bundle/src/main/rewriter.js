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

const { Utils } = require('./utils')

class Rewriters {
    static synthesizeURL(base, referrer, requested, prefix) {
        let synthesized = {
            base: null,
            ref: null,
            dest: new URL('http://example.org'),
        }

        if (!base) base = referrer
        if (!referrer) referrer = base

        if (base) synthesized.base = new URL(base)

        if (referrer) {
            try {
                synthesized.ref = new URL(referrer.pathname.slice(1))
                synthesized.ref.search = referrer.search
                synthesized.ref.hash = referrer.hash
            } catch (e) {
                if (base) {
                    synthesized.ref = new URL(referrer)
                    synthesized.ref.protocol = base.protocol
                    synthesized.ref.host = base.host
                }
            }
        }

        if (prefix != requested.origin) {
            synthesized.dest = new URL(requested)
        } else {
            try {
                synthesized.dest = new URL(requested.pathname.slice(1))
            } catch (e) {
                if (synthesized.ref) {
                    synthesized.dest = new URL(synthesized.ref)
                } else {
                    synthesized.dest = new URL(prefix)
                }
                synthesized.dest.pathname = requested.pathname
            }
        }

        synthesized.dest.search = requested.search
        synthesized.dest.hash = requested.hash

        try {
            synthesized.dest = new URL(Utils.trimPrefix(synthesized.dest.href, prefix + '/'), prefix)
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

module.exports = { Rewriters }
