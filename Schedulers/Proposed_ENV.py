
import csv
from aperiodic_task_sets import tasks as tasksML
from taskset import SIMULATION_TIME

NUM_CORES = 8
CONTEXT_SWITCH_TIME = 1
epsilon = 1e-5

def theta_lambda(env_cond):
    return {'clear': 1.25, 'rainy': 0.84, 'foggy': 0.54}.get(env_cond, 4)

def dynamic_priority(task, env_cond):
    base = task.base_priority
    if env_cond == 'rainy':
        return {1: 3, 3: 1}.get(base, base)
    elif env_cond == 'foggy':
        return {1: 2, 2: 3, 3: 1}.get(base, base)
    return base

def get_environment_condition(current_time):
    if current_time < SIMULATION_TIME // 3:
        return 'clear'
    elif current_time < 2 * SIMULATION_TIME // 3:
        return 'rainy'
    return 'foggy'

def update_laxity(task, current_time):
    return task.deadline - current_time - task.remaining_time

def compute_normalized_laxity(laxity, min_lax, max_lax, prange):
    return (laxity - min_lax) * prange / (max_lax - min_lax + epsilon)

# --- Tracking totals

grand_total_deadline_misses = 0
grand_total_preemptions = 0
grand_total_data_transfers = 0
total_busy_time = 0

summary_log = []
missed_priorities_log = []

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

    prange = max((task.priority for task in unarrived_tasks), default=1)
    for task in unarrived_tasks:
        task.remaining_time = task.burst_time
        task.base_priority = task.priority
        task.completion_time = None
        task.relaxation = 0.0

    ready_tasks = []
    cores = [None] * NUM_CORES

    print(f"\nEvaluating Taskset #{taskset_id} with Normalized Laxity + Env Adaptation")
    print(" t  1  |  2")
    print("------|---")

    for current_time in range(SIMULATION_TIME):
        env_cond = get_environment_condition(current_time)

        all_laxities = [update_laxity(t, current_time) for t in unarrived_tasks + ready_tasks]
        min_laxity = min(all_laxities, default=0)
        max_laxity = max(all_laxities, default=1)

        # Arrival
        for task in unarrived_tasks[:]:
            if task.arrival_time == current_time:
                task.priority = dynamic_priority(task, env_cond)
                laxity = update_laxity(task, current_time)
                norm_lax = compute_normalized_laxity(laxity, min_laxity, max_laxity, prange)
                task.relaxation = theta_lambda(env_cond) * norm_lax + task.priority
                ready_tasks.append(task)
                unarrived_tasks.remove(task)
                data_transfer_count += 1

        # Drop overdue tasks
        for task in ready_tasks[:]:
            if update_laxity(task, current_time) < 0:
                deadline_misses += 1
                missed_priorities.append(task.priority)
                ready_tasks.remove(task)
                data_transfer_count += 1

        # Sort ready queue
        for task in ready_tasks:
            laxity = update_laxity(task, current_time)
            norm_lax = compute_normalized_laxity(laxity, min_laxity, max_laxity, prange)
            task.relaxation = theta_lambda(env_cond) * norm_lax + task.priority
        ready_tasks.sort(key=lambda t: t.relaxation)

        # Assign idle cores
        for core in range(NUM_CORES):
            if cores[core] is None and ready_tasks:
                task = ready_tasks.pop(0)
                task.remaining_time += CONTEXT_SWITCH_TIME
                cores[core] = task
                data_transfer_count += 1

        # Preemption
        if ready_tasks:
            incoming = ready_tasks[0]
            incoming_laxity = update_laxity(incoming, current_time)

            worst_core = max(
                [(i, t.remaining_time) for i, t in enumerate(cores) if t],
                default=(None, -1), key=lambda x: x[1]
            )[0]

            if worst_core is not None and incoming_laxity < cores[worst_core].remaining_time:
                task_out = cores[worst_core]
                task_in = ready_tasks.pop(0)
                task_in.remaining_time += CONTEXT_SWITCH_TIME
                cores[worst_core] = task_in
                ready_tasks.append(task_out)
                preemptions += 1
                data_transfer_count += 2

        # Run tasks
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
                        missed_priorities.append(cores[core].priority)
                    cores[core] = None

        core_status = [str(cores[i].id) if cores[i] else "-" for i in range(NUM_CORES)]
        print(f"{current_time}  {core_status[0]}  |  {core_status[1]}")

    for task in ready_tasks:
        if task.remaining_time > 0:
            deadline_misses += 1
            missed_priorities.append(task.priority)

    makespan = max((t.completion_time for t in completed_tasks), default=0)
    taskset_utilization = (busy_time / (SIMULATION_TIME * NUM_CORES)) * 100

    print(f"\n\U0001F4C8 Total Preemptions: {preemptions}")
    print(f"💥 Total Deadline Misses: {deadline_misses}")
    print(f"🔄 Total Data Transfers: {data_transfer_count}")
    print(f"⏱️ Makespan: {makespan} cycles")
    print(f"⚡ CPU Utilization for this taskset: {taskset_utilization:.2f}%")

    grand_total_deadline_misses += deadline_misses
    grand_total_preemptions += preemptions
    grand_total_data_transfers += data_transfer_count
    total_busy_time += busy_time

    summary_log.append([
        taskset_id, taskset_size, preemptions, deadline_misses,
        data_transfer_count, f"{taskset_utilization:.2f}", makespan
    , wcrt])
    missed_priorities_log.append((taskset_id, missed_priorities))

