;(() => {
    let links = document.getElementsByTagName('link')
    for (let i = links.length - 1; i >= 0; i--) {
        let link = links[i]
        link.onload = () => {
            if (link.rel === 'stylesheet' && link.media === 'none') link.media = 'all'
        }
    }
    window.addEventListener('load', () => {
        for (let i = links.length - 1; i >= 0; i--)
            if (links[i].rel === 'stylesheet' && links[i].media === 'none') links[i].media = 'all'
    })
})()
