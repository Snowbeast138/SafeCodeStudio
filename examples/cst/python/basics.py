"""Functions, Unicode, annotations and comprehensions."""
from dataclasses import dataclass

@dataclass
class Task:
    title: str
    done: bool = False


def pending(tasks: list[Task]) -> list[str]:
    greeting = "¡Hola, mundo! 🌎"
    return [f"{greeting}: {task.title}" for task in tasks if not task.done]
