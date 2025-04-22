// document.getElementById('merge-file-input').addEventListener('change', function () {
//   document.getElementById('merge-upload-form').submit();
// });

// function removeListItem(element) {
//   const filename = element.parentNode.querySelector('p').textContent
//   element.parentNode.remove()
//   updateFilenamesInput()

//   const csrfToken = getCookie('csrftoken')

//   fetch('/remove_file/', {
//     method: 'POST',
//     headers: {
//       'X-CSRFToken': csrfToken,
//       'Content-Type': 'application/json'
//     },
//     body: JSON.stringify({ filename: filename })
//   })
// }

// function getCookie(name) {
//   let cookieValue = null;
//   if (document.cookie && document.cookie !== '') {
//     const cookies = document.cookie.split(';');
//     for (let i = 0; i < cookies.length; i++) {
//       const cookie = cookies[i].trim();
//       if (cookie.substring(0, name.length + 1) === (name + '=')) {
//         cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
//         break;
//       }
//     }
//   }
//   return cookieValue;
// }

// function updateFilenamesInput() {
//   const filenames = Array.from(document.querySelectorAll('.files p')).map((p) => p.textContent)
//   document.getElementById('filenames').value = filenames.join(',')
// }

// window.addEventListener('beforeunload', function () {
//   fetch('/clear_session/', { method: 'POST' })
// })
