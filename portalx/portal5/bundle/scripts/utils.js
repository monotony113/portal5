// utils.js
// Copyright (C) 2020  Tony Wu <tony[dot]wu(at)nyu[dot]edu>
// /* {% if retain_comments %} */
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
// /* {% endif %} */

/* eslint-env serviceworker */

class Utils {
    static async makeRequestOptions(request) {
        let headers = {}
        request.headers.forEach((v, k) => (headers[k] = v))

        let requestOpts = {
            method: request.method,
            headers: headers,
            credentials: request.credentials,
            cache: request.cache,
            redirect: request.redirect,
            integrity: request.integrity,
            referrer: '',
            referrerPolicy: request.referrerPolicy,
            mode: request.mode === 'same-origin' || request.mode === 'no-cors' ? 'same-origin' : 'cors',
        }

        let body = await request.blob()
        if (body.size > 0) {
            requestOpts.body = body
        }

        return requestOpts
    }

    static trimPrefix(str, prefix) {
        if (str.startsWith(prefix)) return this.trimPrefix(str.slice(prefix.length), prefix)
        return str
    }

    static readBlob(blob, func = FileReader.prototype.readAsDataURL, args = []) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader()
            reader.addEventListener('error', reject)
            reader.addEventListener('load', () => resolve(reader.result))
            func.apply(reader, [blob, ...args])
        })
    }
}

class TranscientStorage {
    add(id, data, namespace = 'data', ttl = null) {
        id = namespace + ':' + id
        this[id] = data
        if (ttl) setTimeout(() => this.remove(id), ttl)
    }
    get(id, namespace = 'data') {
        return this[namespace + ':' + id]
    }
    remove(id, namespace = 'data') {
        id = namespace + ':' + id
        let item = this[id]
        delete this[id]
        return item
    }
    keys(namespace = 'data') {
        return Object.keys(this).filter((v) => v.startsWith(namespace + ':'))
    }
}

class ClientRecordStorage extends TranscientStorage {
    constructor() {
        super()
        this.enableTrim()
    }
    enableTrim() {
        this.interval = setInterval(this.trim.bind(this), 300000)
    }
    pauseTrim() {
        clearInterval(this.interval)
    }
    add(id, url) {
        super.add(id, { represented: url, atime: Date.now() }, 'client')
    }
    get(id) {
        return super.get(id, 'client')
    }
    remove(id) {
        return super.remove(id, 'client')
    }
    trim() {
        Promise.all(super.keys('client').map(async (k) => [k, await clients.get(k.slice(7))])).then((r) =>
            r.filter((r) => !r[1]).forEach((r) => delete this[r[0]])
        )
    }
}

class NotificationUtils {
    static askForPermission() {
        if (!('Notification' in self)) return Promise.resolve()
        try {
            return Notification.requestPermission().then(() => {})
        } catch (e) {
            Notification.requestPermission(() => {})
            return Promise.resolve()
        }
    }
    static fireNotification(title, options) {
        if (!('Notification' in self)) return
        if (Notification.permission === 'deny') return
        if (Notification.permission === 'default')
            return NotificationUtils.askForPermission().then(() => NotificationUtils.fireNotification(title, options))
        return new Notification(title, options)
    }
}

/* {% if retain_import_exports %} */
module.exports = { TranscientStorage, ClientRecordStorage, NotificationUtils, Utils }
/* {% endif %} */
