import * as http from 'http';
import { exec } from 'child_process';
import { URL } from 'url';
import * as sqlite3 from 'sqlite3'; // Usamos sqlite3 como ejemplo de BD

// 1. EXPOSICIÓN DE CLAVES PRIVADAS
// Las claves están hardcodeadas en un objeto de configuración global.
// Cualquiera con acceso al archivo (o si hay una vulnerabilidad de LFI) puede extraerlas.
const SYSTEM_SECRETS = {
    awsAccessKey: "AKIAIOSFODNN7EXAMPLE",
    awsSecretKey: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    databaseCert: "-----BEGIN CERTIFICATE-----\nMIIDXTCCAkWgAwIBAgIJAL... (simulado)\n-----END CERTIFICATE-----"
};

// Inicialización de base de datos en memoria para el ejemplo
const db = new sqlite3.Database(':memory:');
db.serialize(() => {
    db.run("CREATE TABLE users (id INT, username TEXT, role TEXT)");
    db.run("INSERT INTO users VALUES (1, 'admin', 'superuser')");
});

const server = http.createServer((req, res) => {
    const parsedUrl = new URL(req.url || '', `http://${req.headers.host}`);

    res.setHeader('Content-Type', 'application/json');

    // 2. INYECCIÓN SQL (Construcción manual de consultas)
    // Se procesa el cuerpo de la petición POST manualmente.
    if (req.method === 'POST' && parsedUrl.pathname === '/api/users/find') {
        let body = '';
        req.on('data', chunk => { body += chunk.toString(); });
        req.on('end', () => {
            try {
                const data = JSON.parse(body); // Espera algo como: { "username": "admin" }
                
                let query = "SELECT * FROM users WHERE ";
                const conditions: string[] = [];
                
                // VULNERABILIDAD: El desarrollador intenta iterar sobre el JSON para hacer
                // una búsqueda dinámica. Piensa que encerrando el valor entre comillas simples ('')
                // es suficiente para protegerse.
                // Sin embargo, si el atacante envía: { "username": "admin' OR 1=1 --" }
                // O peor aún, inyecta en la CLAVE: { "1=1; DROP TABLE users; --": "x" }
                for (const key in data) {
                    conditions.push(`${key} = '${data[key]}'`);
                }
                
                query += conditions.join(' AND ');

                db.all(query, (err, rows) => {
                    if (err) {
                        res.writeHead(500);
                        return res.end(JSON.stringify({ error: "Database error" }));
                    }
                    res.writeHead(200);
                    res.end(JSON.stringify({ results: rows }));
                });
            } catch (e) {
                res.writeHead(400);
                res.end(JSON.stringify({ error: "Invalid JSON body" }));
            }
        });
    }
    
    // 3. EJECUCIÓN DE COMANDOS (Filtro insuficiente)
    // El desarrollador intenta hacer un endpoint para hacer ping a un host.
    else if (req.method === 'GET' && parsedUrl.pathname === '/api/tools/ping') {
        const target = parsedUrl.searchParams.get('host');
        
        if (!target) {
            res.writeHead(400);
            return res.end(JSON.stringify({ error: "Parámetro 'host' faltante" }));
        }

        // VULNERABILIDAD: El desarrollador sabe sobre Command Injection e intenta filtrar.
        // Remueve los caracteres '&' y '|' con una expresión regular.
        // Pero OLVIDA otros operadores críticos en Unix como el punto y coma (;) o los backticks (`).
        // Un atacante puede enviar: ?host=127.0.0.1;cat /etc/passwd
        const sanitizedTarget = target.replace(/[&|]/g, '');

        exec(`ping -c 1 ${sanitizedTarget}`, (error, stdout, stderr) => {
            res.writeHead(200);
            res.end(JSON.stringify({ 
                command_executed: `ping -c 1 ${sanitizedTarget}`,
                output: stdout || stderr || error?.message 
            }));
        });
    } 
    
    else {
        res.writeHead(404);
        res.end(JSON.stringify({ error: "Endpoint not found" }));
    }
});

server.listen(8080, () => {
    console.log("Servidor nativo corriendo en puerto 8080");
});