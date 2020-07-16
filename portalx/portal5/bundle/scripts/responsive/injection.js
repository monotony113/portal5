// injection.js
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

;({
    observatory: {
        PREFIX: '{{ g.server_origin }}/',
        BASE: new URL('{{ base }}'),
        TARGET_ATTRS: ['href', 'src', 'action'],
        TARGET_ATTRS_CAP: undefined,
        ACCEPT_PROTOCOL: { 'http:': true, 'https:': true },
        /**
         *
         * @param {Node[]} nodeList
         */
        processNodes(nodeList) {
            for (let i = nodeList.length - 1; i >= 0; i--) {
                let node = nodeList[i]
                if (!(node.nodeType === Node.ELEMENT_NODE)) continue
                /** @type {Element} */
                let element = node
                for (let j = this.TARGET_ATTRS.length - 1; j >= 0; j--) {
                    let attr = this.TARGET_ATTRS[j]
                    if (element.hasAttribute(attr))
                        try {
                            this.rewriteURL(element, attr, element.getAttribute(attr))
                        } catch (e) {
                            ;() => {}
                        }
                }
            }
        },
        /**
         *
         * @param {Element} element
         * @param {String} attrName
         * @param {String} value
         */
        rewriteURL(element, attrName, value = undefined) {
            let attrNameUpper = this.TARGET_ATTRS_CAP[attrName]
            let attrNameOriginalValue = 'p5' + attrNameUpper + 'Original'
            let attrNameCurrentValue = 'p5' + attrNameUpper + 'Current'

            if (!value) value = element.getAttribute(attrName)
            if (!value) return
            if (value === element.dataset[attrNameCurrentValue]) return
            if (value.charAt(0) == '#') return

            let url = new URL(value, this.BASE)
            if (!(url.protocol in this.ACCEPT_PROTOCOL)) return
            let resolved = '/' + this.trimPrefix(url.href, this.PREFIX)
            element.dataset[attrNameOriginalValue] = value
            element.dataset[attrNameCurrentValue] = resolved
            element.setAttribute(attrName, resolved)
        },
        mutationCallback(mutations) {
            for (let mutation of mutations) {
                switch (mutation.type) {
                    case 'childList':
                        this.processNodes(mutation.addedNodes)
                        break
                    case 'attributes':
                        if (mutation.target.nodeType === Node.ELEMENT_NODE) {
                            this.rewriteURL(mutation.target, mutation.attributeName)
                        }
                        break
                    default:
                        break
                }
            }
        },
        trimPrefix(str, prefix) {
            if (str.startsWith(prefix)) return this.trimPrefix(str.slice(prefix.length), prefix)
            return str
        },
    },
    init() {
        let attrs = this.observatory.TARGET_ATTRS
        // let dataAttrs = attrs.map((s) => `data-${s}`)
        // attrs = attrs.concat(dataAttrs)
        // this.observatory.TARGET_ATTRS = attrs

        let capitalized = {}
        for (let i = attrs.length - 1; i >= 0; i--) {
            let attr = attrs[i]
            capitalized[attr] = attr
                .split('-')
                .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
                .join('')
        }
        this.observatory.TARGET_ATTRS_CAP = capitalized
    },
    start() {
        this.init()
        window.history.pushState(
            '',
            document.title,
            window.location.pathname.replace(this.observatory.BASE.origin + '/', '') +
                window.location.search +
                window.location.hash
        )
        let observer = new MutationObserver(this.observatory.mutationCallback.bind(this.observatory))
        observer.observe(document.documentElement, {
            childList: true,
            attributes: true,
            subtree: true,
            attributeFilter: this.observatory.TARGET_ATTRS,
        })
        let updateAnchors = () => this.observatory.processNodes(document.getElementsByTagName('a'))
        window.addEventListener('load', () => {
            setTimeout(updateAnchors, 1000)
            setInterval(updateAnchors, 30000)
        })
        window.addEventListener('popstate', () => {
            setTimeout(updateAnchors, 1000)
        })
    },
}.start())
