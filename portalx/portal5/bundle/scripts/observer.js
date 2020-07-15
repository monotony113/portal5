// observer.js
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

/* eslint-env browser */

const __portal5MutationObserver = new MutationObserver((mutations) => {
    for (let mutation of mutations) {
        switch (mutation.type) {
            case 'childList':
                for (let node of mutation.addedNodes) console.log('node', node)
                break
            case 'attributes':
                if (mutation.target.nodeType === Node.ELEMENT_NODE) {
                    /** @type {Element} */
                    let element = mutation.target
                    console.log('attribute', element)
                }
                break
            default:
                break
        }
    }
})

__portal5MutationObserver.observe(document.documentElement, {
    childList: true,
    attributes: true,
    subtree: true,
})
