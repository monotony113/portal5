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
const { Portal5 } = require('./portal5')
/* {% endif %} */

importScripts('/~/scripts/injector.js', '/~/scripts/rewriter.js', '/~/scripts/portal5.js', '/~/scripts/utils.js')

class ClientRecordContainer {
    constructor() {
        this.enableTrim()
    }
    enableTrim() {
        this.interval = setInterval(this.trim, 300000)
    }
    pauseTrim() {
        clearInterval(this.interval)
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

function securityCheck(event) {
    /** @type {Request} */
    let request = event.request
    if (request.headers.get(Portal5.headerName)) event.respondWith(new Response(null, { status: 403 }))
}

function specialRoutes(event) {
    /** @type {Request} */
    let request = event.request
    let url = new URL(request.url)
    if (!request.referrer && request.mode == 'navigate' && (request.method == 'GET' || request.method == 'POST')) {
        let handler = self.settings.endpoints[url.pathname]
        switch (handler) {
            case 'directFetch':
                event.respondWith(fetch(event.request))
                break
            case 'authRequired':
                return authorizationRequired(event)
            default:
                break
        }
    }
}

function authorizationRequired(event) {
    /** @type {Request} */
    let request = event.request
    if (request.mode != 'navigate')
        return event.respondWith(new Response(`Unacceptable request mode ${request.mode}`, { status: 403 }))
    if (request.destination != 'document')
        return event.respondWith(
            new Response(`Unacceptable request destination ${request.destination}`, { status: 403 })
        )

    let requestOpts = {
        method: request.method,
        headers: new Headers(),
        mode: 'same-origin',
        credentials: 'same-origin',
        redirect: 'manual',
    }

    let p5 = new Portal5(self.settings)
    p5.setDirective(self.directives)
    p5.writeHeader(requestOpts.headers, 'identity')

    event.respondWith(
        (async () => {
            if (request.method == 'POST') requestOpts.body = await request.blob()
            return makeFetch(new Request(request.url, requestOpts))
        })()
    )
}

async function getClient(event) {
    var client
    client = await clients.get(event.clientId || event.replacesClientId)
    if (!client && 'clients' in self && 'matchAll' in clients) {
        let windows = await clients.matchAll({ type: 'window' })
        windows = windows.filter((w) => w.url == event.request.referrer || w.visibilityState == 'visible' || w.focused)
        if (windows) client = windows[0]
    }
    return client
}

function rewriteRequest(event) {
    event.respondWith(
        (async () => {
            /** @type {Request} */
            let request = event.request
            let settings = self.settings

            var client = await getClient(event)

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

            let p5 = new Portal5(settings)
            p5.setReferrer(request, synthesized)
            if (request.mode == 'navigate') {
                p5.setDirective(self.directives)
            }
            p5.writeHeader(requestOpts.headers, 'regular')

            let outbound = new Request(final.href, requestOpts)
            return makeFetch(outbound, {
                injection_dom_hijack: {
                    run: Portal5.rewriteResponse,
                    args: [self.server, synthesized.url],
                },
            })
        })()
    )
}

async function makeFetch(request, useFeatures = null) {
    let response = await fetch(request)

    let directives = Portal5.parseDirectives(response)
    for (let k in directives) self.directives[k] = directives[k]

    let prefs = self.settings.prefs.local
    if (useFeatures != null) {
        let featureNames = Object.keys(useFeatures)
        for (let i = 0; i < featureNames.length; i++) {
            let name = featureNames[i]
            if (!prefs[name]) continue
            let options = useFeatures[name]
            response = await options.run(response, ...options.args)
        }
    }
    return response
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
self.server = self.settings.origin

self.clientRecords = new ClientRecordContainer()
self.directives = {}

self.addEventListener('install', (event) => {
    event.waitUntil(skipWaiting())
})

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim())
})

self.addEventListener('fetch', securityCheck)
self.addEventListener('fetch', specialRoutes)
self.addEventListener('fetch', rewriteRequest)

/* {% if requires_bundle %} */
importScripts('/~/static/scripts/bundle.min.js')
/* {% endif %} */
