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
const { retryWithInterval } = require('./utils')
const logger = new Logger()

async function initServiceWorker() {
    let reloading = false
    const reload = () => {
        if (reloading) return
        reloading = true
        let dest = new URLSearchParams(window.location.search).get('continue')
        if (!dest) return
        logger.log(`opening ${dest.slice(1)}`)
        window.location = dest
    }
    let registration = await navigator.serviceWorker.getRegistration()
    if (registration) await registration.unregister()
    try {
        logger.log('await navigator.serviceWorker.register')
        let registration = await navigator.serviceWorker.register('/~/sw.js', { scope: '/' })
        registration.addEventListener('updatefound', () => {
            logger.log('await service worker activate')
            registration.installing.addEventListener('statechange', (ev) => {
                if (ev.target.state === 'activated') reload()
            })
        })
        retryWithInterval(
            (ttl) => {
                logger.log(`check worker status (${ttl}/10)`)
                if (registration.active) logger.log('activated')
                else logger.log('still installing')
                return registration.active
            },
            2500,
            10
        )
            .then(reload)
            .catch(() => logger.log('service worker failed to start'))
    } catch (e) {
        logger.log(e, console.error)
        document.querySelector('#worker-failed').style.display = 'block'
    }
}

function init() {
    if ('serviceWorker' in navigator) {
        initServiceWorker()
    } else {
        logger.log('!serviceWorker in navigator', console.error)
        document.querySelector('#worker-unavailable').style.display = 'block'
    }
}

if (document.readyState !== 'loading') {
    init()
} else {
    window.addEventListener('DOMContentLoaded', init)
}
