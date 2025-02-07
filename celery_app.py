from time import sleep
from celery import Celery, exceptions
from kombu.utils.functional import random
from celery.result import AsyncResult
from celery.signals import task_revoked,after_task_publish

aws_access_key = ""
aws_secret_key = ""

broker_url = f"sqs://{aws_access_key}:{aws_secret_key}@".format(
    aws_access_key=aws_access_key, aws_secret_key=aws_secret_key,
)

app = Celery(
    "tasks",
    broker=broker_url,
    backend="db+mysql+pymysql://celery_user:celery_password@localhost/celery_db",
    broker_transport_options = {
        'polling_interval': 1,
        'visibility_timeout': 60 * 3,
        'predefined_queues': {
            'celery': {
                'region': 'eu-central-1',
                'url': 'https://sqs.eu-central-1.amazonaws.com/646721517538/celery',
                'access_key_id': aws_access_key,
                'secret_access_key': aws_secret_key,
            },
        },
    },
    task_create_missing_queues=False,
    broker_connection_retry_on_startup = True
)

@app.task
def add(x, y):
    sleep(random.randint(10,30))
    return x + y

@app.task(bind=True)
def long_running_task(self):
    try:
        for i in range(10):

            print(f"Working... {i+1}/10")

            sleep(5)

            result = AsyncResult(self.request.id)
            if result.state == 'REVOKED':
                print(f"Task {self.request.id} was revoked.")

                return "Task was cancelled."
        return "Task completed successfully."

    except exceptions.TaskRevokedError:
        print(f"Task {self.request.id} has been gracefully terminated.")
        return "Task was gracefully terminated."


from celery.signals import after_task_publish

@after_task_publish.connect
def task_sent_handler(sender=None, headers=None, body=None, **kwargs):
    info = headers if 'task' in headers else body
    print('after_task_publish for task id {info[id]}'.format(
        info=info,
    ))


@task_revoked.connect
def task_revoked_handler(*args, **kwargs):
    print("!!!!!!! Tasks are being revoked")

def get_all_celery_tasks():
    inspect = app.control.inspect()

    active_tasks = inspect.active()
    waiting_to_be_processed = inspect.scheduled()
    queued = inspect.reserved()

    tasks = {
        'active': active_tasks,
        'scheduled': waiting_to_be_processed,
        'reserved': queued
    }

    for state, task_list in tasks.items():
        print(f"\n--- {state.capitalize()} Tasks ---")
        if task_list:
            for worker, tasks_in_worker in task_list.items():
                for task in tasks_in_worker:
                    task_id = task.get('id')

                    print(f"Task ID: {task_id}, Worker: {worker}")

                    result = AsyncResult(task_id, app=app)

                    print(f"  State: {result.state}")
                    print(f"  Result: {result.result}")
                    print(f"  Traceback: {result.traceback if result.state == 'FAILURE' else 'N/A'}")
        else:
            print(f"No {state} tasks found.")


def revoke_all_tasks():
    inspect = app.control.inspect()

    print("Inspecting")
    active_tasks = inspect.active()
    print("Active:" + active_tasks)

    scheduled_tasks = inspect.scheduled()  
    reserved_tasks = inspect.reserved()  

    tasks = {
        'active': active_tasks,
        'scheduled': scheduled_tasks,
        'reserved': reserved_tasks
    }

    for state, task_list in tasks.items():
        print(f"\n--- Revoke {state.capitalize()} Tasks ---")
        if task_list:
            for worker, tasks_in_worker in task_list.items():
                for task in tasks_in_worker:
                    task_id = task.get('id')
                    print(f"Revoking task ID: {task_id} (Worker: {worker})")
                    result = AsyncResult(task_id, app=app)

                    result.revoke(terminate=True)  # Set terminate=True for hard termination

        else:
            print(f"No {state} tasks found.")
