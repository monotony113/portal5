// disambiguate.js
// Copyright (C) 2020  Tony Wu <tony[dot]wu(at)nyu[dot]edu>
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published
// the Free Software Foundation, either version 3 of the License, or
// (at your candidate) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

class Candidate {
    constructor(containerElement) {
        this.id = containerElement.id
        this.container = containerElement

        this.referrer = containerElement.dataset.referrer
        this.destination = containerElement.dataset.dest

        this.actionsElement = containerElement.getElementsByClassName('actions')[0]
        this.highlighted = false

        containerElement.querySelectorAll('.label-container').forEach((e) => {
            let urlList = e.nextElementSibling
            let urlConcise = urlList.getElementsByClassName('url-concise')[0]
            let urlFull = urlList.getElementsByClassName('url-full')[0]
            e.addEventListener('click', (ev) => {
                ev.stopPropagation()
                urlConcise.classList.toggle('hidden')
                urlFull.classList.toggle('hidden')
            })
        })

        let buttons = this.actionsElement.getElementsByTagName('button')
        for (let i = 0; i < buttons.length; i++) {
            let btn = buttons[i]
            btn.addEventListener('click', (ev) => {
                ev.stopPropagation()
            })
        }
    }
    setHighlight(on = undefined) {
        if (on === undefined) on = !this.highlighted
        this.highlighted = on
        if (on) {
            this.container.classList.add('container-style-selected')
            this.actionsElement.classList.remove('hidden')
        } else {
            this.container.classList.remove('container-style-selected')
            this.actionsElement.classList.add('hidden')
        }
        return on
    }
}

class Form {
    constructor(formElement) {
        this.form = formElement
        this.referrerField = formElement.querySelector('input[name="referrer"]')
        this.destField = formElement.querySelector('input[name="dest"]')

        let candidates = {}
        this.candidates = candidates

        let candidateElements = document.getElementsByClassName('candidate-container')
        for (let i = 0; i < candidateElements.length; i++) {
            let element = candidateElements[i]
            candidates[element.id] = new Candidate(element)
            element.addEventListener('mouseenter', (ev) => {
                this.toggle(ev.currentTarget.id, true)
            })
            element.addEventListener('mouseleave', (ev) => {
                this.toggle(ev.currentTarget.id, false)
            })
            element.addEventListener('focusin', (ev) => {
                this.toggle(ev.currentTarget.id, true)
            })
            element.addEventListener('focusout', (ev) => {
                this.toggle(ev.currentTarget.id, false)
            })
            element.addEventListener('keydown', (ev) => {
                if (ev.key === 'Enter' || ev.key === ' ') {
                    ev.preventDefault()
                    this.form.submit()
                }
            })
            element.addEventListener('click', () => {
                this.form.submit()
            })
        }
    }
    toggle(id, on) {
        let container = this.candidates[id]
        container.setHighlight(on)
        if (on) {
            this.referrerField.value = container.referrer
            this.destField.value = container.destination
        } else {
            this.referrerField.value = ''
            this.destField.value = ''
        }
    }
}

window.addEventListener('load', () => {
    window.form = new Form(document.getElementById('mainForm'))
})
