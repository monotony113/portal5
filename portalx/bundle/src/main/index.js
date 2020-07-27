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

self.settings = JSON.parse('{{ settings|default(dict({"":0}))|tojson }}')
self.urlRules = JSON.parse('{{ url_rules|default(dict({"":0}))|tojson }}')

if (self.settings.vendor) importScripts('{{ g.server_map["origins"]["static"] }}/vendor.min.js')

const { Portal5 } = require('./portal5')
const { Rewriters } = require('./rewriter')
const { TranscientStorage, ClientRecordStorage, Utils } = require('./utils')

function securityCheck(event) {
    /** @type {Request} */
    let request = event.request
    if (request.headers.get(Portal5.headerName)) event.respondWith(new Response(null, { status: 403 }))
}

class DefinedHandlers {
    static passthrough(event) {
        return event.respondWith(fetch(event.request))
    }
    static forbidden(event) {
        return event.respondWith(new Response('', { status: 403 }))
    }
    static restricted(event) {
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
            headers: {},
            mode: 'same-origin',
            credentials: 'same-origin',
            redirect: 'manual',
        }

        let p5 = new Portal5(self.settings)
        p5.applyDirective(self.directives)
        p5.writeHeader(requestOpts.headers, 'identity')

        return event.respondWith(
            (async () => {
                if (request.method === 'POST') requestOpts.body = await request.blob()
                return doFetch(new Request(request.url, requestOpts))
            })()
        )
    }
    static disambiguate(event) {
        return event.respondWith(
            (async () => {
                let request = event.request
                let form
                switch (request.method) {
                    case 'GET':
                        form = new URL(request.url).searchParams
                        break
                    case 'POST':
                        form = new URLSearchParams(
                            await Utils.readBlob(await request.blob(), FileReader.prototype.readAsText)
                        )
                        break
                    default:
                        return new Response('', { status: 400 })
                }

                let requestOpts = self.requestOptsCache.remove(form.get('request_opts'), 'request')
                let resumeRequest = new Request(`/~deflect?to=/${encodeURIComponent(form.get('dest'))}`, requestOpts)

                let p5 = new Portal5(self.settings)
                p5.setReferrer(resumeRequest, form.get('referrer'), form.get('dest'))
                p5.writeHeader(requestOpts, 'regular')

                return fetch(resumeRequest)
            })()
        )
    }
}

function withDefinedHandlers(event) {
    /** @type {Request} */
    let request = event.request
    let url = new URL(request.url)
    let endpoint = self.urlRules.endpoints[url.pathname]
    if (!endpoint) return

    let { handler, test } = endpoint
    if (handler) {
        for (let param in test) {
            let allowedValues = test[param]
            if (!(request[param] in allowedValues)) return
        }
        return DefinedHandlers[handler](event)
    }
}

function noRewrite(event) {
    let request = event.request
    let requested = new URL(request.url)
    if (!(requested.protocol in { 'http:': 1, 'https:': 1 })) return event.respondWith(fetch(request.clone()))
    if (!self.settings.prefs.local['basic_rewrite_crosssite']) {
        if (self.server != requested.origin) return event.respondWith(fetch(request.clone()))
    }
    if (request.mode == 'navigate' && requested.pathname.slice(0, 8) == '/direct/')
        return event.respondWith(fetch(request.clone()))
}

function shouldPassthru(url) {
    return url.hostname in self.urlRules.passthrough.domains || url.href in self.urlRules.passthrough.urls
}

function makeRedirect(url) {
    return new Response('', { status: 307, headers: { Location: url } })
}

async function getLocations(event, savedClients) {
    var windows = []
    let client = await clients.get(event.clientId || event.replacesClientId)
    if (client) windows.push(client)
    else if ('matchAll' in clients)
        windows = windows.concat(
            windows,
            (await clients.matchAll({ type: 'window' })).filter((w) => w.url === event.request.referrer || w.focused)
        )

    var locations = []
    for (let i = 0; i < windows.length; i++) {
        let windowClient = windows[i]
        let location = new URL(windowClient.url)

        let represented
        try {
            represented = new URL(location.pathname.slice(1))
        } catch (e) {
            if (savedClients) {
                let stored = savedClients.get(windowClient.id)
                if (stored) {
                    represented = new URL(stored.represented)
                    represented.pathname = location.pathname
                }
            }
        }
        if (represented) {
            represented.search = location.search
            represented.hash = location.hash
            locations.push(represented)
            if (savedClients) savedClients.add(windowClient.id, represented.href)
        }
    }
    return locations
}

