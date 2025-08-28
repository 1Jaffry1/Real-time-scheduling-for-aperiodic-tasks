import random

class Task:
    def __init__(self, id, arrival_time, burst_time, deadline, priority):
        self.id = id
        self.arrival_time = arrival_time
        self.burst_time = burst_time
        self.deadline = deadline
        self.priority = priority
        self.remaining_time = burst_time
        self.completion_time = None
        self.laxity = deadline - burst_time  # (you can recompute elsewhere if needed)

def generate_random_taskset(
    num_tasks=10,
    arrival_time_range=(0, 40),
    burst_time_range=(1, 14),
    deadline_slack_range=(3, 6),
    priority_range=(1, 5),
    num_tasksets=500,
    seed=None,
):
    """
    Generate a list of tasksets. Each taskset is a list of tuples:
    (task_id, arrival_time, burst_time, deadline, priority).
    """
    if seed is not None:
        random.seed(seed)

    all_tasksets = []
    for _ in range(num_tasksets):
        taskset = []
        # Number of tasks in this set (at least 4, at most num_tasks)
        setsize = random.randint(4, num_tasks)
        for task_id in range(1, setsize + 1):
            arrival_time = random.randint(*arrival_time_range)
            burst_time = random.randint(*burst_time_range)
            slack = random.randint(*deadline_slack_range)
            # Deadline after the task would complete + some slack
            deadline = arrival_time + burst_time + slack
            priority = random.randint(*priority_range)

            task = (task_id, arrival_time, burst_time, deadline, priority)
            taskset.append(task)
        all_tasksets.append(taskset)
    return all_tasksets

# Generate random tasksets
random_tasksets = generate_random_taskset()

# Save to a Python file that other simulators can import
filename = 'random_taskset.py'
with open(filename, 'w') as f:
    f.write("from taskset import Task\n")
    f.write("tasks = [\n")
    for taskset in random_tasksets:
        f.write("    [\n")
        for (task_id, arrival_time, burst_time, deadline, priority) in taskset:
            f.write(
                f"        Task({task_id}, {arrival_time}, {burst_time}, {deadline}, {priority}),\n"
            )
        f.write("    ],\n")
    f.write("]\n\n")
    f.write("SIMULATION_TIME = 100\n")

print(f"✅ Saved random tasksets to {filename}!")
