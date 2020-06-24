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

const WORKER_VERSION = 2

const PREFIX = '/portal5/'
const PASSTHRU = {}
PASSTHRU[PREFIX] = true
PASSTHRU[PREFIX + 'index.js'] = true
PASSTHRU[PREFIX + 'index.html'] = true
PASSTHRU[PREFIX + 'style.css'] = true

self.addEventListener('install', (event) => {
    event.waitUntil(skipWaiting())
})

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim())
})

self.addEventListener('message', (event) => {
    let settings = JSON.parse(event.data)
    console.log(settings)
})

self.addEventListener('fetch', handleFetchRewriteURL)

function handleFetchRewriteURL(event) {
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

    let headers = new Headers()
    request.headers.forEach((v, k) => headers.append(k, v))
    headers.set('X-Portal5-Worker-Version', WORKER_VERSION.toString())

    let requestOpts = {
        method: request.method,
        headers: headers,
        body: request.body,
        credentials: request.credentials,
        cache: request.cache,
        redirect: request.redirect,
        integrity: request.integrity,
        referrer: '',
        mode: request.mode == 'same-origin' ? 'same-origin' : 'cors',
    }

    var synthesize = async () => {
        let server
        const client = await clients.get(event.clientId || event.replacesClientId)
        if (client) {
            location = new URL(client.url)
            represented = new URL(location.pathname.substr(9))
            server = location.origin
        }

        if (request.referrer)
            switch (request.referrerPolicy) {
                case 'no-referrer-when-downgrade':
                    break
            }

        if (server != requested.origin) {
            synthesized.pathname = PREFIX + requested.origin + requested.pathname
            synthesized.username = requested.username
            synthesized.password = requested.password
            synthesized.search = requested.search
            synthesized.hash = requested.hash
        } else {
            if (requested.pathname in PASSTHRU) return fetch(request)
            const rePrefixWithHost = new RegExp('^' + PREFIX + represented.protocol + '//' + represented.host)
            const rePrefixWithProtocol = new RegExp('^' + PREFIX + represented.protocol + '/')

            let protocol = represented.protocol
            let host = represented.host
            let pathname = requested.pathname

            if (!rePrefixWithProtocol.test(pathname)) {
                synthesized.pathname = PREFIX + protocol + '//' + host + pathname
            } else if (!rePrefixWithHost.test(requested.pathname)) {
                synthesized.pathname = PREFIX + protocol + '//' + host + pathname.replace(rePrefixWithProtocol, '')
            } else {
                synthesized.pathname = pathname
            }
        }

        synthesized.search = requested.search

        headers.set('X-Portal5-Referrer', referrer)

        let redirect = new Request(synthesized.href, requestOpts)
        return fetch(redirect)
    }

    event.respondWith(synthesize())
}
