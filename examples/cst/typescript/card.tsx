// The TSX grammar recognizes both type annotations and JSX.
type Props = { title: string; done?: boolean };
export function Card({ title, done = false }: Props) {
  return <article data-done={done}><h2>{title}</h2></article>;
}
