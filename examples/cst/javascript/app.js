document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault(); // Evita que la página se recargue

    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const mensaje = document.getElementById('mensaje');

    try {
        // Hace la petición al servidor Python
        const response = await fetch('http://localhost:5000/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (response.ok) {
            mensaje.style.color = 'green';
            mensaje.textContent = data.message;

        } else {
            mensaje.style.color = 'red';
            mensaje.textContent = data.message;
        }
    } catch (error) {
        mensaje.style.color = 'red';
        mensaje.textContent = 'Error al conectar con el servidor.';
    }
});