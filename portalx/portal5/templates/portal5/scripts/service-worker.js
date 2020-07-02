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

self.destinationRequiresRedirect = {
    document: true,
    embed: true,
    object: true,
    script: true,
    style: true,
    worker: true,
}

self.settings = JSON.parse('{{ settings|tojson }}')
self.server = self.settings.protocol + '://' + self.settings.host

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
        if (request.mode != 'navigate') throw new Error(`Unacceptable request mode ${request.mode}`)
        if (request.method != 'GET' && request.method != 'POST')
            throw new Error(`Unacceptable HTTP method ${request.method}`)

        let settings = self.settings
        let headers = new Headers()

        let p5 = new Object()
        p5.version = settings.version
        p5.id = settings.id
        headers.set('X-Portal5', JSON.stringify(p5))

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
                console.log(response.status)
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

            var { referrer, synthesized, requested } = await synthesizeURL(request, client)
            if (synthesized.hostname in settings.passthru.domains || synthesized.href in settings.passthru.urls)
                return fetch(request.clone())

            let final = synthesized.origin != self.server ? new URL(self.server + '/' + synthesized.href) : synthesized
            if (final.href != requested.href && request.destination in self.destinationRequiresRedirect) {
                let redirect = new Response('', { status: 307, headers: { Location: final.href } })
                return redirect
            }

            let requestOpts = await makeRequestOptions(request, referrer, synthesized)

            return fetch(new Request(final.href, requestOpts))
        })()
    )
}

/**
 *
 * @param {Request} request
 * @param {Client} client
 */
async function synthesizeURL(request, client) {
    let location = null
    let represented = null
    let referrer = null
    let requested = new URL(request.url)
    let synthesized = new URL('http://example.org')

    if (client) {
        location = new URL(client.url)
        try {
            represented = new URL(location.pathname.substr(1))
        } catch (e) {
            let stored = self.clientRecords.get(client.id)
            if (stored) {
                represented = new URL(stored.represented)
                represented.pathname = location.pathname
            }
        }
        if (represented) {
            represented.search = location.search
            represented.hash = location.hash
        }
    }

    if (represented) self.clientRecords.add(client.id, represented.href)

    if (request.referrer) {
        let referrerURL = new URL(request.referrer)
        try {
            referrer = new URL(referrerURL.pathname.substr(1))
            referrer.search = referrerURL.search
            referrer.hash = referrerURL.hash
        } catch (e) {
            if (represented) {
                referrer = referrerURL
                referrer.protocol = represented.protocol
                referrer.host = represented.host
            }
        }
    }

    if (!represented) represented = referrer
    if (!referrer) referrer = represented

    if (self.server != requested.origin) {
        synthesized = new URL(requested)
    } else {
        try {
            synthesized = new URL(requested.pathname.substr(1))
        } catch (e) {
            if (referrer) {
                synthesized = new URL(referrer)
            } else {
                synthesized = new URL(self.server)
            }
            synthesized.pathname = requested.pathname
        }
    }

    synthesized.search = requested.search
    synthesized.hash = requested.hash

    synthesized = new URL(trimPrefix(synthesized.href, self.server + '/'), self.server)

    return { referrer, synthesized, requested }
}

async function makeRequestOptions(request, referrer, synthesized) {
    let p5 = new Object()
    p5.version = self.settings.version

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

    if (referrer) {
        let setReferrer = (part) => (p5.referrer = referrer[part])
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

    if (referrer) p5.origin = referrer.origin
    p5.mode = request.mode

    headers.set('X-Portal5', JSON.stringify(p5))

    return requestOpts
}

function trimPrefix(str, prefix) {
    if (str.startsWith(prefix)) return trimPrefix(str.substr(prefix.length), prefix)
    return str
}
