// Functions, private fields, optional chaining and Unicode.
export class TaskList {
  #tasks = [];
  add(title = "¡Hola! 🌎") { this.#tasks.push({ title, done: false }); }
  pending() { return this.#tasks.filter(task => !task.done).map(task => task.title); }
}
export const title = task => task?.title ?? "Sin título";
