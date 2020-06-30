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

self.DESTINATION_307 = {
    document: true,
    embed: true,
    object: true,
    script: true,
    style: true,
    worker: true,
}

self.settings = JSON.parse('{{ settings|tojson }}')

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

self.addEventListener('fetch', handleFetchRewriteURL)

function handleFetchRewriteURL(event) {
    var synthesize = async () => {
        /** @type {Request} */
        let request = event.request
        /** @type {ClientRecordContainer} */
        let clientRecords = self.clientRecords

        var settings = self.settings
        let server = settings.protocol + '://' + settings.host

        // URLs parsed from different sources that will be used to synthesize the final URL for network request
        /**
         * Location of the window that fired this `FetchEvent`, collected from `client.url`, where `client` (the window)
         * is accessed using `FetchEvent.clientId` or `FetchEvent.replacesClientId`
         * @type {URL}
         */
        let location = null
        /**
         * URL to the actual resource that the user is currently visiting (that is instead served via this server);
         * equals `location` minus any server prefixes.
         * @type {URL}
         */
        let represented = null
        /**
         * The referrer, parsed from `FetchEvent.request.referrer`; may not be available depending on the referrer policy.
         * @type {URL}
         */
        let referrer = null
        /**
         * The requested URL that needs to be worked on, from `FetchEvent.request.url`.
         * @type {URL}
         */
        let requested = new URL(request.url)
        /**
         * Stores the final, correct URL, synthesized from the above URLs.
         * @type {URL}
         */
        let synthesized = new URL('http://example.org')

        let headers = new Headers()
        request.headers.forEach((v, k) => headers.append(k, v))
        headers.set('X-Portal5-Worker-Version', settings.version.toString())

        var client = await clients.get(event.clientId || event.replacesClientId)
        if (!client && 'clients' in self && 'matchAll' in clients) {
            let windows = await clients.matchAll({ type: 'window' })
            windows = windows.filter((w) => w.url == request.referrer)
            if (windows) client = windows[0]
        }

        if (client) {
            location = new URL(client.url)
            try {
                represented = new URL(location.pathname.substr(1))
            } catch (e) {
                let stored = clientRecords.get(client.id)
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

        if (represented) clientRecords.add(client.id, represented.href)

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

        if (server != requested.origin) {
            synthesized = new URL(requested)
        } else {
            try {
                synthesized = new URL(requested.pathname.substr(1))
            } catch (e) {
                if (referrer) {
                    synthesized = new URL(referrer)
                } else {
                    synthesized = new URL(server)
                }
                synthesized.pathname = requested.pathname
            }
        }

        synthesized.search = requested.search
        synthesized.hash = requested.hash

        if (synthesized.hostname in settings.passthru.domains || synthesized.href in settings.passthru.urls)
            return fetch(request.clone())

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
            let setReferrer = (part) => headers.set('X-Portal5-Referrer', referrer[part])
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

        if (referrer) headers.set('X-Portal5-Origin', referrer.origin)
        headers.set('X-Portal5-Mode', request.mode)

        let final = new URL(server + '/' + synthesized.href)

        if (final.href != requested.href && request.destination in self.DESTINATION_307) {
            let redirect = new Response('', { status: 307, headers: { Location: final.href } })
            return redirect
        }

        return fetch(new Request(final.href, requestOpts))
    }
    event.respondWith(synthesize())
}
