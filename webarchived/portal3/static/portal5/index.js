// index.js
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

var output = null
var domDeferred = []

function log(msg, fd) {
    if (!fd) fd = console.log
    fd(msg)
    if (!output) output = document.querySelector('#console')
    if (output) output.append(msg + '\n')
    else domDeferred.push(() => log(msg, fd))
}

async function initServiceWorker() {
    const waitAndReload = async () => {
        log('await navigator.serviceWorker.ready')
        await navigator.serviceWorker.ready
        log('window.location.reload')
        window.location.reload()
    }
    let registration = await navigator.serviceWorker.getRegistration()
    if (!navigator.serviceWorker.controller || !registration) {
        try {
            log('await navigator.serviceWorker.register')
            await navigator.serviceWorker.register('/portal5/service-worker.js', { scope: '/' })
            await waitAndReload()
        } catch (e) {
            log(e, console.error)
            document.querySelector('#worker-failed').style.display = 'block'
        }
    } else {
        log('navigator.serviceWorker.controller && true')
        registration.addEventListener('updatefound', async () => {
            log('registration.update')
            await waitAndReload()
        })
    }
}

function init() {
    if ('serviceWorker' in navigator) {
        initServiceWorker()
    } else {
        log('!serviceWorker in navigator')
        document.querySelector('#worker-unavailable').style.display = 'block'
    }
}

window.addEventListener('load', () => {
    for (let action of domDeferred) action()
})
window.addEventListener('load', init)
