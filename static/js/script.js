const dropArea = document.querySelector('.drop-section')
const listSection = document.querySelector('.list-section')
const listContainer = document.querySelector('.list')
const fileSelector = document.querySelector('.file-selector')
const fileSelectorInput = document.querySelector('.file-selector-input')
let accumulatedFiles = [];

// upload files with browse button
fileSelector.onclick = () => fileSelectorInput.click()
fileSelectorInput.onchange = () => {
    [...fileSelectorInput.files].forEach((file) => {
        if (typeValidation(file.type)) {
            accumulatedFiles.push(file);
            uploadFile(file);
        }
    });
}

// when file is over the drag area
dropArea.ondragover = (e) => {
    e.preventDefault();
    [...e.dataTransfer.items].forEach((item) => {
        if (typeValidation(item.type)) {
            dropArea.classList.add('drag-over-effect')
        }
    })
}
// when file leave the drag area
dropArea.ondragleave = () => {
    dropArea.classList.remove('drag-over-effect')
}
// when file drop on the drag area
dropArea.ondrop = (e) => {
    e.preventDefault();
    dropArea.classList.remove('drag-over-effect')
    if (e.dataTransfer.items) {
        [...e.dataTransfer.items].forEach((item) => {
            if (item.kind === 'file') {
                const file = item.getAsFile();
                if (typeValidation(file.type)) {
                    accumulatedFiles.push(file);
                    uploadFile(file)
                }
            }
        })
    } else {
        [...e.dataTransfer.files].forEach((file) => {
            if (typeValidation(file.type)) {
                accumulatedFiles.push(file);
                uploadFile(file)
            }
        })
    }
}


// check the file type
function typeValidation(type) {
    var splitType = type.split('/')[0]
    if (type == 'application/pdf' || splitType == 'image' || splitType == 'video') {
        return true
    }
}

// upload file function
function uploadFile(file) {
    listSection.style.display = 'block'
    var li = document.createElement('li')
    li.classList.add('in-prog')
    li.innerHTML = `
        <div class="col">
            <img src="${STATIC_URL}icons/pdf.png" alt="">
        </div>
        <div class="col">
            <div class="file-name">
                <div class="name">${file.name}</div>
                <span>0%</span>
            </div>
            <div class="file-progress">
                <span></span>
            </div>
            <div class="file-size">${(file.size / (1024 * 1024)).toFixed(2)} MB</div>
        </div>
        <div class="col">
            <svg xmlns="http://www.w3.org/2000/svg" class="cross" height="20" width="20"><path d="m5.979 14.917-.854-.896 4-4.021-4-4.062.854-.896 4.042 4.062 4-4.062.854.896-4 4.062 4 4.021-.854.896-4-4.063Z"/></svg>
            <svg xmlns="http://www.w3.org/2000/svg" class="tick" height="20" width="20"><path d="m8.229 14.438-3.896-3.917 1.438-1.438 2.458 2.459 6-6L15.667 7Z"/></svg>
        </div>
    `;
    listContainer.prepend(li);
    let progress = 0;
    const interval = setInterval(() => {
        progress += 10;
        li.querySelectorAll('span')[0].innerHTML = progress + '%';
        li.querySelectorAll('span')[1].style.width = progress + '%';
        if (progress >= 100) {
            clearInterval(interval);
            li.classList.add('complete');
            li.classList.remove('in-prog');
        }
    }, 200);

    li.querySelector('.cross').onclick = () => {
        clearInterval(interval);
        li.remove();
        accumulatedFiles = accumulatedFiles.filter(f => f !== file);
    };
}

function handleFormSubmission(event) {
    event.preventDefault();
    const formData = new FormData();
    accumulatedFiles.forEach((file, index) => {
        formData.append(`file${index}`, file);
    });

    fetch('/upload_pdfs/', {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        }
    })
        .then(response => response.text())
        .then(html => {
            document.body.innerHTML = html;
        })
        .catch(error => console.error('Error:', error));
}

// Add this at the end of the file
document.querySelector('form').addEventListener('submit', handleFormSubmission);

function removeListItem(element) {
    element.parentNode.remove()
    updateFilenamesInput()
}
function updateFilenamesInput() {
    const filenames = Array.from(document.querySelectorAll('#file-list li p')).map((p) => p.textContent)
    document.getElementById('filenames').value = filenames.join(',')
}

