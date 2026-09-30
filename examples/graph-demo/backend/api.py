from .services.tasks import list_tasks

def index():
    return list_tasks()
