// init.js
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

const { Logger } = require('./logger')
const logger = new Logger()

async function initServiceWorker() {
    let registration = await navigator.serviceWorker.getRegistration()
    if (registration) await registration.unregister()
    try {
        logger.log('await navigator.serviceWorker.register')
        let registration = await navigator.serviceWorker.register('/~/sw.js', { scope: '/' })
        registration.addEventListener('updatefound', () => {
            logger.log('waiting for service worker')
            registration.installing.addEventListener('statechange', (ev) => {
                if (ev.target.state === 'activated') {
                    let dest = new URLSearchParams(window.location.search).get('continue')
                    if (!dest) return
                    logger.log(`opening ${dest.slice(1)}`)
                    window.location = dest
                }
            })
        })
    } catch (e) {
        logger.log(e, console.error)
        document.querySelector('#worker-failed').style.display = 'block'
    }
}

function init() {
    if ('serviceWorker' in navigator) {
        initServiceWorker()
    } else {
        logger.log('!serviceWorker in navigator')
        document.querySelector('#worker-unavailable').style.display = 'block'
    }
}

window.addEventListener('load', init)
