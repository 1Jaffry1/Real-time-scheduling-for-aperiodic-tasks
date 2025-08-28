import csv
from Schedulers.random_taskset import tasks as tasksML
from Schedulers.relax_regular3 import get_logged_priority
from Schedulers.taskset import Task, SIMULATION_TIME

# Config
NUM_CORES = 2
CONTEXT_SWITCH_TIME = 1
ALPHA = 0.6
BETA = 0.4
GAMMA = 0
epsilon = 1e-9

# Placeholder for result logging
def log_results(algorithm, taskset_size, preemptions, deadline_misses, data_transfer_count):
    print(f"\n[LOG] Algorithm: {algorithm}, Taskset Size: {taskset_size}, "
          f"Preemptions: {preemptions}, Misses: {deadline_misses}, Transfers: {data_transfer_count}")

training_log = []

for taskset_id, taskset_ in enumerate(tasksML):
    unarrived_tasks = taskset_.copy()
    taskset_size = len(unarrived_tasks)
    current_time = 0
    preemptions = 0
    deadline_misses = 0
    data_transfer_count = 0
    busy_time = 0
    completed_tasks = []
    missed_priorities = []
    history = []

    for task in unarrived_tasks:
        task.remaining_time = task.burst_time
        task.laxity = task.deadline - task.burst_time
        task.completion_time = None

    prange = max((task.priority for task in unarrived_tasks), default=1)
    arrived_tasks = []
    cores = [None] * NUM_CORES

    print(f"\nEvaluating Taskset #{taskset_id} with Relaxation")
    print(" t  1  |  2")
    print("------|---")

    for current_time in range(SIMULATION_TIME):
        Task.current_time = current_time
        Task.prange = prange

        # Move arrived tasks
        for task in unarrived_tasks[:]:
            if task.arrival_time == current_time:
                arrived_tasks.append(task)
                unarrived_tasks.remove(task)
                data_transfer_count += 1

        # Remove expired tasks
        for task in arrived_tasks[:]:
            if task.update_laxity(current_time) < 0:
                deadline_misses += 1
                missed_priorities.append(get_logged_priority(task.priority))
                arrived_tasks.remove(task)
                data_transfer_count += 1

        # Update relaxation
        for task in arrived_tasks:
            task.update_relaxation(arrived_tasks, current_time, alpha=ALPHA, beta=BETA)

        # Sort by relaxation value
        arrived_tasks.sort(key=lambda t: t.relaxation)

        # Core assignment and preemption
        for core_id in range(NUM_CORES):
            if cores[core_id] is None and arrived_tasks:
                task_to_run = arrived_tasks.pop(0)
                task_to_run.remaining_time += CONTEXT_SWITCH_TIME
                cores[core_id] = task_to_run
                data_transfer_count += 1
                training_log.append([
                    taskset_id, task_to_run.id, current_time, task_to_run.remaining_time,
                    task_to_run.deadline, task_to_run.priority, task_to_run.laxity,
                    core_id, 0  # not preempted
                ])
            elif cores[core_id] is not None and arrived_tasks:
                task_on_core = cores[core_id]
                next_task = arrived_tasks[0]  # Peek
                if next_task.update_laxity(current_time) < task_on_core.remaining_time and next_task.laxity >= 0:
                    preempted = task_on_core
                    task_in = arrived_tasks.pop(0)
                    cores[core_id] = task_in
                    arrived_tasks.append(preempted)
                    task_in.remaining_time += CONTEXT_SWITCH_TIME
                    preemptions += 1
                    data_transfer_count += 2
                    history.append(f"Time {current_time}: Task {task_in.id} (Laxity: {task_in.laxity}) "
                                   f"preempted task {preempted.id} (Remaining time: {preempted.remaining_time}) on Core {core_id}.")
                    training_log.append([
                        taskset_id, task_in.id, current_time, task_in.remaining_time,
                        task_in.deadline, task_in.priority, task_in.laxity,
                        core_id, 1  # preempted
                    ])

        # Task execution
        for core_id in range(NUM_CORES):
            if cores[core_id] is not None:
                cores[core_id].remaining_time -= 1
                busy_time += 1
                if cores[core_id].remaining_time <= 0:
                    cores[core_id].completion_time = current_time
                    completed_tasks.append(cores[core_id])
                    if current_time > cores[core_id].deadline:
                        deadline_misses += 1
                    cores[core_id] = None

        # Print status
        core_status = [str(cores[i].id) if cores[i] else "-" for i in range(NUM_CORES)]
        print(f"{current_time:02d}  {core_status[0]}  |  {core_status[1]}")

    # Check incompleted tasks
    for task in taskset_:
        if task.completion_time is None:
            deadline_misses += 1
            print(f"NOT COMPLETE: Task {task.id} did not complete and missed its deadline.")

    print("\nHistory of preemptions:")
    for event in history:
        print(event)

    print("\nCompletion times and deadlines:")
    for task in completed_tasks:
        if task.completion_time > task.deadline:
            print(f"MISS: Task {task.id} completed at time {task.completion_time} and missed its deadline at {task.deadline}.")
        else:
            print(f"COMPLETION: Task {task.id} completed at time {task.completion_time} with deadline {task.deadline}.")

    print(f"\nTotal preemptions: {preemptions}")
    print(f"Total deadline misses: {deadline_misses}")
    print(f"Total data transfers: {data_transfer_count}")

    log_results('relaxation', taskset_size, preemptions, deadline_misses, data_transfer_count)

# Write training data
with open('../relaxation_training_data.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['taskset_id', 'task_id', 'time', 'remaining_time', 'deadline', 'priority', 'laxity', 'core_id', 'preempted'])
    writer.writerows(training_log)
