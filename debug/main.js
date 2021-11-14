import {Wam} from '/wam_view.js'

document.forms[0].addEventListener("submit", (evt) => {
    evt.preventDefault();
    let formData = new FormData(evt.target)
    let file = formData.get('content')

    readFile(file)
        .then(parseJSONL)
        .then(init)
})

function readFile(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = reject;
        reader.onload = () => resolve(reader.result);
        reader.readAsText(file);
    })
}

function parseJSONL(text) {
    return text
        .split("\n")
        .map(x => x.trim())
        .filter(x => x != "")
        .map(JSON.parse);
}

var wam;
function init(states) {
    let clauses = states[0].Clauses;
    for (let i = 0; i < states.length-1; i++) {
        states[i].Backtrack = states[i+1].Backtracked;
    }
    if (wam !== undefined) {
        wam.destroy()
    }
    wam = new Wam(states, clauses)
    wam.render()
}
