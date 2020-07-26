// injection.js
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

/* eslint-env browser */

;({
    PREFIX: '{{ g.server_origin|default("") }}',
    BASE: new URL('{{ base|default("") }}'),
    TARGET_ATTRS: ['href', 'src', 'action', 'data', 'formaction'],
    TARGET_ATTRS_CAP: undefined,
    ACCEPT_PROTOCOL: { 'http:': true, 'https:': true },
    observer: undefined,
    stat: {
        updateCount: 0,
    },
    manager: {
        /** @type {HTMLElement} */
        element: undefined,
        console: undefined,
        observatory: undefined,
        isHidden: true,
        pref2: new (require('./preferences2').Preferences2)(),
        /**
         *
         * @param {HTMLBodyElement} body
         */
        async attach(body) {
            let template = document.createElement('template')
            if (!('content' in template)) return
            let templateString = await fetch('/~/injection-manager.html', {
                mode: 'same-origin',
                referrer: '',
            }).then((r) => r.text())
            template.innerHTML = templateString

            let manager = this.initInterface(template.content)
            let isolated = document.createElement('div')
            let shadowRoot = isolated.attachShadow({ mode: 'closed' })
            shadowRoot.append(manager)
            this.element = manager
            body.prepend(isolated)

            templateString = await fetch('/~/injection-manager~fonts.html', {
                mode: 'same-origin',
                referrer: '',
            }).then((r) => r.text())
            template.innerHTML = templateString
            document.getElementsByTagName('head')[0].append(template.content)
        },
        initInterface(manager) {
            manager.getElementById('p5-option-more-info').addEventListener('click', (event) => {
                let containers = this.element.getElementsByClassName('p5-container-optional')
                for (let i = containers.length - 1; i >= 0; i--)
                    this.isHidden = containers[i].classList.toggle('p5-hidden')
                event.currentTarget.textContent = this.isHidden ? 'more info' : 'hide details'
                if (!this.console) this.initConsole()
            })
            manager.getElementById('p5-option-close').addEventListener('click', this.toggleVisible.bind(this))

            let doNotShow = manager.getElementById('p5-option-disable-warning')
            doNotShow.addEventListener('change', this.setCookie.bind(this))
            let element = manager.getElementById('p5-injection-manager')
            if (this.pref2.get('nopopup')) {
                element.classList.add('p5-hidden')
                doNotShow.checked = true
            }

            return element
        },
        initConsole() {
            let _ = document.createTextNode.bind(document)
            let __ = document.createElement.bind(document)
            this.console = this.element.querySelector('#p5-console').getElementsByTagName('code')[0]
            /** @type {HTMLElement} */
            let origin = this.makeConsoleDataField(this.observatory.BASE.origin)
            let attributes = this.makeConsoleDataField(this.observatory.TARGET_ATTRS.join(' '))
            let count = this.makeConsoleDataField()
            let refresh = this.makeActionButton('refresh', () => {
                window.history.pushState('', document.title, '/' + this.observatory.BASE.href)
                window.location.reload()
            })
            let start = this.makeActionButton('start', () => this.observatory.startObserving())
            let stop = this.makeActionButton('stop', () => this.observatory.observer.disconnect())
            let forceUpdate = this.makeActionButton('force_update', () => this.observatory.forceUpdateAnchors())
            this.console.append(
                _('origin '),
                origin,
                __('br'),
                _('update attributes '),
                attributes,
                __('br'),
                count,
                _(' urls rewritten'),
                __('br'),
                _(' actions '),
                refresh,
                _(' '),
                start,
                _(' '),
                stop,
                _(' '),
                forceUpdate
            )
            setInterval(() => {
                if (!this.isHidden) count.innerText = this.observatory.stat.updateCount
            }, 1000)
        },
        makeConsoleDataField(text) {
            let field = document.createElement('span')
            field.classList.add('p5-console-data')
            if (text) field.append(document.createTextNode(text.trim()))
            return field
        },
        makeActionButton(text, action) {
            let button = this.makeConsoleDataField()
            let buttonAnchor = document.createElement('a')
            buttonAnchor.href = 'javascript:void(0)'
            buttonAnchor.append(document.createTextNode(text))
            buttonAnchor.addEventListener('click', action)
            button.append(buttonAnchor)
            return button
        },
        setCookie(event) {
            this.pref2.set('nopopup', event.currentTarget.checked)
        },
        toggleVisible() {
            return this.element.classList.toggle('p5-hidden')
        },
    },
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
            if (element.tagName == 'BODY') this.manager.attach(element).catch(console.error)
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
        if (element.hasAttribute('data-p5-ignore')) return
        if (!value) value = element.getAttribute(attrName)
        if (!value) return

        let attrNameUpper = this.TARGET_ATTRS_CAP[attrName]
        let attrNameOriginalValue = 'p5' + attrNameUpper + 'Original'
        let attrNameCurrentValue = 'p5' + attrNameUpper + 'Current'

        if (value === element.dataset[attrNameCurrentValue]) return
        if (value.charAt(0) == '#') return

        let url = new URL(value, this.BASE)
        if (!(url.protocol in this.ACCEPT_PROTOCOL)) return
        let resolved = '/' + this.trimPrefix(url.href, this.PREFIX)
        element.dataset[attrNameOriginalValue] = value
        element.dataset[attrNameCurrentValue] = resolved
        element.setAttribute(attrName, resolved)
        this.stat.updateCount++
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
    patch(func, before, after, thisArg) {
        if (!(typeof before === 'function')) before = () => {}
        if (!(typeof after === 'function')) after = () => {}
        return function () {
            before(...arguments)
            let result = func.apply(thisArg, [...arguments])
            after(result, ...arguments)
            return result
        }
    },
    init() {
        let updateBase = () => (this.BASE = new URL(window.location.pathname + window.location.search, this.BASE))
        window.history.pushState = this.patch(window.history.pushState, undefined, updateBase, window.history)
        window.history.replaceState = this.patch(window.history.replaceState, undefined, updateBase, window.history)

        let attrs = this.TARGET_ATTRS
        // let dataAttrs = attrs.map((s) => `data-${s}`)
        // attrs = attrs.concat(dataAttrs)
        // this.TARGET_ATTRS = attrs

        let capitalized = {}
        for (let i = attrs.length - 1; i >= 0; i--) {
            let attr = attrs[i]
            capitalized[attr] = attr
                .split('-')
                .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
                .join('')
        }
        this.TARGET_ATTRS_CAP = capitalized

        this.manager.observatory = this
        window.p5InjectionManager = (operation) => {
            switch (operation) {
                case 'retrieve':
                    return this
                case 'stopListening':
                    this.observer.disconnect()
                    break
                case 'forceUpdate':
                    this.forceUpdateAnchors()
                    break
                case 'toggle':
                default:
                    this.manager.toggleVisible()
                    break
            }
        }
    },
    start() {
        this.init()

        fetch(this.BASE, { method: 'HEAD' })
        let normalizedPath = window.location.pathname.replace(this.BASE.origin + '/', '').replace(/^\/+/, '/')
        let search = new URLSearchParams(window.location.search)
        search.set('_p5origin', this.BASE.origin)
        window.history.pushState('', document.title, normalizedPath + '?' + search.toString() + window.location.hash)

        this.observer = new MutationObserver(this.mutationCallback.bind(this))
        this.startObserving()

        window.addEventListener('DOMContentLoaded', () => {
            setTimeout(this.forceUpdateAnchors.bind(this), 0)
            setInterval(this.forceUpdateAnchors.bind(this), 30000)
        })
    },
    startObserving() {
        this.observer.observe(document.documentElement, {
            childList: true,
            attributes: true,
            subtree: true,
            attributeFilter: this.TARGET_ATTRS,
        })
    },
    forceUpdateAnchors() {
        this.processNodes(document.getElementsByTagName('a'))
    },
}.start())
