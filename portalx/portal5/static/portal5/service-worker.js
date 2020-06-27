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
/* globals localforage */

importScripts('localforage.min.js')

const K_SETTINGS = 'portal5:worker:settings'

self.settings = null
self.CLIENT_RECORD_LIMIT = 100

localforage.config({ name: 'portal5' })

self.addEventListener('install', (event) => {
    var init = async () => {
        let cache = await caches.open('default')
        await cache.delete('/service-worker-reinstall')
        await cache.add('/service-worker-reinstall')
        return skipWaiting()
    }
    event.waitUntil(init())
})

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim())
})

self.addEventListener('message', (event) => {
    if (event.data.msg == K_SETTINGS) {
        self.settings = event.data.settings
        localforage.setItem('portal5:worker:settings', event.data.settings)
    }
})

self.addEventListener('fetch', handleFetchRewriteURL)

function handleFetchRewriteURL(event) {
    var synthesize = async () => {
        /** @type {Request} */
        let request = event.request

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

        var settings = self.settings
        if (!self.settings) {
            settings = await localforage.getItem('portal5:worker:settings')
            // eslint-disable-next-line require-atomic-updates
            self.settings = settings
        }
        if (!self.settings) return await caches.match('/service-worker-reinstall')

        let server = settings.protocol + '://' + settings.host

        let headers = new Headers()
        request.headers.forEach((v, k) => headers.append(k, v))
        headers.set('X-Portal5-Worker-Version', settings.version.toString())

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
                let stored = await localforage.getItem('portal5:client:' + client.id)
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

        if (represented)
            localforage.setItem('portal5:client:' + client.id, { represented: represented.href, atime: Date.now() })
        trimClientRecords()

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

        headers.set('X-Portal5-Origin', referrer.origin)
        headers.set('X-Portal5-Mode', request.mode)

        let final = new URL(settings.protocol + '://' + settings.host + '/' + synthesized.href)
        if (final.href != requested.href) {
            let redirect = new Response('', { status: 307, headers: { Location: final.href } })
            return redirect
        } else {
            return fetch(new Request(final.href, requestOpts))
        }
    }
    event.respondWith(synthesize())
}

async function trimClientRecords() {
    let limit = self.CLIENT_RECORD_LIMIT
    let length = await localforage.length()
    if (length > limit) {
        let keys = await localforage.keys()
        let staleRecords = (await Promise.all(keys.map(async (k) => [k, (await localforage.getItem(k)).atime])))
            .filter((t) => t[1] != undefined)
            .sort((l, r) => r[1] - l[1])
            .slice(limit)
        await Promise.all(
            staleRecords.map(async (t) => {
                console.log(t[0].slice(15))
                let client = await clients.get(t[0].slice(15))
                if (!client) await localforage.removeItem(t[0])
            })
        )
    }
}