# Final Summary
print("\n\U0001F9FE Priorities of Missed Deadline Tasks (per Taskset):")
for tid, plist in missed_priorities_log:
    print(f"Taskset {tid}: Missed Priorities -> {plist}")

grand_total_utilization = (total_busy_time / (SIMULATION_TIME * NUM_CORES * len(tasksML))) * 100
print("\n\U0001F680 Final Grand Totals:")
print(f"💥 Grand Total Deadline Misses: {grand_total_deadline_misses}")
print(f"🔄 Grand Total Preemptions: {grand_total_preemptions}")
print(f"🔁 Grand Total Data Transfers: {grand_total_data_transfers}")
print(f"⚡ Overall CPU Utilization: {grand_total_utilization:.2f}%")


with open('../normalized_laxity_env_summary.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow([
        'Taskset_ID', 'Taskset Size', 'Preemptions', 'Deadline_Misses',
        'Data_Transfers', 'CPU_Utilization(%)', 'Makespan', 'WCRT', 'Missed_Task_Priorities'
    ])
    for summary, (_, priorities) in zip(summary_log, missed_priorities_log):
        writer.writerow(summary + [wcrt, ','.join(str(p) for p in priorities)])

print("\n✅ Saved normalized laxity + env-aware taskset summaries to 'normalized_laxity_env_summary.csv'")

def dynamic_priority(task, env_cond):
    base = task.base_priority
    if env_cond == 'rainy':
        return {1: 3, 3: 1}.get(base, base)
    elif env_cond == 'foggy':
        return {1: 2, 2: 3, 3: 1}.get(base, base)
    return base

def get_environment_condition(current_time):
    if current_time < SIMULATION_TIME // 3:
        return 'clear'
    elif current_time < 2 * SIMULATION_TIME // 3:
        return 'rainy'
    return 'foggy'

def update_laxity(task, current_time):
    return task.deadline - current_time - task.remaining_time

def compute_normalized_laxity(laxity, min_lax, max_lax, prange):
    return (laxity - min_lax) * prange / (max_lax - min_lax + epsilon)

# --- Tracking totals

grand_total_deadline_misses = 0
grand_total_preemptions = 0
grand_total_data_transfers = 0
total_busy_time = 0

