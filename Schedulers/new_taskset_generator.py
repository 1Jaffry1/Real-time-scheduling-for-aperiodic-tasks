import random
from pathlib import Path

class Task:
    def __init__(self, id, arrival_time, burst_time, deadline, priority):
        self.relaxation = None
        self.id = id
        self.arrival_time = arrival_time
        self.burst_time = burst_time
        self.deadline = deadline
        self.priority = priority
        self.remaining_time = burst_time
        self.laxity = deadline - burst_time
        self.dropped = False
        self.completion_time = None

def generate_task(task_id):
    arrival_time = random.randint(0, 100)
    burst_time = random.randint(1, 20)
    deadline = random.randint(burst_time + 5, burst_time + 30)
    priority = random.randint(1, 5)
    return f"Task({task_id}, {arrival_time}, {burst_time}, {deadline}, {priority})"

def generate_task_set(size, offset=0):
    return [generate_task(i + offset) for i in range(size)]

def save_to_python_file(filename="aperiodic_task_sets.py"):
    with open(filename, "w") as f:
        f.write("from __main__ import Task\n\n")
        f.write("tasks = [\n")

        for size in range(6, 55):
            for set_num in range(1, 4):  # generate 3 sets per size
                f.write(f"    # Task set with size = {size}, set #{set_num}\n")
                task_list = generate_task_set(size, offset=0)
                f.write("    [\n")
                for task_str in task_list:
                    f.write(f"        {task_str},\n")
                f.write("    ],\n\n")

        f.write("]\n")

    print(f"Saved 3 task sets for each size from 6 to 54 in {filename}")

if __name__ == "__main__":
    save_to_python_file()
