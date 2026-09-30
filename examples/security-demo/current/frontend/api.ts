export function load(req: any, db: any) {
  const name = req.query.name;
  db.query(`SELECT * FROM users WHERE name='${name}'`);
}