summary_log = []
missed_priorities_log = []

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

    prange = max((task.priority for task in unarrived_tasks), default=1)
    for task in unarrived_tasks:
        task.remaining_time = task.burst_time
        task.base_priority = task.priority
        task.completion_time = None
        task.relaxation = 0.0

    ready_tasks = []
    cores = [None] * NUM_CORES

    print(f"\nEvaluating Taskset #{taskset_id} with Normalized Laxity + Env Adaptation")
    print(" t  1  |  2")
    print("------|---")

    for current_time in range(SIMULATION_TIME):
        env_cond = get_environment_condition(current_time)

        all_laxities = [update_laxity(t, current_time) for t in unarrived_tasks + ready_tasks]
        min_laxity = min(all_laxities, default=0)
        max_laxity = max(all_laxities, default=1)

        # Arrival
        for task in unarrived_tasks[:]:
            if task.arrival_time == current_time:
                task.priority = dynamic_priority(task, env_cond)
                laxity = update_laxity(task, current_time)
                norm_lax = compute_normalized_laxity(laxity, min_laxity, max_laxity, prange)
                task.relaxation = theta_lambda(env_cond) * norm_lax + task.priority
                ready_tasks.append(task)
                unarrived_tasks.remove(task)
                data_transfer_count += 1

        # Drop overdue tasks
        for task in ready_tasks[:]:
            if update_laxity(task, current_time) < 0:
                deadline_misses += 1
                missed_priorities.append(task.priority)
                ready_tasks.remove(task)
                data_transfer_count += 1

        # Sort ready queue
        for task in ready_tasks:
            laxity = update_laxity(task, current_time)
            norm_lax = compute_normalized_laxity(laxity, min_laxity, max_laxity, prange)
            task.relaxation = theta_lambda(env_cond) * norm_lax + task.priority
        ready_tasks.sort(key=lambda t: t.relaxation)

        # Assign idle cores
        for core in range(NUM_CORES):
            if cores[core] is None and ready_tasks:
                task = ready_tasks.pop(0)
                task.remaining_time += CONTEXT_SWITCH_TIME
                cores[core] = task
                data_transfer_count += 1

        # Preemption
        if ready_tasks:
            incoming = ready_tasks[0]
            incoming_laxity = update_laxity(incoming, current_time)

            worst_core = max(
                [(i, t.remaining_time) for i, t in enumerate(cores) if t],
                default=(None, -1), key=lambda x: x[1]
            )[0]

            if worst_core is not None and incoming_laxity < cores[worst_core].remaining_time:
                task_out = cores[worst_core]
                task_in = ready_tasks.pop(0)
                task_in.remaining_time += CONTEXT_SWITCH_TIME
                cores[worst_core] = task_in
                ready_tasks.append(task_out)
                preemptions += 1
                data_transfer_count += 2

        # Run tasks
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
                        missed_priorities.append(cores[core].priority)
                    cores[core] = None

        core_status = [str(cores[i].id) if cores[i] else "-" for i in range(NUM_CORES)]
        print(f"{current_time}  {core_status[0]}  |  {core_status[1]}")

    for task in ready_tasks:
        if task.remaining_time > 0:
            deadline_misses += 1
            missed_priorities.append(task.priority)

    makespan = max((t.completion_time for t in completed_tasks), default=0)
    taskset_utilization = (busy_time / (SIMULATION_TIME * NUM_CORES)) * 100

    print(f"\n\U0001F4C8 Total Preemptions: {preemptions}")
    print(f"💥 Total Deadline Misses: {deadline_misses}")
    print(f"🔄 Total Data Transfers: {data_transfer_count}")
    print(f"⏱️ Makespan: {makespan} cycles")
    print(f"⚡ CPU Utilization for this taskset: {taskset_utilization:.2f}%")

    grand_total_deadline_misses += deadline_misses
    grand_total_preemptions += preemptions
    grand_total_data_transfers += data_transfer_count
    total_busy_time += busy_time

    summary_log.append([
        taskset_id, taskset_size, preemptions, deadline_misses,
        data_transfer_count, f"{taskset_utilization:.2f}", makespan
    , wcrt])
    missed_priorities_log.append((taskset_id, missed_priorities))

# Final Summary
print("\n\U0001F9FE Priorities of Missed Deadline Tasks (per Taskset):")
for tid, plist in missed_priorities_log:
    print(f"Taskset {tid}: Missed Priorities -> {plist}")

grand_total_utilization = (total_busy_time / (SIMULATION_TIME * NUM_CORES * len(tasksML))) * 100
print("\n\U0001F680 Final Grand Totals:")
print(f"💥 Grand Total Deadline Misses: {grand_total_deadline_misses}")
print(f"🔄 Grand Total Preemptions: {grand_total_preemptions}")
print(f"🔁 Grand Total Data Transfers: {grand_total_data_transfers}")
print(f"⚡ Overall CPU Utilization: {grand_total_utilization:.2f}%")


with open('../normalized_laxity_env_summary.csv', 'w', newline='') as f:
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

print("\n✅ Saved normalized laxity + env-aware taskset summaries to 'normalized_laxity_env_summary.csv'")
