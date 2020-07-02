// service-worker.js
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

const noop = () => {}

self.destinationRequiresRedirect = {
    document: true,
    embed: true,
    object: true,
    script: true,
    style: true,
    worker: true,
}

class ClientRecordContainer {
    constructor() {
        setInterval(this.trim, 300000)
    }
    add(id, url) {
        this['client:' + id] = { represented: url, atime: Date.now() }
    }
    get(id) {
        return this['client:' + id]
    }
    remove(id) {
        delete this['client:' + id]
    }
    async trim() {
        await Promise.all(
            Object.keys(this)
                .filter((k) => k.substr(0, 7) == 'client:')
                .map(async (k) => [k, await clients.get(k.substr(7))])
        ).then((r) => r.filter((r) => !r[1]).forEach((r) => delete this[r[0]]))
    }
}

class Portal5Request {
    constructor(settings) {
        this.id = settings.id
        this.version = settings.version
        this.prefs = settings.prefs.value
    }
    /**
     *
     * @param {Request} request
     * @param {URL} referrer
     * @param {URL} synthesized
     */
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
    /**
     *
     * @param {Headers} headers
     */
    setHeader(headers, mode) {
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
}

self.settings = JSON.parse('{{ settings|tojson }}')
self.server = self.settings.protocol + '://' + self.settings.host
self.clientRecords = new ClientRecordContainer()

self.addEventListener('install', (event) => {
    event.waitUntil(skipWaiting())
})

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim())
})

self.addEventListener('fetch', requiresAuthorization)
self.addEventListener('fetch', rewriteURL)

function requiresAuthorization(event) {
    /** @type {Request} */
    let request = event.request
    let url = new URL(request.url)
    if (url.pathname in self.settings.restricted) {
        if (request.mode != 'navigate')
            return event.respondWith(new Response(`Unacceptable request mode ${request.mode}`, { status: 403 }))
        if (request.method != 'GET' && request.method != 'POST')
            return event.respondWith(new Response(`Unacceptable HTTP method ${request.method}`, { status: 403 }))

        let headers = new Headers()
        let p5 = new Portal5Request(self.settings)
        p5.setHeader(headers, 'secret')

        event.respondWith(
            (async () => {
                let requestOpts = {
                    method: request.method,
                    mode: 'same-origin',
                    credentials: 'same-origin',
                    headers: headers,
                }
                if (request.method == 'POST') requestOpts.body = await request.blob()
                let response = await fetch(request.url, requestOpts)
                return response
            })()
        )
    }
}

function rewriteURL(event) {
    event.respondWith(
        (async () => {
            /** @type {Request} */
            let request = event.request
            let settings = self.settings

            var client = await clients.get(event.clientId || event.replacesClientId)
            if (!client && 'clients' in self && 'matchAll' in clients) {
                let windows = await clients.matchAll({ type: 'window' })
                windows = windows.filter((w) => w.url == request.referrer)
                if (windows) client = windows[0]
            }

            let requested = new URL(request.url)
            let referrer
            try {
                referrer = new URL(request.referrer)
            } catch (e) {
                noop()
            }

            if (!settings.prefs.local['basic_rewrite_crosssite'] && self.server != requested.origin)
                return fetch(request.clone())

            var synthesized = await synthesizeURL(requested, referrer, client, self.clientRecords, self.server)

            if (synthesized.url.hostname in settings.passthru.domains || synthesized.url.href in settings.passthru.urls)
                return fetch(request.clone())

            let final =
                synthesized.url.origin != self.server
                    ? new URL(self.server + '/' + synthesized.url.href)
                    : synthesized.url
            if (final.href != requested.href && request.destination in self.destinationRequiresRedirect) {
                let redirect = new Response('', { status: 307, headers: { Location: final.href } })
                return redirect
            }

            let requestOpts = await makeRequestOptions(request)

            let p5 = new Portal5Request(settings)
            p5.setReferrer(request, synthesized)
            p5.setHeader(requestOpts.headers)

            let response = await fetch(new Request(final.href, requestOpts))
            return response
        })()
    )
}

/**
 *
 * @param {URL} requested
 * @param {URL} referrer
 * @param {Client} client
 * @param {ClientRecordContainer} savedClients
 * @param {String} prefix
 */
async function synthesizeURL(requested, referrer, client, savedClients, prefix) {
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

    if (!represented) represented = referrer
    if (!referrer) referrer = represented

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
        synthesized.url = new URL(trimPrefix(synthesized.url.href, prefix + '/'), prefix)
    } catch (e) {
        noop()
    }

    return synthesized
}

async function makeRequestOptions(request) {
    let headers = new Headers()
    request.headers.forEach((v, k) => headers.append(k, v))

    let requestOpts = {
        method: request.method,
        headers: headers,
        credentials: request.credentials,
        cache: request.cache,
        redirect: request.redirect,
        integrity: request.integrity,
        referrer: '',
        referrerPolicy: request.referrerPolicy,
        mode: request.mode == 'same-origin' || request.mode == 'no-cors' ? 'same-origin' : 'cors',
    }

    let body = await request.blob()
    if (body.size > 0) requestOpts.body = body

    return requestOpts
}

function trimPrefix(str, prefix) {
    if (str.startsWith(prefix)) return trimPrefix(str.substr(prefix.length), prefix)
    return str
}
