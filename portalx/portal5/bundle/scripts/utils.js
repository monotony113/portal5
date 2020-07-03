// utils.js
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

class Utils {
    static async makeRequestOptions(request) {
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

    static trimPrefix(str, prefix) {
        if (str.startsWith(prefix)) return this.trimPrefix(str.substr(prefix.length), prefix)
        return str
    }
}

/* {% if retain_import_exports %} */
module.exports = { Utils }
/* {% endif %} */