async function filterMultipleChoices(destinations) {
    if (destinations.length === 1) return destinations
    let deduped = {}
    let j = 0
    for (let i = 0; i < destinations.length; i++) {
        let tuple = destinations[i]
        let href = tuple['dest'].href
        let existing = deduped[href]
        if (!existing) {
            deduped[href] = existing = tuple
            j++
        }
        if (existing.ref.origin === tuple.ref.origin) existing.ref = tuple.ref
    }
    destinations = Object.values(deduped)
    if (j === 1) return destinations
    if (self.settings.prefs.local['disambiguation_test_url']) {
        try {
            let filtered = (
                await Promise.all(
                    destinations.map(async (t) => [
                        t,
                        await fetch('/direct/' + t.dest.href, {
                            method: 'HEAD',
                            redirect: 'manual',
                        }),
                    ])
                )
            )
                .filter((p) => (p[1].status >= 200 && p[1].status < 300) || p[1].status === 405)
                .map((p) => p[0])
            if (filtered.length) destinations = filtered
        } catch (e) {
            ;() => {}
        }
    }
    return destinations
}

async function doMultipleChoices(request, destinations) {
    let requestInfo = await Utils.makeRequestOptions(request)
    let metadata = {
        request: requestInfo,
        candidates: destinations,
    }

    let requestId = Date.now() + '.' + Math.random()
    self.requestOptsCache.add(requestId, requestInfo, 'request')
    metadata.id = requestId

    let p5 = new Portal5(self.settings)
    let opts = {
        method: request.method,
        headers: {},
        redirect: 'manual',
    }
    if (request.method === 'GET') {
        p5.signals['disambiguate'] = JSON.parse(JSON.stringify(metadata))
    } else {
        opts.body = JSON.stringify(metadata)
        opts.headers['Content-Type'] = 'application/json'
    }
    p5.writeHeader(opts.headers, 'regular')

    let params = new URL(request.url).searchParams
    let api = '/~multiple-choices'
    if (params.has('_portal5origin')) api += `?_portal5origin=${params.get('_portal5origin')}`
    return fetch(api, opts)
}

async function interceptFetch(event) {
    var request = event.request
    var destinations = await resolveFetch(event)
    destinations = await filterMultipleChoices(destinations)

    let referrer = undefined
    let dest = undefined
    if (destinations.length === 1) {
        let synthesized = destinations[0]
        referrer = synthesized.ref
        dest = synthesized.dest
    } else if (request.mode === 'navigate') {
        return doMultipleChoices(request, destinations)
    }

    if (!dest) {
        dest = new URL(request.url)
    }
    dest.pathname = Utils.trimPrefix(dest.pathname, '/' + dest.origin)

    if (shouldPassthru(dest)) {
        return fetch(request.clone())
    }

    let final
    if (dest.origin != self.server) {
        final = new URL(self.server + '/' + dest.href)
    } else {
        final = dest
    }

    if (
        dest.origin != new URL(request.url).origin &&
        final.href != request.url &&
        request.destination in self.destinationRequiresRedirect
    ) {
        return makeRedirect(final.href)
    }
    let outbound = await makeFetch(request, referrer, final)
    return doFetch(outbound, {
        injection_dom_hijack: {
            run: Portal5.inject,
            signal: 'hijack',
            args: [dest],
        },
    })
}

async function resolveFetch(event) {
    /** @type {Request} */
    let request = event.request

    let requested = new URL(request.url)
    let referrer
    try {
        referrer = new URL(request.referrer)
    } catch (e) {
        ;() => {}
    }

    var locations = await getLocations(event, self.clientRecords)
    var destinations = []
    if (locations.length) {
        for (let i = 0; i < locations.length; i++) {
            let represented = locations[i]
            destinations.push(Rewriters.synthesizeURL(represented, referrer, requested, self.server))
        }
    } else {
        destinations.push(Rewriters.synthesizeURL(null, referrer, requested, self.server))
    }

    return destinations
}

async function makeFetch(request, referrer, destination) {
    let p5 = new Portal5(self.settings)
    let requestOpts = await Utils.makeRequestOptions(request)
    if (requestOpts.mode === 'navigate') requestOpts.redirect = 'manual'
    p5.setReferrer(request, referrer, destination)
    if (request.method === 'GET' && request.mode === 'navigate') {
        p5.applyDirective(self.directives)
    }
    p5.writeHeader(requestOpts.headers, 'regular')

    let outbound = new Request(destination.href, requestOpts)
    return outbound
}

async function doFetch(request, useFeatures = null) {
    let response = await fetch(request)

    let directives = Portal5.parseDirectives(response)

    let prefs = self.settings.prefs.local
    if (useFeatures != null) {
        let featureNames = Object.keys(useFeatures)
        for (let i = 0; i < featureNames.length; i++) {
            let name = featureNames[i]
            let options = useFeatures[name]
            if (!prefs[name]) continue
            if (options.signal) {
                if (!(options.signal in directives)) continue
                delete directives[options.signal]
            }
            response = await options.run(response, ...options.args)
        }
    }

    for (let k in directives) self.directives[k] = directives[k]
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

self.server = self.settings.origin
self.directives = {}

self.clientRecords = new ClientRecordStorage()
self.requestOptsCache = new TranscientStorage()

self.addEventListener('install', (event) => {
    event.waitUntil(skipWaiting())
})

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim())
})

self.addEventListener('fetch', securityCheck)
self.addEventListener('fetch', withDefinedHandlers)
self.addEventListener('fetch', noRewrite)
self.addEventListener('fetch', (event) => {
    event.respondWith(interceptFetch(event))
})
