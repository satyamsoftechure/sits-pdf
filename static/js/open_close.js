document.getElementById('merge-upload').addEventListener('change', handleFileUpload);
document.getElementById('add_more_files_input').addEventListener('change', handleFileUpload);

function handleFileUpload(e) {
    e.preventDefault();
    const formData = new FormData();
    
    // Add files from the input that triggered the event
    for (let file of e.target.files) {
        formData.append('pdfs', file);
    }
    
    fetch('{% url 'upload_pdfs' %}', {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': '{{ csrf_token }}'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('file-selection-section').style.display = 'none';
            document.getElementById('result-section').style.display = 'block';
            updateFileDisplay(data.file_data);
            updateFilenames(data.filenames);
        } else {
            alert(data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred while processing your request.');
    });

    // Clear the input so the same file can be selected again if needed
    e.target.value = '';
}

function updateFileDisplay(fileData) {
    const displayFiles = document.getElementById('displayFiles');
    displayFiles.innerHTML = ''; // Clear existing files
    fileData.forEach(file => {
        const fileDiv = document.createElement('div');
        fileDiv.className = 'files';
        fileDiv.setAttribute('data-filename', file.filename);
        fileDiv.innerHTML = `
            <img src="${file.image_data}" alt="Preview of ${file.filename}" />
            <p class="m-0">${file.filename}</p>
            <button class="close-btn" onclick="removeFile('${file.filename}')"><i class="fa-regular fa-circle-xmark delete-btn"></i></button>
        `;
        displayFiles.appendChild(fileDiv);
    });
}

function updateFilenames(filenames) {
    document.getElementById('filenames').value = filenames.join(',');
}

function removeFile(filename) {
    fetch('{% url 'remove_file' %}', {
        method: 'POST',
        body: JSON.stringify({ filename: filename }),
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': '{{ csrf_token }}'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            updateFileDisplay(data.file_data);
            updateFilenames(data.filenames);
        } else {
            alert(data.error);
        }
    });
}