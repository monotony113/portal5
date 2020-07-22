// portal5.js
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

/* eslint-env serviceworker */

const { Injector } = require('./injector')
var parse5
try {
    parse5 = require('parse5')
} catch (e) {
    parse5 = undefined
}

class Portal5 {
    constructor(settings) {
        this.id = settings.id
        this.version = settings.version
        this.secret = settings.secret
        this.prefs = settings.prefs.value
        this.signals = Object.assign({}, settings.signals)
    }
    setReferrer(request, referrer, destination) {
        this.mode = request.mode
        if (referrer) {
            this.origin = referrer.origin
            let setReferrer = (part) => (this.referrer = referrer[part])
            switch (request.referrerPolicy) {
                case 'no-referrer':
                    break
                case 'no-referrer-when-downgrade':
                    if (destination.protocol === referrer.protocol) setReferrer('href')
                    break
                case 'origin':
                    setReferrer('origin')
                    break
                case 'origin-when-cross-origin':
                    if (destination.origin != referrer.origin) setReferrer('origin')
                    else setReferrer('href')
                    break
                case 'same-origin':
                    if (destination.origin === referrer.origin) setReferrer('href')
                    break
                case 'strict-origin':
                    if (destination.protocol === referrer.protocol) setReferrer('origin')
                    break
                case 'strict-origin-when-cross-origin':
                    if (destination.origin === referrer.origin) setReferrer('href')
                    else if (destination.protocol === referrer.protocol) setReferrer('origin')
                    break
                default:
                    setReferrer('href')
                    break
            }
        }
    }
    applyDirective(directives) {
        if (directives['revalidate-on-next-request']) {
            delete directives['revalidate-on-next-request']
            this.signals['revalidate'] = true
        }
    }
    writeHeader(headers, mode) {
        let p5 = {}

        let attributes = []
        switch (mode) {
            case 'regular':
                attributes = ['version', 'prefs', 'mode', 'origin', 'referrer', 'signals']
                break
            case 'identity':
                attributes = ['id', 'version', 'prefs', 'signals']
                break
            default:
                break
        }
        for (let i = 0; i < attributes.length; i++) p5[attributes[i]] = this[attributes[i]]

        headers[Portal5.headerName] = JSON.stringify(p5)
    }
    static parseDirectives(response) {
        return JSON.parse(response.headers.get('X-Portal5-Signal') || '{}')
    }
    static async rewriteResponse(response, base) {
        let contentType = response.headers.get('Content-Type')
        if (contentType && contentType.startsWith('text/html')) {
            try {
                let text = await response.text()
                let body = null
                if (text.length) {
                    let document = parse5.parse(text)
                    let observer = Injector.makeElementNode('script', {
                        src: `/~/client/injection.js?args=${btoa(JSON.stringify({ base: base }))}`,
                        referrerpolicy: 'no-referrer',
                    })
                    let head = Injector.dfsFirstInTree(document, (node) => node.tagName === 'head', 'childNodes')
                    Injector.prepend(head, observer)
                    body = parse5.serialize(document)
                }
                let res = new Response(body, {
                    status: response.status,
                    statusText: response.statusText,
                    headers: response.headers,
                })
                return res
            } catch (e) {
                ;() => {}
            }
        }
        return response
    }
}
Portal5.headerName = 'X-Portal5'

module.exports = { Portal5 }
