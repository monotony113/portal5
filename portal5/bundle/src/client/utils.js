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

class Preferences2 {
    get pref() {
        let cookies = document.cookie.split('; ')
        let pref
        for (let i = cookies.length - 1; i >= 0; i--) {
            let [key, ...value] = cookies[i].split('=')
            value = value.join('=')
            if (key.trim() === 'portal5prefs2') pref = value
        }
        try {
            return JSON.parse(atob(pref))
        } catch (e) {
            return {}
        }
    }
    set pref(p) {
        document.cookie = `portal5prefs2=${btoa(JSON.stringify(p))}; path=/; max-age=31536000; secure`
    }
    get(key) {
        return this.pref[key]
    }
    set(key, value) {
        let pref = this.pref
        pref[key] = value
        this.pref = pref
    }
}

function retryWithInterval(precondition, timeout = 0, ttl = 5) {
    return new Promise((resolve, reject) => {
        setTimeout(async () => {
            ttl--
            if (!(await precondition(ttl + 1))) {
                if (ttl) return retryWithInterval(precondition, timeout, ttl).then(resolve).catch(reject)
                else return reject()
            }
            return resolve()
        }, timeout)
    })
}

class Logger {
    constructor() {
        this.output = null
        this.deferredOutput = []
        window.addEventListener('DOMContentLoaded', () => {
            for (let action of this.deferredOutput) action()
        })
    }
    log(msg, fd) {
        return new Promise(() => {
            if (!fd) fd = console.log
            fd(msg)
            if (!this.output) this.output = document.querySelector('#console')
            if (this.output) {
                let code = document.createElement('code')
                code.append(msg, document.createElement('br'))
                if (fd === console.error) code.className = 'color-red-fg'
                this.output.appendChild(code)
            } else {
                this.deferredOutput.push(() => this.log(msg, fd))
            }
        })
    }
}

module.exports = { Preferences2, retryWithInterval, Logger }
