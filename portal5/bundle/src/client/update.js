// update.js
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

const { Logger, retryWithInterval } = require('./utils')
const logger = new Logger()

async function update() {
    let reloading = false
    const reload = () => {
        if (reloading) return
        reloading = true
        logger.log('reload')
        history.pushState('', document.title, '#updated')
        window.location.reload()
    }
    try {
        if ('serviceWorker' in navigator) {
            logger.log('update worker')
            let registration = await navigator.serviceWorker.getRegistration()
            let current = registration.active
            registration.addEventListener('updatefound', () => {
                logger.log('wait for update to take effect')
                registration.installing.addEventListener('statechange', (ev) => {
                    if (ev.target.state === 'activated') reload()
                })
            })
            let isActivated = () => registration.active !== null && registration.active !== current
            retryWithInterval(
                (ttl) => {
                    logger.log(`check worker status (${ttl}/10)`)
                    let activated = isActivated()
                    if (activated) logger.log('activated')
                    else logger.log('still updating')
                    return activated
                },
                2500,
                10
            )
                .then(reload)
                .catch(() => logger.log('service worker failed to restart', console.error))
        }
    } catch (e) {
        logger.log(e, console.error)
    }
}

if (document.readyState !== 'loading') {
    update()
} else {
    window.addEventListener('DOMContentLoaded', update)
}
