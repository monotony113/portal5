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

/* {% set retain_import_exports = False %} */
/* {% if retain_import_exports %} */
const { Rewriters } = require('./rewriter')
const { Utils } = require('./utils')
const { Portal5Request } = require('./portal5')
/* {% endif %} */

importScripts('/~/scripts/injector.js', '/~/scripts/rewriter.js', '/~/scripts/portal5.js', '/~/scripts/utils.js')

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

function authorizationRequired(event) {
    /** @type {Request} */
    let request = event.request
    let url = new URL(request.url)
    if (url.pathname in self.settings.authRequired) {
        if (request.mode != 'navigate')
            return event.respondWith(new Response(`Unacceptable request mode ${request.mode}`, { status: 403 }))
        if (request.method != 'GET' && request.method != 'POST')
            return event.respondWith(new Response(`Unacceptable HTTP method ${request.method}`, { status: 403 }))

        let headers = new Headers()
        let p5 = new Portal5Request(self.settings)
        p5.writeHeader(headers, 'secret')

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

function rewriteRequest(event) {
    event.respondWith(
        (async () => {
            /** @type {Request} */
            let request = event.request
            let settings = self.settings
            console.log(request.referrer, request.destination)
            var client = await clients.get(event.clientId || event.replacesClientId)
            if (!client && 'clients' in self && 'matchAll' in clients) {
                let windows = await clients.matchAll({ type: 'window' })
                windows = windows.filter(
                    (w) => w.url == request.referrer || w.focused || w.visibilityState == 'visible'
                )
                if (windows) client = windows[0]
            }

            let requested = new URL(request.url)
            let referrer
            try {
                referrer = new URL(request.referrer)
            } catch (e) {
                ;() => {}
            }

            if (!settings.prefs.local['basic_rewrite_crosssite'] && self.server != requested.origin)
                return fetch(request.clone())

            var synthesized = await Rewriters.synthesizeURL(
                requested,
                referrer,
                client,
                self.clientRecords,
                self.server
            )

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

            let requestOpts = await Utils.makeRequestOptions(request)

            let p5 = new Portal5Request(settings)
            p5.setReferrer(request, synthesized)
            p5.writeHeader(requestOpts.headers)

            let outbound = new Request(final.href, requestOpts)

            if (settings.prefs.local['injection_dom_hijack']) {
                let response = await fetch(outbound)
                return await Portal5Request.rewriteResponse(response, self.server, synthesized.url)
            }
            return fetch(outbound)
        })()
    )
}

self.destinationRequiresRedirect = {
    document: true,
    embed: true,
    object: true,
    script: true,
    style: true,
    worker: true,
}

self.settings = JSON.parse('{{ settings|default(dict())|tojson }}')
self.server = self.settings.protocol + '://' + self.settings.host
self.clientRecords = new ClientRecordContainer()

self.addEventListener('install', (event) => {
    event.waitUntil(skipWaiting())
})

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim())
})

self.addEventListener('fetch', authorizationRequired)
self.addEventListener('fetch', rewriteRequest)

/* {% if requires_bundle %} */
importScripts('/~/static/scripts/bundle.min.js')
/* {% endif %} */
