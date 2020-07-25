;(() => {
    let links = document.getElementsByTagName('link')
    for (let i = links.length - 1; i >= 0; i--) {
        let link = links[i]
        link.addEventListener('load', () => {
            if (link.rel === 'stylesheet') link.media = 'all'
        })
    }
})()
