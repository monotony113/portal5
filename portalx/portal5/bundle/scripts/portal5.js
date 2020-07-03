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

/* {% set retain_import_exports = False %} */
/* {% if retain_import_exports %} */
const parse5 = require('parse5')
const { Injector } = require('./injector')
/* {% endif %} */

const observerScript = `{% include "scripts/observer.js" %}`

class Portal5Request {
    constructor(settings) {
        this.id = settings.id
        this.version = settings.version
        this.prefs = settings.prefs.value
    }
    setReferrer(request, synthesized) {
        this.mode = request.mode
        let referrer = synthesized.referrer
        synthesized = synthesized.url
        if (referrer) {
            this.origin = referrer.origin
            let setReferrer = (part) => (this.referrer = referrer[part])
            switch (request.referrerPolicy) {
                case 'no-referrer':
                    break
                case 'no-referrer-when-downgrade':
                    if (synthesized.protocol == referrer.protocol) setReferrer('href')
                    break
                case 'origin':
                    setReferrer('origin')
                    break
                case 'origin-when-cross-origin':
                    if (synthesized.origin != referrer.origin) setReferrer('origin')
                    else setReferrer('href')
                    break
                case 'same-origin':
                    if (synthesized.origin == referrer.origin) setReferrer('href')
                    break
                case 'strict-origin':
                    if (synthesized.protocol == referrer.protocol) setReferrer('origin')
                    break
                case 'strict-origin-when-cross-origin':
                    if (synthesized.origin == referrer.origin) setReferrer('href')
                    else if (synthesized.protocol == referrer.protocol) setReferrer('origin')
                    break
                default:
                    setReferrer('href')
                    break
            }
        }
    }
    writeHeader(headers, mode) {
        let p5 = Object.assign({}, this)
        switch (mode) {
            case 'secret':
                delete p5.mode
                delete p5.origin
                delete p5.referrer
                break
            default:
                delete p5.id
                break
        }
        headers.set('X-Portal5', JSON.stringify(p5))
    }
    static async rewriteResponse(response, prefix, base) {
        let contentType = response.headers.get('Content-Type')
        if (contentType && contentType.startsWith('text/html')) {
            try {
                let text = await response.text()
                let body = null
                if (text.length) {
                    let document = parse5.parse(text)
                    let observer = Injector.makeElementNode('script', {}, observerScript)
                    let head = Injector.dfsFirstInTree(document, (node) => node.tagName == 'head', 'childNodes')
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

/* {% if retain_import_exports %} */
module.exports = { Portal5Request }
/* {% endif %} */
