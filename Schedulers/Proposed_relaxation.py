import csv
from aperiodic_task_sets import tasks as tasksML
from taskset import Task, current_time, SIMULATION_TIME

# Config
NUM_CORES = 8
CONTEXT_SWITCH_TIME = 1
ALPHA = 0.7
BETA = 0.3

# Totals
grand_total_deadline_misses = 0
grand_total_preemptions = 0
grand_total_data_transfers = 0
total_busy_time = 0

summary_log = []
missed_priorities_log = []

def get_environment_condition(current_time):
    if current_time < SIMULATION_TIME // 3:
        return 'clear'
    elif current_time < 2 * SIMULATION_TIME // 3:
        return 'rainy'
    else:
        return 'foggy'

def get_logged_priority(original_priority):
    condition = get_environment_condition(current_time)

    if condition == 'rainy':
        if original_priority == 3:
            return 1
        elif original_priority == 1:
            return 3

    elif condition == 'foggy':
        if original_priority == 2:
            return 3
        elif original_priority == 1:
            return 2
        elif original_priority == 3:
            return 1

    return original_priority  # No inversion for 'clear' or unmatched cases


for taskset_id, taskset_ in enumerate(tasksML):
    unarrived_tasks = taskset_.copy()
    taskset_size = len(unarrived_tasks)
    current_time = 0
    preemptions = 0
    deadline_misses = 0
    data_transfer_count = 0
    busy_time = 0
    wcrt = 0  # Worst-case response time (completion - arrival) for this taskset
    completed_tasks = []
    missed_priorities = []

    for task in unarrived_tasks:
        if not hasattr(task, 'laxity'):
            task.laxity = task.deadline - task.burst_time

    prange = max((task.priority for task in unarrived_tasks), default=1)
    arrived_tasks = []
    cores = [None] * NUM_CORES

    print(f"\nEvaluating Taskset #{taskset_id} with Relaxation")
    print(" t  1  |  2")
    print("------|---")

    for current_time in range(SIMULATION_TIME):
        # Update global variables for task class
        Task.current_time = current_time
        Task.prange = prange

        # Move arrived tasks
        for task in unarrived_tasks[:]:
            if task.arrival_time == current_time:
                arrived_tasks.append(task)
                unarrived_tasks.remove(task)
                data_transfer_count += 1

        # Remove tasks with negative laxity
        for task in arrived_tasks[:]:
            if task.update_laxity(current_time) < 0:
                deadline_misses += 1
                missed_priorities.append(get_logged_priority(task.priority))
                arrived_tasks.remove(task)
                data_transfer_count += 1

        # Sort tasks by relaxation
        for task in arrived_tasks:
            task.update_relaxation(arrived_tasks, current_time, alpha=ALPHA, beta=BETA)
        arrived_tasks.sort(key=lambda t: t.update_relaxation(arrived_tasks, current_time ,alpha=ALPHA, beta=BETA))


        # Assign to empty cores
        for core in range(NUM_CORES):
            if cores[core] is None and arrived_tasks:
                cores[core] = arrived_tasks.pop(0)
                cores[core].remaining_time += CONTEXT_SWITCH_TIME
                data_transfer_count += 1

        # Preemption logic
        if arrived_tasks:
            task = arrived_tasks[0]
            worst_core = max(
                [(i, t.remaining_time) for i, t in enumerate(cores) if t],
                key=lambda x: x[1],
                default=(None, -1)
            )[0]

            if (worst_core is not None and
                task.update_laxity(current_time) < cores[worst_core].remaining_time and
                task.laxity >= 0):
                task_out = cores[worst_core]
                task_in = arrived_tasks.pop(0)
                cores[worst_core] = task_in
                arrived_tasks.append(task_out)
                preemptions += 1
                data_transfer_count += 2
                task_in.remaining_time += CONTEXT_SWITCH_TIME

        # Process tasks
        for core in range(NUM_CORES):
            if cores[core]:
                cores[core].remaining_time -= 1
                busy_time += 1

                if cores[core].remaining_time <= 0:
                    cores[core].completion_time = current_time
                    # Update WCRT upon completion
                    try:
                        rt = cores[core].completion_time - cores[core].arrival_time
                        if rt > wcrt:
                            wcrt = rt
                    except Exception:
                        pass
                    completed_tasks.append(cores[core])
                    if cores[core].completion_time > cores[core].deadline:
                        deadline_misses += 1
                        missed_priorities.append(get_logged_priority(cores[core].priority))
                    cores[core] = None

        core_status = [str(t.id) if t else "-" for t in cores]
        print(f"{current_time}  {core_status[0]}  |  {core_status[1]}")

    # Handle incomplete tasks
    for task in arrived_tasks:
        if task.remaining_time > 0:
            deadline_misses += 1
            missed_priorities.append(get_logged_priority(task.priority))
            print(f"⚠️ Task {task.id} did not complete and missed its deadline.")

    makespan = max((t.completion_time or 0) for t in completed_tasks) if completed_tasks else 0
    utilization = (busy_time / (SIMULATION_TIME * NUM_CORES)) * 100

    print(f"\n📈 Total Preemptions: {preemptions}")
    print(f"💥 Total Deadline Misses: {deadline_misses}")
    print(f"🔄 Total Data Transfers: {data_transfer_count}")
    print(f"⏱️ Makespan: {makespan}")
    print(f"⚡ CPU Utilization: {utilization:.2f}%")

    grand_total_deadline_misses += deadline_misses
    grand_total_preemptions += preemptions
    grand_total_data_transfers += data_transfer_count
    total_busy_time += busy_time

    summary_log.append([taskset_id, taskset_size, preemptions, deadline_misses,
                        data_transfer_count, f"{utilization:.2f}", makespan, wcrt])
    missed_priorities_log.append((taskset_id, missed_priorities))

# Final reporting
overall_util = (total_busy_time / (SIMULATION_TIME * NUM_CORES * len(tasksML))) * 100

print("\n🧾 Priorities of Missed Deadline Tasks:")
for tid, plist in missed_priorities_log:
    print(f"Taskset {tid}: {plist}")

print("\n🚀 Grand Totals:")
print(f"💥 Deadline Misses: {grand_total_deadline_misses}")
print(f"🔄 Preemptions: {grand_total_preemptions}")
print(f"🔁 Data Transfers: {grand_total_data_transfers}")
print(f"⚡ Utilization: {overall_util:.2f}%")

# Save CSV
with open('../relax_taskset_summary.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow([
        'Taskset_ID',
        'Taskset Size',
        'Preemptions',
        'Deadline_Misses',
        'Data_Transfers',
        'CPU_Utilization(%)',
        'Makespan', 'WCRT', 'Missed_Task_Priorities'
    ])
    for summary, (_, priorities) in zip(summary_log, missed_priorities_log):
        # Don't add wcrt again; it's already inside `summary`
        writer.writerow(summary + [','.join(str(p) for p in priorities)])


print("\n✅ Summary saved to 'relax_taskset_summary.csv'")
