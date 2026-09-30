// Interfaces, generics, union types and annotations.
export interface Task { title: string; done: boolean; }
export type State = "pending" | "done";
export function titles<T extends Task>(tasks: readonly T[]): string[] {
  return tasks.filter(task => !task.done).map(task => task.title);
}
const greeting: string = "¡Hola! 🌎";
