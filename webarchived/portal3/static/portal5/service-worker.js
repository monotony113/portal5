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
PASSTHRU[PREFIX + 'index.js'] = true
PASSTHRU[PREFIX + 'index.html'] = true
PASSTHRU[PREFIX + 'style.css'] = true

self.addEventListener('install', (event) => {
    event.waitUntil(skipWaiting())
})

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim())
})

self.addEventListener('fetch', (event) => {
    /** @type {Request} */
    let request = event.request
    let requestURL = new URL(request.url)

    let synthesizedHeaders = new Headers()
    request.headers.forEach((v, k) => synthesizedHeaders.append(k, v))
    synthesizedHeaders.set('X-Portal5-Worker-Version', WORKER_VERSION.toString())

    let requestOpts = {
        method: request.method,
        headers: synthesizedHeaders,
        body: request.body,
        credentials: request.credentials,
        cache: request.cache,
        redirect: request.redirect,
        integrity: request.integrity,
        referrer: '',
        mode: 'cors',
    }

    var synthesize = async () => {
        const client = await clients.get(event.clientId)
        if (!client) return fetch(request)
        if (request.destination == 'document') return fetch(new Request(request.url, requestOpts))
        var clientURL = new URL(client.url)
        if (clientURL.pathname === PREFIX) return fetch(request)

        var server = clientURL.origin

        var documentURL = new URL(clientURL.pathname.substr(9))

        synthesizedHeaders.set('X-Portal5-Referrer', documentURL)

        var synthesizedURL = new URL(`${clientURL.protocol}//${clientURL.host}`)
        synthesizedURL.search = requestURL.search

        if (server != requestURL.origin) {
            synthesizedURL.pathname = PREFIX + requestURL.origin + requestURL.pathname
            synthesizedURL.username = requestURL.username
            synthesizedURL.password = requestURL.password
            synthesizedURL.search = requestURL.search
            synthesizedURL.hash = requestURL.hash
        } else {
            if (requestURL.pathname in PASSTHRU) return fetch(request)
            const rePrefixWithHost = new RegExp('^' + PREFIX + documentURL.protocol + '//' + documentURL.host)
            const rePrefixWithProtocol = new RegExp('^' + PREFIX + documentURL.protocol + '/')

            let protocol = documentURL.protocol
            let host = documentURL.host
            let pathname = requestURL.pathname

            if (!rePrefixWithProtocol.test(pathname)) {
                synthesizedURL.pathname = PREFIX + protocol + '//' + host + pathname
            } else if (!rePrefixWithHost.test(requestURL.pathname)) {
                synthesizedURL.pathname = PREFIX + protocol + '//' + host + pathname.replace(rePrefixWithProtocol, '')
            } else {
                synthesizedURL.pathname = pathname
            }
        }

        let redirect = new Request(synthesizedURL.href, requestOpts)
        return fetch(redirect)
    }

    event.respondWith(synthesize())
})
