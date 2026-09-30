// Parsing JSX does not require installing React.
export function Card({ title, done }) {
  return <article className={done ? "done" : "pending"}><h2>{title}</h2></article>;
}
