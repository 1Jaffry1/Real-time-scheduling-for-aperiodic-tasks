import joblib
import csv
import warnings
from aperiodic_task_sets import tasks as tasks
from taskset import SIMULATION_TIME

warnings.filterwarnings("ignore")
model = joblib.load('../relaxation_rf_model.pkl')

NUM_CORES = 2
CONTEXT_SWITCH_TIME = 1

correct_predictions = 0
total_predictions = 0
grand_total_deadline_misses = 0
grand_total_preemptions = 0
grand_total_utilization = 0

summary_log = []
missed_priorities_log = []

for taskset_id, taskset_ in enumerate(tasks):
    unarrived_tasks = taskset_.copy()
    current_time = 0
    deadline_misses = 0
    preemptions = 0
    busy_time = 0
    wcrt = 0  # ✅ Worst-case response time (completion - arrival) for this taskset
    completed_tasks = []
    missed_priorities = []

    # Initialize task attributes
    for task in unarrived_tasks:
        task.remaining_time = task.burst_time
        task.laxity = task.deadline - task.burst_time
        task.completion_time = None

    active_tasks = []
    cores = [None] * NUM_CORES

    print(f"\nEvaluating Taskset #{taskset_id}\n t  1  |  2\n------|---")

    for current_time in range(SIMULATION_TIME):
        # Move arrived tasks to active queue
        for task in unarrived_tasks[:]:
            if task.arrival_time == current_time:
                active_tasks.append(task)
                unarrived_tasks.remove(task)

        # Sort active tasks by (deadline, laxity)
        active_tasks.sort(key=lambda t: (t.deadline, t.laxity))

        # Core assignment
        for core_id in range(NUM_CORES):
            if cores[core_id] is None and active_tasks:
                task = active_tasks[0]  # Peek the first task

                features = [[
                    taskset_id,
                    current_time,
                    task.remaining_time,
                    task.deadline,
                    getattr(task, 'priority', 0),
                    task.laxity
                ]]

                predicted_core = model.predict(features)[0]
                assigned_core = None

                if cores[predicted_core] is None:
                    assigned_core = predicted_core
                else:
                    if cores[predicted_core].remaining_time > task.remaining_time:
                        # Preempt the current task
                        active_tasks.append(cores[predicted_core])
                        cores[predicted_core] = None
                        preemptions += 1
                        task.remaining_time += CONTEXT_SWITCH_TIME
                        assigned_core = predicted_core
                    else:
                        if cores[core_id] is None:
                            assigned_core = core_id

                if assigned_core is not None and cores[assigned_core] is None:
                    # Sort again before popping
                    active_tasks.sort(key=lambda t: (t.deadline, t.laxity))
                    task = active_tasks.pop(0)
                    task.remaining_time += CONTEXT_SWITCH_TIME
                    cores[assigned_core] = task

                    if assigned_core == predicted_core:
                        correct_predictions += 1
                    total_predictions += 1

        # Execute tasks
        for core_id in range(NUM_CORES):
            task = cores[core_id]
            if task:
                task.remaining_time -= 1
                busy_time += 1
                if task.remaining_time <= 0:
                    task.completion_time = current_time
                    # ✅ Update WCRT upon completion
                    try:
                        rt = task.completion_time - task.arrival_time
                        if rt > wcrt:
                            wcrt = rt
                    except Exception:
                        pass

                    completed_tasks.append(task)
                    if current_time > task.deadline:
                        deadline_misses += 1
                        missed_priorities.append(getattr(task, 'priority', -1))
                    cores[core_id] = None

        # Print core status
        core_status = [str(cores[i].id) if cores[i] else "-" for i in range(NUM_CORES)]
        print(f"{current_time:02d}  {core_status[0]}  |  {core_status[1]}")

    # Handle unfinished tasks
    for task in active_tasks:
        if task.remaining_time > 0:
            deadline_misses += 1
            missed_priorities.append(getattr(task, 'priority', -1))
            print(f"⚠️ Task {task.id} did not complete and missed its deadline.")

    # Makespan and Utilization
    makespan = max((t.completion_time for t in completed_tasks), default=0)
    utilization = (busy_time / (SIMULATION_TIME * NUM_CORES)) * 100

    summary_log.append([
        taskset_id,
        len(taskset_),
        preemptions,
        deadline_misses,
        0,  # No data transfer tracking
        f"{utilization:.2f}",
        makespan,
        wcrt,  # ✅ include WCRT in the summary row
    ])
    missed_priorities_log.append((taskset_id, missed_priorities))

    grand_total_deadline_misses += deadline_misses
    grand_total_preemptions += preemptions
    grand_total_utilization += busy_time

# Final evaluation
print("\nFinal Evaluation Results")
print(f"Total Predictions: {total_predictions}")
print(f"Correct Predictions: {correct_predictions}")
accuracy = (correct_predictions / total_predictions) * 100 if total_predictions > 0 else 0
print(f"Core Assignment Accuracy: {accuracy:.2f}%")

print("\nFinal Grand Totals:")
print(f"Grand Total Deadline Misses: {grand_total_deadline_misses}")
print(f"Grand Total Preemptions: {grand_total_preemptions}")
grand_total_utilization = (grand_total_utilization / (SIMULATION_TIME * NUM_CORES * len(tasks))) * 100
print(f"Grand Total CPU Utilization: {grand_total_utilization:.2f}%")

# Save summary to CSV
with open('../RF_taskset_summary.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow([
        'Taskset_ID',
        'Taskset Size',
        'Preemptions',
        'Deadline_Misses',
        'Data_Transfers',
        'CPU_Utilization(%)',
        'Makespan',
        'WCRT',  # ✅ header includes WCRT
        'Missed_Task_Priorities'
    ])
    for summary, (_, priorities) in zip(summary_log, missed_priorities_log):
        # ✅ do NOT append wcrt again; it's already in `summary`
        writer.writerow(summary + [','.join(str(p) for p in priorities)])

print("\n✅ Saved RF taskset summaries to 'RF_taskset_summary.csv'")
