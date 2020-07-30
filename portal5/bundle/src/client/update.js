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

const { Logger } = require('./logger')
const logger = new Logger()

window.addEventListener('load', async () => {
    try {
        if ('serviceWorker' in navigator) {
            logger.log('updating')
            let registration = await navigator.serviceWorker.getRegistration()
            registration.addEventListener('updatefound', () => {
                logger.log('waiting for update to take effect')
                registration.installing.addEventListener('statechange', (ev) => {
                    if (ev.target.state === 'activated') {
                        logger.log('refreshing')
                        history.pushState('', document.title, '#updated')
                        window.location.reload()
                    }
                })
            })
        }    
    } catch(e) {
        logger.log(e, console.error)
    }
})
